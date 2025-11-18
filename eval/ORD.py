import os
import re
import ast
import json
from typing import List, Dict, Any, Tuple
from itertools import combinations
from tqdm import tqdm

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ============================================
# Basic configuration
# ============================================
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

MODEL_NAME = "xxx"

INPUT_JSON_PATH = "xxx/ORD_test.json"
OUTPUT_JSON_PATH = "xxx/eval_ORD.jsonl"

# Generation parameters
MAX_NEW_TOKENS = 128
TEMPERATURE = 0.0
TOP_P = 1.0
DO_SAMPLE = False
ENABLE_THINKING = False

# Enforce 1-based strictness
STRICT_ONE_BASED = True


# ============================================
# Dataset Parsing
# ============================================
def load_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Input must be a JSON array.")
    return data


def parse_steps_from_question(question: str) -> List[str]:
    """Extract lines matching 'Step i: ...' in order of appearance."""
    steps = []
    for line in question.splitlines():
        m = re.match(r"\s*Step\s*\d+\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if m:
            steps.append(m.group(1).strip())
    if not steps:
        raise ValueError("No 'Step i: ...' lines found in question.")
    return steps


def gold_indices_from_sample(sample: Dict[str, Any]) -> List[int]:
    """Parse gold indices (1-based) from sample's conversation."""
    gold_str = sample["conversations"][1]["value"]
    idx_list = ast.literal_eval(gold_str)
    if not isinstance(idx_list, list):
        raise ValueError("Gold annotation must be a list.")
    return [int(i) for i in idx_list]  # keep 1-based


def reorder_by_indices_1based(items: List[str], one_based_indices: List[int]) -> List[str]:
    """Reorder items according to 1-based indices."""
    return [items[i - 1] for i in one_based_indices]


# ============================================
# Prompt construction & inference
# ============================================
def build_prompt(question: str, n_steps: int) -> str:
    """Require model to output only a 1-based Python list."""
    suffix = (
        f"\n\nIMPORTANT: Return ONLY a Python list of integers 1..{n_steps} that sorts the steps into the correct order. Output nothing else."
    )
    return question + suffix


def run_inference(model, tokenizer, prompt: str) -> str:
    messages = [{"role": "user", "content": prompt}]
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


# ============================================
# Parsing model outputs (strict 1-based)
# ============================================
def _parse_index_list_1based(generated_str: str, n_steps: int) -> List[int]:
    """
    Extract a strict 1-based integer list:
      - Try literal_eval on entire string
      - Fall back to regex extracting final '[...]' segment
      - Validate set == {1..n_steps}, no duplicates, no missing values
    """
    s = (generated_str or "").strip()

    # Clean leftover reasoning chunks
    if "</think>" in s:
        s = s.split("</think>")[-1]
    if "[/INST]" in s:
        s = s.split("[/INST]")[-1]

    def _try_literal(txt):
        try:
            lst = ast.literal_eval(txt)
            return lst if isinstance(lst, list) else None
        except Exception:
            return None

    idx_list = _try_literal(s)

    if idx_list is None:
        matches = re.findall(r"\[(?:\s*\d+\s*(?:,\s*\d+\s*)*)\]", s)
        if matches:
            idx_list = _try_literal(matches[-1])

    if idx_list is None:
        raise ValueError("No parsable list found.")

    try:
        idx_list = [int(x) for x in idx_list]
    except Exception:
        raise ValueError("List contains non-integer values.")

    # Strict 1-based validation
    set_idx = set(idx_list)
    expected = set(range(1, n_steps + 1))

    if set_idx != expected:
        if STRICT_ONE_BASED:
            raise ValueError(f"Index set mismatch: got {set_idx}, expected {expected}")

    if len(set(idx_list)) != n_steps or len(idx_list) != n_steps:
        raise ValueError("Duplicate or missing indices.")

    return idx_list


def extract_predicted_order_1based(generated_str: str, wrong_steps: List[str], n_steps: int) -> Tuple[List[int], List[str]]:
    """Return 1-based indices and the reordered step texts."""
    one_based = _parse_index_list_1based(generated_str, n_steps)
    predicted_steps = [wrong_steps[i - 1] for i in one_based]
    return one_based, predicted_steps


# ============================================
# Metrics (1-based)
# ============================================
def calculate_exact_match_indices(gts_1b: List[List[int]], preds_1b: List[List[int]]) -> float:
    correct = sum([gt == pr for gt, pr in zip(gts_1b, preds_1b)])
    return correct / len(gts_1b) if gts_1b else 0.0


def calculate_kendall_tau_indices(gts_1b: List[List[int]], preds_1b: List[List[int]]) -> float:
    total_pairs = 0
    concordant_pairs = 0

    for gt, pr in zip(gts_1b, preds_1b):
        gt_rank = {v: i for i, v in enumerate(gt)}
        pr_rank = {v: i for i, v in enumerate(pr)}

        for a, b in combinations(gt, 2):
            gt_order = gt_rank[a] - gt_rank[b]
            pr_order = pr_rank[a] - pr_rank[b]
            if gt_order * pr_order > 0:
                concordant_pairs += 1
            total_pairs += 1

    if total_pairs == 0:
        return 0.0
    return (2 * concordant_pairs - total_pairs) / total_pairs


def evaluate_sorting_predictions_1based(output_file_path: str):
    """Load results and compute preds/gts (1-based), failed count, total count."""
    with open(output_file_path, 'r', encoding="utf-8") as f:
        data = json.load(f)

    preds_1b, gts_1b = [], []
    failed, total = 0, 0

    for item in tqdm(data, desc="Evaluating"):
        if isinstance(item, dict) and "metrics" in item:
            continue
        total += 1

        try:
            wrong_steps = item["wrong_steps"]
            correct_steps = item["correct_steps"]
            n = len(correct_steps)

            # Recover gold (1-based)
            if "gold_indices_1based" in item:
                gold_1b = [int(x) for x in item["gold_indices_1based"]]
            elif "gold_indices" in item:
                gold_1b = [int(x) + 1 for x in item["gold_indices"]]
            else:
                pos = {s: i for i, s in enumerate(wrong_steps)}
                gold_1b = [pos[s] + 1 for s in correct_steps]

            # Parse predicted order (strict)
            pred_1b, _ = extract_predicted_order_1based(item["generated_response"], wrong_steps, n)

            preds_1b.append(pred_1b)
            gts_1b.append(gold_1b)

        except Exception:
            failed += 1

    return preds_1b, gts_1b, failed, total


# ============================================
# Main: inference -> write file -> evaluate
# ============================================
def main():
    dataset = load_dataset(INPUT_JSON_PATH)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
        device_map="auto",
    )

    outputs = []

    for idx, sample in enumerate(tqdm(dataset, desc="Generating")):
        question = sample["conversations"][0]["value"]
        wrong_steps = parse_steps_from_question(question)
        gold_1based = gold_indices_from_sample(sample)
        correct_steps = reorder_by_indices_1based(wrong_steps, gold_1based)

        prompt = build_prompt(question, n_steps=len(wrong_steps))
        gen_text = run_inference(model, tokenizer, prompt)

        try:
            pred_1b, _ = extract_predicted_order_1based(gen_text, wrong_steps, len(wrong_steps))
        except Exception:
            pred_1b = None

        outputs.append({
            "index": idx,
            "question": question,
            "wrong_steps": wrong_steps,
            "correct_steps": correct_steps,
            "gold_indices_1based": gold_1based,
            "generated_response": gen_text,
            "pred_indices_1based": pred_1b
        })

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=2)

    preds_1b, gts_1b, failed, total = evaluate_sorting_predictions_1based(OUTPUT_JSON_PATH)
    exact_match = calculate_exact_match_indices(gts_1b, preds_1b)
    kendall_tau = calculate_kendall_tau_indices(gts_1b, preds_1b)

    print("\n=== Final Sorting Evaluation (1-based) ===")
    print(f"Exact Match   : {exact_match:.4f}")
    print(f"Kendall's Tau : {kendall_tau:.4f}")
    print(f"Failed Parses : {failed}/{total} ({(failed/total*100 if total else 0):.2f}%)")
    print(f"Total Samples : {total}")
    print("---------------------------")

    summary = {
        "metrics": {
            "index_base": "1-based",
            "total": total,
            "evaluated": len(preds_1b),
            "failed": failed,
            "failure_rate": (failed / total) if total else 0.0,
            "exact_match": exact_match,
            "kendall_tau": kendall_tau,
        }
    }

    try:
        with open(OUTPUT_JSON_PATH, "r", encoding="utf-8") as f:
            arr = json.load(f)
        arr.append(summary)
        with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
    except Exception:
        with open(OUTPUT_JSON_PATH + ".metrics.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
