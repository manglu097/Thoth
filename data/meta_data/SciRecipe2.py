import os
import json
import random
import re
from typing import List, Dict, Tuple, Any, Set
from tqdm import tqdm
from openai import OpenAI
from prompt import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE_LEVEL1, 
    REPAIR_PROMPT,
    TYPE_INSTRUCTIONS,
    SYSTEM_PROMPT2,
    USER_PROMPT_TEMPLATE2,
)

# ================= Configuration =================
BASE_URL = "xxx" #API_URL
MODEL_NAME = "xxx" #API_model
OPENAI_API_KEY = "sk-xxx" #API_key

INPUT_FILE = "Problem-Solving.jsonl"
OUTPUT_FILE = "Problem-Solving-success.jsonl"
UNCHECKED_OUTPUT_FILE = "Problem-Solving-failed.jsonl"

# Number of samples per selected type (random in closed interval); default: 1 per type
PER_TYPE_MIN = 1
PER_TYPE_MAX = 1
TEMPERATURE = 0.6
MAX_REPAIR_TRIES = 2

# Resume support: whether to clear output files at startup
CLEAR_OUTPUT_ON_START = False

# Secondary validation model
VALIDATION_MODEL_NAME = "xxx"
VALIDATION_TEMPERATURE = 0.2

# Randomly choose N types from the six available categories (default 3)
# Six categories: retrieval, planning, troubleshooting, constraint, scaling, safety
NUM_TYPES_PER_PROTOCOL = 3

VERBOSE = False  # True enables additional logs
# ================================================


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

VALIDATION_REPORT_PATTERN = re.compile(
    r"<validation_report>.*?"
    r"<accuracy_check>(?P<accuracy>.*?)</accuracy_check>.*?"
    r"<safety_compliance_check>(?P<safety>.*?)</safety_compliance_check>.*?"
    r"<logical_coherence_check>(?P<coherence>.*?)</logical_coherence_check>.*?"
    r"<clarity_ambiguity_check>(?P<clarity>.*?)</clarity_ambiguity_check>.*?"
    r"<generality_specificity_check>(?P<generality>.*?)</generality_specificity_check>.*?"
    r"<efficiency_resource_optimization_check>(?P<efficiency>.*?)</efficiency_resource_optimization_check>.*?"
    r"</validation_report>",
    re.S | re.I
)


def extract_qa_blocks(text: str) -> List[Dict[str, str]]:
    items = []
    for m in QA_PATTERN.finditer(text or ""):
        q = m.group("q").strip()
        think = m.group("think").strip()
        key = m.group("key").strip()
        orc = m.group("orc").strip()
        note = m.group("note").strip()
        answer_block = f"<think>{think}</think>\n\n<orc>{orc}</orc>\n\n<note>{note}</note>"
        items.append({
            "question": q,
            "think": think,
            "key": key,
            "orc": orc,
            "note": note,
            "answer": answer_block, 
        })
    return items


def _is_lower_str_list(lst) -> bool:
    """Check that list elements are lowercase strings."""
    if not isinstance(lst, list):
        return False
    for x in lst:
        if not isinstance(x, str):
            return False
        letters = "".join([ch for ch in x if ch.isalpha()])
        if letters and letters != letters.lower():
            return False
    return True


def _parse_key_steps(key_block: str) -> Tuple[List[int], List[Dict[str, Any]], List[str]]:
    """Parse JSON steps inside <key>."""
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
        letters = "".join([ch for ch in obj["action"] if ch.isalpha()])
        if letters and letters != letters.lower():
            return False, f"Step {idx} 'action' must be lowercase in <key>.", []
        if not _is_lower_str_list(obj.get("objects", [])):
            return False, f"Step {idx} 'objects' must be a lowercase string list in <key>.", []
        if not _is_lower_str_list(obj.get("parameters", [])):
            return False, f"Step {idx} 'parameters' must be a lowercase string list in <key>.", []

    return True, "ok", step_objs


def count_orc_steps(orc_block: str) -> Tuple[bool, str, int, List[int]]:
    matches = list(STEP_TEXT_LINE.finditer(orc_block or ""))
    if not matches:
        return False, "No 'Step X: ...' lines found in <orc>.", 0, []
    step_nums = [int(m.group(1)) for m in matches]
    if step_nums != list(range(1, len(step_nums) + 1)):
        return False, f"Non-consecutive step numbers in <orc>: {step_nums}", len(matches), step_nums
    return True, "ok", len(matches), step_nums


def validate_item(item: Dict[str, str]) -> Tuple[bool, str, List[Dict[str, Any]]]:
    for k in ["question", "think", "key", "orc", "note"]:
        if not item.get(k) or not item[k].strip():
            return False, f"Missing or empty <{k}>.", []

    ok_key, msg_key, key_steps = validate_key(item["key"])
    if not ok_key:
        return False, msg_key, []

    ok_orc, msg_orc, orc_cnt, _ = count_orc_steps(item["orc"])
    if not ok_orc:
        return False, msg_orc, []

    if orc_cnt != len(key_steps):
        return False, f"Step count mismatch: <key> has {len(key_steps)} steps, <orc> has {orc_cnt}.", []

    return True, "ok", key_steps


def run_secondary_validation(client: OpenAI, qa_pair: Dict[str, str]) -> Dict[str, str]:
    user_prompt_val = USER_PROMPT_TEMPLATE2.format(
        question_text=qa_pair["question"],
        answer_text=qa_pair["answer"]
    )
    response = client.chat.completions.create(
        model=VALIDATION_MODEL_NAME,
        temperature=VALIDATION_TEMPERATURE,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT2},
            {"role": "user", "content": user_prompt_val},
        ],
    )
    validation_output_text = response.choices[0].message.content or ""
    report_match = VALIDATION_REPORT_PATTERN.search(validation_output_text)
    if report_match:
        return {
            "accuracy_check": report_match.group("accuracy").strip(),
            "safety_compliance_check": report_match.group("safety").strip(),
            "logical_coherence_check": report_match.group("coherence").strip(),
            "clarity_ambiguity_check": report_match.group("clarity").strip(),
            "generality_specificity_check": report_match.group("generality").strip(),
            "efficiency_resource_optimization_check": report_match.group("efficiency").strip(),
        }
    else:
        return {
            "accuracy_check": "Validation report malformed.",
            "safety_compliance_check": "Validation report malformed.",
            "logical_coherence_check": "Validation report malformed.",
            "clarity_ambiguity_check": "Validation report malformed.",
            "generality_specificity_check": "Validation report malformed.",
            "efficiency_resource_optimization_check": "Validation report malformed.",
            "raw_validation_output": validation_output_text
        }


def is_validation_pass(validation_report: Dict[str, str]) -> bool:
    pass_conditions = {
        "accuracy_check": "No significant scientific inaccuracies found.",
        "safety_compliance_check": "Safety and compliance information is adequate and accurate.",
        "logical_coherence_check": "Logical coherence and actionability are sound.",
        "clarity_ambiguity_check": "All information is clear and unambiguous.",
        "generality_specificity_check": "Appropriate balance of generality and specificity.",
        "efficiency_resource_optimization_check": "Plan demonstrates good efficiency and resource optimization.",
    }
    for k, expect in pass_conditions.items():
        if validation_report.get(k) != expect:
            return False
    if "raw_validation_output" in validation_report:
        return False
    return True


def count_validation_errors(validation_report: Dict[str, str]) -> Tuple[int, int]:
    pass_conditions = {
        "accuracy_check": "No significant scientific inaccuracies found.",
        "safety_compliance_check": "Safety and compliance information is adequate and accurate.",
        "logical_coherence_check": "Logical coherence and actionability are sound.",
        "clarity_ambiguity_check": "All information is clear and unambiguous.",
        "generality_specificity_check": "Appropriate balance of generality and specificity.",
        "efficiency_resource_optimization_check": "Plan demonstrates good efficiency and resource optimization.",
    }
    e0 = 0
    e1 = 0
    for k, expect in pass_conditions.items():
        if validation_report.get(k) != expect:
            e0 += 1
            if k != "accuracy_check":
                e1 += 1
    return e0, e1


def normalize_protocol_fields(proto: Dict[str, Any]) -> Dict[str, str]:
    return {
        "exp_name": str(proto.get("exp_name") or "").strip(),
        "abstract": str(proto.get("abstract") or "").strip(),
        "materials": str(proto.get("materials") or "").strip(),
        "equipment": str((proto.get("equipment") or proto.get("equipments") or "")).strip(),
        "procedure": str((proto.get("procedure") or proto.get("procedures") or "")).strip(),
        "notes": str(proto.get("notes") or "").strip(),
    }


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


def extract_actions_from_key(key_block: str) -> List[str]:
    actions: List[str] = []
    seen = set()
    for m in STEP_JSON_LINE.finditer(key_block or ""):
        try:
            obj = json.loads(m.group(2).strip())
            act = obj.get("action")
            if isinstance(act, str) and act not in seen:
                seen.add(act)
                actions.append(act)
        except Exception:
            continue
    return actions


def _flush_and_sync(fobj):
    try:
        fobj.flush()
        os.fsync(fobj.fileno())
    except Exception:
        pass


def main():
    api_key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
    client = OpenAI(base_url=BASE_URL, api_key=api_key)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    os.makedirs(os.path.dirname(UNCHECKED_OUTPUT_FILE), exist_ok=True)
    if CLEAR_OUTPUT_ON_START:
        open(OUTPUT_FILE, "w", encoding="utf-8").close()
        open(UNCHECKED_OUTPUT_FILE, "w", encoding="utf-8").close()
    processed_ids = load_existing_ids(OUTPUT_FILE, UNCHECKED_OUTPUT_FILE) if not CLEAR_OUTPUT_ON_START else set()
    if VERBOSE:
        print(f"[Resume] Already processed ids: {len(processed_ids)}")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        num_lines = sum(1 for _ in f)

    total_items = 0
    total_passed = 0
    total_unchecked = 0
    skipped = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as fin, \
         open(OUTPUT_FILE, "a", encoding="utf-8") as fout_ok, \
         open(UNCHECKED_OUTPUT_FILE, "a", encoding="utf-8") as fout_unchecked:

        for idx, line in enumerate(tqdm(fin, total=num_lines, desc="Processing protocols")):
            line = line.strip()
            if not line:
                continue
            try:
                proto = json.loads(line)
            except Exception as e:
                if VERBOSE:
                    print(f"[Skip] bad json line: {e}")
                continue

            rec_id = proto.get("id", f"auto_{idx}")
            if rec_id in processed_ids:
                skipped += 1
                continue

            norm = normalize_protocol_fields(proto)
            if not norm["exp_name"] and not norm["procedure"]:
                if VERBOSE:
                    print("[Skip] missing essential fields (exp_name/procedure).")
                continue

            six_core = ["retrieval", "planning", "troubleshooting", "constraint", "scaling", "safety"]
            available = [t for t in six_core if t in TYPE_INSTRUCTIONS]
            k = max(0, min(NUM_TYPES_PER_PROTOCOL, len(available)))
            selected_types = random.sample(available, k=k)

            for type_name in selected_types:
                type_instruction = TYPE_INSTRUCTIONS[type_name]
                num_to_generate = random.randint(PER_TYPE_MIN, PER_TYPE_MAX)

                user_prompt = USER_PROMPT_TEMPLATE_LEVEL1.format(
                    exp_name=norm["exp_name"],
                    abstract=norm["abstract"],
                    materials=norm["materials"],
                    equipment=norm["equipment"],
                    procedure=norm["procedure"],
                    notes=norm["notes"],
                    type_name=type_name,
                    type_instruction=type_instruction,
                    num_qa=num_to_generate,
                )

                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    temperature=TEMPERATURE,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                output_text = response.choices[0].message.content or ""
                items = extract_qa_blocks(output_text)

                initially_validated: List[Dict[str, str]] = []
                for it in items:
                    ok, msg, key_steps = validate_item(it)
                    if ok:
                        initially_validated.append(it)
                    else:
                        if MAX_REPAIR_TRIES > 0:
                            raw_block = (
                                f"<question>{it.get('question','')}</question>\n"
                                f"<think>{it.get('think','')}</think>\n"
                                f"<key>{it.get('key','')}</key>\n"
                                f"<orc>{it.get('orc','')}</orc>\n"
                                f"<note>{it.get('note','')}</note>"
                            )
                            rep = client.chat.completions.create(
                                model=MODEL_NAME,
                                temperature=0.2,
                                messages=[
                                    {"role": "system", "content": REPAIR_PROMPT},
                                    {"role": "user", "content": raw_block}
                                ],
                            )
                            rep_text = rep.choices[0].message.content or ""
                            cand = extract_qa_blocks(rep_text)
                            if cand:
                                ok2, msg2, _ = validate_item(cand[0])
                                if ok2:
                                    initially_validated.append(cand[0])

                for qa_pair in initially_validated:
                    total_items += 1
                    validation_report = run_secondary_validation(client, qa_pair)

                    record = {
                        "id": rec_id,
                        "type": type_name,
                        "question": qa_pair["question"],
                        "think": qa_pair["think"],
                        "key": qa_pair["key"],
                        "orc": qa_pair["orc"],
                        "note": qa_pair["note"],
                        "action": extract_actions_from_key(qa_pair.get("key", "")),
                    }

                    if is_validation_pass(validation_report):
                        fout_ok.write(json.dumps(record, ensure_ascii=False) + "\n")
                        _flush_and_sync(fout_ok)
                        total_passed += 1
                    else:
                        record_failed = dict(record)
                        err, err1 = count_validation_errors(validation_report)
                        record_failed["check_report"] = validation_report
                        record_failed["error"] = err
                        record_failed["error1"] = err1
                        fout_unchecked.write(json.dumps(record_failed, ensure_ascii=False) + "\n")
                        _flush_and_sync(fout_unchecked)
                        total_unchecked += 1

            processed_ids.add(rec_id) 
            _flush_and_sync(fout_ok)
            _flush_and_sync(fout_unchecked)

    print("\n========== Summary ==========")
    print(f"Input lines:                        {num_lines}")
    print(f"Skipped by resume (seen ids):       {skipped}")
    print(f"Generated (post-format-pass) items: {total_items}")
    print(f"✅ Passed secondary validation:     {total_passed}")
    print(f"❌ Failed secondary validation:     {total_unchecked}")
    print(f"Saved OK to:        {OUTPUT_FILE}")
    print(f"Saved UNCHECKED to: {UNCHECKED_OUTPUT_FILE}")


if __name__ == "__main__":
    main()
