import os
import re
import json
import math
import random
from typing import Any, Dict, List, Optional, Tuple
import traceback
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from tqdm import tqdm
from sacrebleu.metrics import BLEU
from nltk.translate.meteor_score import meteor_score
from rouge_score import rouge_scorer
from bert_score import score as bert_score
from keybert import KeyBERT
from sentence_transformers import SentenceTransformer

import nltk
NLTK_DATA_DIR = os.getenv("NLTK_DATA_DIR", "").strip()
if NLTK_DATA_DIR:
    nltk.data.path.append(NLTK_DATA_DIR)

# KeyBERT local embedding model
KW_MODEL = KeyBERT(model=SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
))

BERTSCORE_MODEL = os.getenv("BERTSCORE_MODEL", "roberta-large")
BERTSCORE_DEVICE = os.getenv("BERTSCORE_DEVICE", "cuda")
# ======================================================
# User configuration
# ======================================================
MODEL_PATH   = os.getenv("MODEL_PATH", "xxx")
INPUT_JSONL  = os.getenv("INPUT_JSONL", "xxx/SciRecipe-Eval.jsonl")
OUTPUT_JSONL = os.getenv("OUTPUT_JSONL", "xxx/output.jsonl")

DTYPE = "bfloat16"      
ATTN_IMPL = "flash_attention_2"
DEVICE_MAP = "auto"

MAX_NEW_TOKENS = 1024
TEMPERATURE    = 0.6
TOP_P          = 0.95
DO_SAMPLE      = False
BATCH_SIZE     = 32

PRINT_EACH = True
SEED = 42  # used only for deterministic action set shuffling
EVAL_SAMPLE_N = 0

# ======================================================
# Parsing helpers
# ======================================================
TAG_PATTERN = re.compile(
    r"<think>(?P<think>.*?)</think>\s*"
    r"<key>(?P<key>.*?)</key>\s*"
    r"<orc>(?P<orc>.*?)</orc>\s*"
    r"<note>(?P<note>.*?)</note>",
    flags=re.DOTALL | re.IGNORECASE
)

STEP_JSON_PAT = re.compile(
    r"^Step\s+\d+\s*:\s*(\{.*\})\s*$",
    flags=re.IGNORECASE
)


def extract_blocks(text: str) -> Optional[Dict[str, str]]:
    """Extract <think>, <key>, <orc>, <note> blocks from model output."""
    if not isinstance(text, str):
        return None
    m = TAG_PATTERN.search(text)
    if not m:
        return None
    return {
        "think": m.group("think"),
        "key":   m.group("key"),
        "orc":   m.group("orc"),
        "note":  m.group("note"),
    }


def step_lines(block: str) -> List[str]:
    return [ln.rstrip() for ln in block.strip().splitlines() if ln.strip()]


def parse_key_line_json(line: str) -> Optional[Dict]:
    """Parse a single 'Step X: {...}' line into JSON."""
    m = STEP_JSON_PAT.match(line)
    if not m:
        return None
    try:
        obj = json.loads(m.group(1))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def _lower_str(s: str) -> str:
    return s.strip().lower()


def _lower_list_str(lst: List[str]) -> List[str]:
    return [_lower_str(x) for x in lst if isinstance(x, str) and x.strip()]


def _parse_key_steps_lower(block: str) -> List[Dict[str, List[str] or str]]:
    """Parse <key> block into normalized action/object/parameter triplets."""
    steps = []
    for ln in step_lines(block):
        obj = parse_key_line_json(ln)
        if not obj:
            continue
        steps.append({
            "action":    _lower_str(obj.get("action", "")),
            "objects":   _lower_list_str(obj.get("objects", [])),
            "parameters": _lower_list_str(obj.get("parameters", [])),
        })
    return steps


def _actions_from_steps(steps: List[Dict]) -> List[str]:
    return [s["action"] for s in steps]


# ======================================================
# Structured metrics
# ======================================================
def _lcs_len(a: List[str], b: List[str]) -> int:
    """Compute LCS length."""
    n, m = len(a), len(b)
    dp = [[0]*(m+1) for _ in range(n+1)]
    for i in range(1, n+1):
        ai = a[i-1]
        for j in range(1, m+1):
            if ai == b[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    return dp[n][m]


def compute_order_score(pred_actions: List[str], gt_actions: List[str],
                        mode: str = "strict_subseq") -> float:
    """Order score with either strict equality or LCS-F1."""
    if mode == "strict_subseq":
        return 1.0 if pred_actions == gt_actions else 0.0

    if not pred_actions and not gt_actions:
        return 1.0

    l = _lcs_len(pred_actions, gt_actions)
    denom = max(1, len(pred_actions) + len(gt_actions))
    return (2.0 * l) / denom


def pair_by_action_sequence(pred_actions: List[str], gt_actions: List[str]) -> List[Tuple[int, int]]:
    """Greedy alignment of equal actions in sequence."""
    pairs, j = [], 0
    for i, act in enumerate(pred_actions):
        while j < len(gt_actions) and gt_actions[j] != act:
            j += 1
        if j < len(gt_actions) and gt_actions[j] == act:
            pairs.append((i, j))
            j += 1
    return pairs


from itertools import combinations

def _kendall_tau_from_pairs(pairs: List[Tuple[int, int]]) -> float:
    """Compute Kendall tau on the aligned pairs."""
    n = len(pairs)
    if n <= 1:
        return 0.0
    gt_seq = [gi for _, gi in pairs]
    concord, discord = 0, 0
    for i, j in combinations(range(n), 2):
        if gt_seq[i] < gt_seq[j]:
            concord += 1
        elif gt_seq[i] > gt_seq[j]:
            discord += 1
    total = concord + discord
    return (concord - discord) / total if total else 0.0


def _set_iou(a, b) -> float:
    A, B = set(a), set(b)
    if not A and not B:
        return 1.0
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def _keyword_set(text: str, top_k: int = 64) -> set:
    """Tokenize to form a simple keyword set."""
    if not text:
        return set()
    text = text.lower()
    tokens = re.split(r"[^a-z0-9%µμ\-\._]+", text)
    return set(t for t in tokens if t)


def compute_keyword_iou(ref_text: str, gen_text: str, top_k: int = 64) -> float:
    """Keyword IoU with optional fallback extraction."""
    ref_kw, gen_kw = _keyword_set(ref_text, top_k), _keyword_set(gen_text, top_k)
    if not ref_kw and not gen_kw:
        return 1.0
    if not ref_kw or not gen_kw:
        return 0.0
    return len(ref_kw & gen_kw) / len(ref_kw | gen_kw)


def _compute_step_scores(pred_step, gt_step, pred_idx, gt_idx, gt_len,
                         lambda_decay=1.5):
    """Compute content alignment for a step pair."""
    obj_iou = _set_iou(pred_step["objects"], gt_step["objects"])
    if obj_iou == 0.0:
        obj_iou = compute_keyword_iou(" ".join(gt_step["objects"]),
                                      " ".join(pred_step["objects"]))

    para_score = 0.0
    if obj_iou >= 0.5:
        pred_params, gt_params = pred_step["parameters"], gt_step["parameters"]
        if not pred_params and not gt_params:
            para_score = 1.0
        elif pred_params and gt_params:
            para_score = compute_keyword_iou(" ".join(gt_params),
                                             " ".join(pred_params))

    x = abs(pred_idx - gt_idx)
    D = max(1, gt_len)
    m_x = 0.0 if x >= D else max(0.0, 1.0 - (x/float(D))**lambda_decay)
    step_score = m_x * (obj_iou + 0.5 * para_score)

    return float(step_score), float(obj_iou), float(para_score), float(m_x)


def compute_structured_metrics(pred_key_block: str, gt_key_block: str) -> Dict[str, float]:
    """Compute all structured metrics based on <key> block."""
    try:
        step_match = 1.0 if len(step_lines(pred_key_block)) == len(step_lines(gt_key_block)) else 0.0

        pred_steps = _parse_key_steps_lower(pred_key_block)
        gt_steps   = _parse_key_steps_lower(gt_key_block)

        pred_actions = _actions_from_steps(pred_steps)
        gt_actions   = _actions_from_steps(gt_steps)

        order_strict = compute_order_score(pred_actions, gt_actions, mode="strict_subseq")
        order_lcs    = compute_order_score(pred_actions, gt_actions, mode="lcs")

        pairs = pair_by_action_sequence(pred_actions, gt_actions)
        if not pairs:
            return {
                "step_match": step_match,
                "order_strict": order_strict,
                "order_lcs": order_lcs,
                "order_tau": 0.0,
                "content_score": 0.0,
                "avg_obj": 0.0,
                "avg_para": 0.0,
                "avg_mx": 0.0
            }

        scores, obj_vals, para_vals, mx_vals = [], [], [], []
        for (pi, gi) in pairs:
            s, o, p, mx = _compute_step_scores(pred_steps[pi], gt_steps[gi], pi, gi, len(gt_steps))
            scores.append(s)
            obj_vals.append(o)
            para_vals.append(p)
            mx_vals.append(mx)

        tau = _kendall_tau_from_pairs(pairs)
        denom = max(1, len(pairs))

        return {
            "step_match": step_match,
            "order_strict": order_strict,
            "order_lcs": order_lcs,
            "order_tau": tau,
            "content_score": sum(scores)/denom,
            "avg_obj": sum(obj_vals)/denom,
            "avg_para": sum(para_vals)/denom,
            "avg_mx": sum(mx_vals)/denom
        }

    except Exception:
        return {
            "step_match":0.0,"order_strict":0.0,"order_lcs":0.0,"order_tau":0.0,
            "content_score":0.0,"avg_obj":0.0,"avg_para":0.0,"avg_mx":0.0
        }


# ======================================================
# Text metrics (for <orc>)
# ======================================================
bleu_metric = BLEU(effective_order=True)
rouge = rouge_scorer.RougeScorer(
    ['rouge1','rouge2','rougeL'],
    use_stemmer=True
)


def compute_text_metrics(ref: str, pred: str, lang: str = "en") -> Dict[str, float]:
    """Compute BLEU/METEOR/ROUGE/Keyword/BERTScore metrics."""
    metrics = {}
    ref, pred = (ref or "").strip(), (pred or "").strip()

    if not ref or not pred:
        return {m: 0.0 for m in [
            "bleu1","bleu2","bleu3","bleu4","bleu_avg",
            "meteor","rouge1","rouge2","rougeL",
            "kw_precision","kw_recall","kw_f1",
            "bertscore_p","bertscore_r","bertscore_f1"
        ]}

    # BLEU
    bleu = bleu_metric.sentence_score(pred, [ref])
    metrics["bleu1"] = bleu.precisions[0] / 100.0
    metrics["bleu2"] = bleu.precisions[1] / 100.0
    metrics["bleu3"] = bleu.precisions[2] / 100.0
    metrics["bleu4"] = bleu.precisions[3] / 100.0
    metrics["bleu_avg"] = sum(metrics[f"bleu{i}"] for i in range(1,5)) / 4.0

    # METEOR
    try:
        metrics["meteor"] = meteor_score([ref.split()], pred.split())
    except Exception:
        metrics["meteor"] = 0.0

    # ROUGE
    r = rouge.score(ref, pred)
    metrics["rouge1"] = r["rouge1"].fmeasure
    metrics["rouge2"] = r["rouge2"].fmeasure
    metrics["rougeL"] = r["rougeL"].fmeasure

    # Keyword F1
    try:
        ref_kw = set([kw for kw,_ in KW_MODEL.extract_keywords(ref, top_n=64)])
        gen_kw = set([kw for kw,_ in KW_MODEL.extract_keywords(pred, top_n=64)])
        inter  = ref_kw & gen_kw
        prec   = len(inter) / len(gen_kw) if gen_kw else 0.0
        rec    = len(inter) / len(ref_kw) if ref_kw else 0.0
        f1     = 2 * prec * rec / (prec + rec + 1e-8) if (prec + rec) else 0.0
        metrics["kw_precision"] = prec
        metrics["kw_recall"]    = rec
        metrics["kw_f1"]        = f1
    except Exception:
        metrics["kw_precision"] = metrics["kw_recall"] = metrics["kw_f1"] = 0.0

    # BERTScore
    try:
        strip_header = lambda s: re.sub(r"(?im)^step\s*\d+\s*:\s*", "", s)
        ref_clean  = strip_header(ref)
        pred_clean = strip_header(pred)

        P, R, F1 = bert_score(
            [pred_clean], [ref_clean],
            lang="en",
            rescale_with_baseline=False,
            device=BERTSCORE_DEVICE,
            model_type=BERTSCORE_MODEL,
            num_layers=24
        )


        metrics["bertscore_p"]  = float(P.mean())
        metrics["bertscore_r"]  = float(R.mean())
        metrics["bertscore_f1"] = float(F1.mean())

    except Exception:
        traceback.print_exc()
        metrics["bertscore_p"] = metrics["bertscore_r"] = metrics["bertscore_f1"] = 0.0

    return metrics


# ======================================================
# Prompt builder
# ======================================================
SYSTEM_PROMPT = (
    "You are a bio-expert scientific assistant. Produce a single output containing "
    "four blocks in order: <think>, <key>, <orc>, <note>. "
    "<think> contains reasoning, <key> contains step-wise JSON actions with atomic "
    "action/objects/parameters, <orc> is a readable summary, and <note> contains "
    "safety comments. Output must begin with <think>."
)


def build_user_prompt(question: str, actions: List[str], do_shuffle: bool = True) -> str:
    """Build user prompt with an optional deterministic action-set shuffle."""
    actions = [a for a in actions if isinstance(a, str) and a.strip()]
    if do_shuffle:
        shuffled = actions[:]
        rnd = random.Random(SEED)
        rnd.shuffle(shuffled)
        lowered = [s.strip().lower() for s in shuffled]
    else:
        lowered = [s.strip().lower() for s in actions]

    quoted = '", "'.join(lowered)
    note = f'Please note that you can only use the following actions: "{quoted}".'
    return (
        question.strip()
        + " Please provide the experimental protocol to solve this problem. "
        + note
    )


# ======================================================
# Inference utilities
# ======================================================
def load_model_and_tokenizer():
    torch_dtype = torch.bfloat16 if DTYPE == "bfloat16" else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch_dtype,
        attn_implementation=ATTN_IMPL,
        device_map=DEVICE_MAP
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)

    # Required for batch padding
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model.eval()
    return model, tokenizer


def generate_response(model, tokenizer, system_prompt: str, user_prompt: str) -> str:
    """Single-sample generation (not used in batch path)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",  "content": user_prompt},
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True
    )
    inputs = tokenizer([text], return_tensors="pt").to(model.device)

    outputs = model.generate(
        **inputs,
        max_new_tokens=MAX_NEW_TOKENS,
        temperature=TEMPERATURE,
        top_p=TOP_P,
        do_sample=DO_SAMPLE
    )

    gen_ids = outputs[0][inputs.input_ids.shape[1]:]
    return tokenizer.decode(gen_ids, skip_special_tokens=True)


def batch_generate_responses(model, tokenizer, sys_prompt: str,
                             user_prompts: List[str]) -> List[str]:
    """Batched inference for efficiency."""
    texts = []
    for up in user_prompts:
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user",   "content": up},
        ]
        texts.append(tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=True
        ))

    enc = tokenizer(
        texts,
        return_tensors="pt",
        padding=True,
        truncation=False
    ).to(model.device)

    with torch.inference_mode():
        out = model.generate(
            **enc,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            do_sample=DO_SAMPLE,
            pad_token_id=tokenizer.pad_token_id,
            return_dict_in_generate=True
        )

    seqs = out.sequences
    attn = enc.attention_mask
    prompt_lens = attn.sum(dim=1).tolist()

    res = []
    for i, pl in enumerate(prompt_lens):
        gen_ids = seqs[i, pl:]
        res.append(tokenizer.decode(gen_ids, skip_special_tokens=True))
    return res


# ======================================================
# Aggregation helpers
# ======================================================
ALL_METRICS = [
    "step_match","order_strict","order_lcs","order_tau",
    "content_score","avg_obj","avg_para","avg_mx",
    "bleu1","bleu2","bleu3","bleu4","bleu_avg","meteor",
    "rouge1","rouge2","rougeL",
    "kw_precision","kw_recall","kw_f1",
    "bertscore_p","bertscore_r","bertscore_f1"
]


def _empty_agg() -> Dict[str, float]:
    d = {m: 0.0 for m in ALL_METRICS}
    d["count"] = 0
    return d


def _add_to_agg(agg: Dict[str, Dict[str, float]], key: str, row: Dict[str, float]):
    if key not in agg:
        agg[key] = _empty_agg()
    for m in ALL_METRICS:
        agg[key][m] += row.get(m, 0.0)
    agg[key]["count"] += 1


def _finalize_agg(entry: Dict[str, float]) -> Dict[str, float]:
    c = max(1, int(entry.get("count", 0)))
    out = {m: entry[m] / c for m in ALL_METRICS}
    out["num_samples"] = c
    return out


# ======================================================
# Main
# ======================================================
def main():
    samples = []
    with open(INPUT_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))

    if isinstance(EVAL_SAMPLE_N, int) and EVAL_SAMPLE_N > 0 and EVAL_SAMPLE_N < len(samples):
        rnd = random.Random(SEED)
        idxs = rnd.sample(range(len(samples)), EVAL_SAMPLE_N)
        idxs.sort()
        samples = [samples[i] for i in idxs]

    model, tokenizer = load_model_and_tokenizer()
    fout = open(OUTPUT_JSONL, "w", encoding="utf-8")

    overall = _empty_agg()
    by_level = {}
    by_type  = {}

    for start in tqdm(range(0, len(samples), BATCH_SIZE), desc="Infer+Eval (batched)"):
        chunk = samples[start:start+BATCH_SIZE]

        user_prompts = []
        metas = []

        for i, item in enumerate(chunk):
            sid    = item.get("id", f"sample_{start+i}")
            stype  = str(item.get("type","unknown"))
            slevel = str(item.get("level","unknown"))

            question     = str(item.get("question","")).strip()
            gt_key_block = str(item.get("key","")).strip()
            gt_orc       = str(item.get("orc","")).strip()

            actions_new  = item.get("action_new", None)
            actions      = actions_new if isinstance(actions_new, list) else item.get("action", [])

            if not question or not isinstance(actions, list):
                metas.append(None)
                continue

            shuffle_flag = not isinstance(actions_new, list)
            user_prompt = build_user_prompt(question, actions, do_shuffle=shuffle_flag)

            metas.append({
                "id": sid,
                "type": stype,
                "level": slevel,
                "question": question,
                "gt_key_block": gt_key_block,
                "gt_orc": gt_orc,
                "actions_prompt_tail": user_prompt.split(
                    "Please note that you can only use the following actions:"
                )[-1].strip()
            })

            user_prompts.append(user_prompt)

        if not user_prompts:
            continue

        try:
            outputs = batch_generate_responses(model, tokenizer, SYSTEM_PROMPT, user_prompts)
        except Exception as e:
            outputs = [f"[ERROR during generation] {e}"] * len(user_prompts)

        k = 0
        for i in range(len(chunk)):
            meta = metas[i]
            if meta is None:
                continue

            model_output = outputs[k]
            k += 1

            blocks = extract_blocks(model_output)
            pred_key_block = blocks["key"] if (blocks and isinstance(blocks.get("key"), str)) else model_output
            pred_orc       = blocks["orc"] if blocks else ""

            struct_metrics = compute_structured_metrics(pred_key_block, meta["gt_key_block"])
            text_metrics   = compute_text_metrics(meta["gt_orc"], pred_orc)
            row_metrics    = {**struct_metrics, **text_metrics}

            _add_to_agg({"overall": overall}, "overall", row_metrics)
            _add_to_agg(by_level, meta["level"], row_metrics)
            _add_to_agg(by_type,  meta["type"],  row_metrics)

            if PRINT_EACH:
                sm, tm = struct_metrics, text_metrics
                print(
                    f"[{start+i+1}] id={meta['id']} level={meta['level']} type={meta['type']} | "
                    f"step={sm['step_match']:.2f} strict={sm['order_strict']:.2f} "
                    f"lcs={sm['order_lcs']:.2f} content={sm['content_score']:.2f} "
                    f"(obj={sm['avg_obj']:.2f}, para={sm['avg_para']:.2f}, mx={sm['avg_mx']:.2f}) | "
                    f"BLEU4={tm['bleu4']:.3f} METEOR={tm['meteor']:.3f} "
                    f"R1={tm['rouge1']:.3f} R2={tm['rouge2']:.3f} RL={tm['rougeL']:.3f} "
                    f"KW_F1={tm['kw_f1']:.3f} BERT_F1={tm['bertscore_f1']:.3f}"
                )

            out_line = {
                "id": meta["id"],
                "type": meta["type"],
                "level": meta["level"],
                "question": meta["question"],
                "actions_prompt_tail": meta["actions_prompt_tail"],
                "model_output": model_output,
                "pred_key_block": pred_key_block,
                "gt_key_block": meta["gt_key_block"],
                "pred_orc": pred_orc,
                "gt_orc": meta["gt_orc"],
                "metrics": row_metrics
            }
            fout.write(json.dumps(out_line, ensure_ascii=False) + "\n")

    # Final reports
    overall_report = _finalize_agg(overall) if overall["count"] > 0 else {}
    level_report   = {k: _finalize_agg(v) for k, v in by_level.items()}
    type_report    = {k: _finalize_agg(v) for k, v in by_type.items()}

    report = {
        "overall": overall_report,
        "by_level": level_report,
        "by_type":  type_report
    }

    # Printing summary
    print("\n== Final Averages (Overall) ==")
    if overall_report:
        for k, v in overall_report.items():
            if k == "num_samples":
                print(f"{k}: {v}")
            else:
                print(f"{k}: {v:.4f}")

    print("\n-- By Level --")
    for k, v in level_report.items():
        stats = ", ".join([f"{m}={v[m]:.4f}" if m!="num_samples"
                           else f"{m}={v[m]}" for m in v])
        print(f"[{k}] {stats}")

    print("\n-- By Type --")
    for k, v in type_report.items():
        stats = ", ".join([f"{m}={v[m]:.4f}" if m!="num_samples"
                           else f"{m}={v[m]}" for m in v])
        print(f"[{k}] {stats}")

    fout.write(json.dumps({"report": report}, ensure_ascii=False) + "\n")
    fout.close()


if __name__ == "__main__":
    main()
