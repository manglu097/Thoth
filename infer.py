import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ======================================================
# Fixed configuration
# ======================================================
MODEL_PATH = "xxx"   
DTYPE = "bfloat16"              
ATTN_IMPL = "flash_attention_2"
DEVICE_MAP = "auto"

MAX_NEW_TOKENS = 1024
TEMPERATURE    = 0.6
TOP_P          = 0.95
DO_SAMPLE      = True


# ======================================================
# Prompts — USER ONLY EDITS THESE TWO
# ======================================================
SYSTEM_PROMPT = """You are an bio-expert scientific assistant. Your task is to provide a single, continuous string containing a complete, structured solution. Your response must begin with <think> and have four components, each enclosed in its respective tag in the following order: <think>, <key>, <orc>, and <note>. The <think> tag must contain your scientific reasoning and strategy. The <key> tag is the structured plan, and it is crucial that each step is a single JSON object with its content distilled into atomic keywords for the action, objects, and parameters. The <orc> tag will be a human-readable summary of the plan, and <note> will provide critical safety information. The final output structure must be: <think>...</think>\n\n<key>...</key>\n\n<orc>...</orc>\n\n<note>...</note>"""

USER_PROMPT = """You need to prepare gel embedding solution according to the protocol, which specifies mixing 5 mL gel embedding premix with 25 µL of 10% ammonium persulfate and 2.5 µL TEMED. However, you only need to embed a single thin brain slice and want to scale this recipe down to 1 mL of gel embedding premix while keeping the same ratios of components. What exact volumes of ammonium persulfate and TEMED should you add, and how should you prepare this scaled-down solution?"""

# ======================================================
# Load model
# ======================================================
def load_model_and_tokenizer(model_path: str):
    dtype = torch.bfloat16 if DTYPE == "bfloat16" else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=dtype,
        attn_implementation=ATTN_IMPL,
        device_map=DEVICE_MAP,
    )
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    return model, tokenizer


# ======================================================
# Single inference
# ======================================================
def generate(model, tokenizer, system_prompt: str, user_prompt: str) -> str:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=True,
    )

    inputs = tokenizer([text], return_tensors="pt").to(model.device)

    with torch.inference_mode():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            do_sample=DO_SAMPLE,
            pad_token_id=tokenizer.pad_token_id,
        )

    gen_ids = output_ids[0][inputs.input_ids.shape[1]:]
    return tokenizer.decode(gen_ids, skip_special_tokens=True)


# ======================================================
# Main
# ======================================================
def main():
    print("Loading model...")
    model, tokenizer = load_model_and_tokenizer(MODEL_PATH)
    print("Model loaded.\n")

    result = generate(model, tokenizer, SYSTEM_PROMPT, USER_PROMPT)

    print("=== Model Output ===")
    print(result)
    print("====================\n")


if __name__ == "__main__":
    main()
