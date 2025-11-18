import os
import json
from typing import List, Dict, Any, Tuple
from tqdm import tqdm

import torch
import numpy as np
from transformers import AutoModelForCausalLM, AutoTokenizer
from sklearn.metrics import brier_score_loss

# ============================================
# Basic configuration
# ============================================
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

MODEL_NAME = "xxx"

INPUT_JSON_PATH = "xxx/PQA_test.json"
OUTPUT_JSONL_PATH = "xxx/eval_PQA.jsonl"

# Generation settings (deterministic for evaluation)
MAX_NEW_TOKENS = 256
TEMPERATURE = 0.0
TOP_P = 1.0
DO_SAMPLE = False
ENABLE_THINKING = False


# ============================================
# Utility functions
# ============================================
def load_dataset(path: str) -> List[Dict[str, Any]]:
    """Load a JSON array file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Input file must be a JSON array.")
    return data


def parse_choices(question: str) -> Dict[str, str]:
    """
    Parse options from question text.
    Supports formats like "A) xxx", "A. xxx", "A: xxx", etc.
    Returns dict: { 'A': '...', 'B': '...' }
    """
    import re
    mapping = {}
    for line in question.splitlines():
        m = re.match(r"\s*([A-Ea-e])\s*[\)\.：:\-、]?\s*(.+?)\s*$", line)
        if m:
            key = m.group(1).upper()
            val = m.group(2).strip()
            if key in "ABCDE":
                mapping[key] = val
    return mapping


def normalize(s: str) -> str:
    """Normalize string for exact match."""
    return " ".join(s.strip().split())


def gold_from_sample(sample: Dict[str, Any]) -> str:
    return sample["conversations"][1]["value"]


def question_from_sample(sample: Dict[str, Any]) -> str:
    return sample["conversations"][0]["value"]


def build_prompt(question: str) -> str:
    """Append mandatory evaluation instruction."""
    suffix = (
        "\n\nPlease must output the full option and your confidence (0–100). "
        "The format should be: {full option} & {confidence}"
    )
    return question + suffix


def run_inference(model, tokenizer, question: str) -> str:
    """Run model inference and return generated text."""
    messages = [{"role": "user", "content": build_prompt(question)}]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=ENABLE_THINKING,
    )
    model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

    with torch.no_grad():
        gen_ids = model.generate(
            **model_inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            do_sample=DO_SAMPLE,
        )

    gen_ids = [out[len(inp):] for inp, out in zip(model_inputs.input_ids, gen_ids)]
    response = tokenizer.batch_decode(gen_ids, skip_special_tokens=True)[0]
    print(f"####{response}")
    return response.strip()


def parse_pred_and_conf(raw_resp: str, choices_map: Dict[str, str]) -> Tuple[str, int, bool]:
    """
    Parse: (full option, confidence 0–100).
    Expected format: "E) xxx & 95".
    If incomplete, attempts to recover option from letter.
    Returns: (normalized_pred, confidence_int, failure_flag)
    Failure=True only when output is empty.
    """
    if raw_resp is None or raw_resp.strip() == "":
        return "", 0, True

    import re
    s = raw_resp.strip()

    # confidence
    conf = 0
    m_conf = re.search(r"&\s*([0-9]+(?:\.[0-9]+)?)", s)
    if m_conf:
        try:
            conf_val = float(m_conf.group(1))
            if np.isnan(conf_val) or np.isinf(conf_val):
                conf = 0
            else:
                conf = int(round(conf_val))
        except Exception:
            conf = 0
        conf = max(0, min(100, conf))

    # option letter
    m_letter_exact = re.match(r"^\s*([A-Ea-e])\b", s)
    letter = None
    if m_letter_exact:
        letter = m_letter_exact.group(1).upper()
    else:
        m_letter_any = re.search(r"\b([A-Ea-e])\b", s)
        if m_letter_any:
            letter = m_letter_any.group(1).upper()

    pred_std = s
    if letter:
        if letter in choices_map:
            pred_std = f"{letter}) {choices_map[letter]}"
        else:
            m_full = re.match(r"^\s*[A-Ea-e]\s*[\)\.：:\-、]?\s*(.+?)\s*(?:&|$)", s)
            if m_full:
                pred_std = f"{letter}) {m_full.group(1).strip()}"
            else:
                pred_std = f"{letter})"

    return pred_std, conf, False


def evaluate_predictions(records_path: str) -> Tuple[List[int], List[int], int, int]:
    """
    Return:
      accs   — list of 0/1 for non-failure samples
      cfds   — list of confidences
      failed — count of failures
      total  — total samples
    """
    accs, cfds = [], []
    failed, total = 0, 0
    with open(records_path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if "metrics" in obj:
                continue
            total += 1
            if obj.get("failure", False):
                failed += 1
                continue
            accs.append(1 if obj.get("correct", False) else 0)
            cfds.append(int(obj.get("confidence", 0)))
    return accs, cfds, failed, total


# ============================================
# Main evaluation pipeline
# ============================================
def main():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
        device_map="auto",
    )

    data = load_dataset(INPUT_JSON_PATH)
    fout = open(OUTPUT_JSONL_PATH, "w", encoding="utf-8")

    for idx, sample in enumerate(tqdm(data, desc="Evaluating")):
        q = question_from_sample(sample)
        gold = gold_from_sample(sample)
        gold_norm = normalize(gold)

        choices_map = parse_choices(q)
        raw_resp = run_inference(model, tokenizer, q)

        if raw_resp.strip() == "":
            rec = {
                "index": idx,
                "question": q,
                "gold": gold,
                "prediction_raw": raw_resp,
                "prediction_std": "",
                "confidence": 0,
                "correct": False,
                "failure": True,
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            continue

        pred_std, conf, _ = parse_pred_and_conf(raw_resp, choices_map)
        pred_norm = normalize(pred_std)
        correct = (pred_norm == gold_norm)

        rec = {
            "index": idx,
            "question": q,
            "gold": gold,
            "prediction_raw": raw_resp,
            "prediction_std": pred_std,
            "confidence": conf,
            "correct": correct,
            "failure": False,
        }
        fout.write(json.dumps(rec, ensure_ascii=False) + "\n")

    fout.close()

    # compute metrics
    accs, cfds, failed, total = evaluate_predictions(OUTPUT_JSONL_PATH)
    accuracy = (sum(accs) / len(accs)) if accs else 0
    brier = brier_score_loss(accs, np.array(cfds) / 100) if accs else None
    failure_rate = (failed / total) if total else 0

    metrics = {
        "total": total,
        "evaluated": len(accs),
        "failed": failed,
        "failure_rate": failure_rate,
        "acc": accuracy,
        "brier_score": brier,
    }

    with open(OUTPUT_JSONL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"metrics": metrics}, ensure_ascii=False) + "\n")

    # print summary
    print("\n=== Final Evaluation Metrics ===")
    print(f"Total                 : {metrics['total']}")
    print(f"Evaluated (non-empty) : {metrics['evaluated']}")
    print(f"Failure Count         : {metrics['failed']}")
    print(f"Failure Rate          : {metrics['failure_rate']:.4f}")
    print(f"Accuracy              : {metrics['acc']:.4f}")
    print(f"Brier Score           : {metrics['brier_score'] if metrics['brier_score'] is not None else 'N/A'}")


if __name__ == "__main__":
    main()
