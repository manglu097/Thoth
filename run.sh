#!/bin/bash
set -e

# Paths (allow override from env)
export TRAIN_DATA="${TRAIN_DATA:-xxx/train.parquet}"
export TEST_DATA="${TEST_DATA:-xxx/test.parquet}"
export MODEL_PATH="${MODEL_PATH:-xxx}"
export REWARD_PATH="${REWARD_PATH:-./verl/verl/utils/reward_score/SCORE.py}"

export PROJECT_NAME="${PROJECT_NAME:-Thoth}"
export EXPERIMENT_NAME="${EXPERIMENT_NAME:-Thoth_exp1}"
export CKPT_DIR="${CKPT_DIR:-xxx/${EXPERIMENT_NAME}}"

# SCORE configuration (allow override)
export GRPO_ORDER_MODE="${GRPO_ORDER_MODE:-strict_subseq}"   # strict_subseq | lcs
export GRPO_COMBINE_MODE="${GRPO_COMBINE_MODE:-sum}"         # sum | product
export GRPO_CONTENT_DENOM="${GRPO_CONTENT_DENOM:-matched}"   # matched | max_len
export GRPO_FINAL_COMBINE="${GRPO_FINAL_COMBINE:-product}"   # product | sum

bash ./train/score_start.sh "$@"
