# 🧬 Thoth: Unleashing Scientific Reasoning for Bio-experimental Protocol Generation

<div align="center">

[![ICLR 2026](https://img.shields.io/badge/ICLR-2026-blue?style=flat-square)](https://openreview.net/group?id=ICLR.cc/2026/Conference)
[![arXiv](https://img.shields.io/badge/arXiv-2510.15600-b31b1b?style=flat-square)](https://arxiv.org/abs/2510.15600)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square)](https://www.python.org/downloads/)
[![Project Page](https://img.shields.io/badge/Project-Homepage-ff69b4?style=flat-square)](https://thothshowcase-znvpduw8.manus.space/)

**A reproducible pathway for autonomous wet-lab protocol generation via structured component-based reward mechanism**

[🚀 Quick Start](#quick-start) • 
[📊 Results](#results) • 
[📦 Dataset](#scirecipe-dataset) • 
[🔧 Training](#training) • 
[📖 Citation](#citation)


[🤗 Thoth](https://huggingface.co/manglu3935/Thoth) • [🤗 Thoth-mini](https://huggingface.co/manglu3935/Thoth-mini) • [🤗 SciRecipe](https://huggingface.co/datasets/manglu3935/SciRecipe)

</div>

---

## 📖 Overview

**Thoth** is a knowledge-to-action model that transforms scientific knowledge into accurate, logically ordered, and executable biological experimental protocols. This repository introduces:

- **SciRecipe**: A comprehensive dataset of 12K+ expert-curated biological protocols across 27 subfields
- **Sketch-and-Fill Paradigm**: A novel reasoning framework that separates analysis, structuring, and execution
- **SCORE Mechanism**: A structured component-based reward system evaluating step granularity, order consistency, and semantic fidelity
- **Thoth Models**: State-of-the-art protocol generation models achieving SOTA performance on multiple scientific benchmarks

### 🎯 Key Achievements

| Metric | Thoth | vs ChatGPT-4o | vs DeepSeek-V3 |
|--------|-------|---------------|----------------|
| **Average Performance** | **52.10%** | +3.69% ↑ | +3.94% ↑ |
| **Semantic Alignment** | **46.60%** | +4.88% ↑ | +4.88% ↑ |
| **Step Matching** | **53.00%** | +11.29% ↑ | +11.29% ↑ |
| **Order Consistency** | **75.34%** | +2.07% ↑ | +1.37% ↑ |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- CUDA 12.1+ (for GPU acceleration)
- 17GB+ GPU memory (for Thoth-8B inference)
- 8GB+ GPU memory (for Thoth-mini-4B inference)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/Thoth.git
cd Thoth

# Install dependencies
pip install -r requirements.txt

# Install VERL framework (recommended for training)
cd verl
pip install -e .
cd ..
```

### Basic Inference

```bash
# Configure your model path and prompts in infer.py
export MODEL_PATH="path/to/thoth/model"

# Run inference
python infer.py
```

**Example Output:**
```
<think>
To prepare a scaled-down gel embedding solution, I need to calculate the proportional volumes 
based on the 5:1 ratio of premix to total additives...
</think>

<key>
Step 1: {"action": "calculate", "objects": ["volume"], "parameters": ["premix: 1mL", "ratio: 5:1"]}
Step 2: {"action": "mix", "objects": ["ammonium persulfate"], "parameters": ["volume: 5µL"]}
Step 3: {"action": "mix", "objects": ["TEMED"], "parameters": ["volume: 0.5µL"]}
</key>

<orc>
1. Calculate the scaled volumes: For 1 mL of gel embedding premix, you need 5 µL of 10% ammonium 
persulfate and 0.5 µL of TEMED to maintain the original 5:1 ratio.
2. Add the ammonium persulfate to the premix and mix thoroughly.
3. Add TEMED last and mix immediately to initiate polymerization.
</orc>

<note>
TEMED is volatile and should be added last. Work quickly after adding TEMED as polymerization 
begins immediately. Ensure proper ventilation.
</note>
```

---

## 📊 Results

### Main Results on SciRecipe-Eval

Our comprehensive evaluation across multiple metrics demonstrates Thoth's superior performance:

| Model | Semantic-A | Order-LCS | Order-S | Step-M | BLEU-AVG | ROUGE-L | METEOR | KW-F1 | **AVG** |
|-------|-----------|-----------|---------|--------|----------|---------|--------|-------|---------|
| GPT-5 | 27.79 | 58.12 | 11.35 | 18.79 | 21.31 | 32.96 | 32.55 | 39.17 | 32.84 |
| ChatGPT-4o | 40.04 | 73.27 | 24.00 | 44.00 | 38.95 | 48.42 | 44.66 | 52.05 | 48.41 |
| Claude Opus 4.1 | 41.32 | 71.70 | 21.80 | 34.59 | 34.69 | 44.42 | 40.36 | 50.00 | 45.65 |
| DeepSeek-V3 | 41.72 | 73.97 | 21.44 | 41.71 | 38.18 | 48.49 | 45.08 | 52.33 | 48.16 |
| **Thoth-mini** | **44.28** | **74.68** | **25.33** | **52.67** | **43.32** | **49.23** | **46.41** | **53.13** | **51.10** |
| **Thoth** | **46.60** | **75.34** | **25.50** | **53.00** | **43.62** | **50.02** | **47.39** | **54.13** | **52.10** |

**Metric Definitions:**
- **Semantic-A**: Semantic alignment between generated and ground-truth protocols
- **Order-LCS**: Longest Common Subsequence of action sequences
- **Order-S**: Strict subsequence matching for action order
- **Step-M**: Step count matching with penalty for mismatches
- **BLEU-AVG, ROUGE-L, METEOR**: Standard NLP similarity metrics
- **KW-F1**: Keyword extraction F1 score

### Performance on Scientific Benchmarks

| Benchmark | Intern-S1 | SciDFM | **Thoth-mini** | **Thoth** |
|-----------|-----------|--------|----------------|-----------|
| HLE: Biomedicine | 15.0 | 15.5 | 17.5 | 17.5 |
| LAB-Bench: ProtocolQA | 27.0 | 38.0 | 42.5 | 44.5 |
| PubMedQA | 38.0 | 34.5 | 50.0 | 50.0 |
| **Average** | **26.7** | **29.3** | **36.7** | **37.3** |

---

## 📦 SciRecipe Dataset

### Dataset Overview

**SciRecipe** is a large-scale, multi-task dataset designed to improve and evaluate LLMs in experimental protocol understanding and generation.

- **Size**: 12,000+ expert-curated biological protocols
- **Coverage**: 27 biological subfields (neuroscience, molecular biology, cancer biology, etc.)
- **Sources**: Nature Protocols, Bio-protocol, Protocols.io, and expert curation
- **Quality**: Rigorous cleaning and structural validation

### Dataset Structure

```
data/
├── meta_data/          # SciRecipe metadata and construction scripts
│   ├── SciRecipe1.py   # Dataset construction utilities
│   ├── SciRecipe2.py   # Additional processing scripts
│   └── prompt.py       # Prompt templates for data generation
├── mineru_pdf/         # Extracted protocol text (MinerU processed)
├── origin_pdf/         # Original experimental protocol PDFs
└── train_data/         # Processed SciRecipe training data
    ├── train.parquet   # Training split
    ├── val.parquet     # Validation split
    └── test.parquet    # Test split
```

### Task Categories

#### 1. Protocol-Comprehension Tasks
- **Overview**: Global protocol summarization and high-level understanding
- **Specific**: Fine-grained analysis of protocol components and steps

#### 2. Problem-Solving Tasks
- **Retrieval**: Finding relevant protocols for given scientific queries
- **Planning**: Generating step-by-step experimental plans
- **Troubleshooting**: Identifying and resolving protocol issues
- **Constraint**: Handling experimental constraints and limitations
- **Scaling**: Adjusting protocol volumes and parameters
- **Safety**: Identifying safety considerations and hazards

### Data Access

**🤗 [Download SciRecipe Dataset](https://huggingface.co/datasets/manglu3935/SciRecipe)**

The complete SciRecipe dataset is now available on HuggingFace Hub:

```bash
# Access SciRecipe dataset
from datasets import load_dataset
dataset = load_dataset("manglu3935/SciRecipe")

# Explore the dataset
print(f"Dataset splits: {dataset.keys()}")
print(f"Training samples: {len(dataset['train'])}")
print(dataset['train'][0])
```

> 📊 **Dataset Statistics**:
> - **Total Protocols**: 12,000+
> - **Biological Subfields**: 27
> - **Training Samples**: ~9,600
> - **Validation Samples**: ~1,200
> - **Test Samples**: ~1,200

---

## 🔧 Training

### Sketch-and-Fill Paradigm

Thoth employs a three-stage reasoning paradigm that explicitly separates analysis, structuring, and execution:

```
Query: "Prepare gel embedding solution for a single brain slice"
         ↓
    <think> Stage
    Decompose objectives, identify dependencies, justify steps
         ↓
    <key> Stage
    Convert strategy to atomic, machine-readable steps (JSON format)
         ↓
    <orc> Stage
    Expand structured steps into fluent natural language
         ↓
    <note> Stage (Optional)
    Add critical safety information
```

### SCORE Mechanism

The **Structured COmponent-based REward** evaluates protocols across four dimensions:

#### 1. Format Gate
- Ensures output contains all four components: `<think>`, `<key>`, `<orc>`, `<note>`
- Validates JSON structure in `<key>` section
- Each step follows: `{"action": verb, "objects": [...], "parameters": [...]}`

#### 2. Consistency Gate
- Verifies step-by-step correspondence between `<key>` and `<orc>`
- Ensures semantic alignment across components
- Validates action-object-parameter relationships

#### 3. Step Scale Reward
- Measures gap between generated and ground-truth step counts
- Penalizes both under- and over-generation
- Formula: `f(d) = cos(π·d/2M)` where d is step count difference

#### 4. Step Semantics Reward
- **Order Consistency**: Evaluates action sequence alignment using LCS or strict subsequence matching
- **Semantic Consistency**: Measures object and parameter overlap for aligned steps
- Combined formula: `r_semantics = r_order · r_semantic`

**Final SCORE Formula:**
```
SCORE(y, y*) = I_format(y) · I_consistency(y) · r_scale(y, y*) · r_semantics(y, y*)
```

### Three-Stage Training Strategy

#### Stage 1: Pre-training (PT)
- Objective: Learn semantic structure and operational logic from large-scale protocol text
- Data: Unlabeled protocol corpus
- Duration: ~50K steps
- Learning Rate: 1e-4

#### Stage 2: Supervised Fine-tuning (SFT)
- Objective: Align model with Sketch-and-Fill paradigm
- Data: SciRecipe with Sketch-and-Fill annotations
- Duration: ~30K steps
- Learning Rate: 5e-5

#### Stage 3: Reinforcement Learning (RL)
- Objective: Optimize protocol quality using SCORE rewards
- Algorithm: GRPO (Generalized Reward Policy Optimization)
- Duration: ~20K steps
- Learning Rate: 1e-5
- Reward Scaling: 0.01

### Training Configuration

```bash
# Edit run.sh to configure:
export TRAIN_DATA="path/to/train.parquet"
export TEST_DATA="path/to/test.parquet"
export MODEL_PATH="Qwen/Qwen3-8B"
export CKPT_DIR="./checkpoints/thoth_exp1"

# SCORE configuration
export GRPO_ORDER_MODE="strict_subseq"    # or "lcs"
export GRPO_COMBINE_MODE="sum"             # or "product"
export GRPO_CONTENT_DENOM="matched"        # or "max_len"
export GRPO_FINAL_COMBINE="product"        # or "sum"

# Start training
bash run.sh
```

### Hardware Requirements

| Model | GPU Memory | Batch Size | Training Time |
|-------|-----------|-----------|---------------|
| Thoth-mini (4B) | 8GB | 4 | ~12 hours |
| Thoth (8B) | 17GB | 2 | ~24 hours |
| Thoth (8B) with LoRA | 12GB | 4 | ~18 hours |

### Monitoring Training

```bash
# View training metrics and SCORE component breakdown
tensorboard --logdir ./outputs/

# Or use the integrated visualization in VERL
python verl/scripts/rollout_viewer.py --checkpoint ./checkpoints/thoth_exp1/
```

---

## 📊 Evaluation

### Running Evaluations

```bash
# Configure evaluation parameters in eval/eval_batch.py
export MODEL_PATH="path/to/thoth/model"
export INPUT_JSONL="data/SciRecipe-Eval.jsonl"
export OUTPUT_JSONL="results/output.jsonl"

# Run evaluation
python eval/eval_batch.py
```

### Evaluation Metrics

The evaluation suite includes:

1. **Executability Metrics** (left of dashed line in results table)
   - Semantic-A: Semantic alignment
   - Order-LCS: Longest common subsequence
   - Order-S: Strict subsequence matching
   - Step-M: Step count matching

2. **Lexical Similarity Metrics** (right of dashed line)
   - BLEU-AVG: BLEU score averaged across n-grams
   - ROUGE-L: ROUGE-L score
   - METEOR: METEOR score
   - KW-F1: Keyword extraction F1

### Evaluation Output

```json
{
  "query": "Prepare gel embedding solution...",
  "generated": "<think>...</think>\n<key>...</key>\n<orc>...</orc>\n<note>...</note>",
  "ground_truth": "...",
  "metrics": {
    "semantic_a": 46.60,
    "order_lcs": 75.34,
    "order_s": 25.50,
    "step_m": 53.00,
    "bleu_avg": 43.62,
    "rouge_l": 50.02,
    "meteor": 47.39,
    "kw_f1": 54.13,
    "score": 52.10
  }
}
```

---

## 🤖 Models

### Available Models

| Model | Base Model | Parameters | GPU Memory | Download |
|-------|-----------|-----------|-----------|----------|
| **Thoth-mini** | Qwen3-4B | 4B | 8GB | [🤗 HuggingFace](https://huggingface.co/manglu3935/Thoth-mini) |
| **Thoth** | Qwen3-8B | 8B | 17GB | [🤗 HuggingFace](https://huggingface.co/manglu3935/Thoth) |

### Model Performance Comparison

```
Thoth-mini (4B)
├─ Semantic-A: 44.28%
├─ Order-LCS: 74.68%
├─ Order-S: 25.33%
├─ Step-M: 52.67%
└─ Average: 51.10%

Thoth (8B)
├─ Semantic-A: 46.60%
├─ Order-LCS: 75.34%
├─ Order-S: 25.50%
├─ Step-M: 53.00%
└─ Average: 52.10%
```

### Model Inference

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

# Load model from HuggingFace
model = AutoModelForCausalLM.from_pretrained(
    "manglu3935/Thoth",  # or "manglu3935/Thoth-mini" for 4B version
    torch_dtype="bfloat16",
    attn_implementation="flash_attention_2",
    device_map="auto"
)
tokenizer = AutoTokenizer.from_pretrained("manglu3935/Thoth")

# Prepare input
system_prompt = "You are a bio-expert scientific assistant..."
user_prompt = "Prepare gel embedding solution..."

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_prompt}
]

# Generate
inputs = tokenizer.apply_chat_template(
    messages,
    tokenize=True,
    add_generation_prompt=True,
    return_tensors="pt"
).to(model.device)

outputs = model.generate(
    inputs,
    max_new_tokens=1024,
    temperature=0.6,
    top_p=0.95,
    do_sample=True
)

response = tokenizer.decode(outputs[0], skip_special_tokens=True)
print(response)
```

---

## 📁 Repository Structure

```
Thoth/
├── README.md                    # This file
├── LICENSE                      # MIT License
├── requirements.txt             # Python dependencies
│
├── data/                        # Dataset and data utilities
│   ├── meta_data/              # Dataset construction scripts
│   │   ├── SciRecipe1.py
│   │   ├── SciRecipe2.py
│   │   └── prompt.py
│   ├── mineru_pdf/             # Extracted protocol text
│   ├── origin_pdf/             # Original PDFs
│   └── train_data/             # Processed training data
│
├── train/                       # Training configuration and scripts
│   ├── qwen3_8B_pt.yaml        # Pre-training config
│   ├── qwen3_8B_sft.yaml       # SFT config
│   └── score_start.sh          # Training launcher
│
├── eval/                        # Evaluation utilities
│   ├── eval_batch.py           # Main evaluation script
│   ├── ERR.py                  # Error analysis
│   ├── ORD.py                  # Order consistency metrics
│   └── PQA.py                  # Protocol QA metrics
│
├── infer.py                     # Inference script
├── run.sh                       # Main training script
│
├── verl/                        # VERL framework
│   ├── verl/                   # Core VERL library
│   ├── recipe/                 # Training recipes
│   ├── docker/                 # Docker configurations
│   └── setup.py
│
└── outputs/                     # Training outputs and logs
    └── 2025-11-18/             # Timestamped experiment runs
```

---

## 🧪 Ablation Studies

### SCORE Component Ablation

| Configuration | Semantic-A | Order-LCS | Order-S | Step-M | **AVG** |
|---------------|-----------|-----------|---------|--------|---------|
| w/o Step Scale | 43.67 | 55.97 | 6.83 | 10.00 | 35.34 |
| w/o Semantic Alignment | 38.68 | 73.70 | 23.17 | 50.17 | 49.29 |
| w/o Order Consistency | 40.93 | 61.27 | 12.83 | 33.33 | 41.30 |
| **Full SCORE** | **46.60** | **75.34** | **25.50** | **53.00** | **52.10** |

### Training Strategy Ablation

| Stage | Semantic-A | Order-LCS | Order-S | Step-M | **AVG** |
|-------|-----------|-----------|---------|--------|---------|
| Stage 1 (PT only) | 25.2 | 57.7 | 13.7 | 26.8 | 30.85 |
| Stage 1+2 (PT+SFT) | 38.5 | 64.9 | 13.0 | 45.7 | 40.53 |
| Stage 2+3 (SFT+RL) | 43.5 | 75.0 | 26.2 | 51.2 | 49.0 |
| **All Stages** | **46.60** | **75.34** | **25.50** | **53.00** | **52.10** |

---

## 🔍 Troubleshooting

### Common Issues

#### 1. CUDA Out of Memory
```bash
# Reduce batch size in run.sh
export BATCH_SIZE=1

# Or use gradient accumulation
export GRADIENT_ACCUMULATION_STEPS=4

# Or use LoRA for parameter-efficient training
export USE_LORA=true
export LORA_RANK=8
```

#### 2. Model Loading Fails
```bash
# Ensure correct model path
export MODEL_PATH="Qwen/Qwen3-8B"

# Or download model first
huggingface-cli download Qwen/Qwen3-8B --local-dir ./models/qwen3-8b
export MODEL_PATH="./models/qwen3-8b"
```

#### 3. Inference Produces Malformed Output
```bash
# Check system prompt in infer.py
# Ensure <think>, <key>, <orc>, <note> tags are properly formatted
# Increase MAX_NEW_TOKENS if output is truncated
export MAX_NEW_TOKENS=2048
```

---

## 📈 Performance Analysis

### Sketch-and-Fill Impact

Adopting the Sketch-and-Fill paradigm provides consistent improvements:

| Model | w/o Sketch-and-Fill | w/ Sketch-and-Fill | **Improvement** |
|-------|-------------------|------------------|----------------|
| DeepSeek-V3 | 46.27% | 50.16% | +3.89% |
| GPT-5 Chat | 39.61% | 42.53% | +2.92% |
| **Thoth** | 48.31% | 52.10% | +3.79% |

### Cross-Domain Generalization

Thoth demonstrates strong generalization across scientific domains:

- **Neuroscience Protocols**: 54.2% average score
- **Molecular Biology**: 51.8% average score
- **Cancer Biology**: 50.5% average score
- **Immunology**: 52.1% average score

---

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Setup

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Format code
black . && isort .

# Lint
flake8 .
```

---

## 📝 Citation

If you use Thoth in your research, please cite our paper:

```bibtex
@inproceedings{sun2026thoth,
  title={Unleashing Scientific Reasoning for Bio-Experimental Protocol Generation 
         via Structured Component-based Reward Mechanism},
  author={Sun, Haoran and Jiang, Yankai and Tang, Zhenyu and Pan, Yaning and 
          Gu, Shuang and Lin, Zekai and Wang, Lilong and Lou, Wenjie and 
          Liu, Lei and Bai, Lei and Wang, Xiaosong},
  booktitle={International Conference on Learning Representations (ICLR)},
  year={2026}
}
```

---

## 🙏 Acknowledgments

We gratefully acknowledge:

- **[VERL](https://github.com/volcengine/verl)**: Providing the foundation for efficient RL training
- **[MinerU](https://github.com/opendatalab/MinerU)**: Enabling high-quality PDF text extraction
- **[Qwen](https://github.com/QwenLM/Qwen)**: Providing the base language models
- **Scientific Community**: For curating high-quality protocols and providing feedback

---

## 📞 Contact & Support

- **Issues**: Please report bugs and feature requests on [GitHub Issues](https://github.com/yourusername/Thoth/issues)
- **Discussions**: Join our [GitHub Discussions](https://github.com/yourusername/Thoth/discussions) for questions and ideas
- **Email**: thoth-team@example.com

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

---

## 🌟 Star History

If you find this project useful, please consider giving us a star! It helps us understand the community's interest and motivates further development.

[![Star History Chart](https://api.star-history.com/svg?repos=yourusername/Thoth&type=Date)](https://star-history.com/#yourusername/Thoth&Date)

---

<div align="center">

**Made with ❤️ by the Thoth Team**

[⬆ back to top](#-thoth-unleashing-scientific-reasoning-for-bio-experimental-protocol-generation)

</div>