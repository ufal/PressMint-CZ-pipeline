#!/bin/bash
#SBATCH --job-name=PressMint
#SBATCH --partition=gpu-troja,gpu-ms
#SBATCH --output=logs/slurm/process_%A_%a.out
#SBATCH --error=logs/slurm/process_%A_%a.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:1                  # Requests exactly 1 GPU
#SBATCH --cpus-per-task=4          # Adjust if your process uses multi-threading
#SBATCH --mem=16G                   # Adjust memory per line/task

# Ensure the tasks file path is provided via environment variable
if [ -z "$TASKS_FILE" ]; then
    echo "Error: TASKS_FILE variable is not set."
    exit 1
fi

# Ensure the tasks file path is provided via environment variable
if [ -z "$MAKEFILE_TARGET" ]; then
    echo "Error: MAKEFILE_TARGET variable is not set."
    exit 1
fi

export PERLBREW_ROOT=$HOME/perl5/perlbrew
source ${PERLBREW_ROOT}/etc/bashrc
perlbrew use pressmint

# Environment optimization variables for PyTorch / TensorFlow backends
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export MKL_NUM_THREADS=$SLURM_CPUS_PER_TASK

# Extract the specific line matching this Slurm task index
# $SLURM_ARRAY_TASK_ID will be 1, 2, 3... up to your max lines
UUID_PATH=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$TASKS_FILE")

# 3. Prevent running empty tasks if file has trailing empty lines
if [ -z "$UUID_PATH" ]; then
    echo "Task ID $SLURM_ARRAY_TASK_ID matched an empty line. Exiting."
    exit 0
fi

echo "Task ${SLURM_ARRAY_TASK_ID} running on node ${SLURM_NODENAME} with GPU ${CUDA_VISIBLE_DEVICES}"
echo "PROCESSING: $MAKEFILE_TARGET with UUID_PATH: $UUID_PATH"
echo "DATADIR: $DATADIR"

echo -e "$(date +"%Y-%m-%dT%T") START (${SLURM_ARRAY_TASK_ID}): $UUID_PATH" >> logs/PressMint-CZ.slurm.log
# 4. Execute your existing Make command for this specific line
CMD="make $MAKEFILE_TARGET UUID_PATH=$UUID_PATH DEVICE=$DEVICE PERO_OCR_MODEL_CONFIG=$PERO_OCR_MODEL_CONFIG PERO_OCR_MODEL_NAME=$PERO_OCR_MODEL_NAME"
RES=$(/usr/bin/time --output=logs/PressMint-CZ.slurm.$SLURM_JOB_ID.${SLURM_ARRAY_TASK_ID}.tmp -f "%x#%E real, %U user, %S sys, %M kB" $CMD)
TIME=$(cut -d'#' -f 2 logs/PressMint-CZ.slurm.$SLURM_JOB_ID.${SLURM_ARRAY_TASK_ID}.tmp)
CODE=$(cut -d'#' -f 1 logs/PressMint-CZ.slurm.$SLURM_JOB_ID.${SLURM_ARRAY_TASK_ID}.tmp)
if [ $((10#$CODE)) -gt 0 ]; then STATUS="FAILED-$CODE"; else STATUS="FINISHED"; fi
rm logs/PressMint-CZ.slurm.$SLURM_JOB_ID.${SLURM_ARRAY_TASK_ID}.tmp
echo -e "$(date +"%Y-%m-%dT%T") DONE (${SLURM_ARRAY_TASK_ID}): $UUID_PATH   $STATUS    $SLURM_JOB_ID/${SLURM_ARRAY_TASK_ID}   $(hostname)     $TIME         $CMD" >> logs/PressMint-CZ.slurm.log

