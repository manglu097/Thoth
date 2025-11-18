import os
import json
import re
from typing import List, Dict, Tuple, Any, Set
from tqdm import tqdm
from openai import OpenAI
from prompt2 import (
    SYSTEM_PROMPT,
    TYPE_INSTRUCTIONS,
    USER_PROMPT_TEMPLATE_LEVEL2,
    REPAIR_PROMPT,
)

# ================= Configurations =================
BASE_URL = "xxx" #API_URL
MODEL_NAME = "xxx" #API_model
OPENAI_API_KEY = "sk-xxx" #API_key

INPUT_FILE = "Protocol-Comprehension.json"
OUTPUT_FILE = "Protocol-Comprehension-success.jsonl"
UNCHECKED_OUTPUT_FILE = "Protocol-Comprehension-failed.jsonl"

TEMPERATURE = 0.6
MAX_REPAIR_TRIES = 2 #retry 
VERBOSE = False

# 🔴 Explicitly specify the types and number of samples to generate
SELECTED_TYPES: Dict[str, int] = {
    "overview_qa": 2,
    "specific_step_qa": 5,
    "retrieval": 0,
    "planning": 0,
    "troubleshooting": 0,
    "constraint": 0,
    "scaling": 0,
    "safety": 0,
}

QA_PATTERN = re.compile(
    r"<question>(?P<q>.*?)</question>\s*"
    r"<think>(?P<think>.*?)</think>\s*"
    r"<key>(?P<key>.*?)</key>\s*"
    r"<orc>(?P<orc>.*?)</orc>\s*"
    r"<note>(?P<note>.*?)</note>",
    re.S | re.I
)

STEP_JSON_LINE = re.compile(r"^\s*Step\s+(\d+):\s*(\{.*\})\s*$", re.I | re.M)
STEP_TEXT_LINE = re.compile(r"^\s*Step\s+(\d+):\s*(.+?)\s*$", re.I | re.M)

def extract_qa_blocks(text: str) -> List[Dict[str, str]]:
    items = []
    for m in QA_PATTERN.finditer(text or ""):
        items.append({
            "question": m.group("q").strip(),
            "think": m.group("think").strip(),
            "key": m.group("key").strip(),
            "orc": m.group("orc").strip(),
            "note": m.group("note").strip(),
        })
    return items

def _is_lower_str_list(lst: List[Any]) -> bool:
    for x in lst:
        if not isinstance(x, str):
            return False
        letters = "".join([ch for ch in x if ch.isalpha()])
        if letters and letters != letters.lower():
            return False
    return True

def _parse_key_steps(key_block: str) -> Tuple[List[int], List[Dict[str, Any]], List[str]]:
    step_nums: List[int] = []
    step_objs: List[Dict[str, Any]] = []
    errors: List[str] = []

    matches = list(STEP_JSON_LINE.finditer(key_block or ""))
    if not matches:
        errors.append("No valid 'Step X: {...}' lines found in <key>.")
        return step_nums, step_objs, errors

    for m in matches:
        n_str = m.group(1)
        j_str = m.group(2).strip()
        try:
            obj = json.loads(j_str)
        except Exception:
            errors.append(f"Step {n_str} JSON not parseable in <key>.")
            continue

        if not isinstance(obj, dict):
            errors.append(f"Step {n_str} must be a JSON object in <key>.")
            continue

        step_nums.append(int(n_str))
        step_objs.append(obj)

    return step_nums, step_objs, errors

def validate_key(key_block: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    step_nums, step_objs, errors = _parse_key_steps(key_block)

    if not step_nums:
        return False, "No valid steps in <key>.", []

    if step_nums != list(range(1, len(step_nums) + 1)):
        return False, f"Non-consecutive step numbers in <key>: {step_nums}", []

    for idx, obj in enumerate(step_objs, start=1):
        keys = set(obj.keys())
        if keys != {"action", "objects", "parameters"}:
            return False, f"Step {idx} in <key> must have action/objects/parameters only.", []
        if not isinstance(obj.get("action"), str):
            return False, f"Step {idx} 'action' must be str in <key>.", []
        if not isinstance(obj.get("objects"), list) or not _is_lower_str_list(obj["objects"]):
            return False, f"Step {idx} 'objects' must be a lowercase string list in <key>.", []
        if not isinstance(obj.get("parameters"), list) or not _is_lower_str_list(obj["parameters"]):
            return False, f"Step {idx} 'parameters' must be a lowercase string list in <key>.", []

        letters = "".join([ch for ch in obj["action"] if ch.isalpha()])
        if letters and letters != letters.lower():
            return False, f"Step {idx} 'action' must be lowercase in <key>.", []

    return True, "ok", step_objs

def count_orc_steps(orc_block: str) -> Tuple[bool, str, int, List[int]]:
    matches = list(STEP_TEXT_LINE.finditer(orc_block or ""))
    if not matches:
        return False, "No 'Step X: ...' lines found in <orc>.", 0, []

    step_nums = [int(m.group(1)) for m in matches]
    if step_nums != list(range(1, len(step_nums) + 1)):
        return False, f"Non-consecutive step numbers in <orc>: {step_nums}", len(step_nums), step_nums

    return True, "ok", len(matches), step_nums

def validate_item(item: Dict[str, str]) -> Tuple[bool, str, List[Dict[str, Any]]]:
    for k in ["question", "think", "key", "orc", "note"]:
        if not item.get(k):
            return False, f"Missing <{k}>.", []

    ok_key, msg_key, key_steps = validate_key(item["key"])
    if not ok_key:
        return False, msg_key, []

    ok_orc, msg_orc, orc_count, _ = count_orc_steps(item["orc"])
    if not ok_orc:
        return False, msg_orc, []

    if orc_count != len(key_steps):
        return False, f"Step count mismatch: <key> has {len(key_steps)} steps, <orc> has {orc_count}.", []

    return True, "ok", key_steps

def extract_actions_from_key_steps(key_steps: List[Dict[str, Any]]) -> List[str]:
    actions: List[str] = []
    seen = set()
    for obj in key_steps or []:
        act = obj.get("action")
        if isinstance(act, str) and act not in seen:
            seen.add(act)
            actions.append(act)
    return actions

def normalize_protocol_fields(proto: Dict[str, Any]) -> Dict[str, str]:
    return {
        "title": proto.get("title") or proto.get("exp_name") or "",
        "abstract": proto.get("abstract") or "",
        "problem": proto.get("problem") or "",
        "method": proto.get("method") or "",
        "innovation": proto.get("innovation") or "",
        "application": proto.get("application") or "",
        "input": proto.get("input") or (
            "materials: " + (proto.get("materials") or "") +
            "; equipment: " + (proto.get("equipment") or proto.get("equipments") or "")
        ),
        "hierarchical_protocol": proto.get("hierarchical_protocol") or proto.get("procedure") or proto.get("procedures") or "",
    }

def load_protocols(input_file: str):
    with open(input_file, "r", encoding="utf-8") as f:
        first_char = f.read(1)
        f.seek(0)
        if first_char == "[":
            data = json.load(f)
            return data
        else:
            return [json.loads(line) for line in f if line.strip()]

def load_existing_ids(*paths: str) -> Set[Any]:
    processed: Set[Any] = set()
    for p in paths:
        if not p or not os.path.exists(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    pid = obj.get("id")
                    if pid is not None:
                        processed.add(pid)
                except Exception:
                    continue
    return processed

# ================= Main Workflow =================
def main():
    client = OpenAI(base_url=BASE_URL, api_key=OPENAI_API_KEY)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(UNCHECKED_OUTPUT_FILE), exist_ok=True)

    # 1) Preload input
    data = load_protocols(INPUT_FILE)

    # 2) Load processed IDs (check both ok/failed files)
    processed_ids = load_existing_ids(OUTPUT_FILE, UNCHECKED_OUTPUT_FILE)
    if VERBOSE:
        print(f"[Resume] Found {len(processed_ids)} processed ids. Will skip them.")

    # 3) Iterate over inputs and generate output
    skipped = 0
    written_ok = 0
    written_bad = 0

    for idx, proto in enumerate(tqdm(data, total=len(data), desc="Processing protocols")):
        rec_id = proto.get("id", f"protocol_{idx}") 
        if rec_id in processed_ids:
            skipped += 1
            continue

        norm = normalize_protocol_fields(proto)

        for type_name, num in SELECTED_TYPES.items():
            if num <= 0:
                continue

            user_prompt = USER_PROMPT_TEMPLATE_LEVEL2.format(
                **norm,
                num_qa=num,
                type_name=type_name,
                type_instruction=TYPE_INSTRUCTIONS[type_name],
            )

            resp = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = resp.choices[0].message.content or ""
            items = extract_qa_blocks(text)

            if len(items) > num:
                items = items[:num]

            for it in items:
                ok, msg, key_steps = validate_item(it)
                actions = extract_actions_from_key_steps(key_steps)

                out = {
                    "id": rec_id,
                    "type": type_name,
                    "question": it["question"],
                    "think": it["think"],
                    "key": it["key"],
                    "orc": it["orc"],
                    "note": it["note"],
                    "action": actions, 
                }

                if ok:
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as fout_ok:
                        fout_ok.write(json.dumps(out, ensure_ascii=False) + "\n")
                    written_ok += 1
                else:
                    out["error"] = msg
                    with open(UNCHECKED_OUTPUT_FILE, "a", encoding="utf-8") as fout_bad:
                        fout_bad.write(json.dumps(out, ensure_ascii=False) + "\n")
                    written_bad += 1
        processed_ids.add(rec_id)

    print("\n========== Summary ==========")
    print(f"Input protocols:                  {len(data)}")
    print(f"Skipped by resume (seen ids):     {skipped}")
    print(f"✅ Written OK (format passed):     {written_ok}")
    print(f"❌ Written UNCHECKED (format fail): {written_bad}")
    print(f"Saved OK to:        {OUTPUT_FILE}")
    print(f"Saved UNCHECKED to: {UNCHECKED_OUTPUT_FILE}")

if __name__ == "__main__":
    main()
