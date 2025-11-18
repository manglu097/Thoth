import os
import re
import json
from typing import List, Dict, Any, Tuple
from tqdm import tqdm

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ============================================
# Basic configuration
# ============================================
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

MODEL_NAME = "xxx"

INPUT_JSON_PATH = "xxx/ERR_test.json"
OUTPUT_JSONL_PATH = "xxx/eval_ERR.jsonl"

# Generation parameters
MAX_NEW_TOKENS = 64
TEMPERATURE = 0.0
TOP_P = 1.0
DO_SAMPLE = False
ENABLE_THINKING = False


# ============================================
# Dataset & Prompt Handling
# ============================================
def load_dataset(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Input must be a JSON array.")
    return data


def get_question(sample: Dict[str, Any]) -> str:
    return sample["conversations"][0]["value"]


def get_gold_str(sample: Dict[str, Any]) -> str:
    return sample["conversations"][1]["value"].strip()


def gold_to_bool(gold_str: str) -> bool:
    if gold_str.lower() == "true":
        return True
    if gold_str.lower() == "false":
        return False
    raise ValueError(f"Invalid boolean gold: {gold_str}")


def build_prompt(question: str) -> str:
    """Return the original question as the prompt."""
    return question


# ============================================
# Inference
# ============================================
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
# Prediction Parsing
# ============================================
def extract_binary_answer(generated_str):
    """Extract boolean answer from model output."""

    # Remove template leftovers
    if "</think>" in generated_str:
        generated_str = generated_str.split("</think>")[-1]
    if "[/INST]" in generated_str:
        generated_str = generated_str.split("[/INST]")[-1]

    # Check for [ANSWER_START]...[ANSWER_END]
    pattern = r"\[ANSWER_START\](.*?)\[ANSWER_END\]"
    match = re.search(pattern, generated_str, re.DOTALL)

    if match:
        answer = match.group(1).strip()
    else:
        last_line = generated_str.strip().split("\n")[-1]
        answer = last_line.strip()

    # Interpret boolean
    if "true" in answer.lower():
        return True
    elif "false" in answer.lower():
        return False
    else:
        raise ValueError("Unrecognized boolean answer.")


# ============================================
# Evaluation
# ============================================
def evaluate_correction_task(output_file_path):
    preds, gts = [], []
    failed, total = 0, 0

    with open(output_file_path, 'r', encoding="utf-8") as f:
        data = json.load(f)

    for item in tqdm(data, desc="Evaluating"):
        if isinstance(item, dict) and "metrics" in item:
            continue

        total += 1
        try:
            pred = extract_binary_answer(item["generated_response"])
            gt = item["is_correct"]
            preds.append(pred)
            gts.append(gt)
        except Exception:
            failed += 1

    return preds, gts, failed, total


def compute_classification_metrics(preds, gts):
    """Compute accuracy, precision, recall, F1 where False = positive class (detecting error)."""

    TP = sum((p is False and g is False) for p, g in zip(preds, gts))
    FP = sum((p is False and g is True) for p, g in zip(preds, gts))
    FN = sum((p is True and g is False) for p, g in zip(preds, gts))

    accuracy = sum(p == g for p, g in zip(preds, gts)) / len(preds) if preds else 0
    precision = TP / (TP + FP) if (TP + FP) > 0 else 0
    recall = TP / (TP + FN) if (TP + FN) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {"accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1}


# ============================================
# Main procedure
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
        question = get_question(sample)
        gold_str = get_gold_str(sample)

        try:
            is_correct = gold_to_bool(gold_str)
        except Exception:
            is_correct = None

        prompt = build_prompt(question)
        gen_text = run_inference(model, tokenizer, prompt)

        outputs.append({
            "index": idx,
            "question": question,
            "gold_raw": gold_str,
            "is_correct": is_correct,
            "generated_response": gen_text
        })

    with open(OUTPUT_JSONL_PATH, "w", encoding="utf-8") as f:
        json.dump(outputs, f, ensure_ascii=False, indent=2)

    preds, gts, failed, total = evaluate_correction_task(OUTPUT_JSONL_PATH)
    metrics = compute_classification_metrics(preds, gts)
    failed_rate = (failed / total) if total else 0.0

    print("\n=== Final Correction Evaluation ===")
    print(f"Accuracy      : {metrics['accuracy']:.4f}")
    print(f"Precision     : {metrics['precision']:.4f}")
    print(f"Recall        : {metrics['recall']:.4f}")
    print(f"F1 Score      : {metrics['f1']:.4f}")
    print(f"Failed Parses : {failed}/{total} ({failed_rate*100:.2f}%)")
    print(f"Total Samples : {total}")
    print("----------------------")

    summary = {
        "metrics": {
            "total": total,
            "evaluated": len(preds),
            "failed": failed,
            "failure_rate": failed_rate,
            "accuracy": metrics["accuracy"],
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
        }
    }

    try:
        with open(OUTPUT_JSONL_PATH, "r", encoding="utf-8") as f:
            arr = json.load(f)
        arr.append(summary)
        with open(OUTPUT_JSONL_PATH, "w", encoding="utf-8") as f:
            json.dump(arr, f, ensure_ascii=False, indent=2)
    except Exception:
        with open(OUTPUT_JSONL_PATH + ".metrics.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
