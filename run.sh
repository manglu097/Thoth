#!/bin/bash
set -e

# Paths
export TRAIN_DATA=xxx/train.parquet
export TEST_DATA=xxx/test.parquet
export MODEL_PATH=xxx 
export REWARD_PATH=./verl/verl/utils/reward_score/SCORE.py

export PROJECT_NAME=Thoth
export EXPERIMENT_NAME=Thoth_exp1
export CKPT_DIR=xxx/${EXPERIMENT_NAME}

# Reward switches (now env variables)
export GRPO_ORDER_MODE="strict_subseq" # "strict_subseq" or "lcs"
export GRPO_COMBINE_MODE="sum"         # "sum" or "product"
export GRPO_CONTENT_DENOM="matched"    # "matched" or "max_len"
export GRPO_FINAL_COMBINE="product"    # "product" or "sum"
     
bash ./train/score_start.sh "$@"

