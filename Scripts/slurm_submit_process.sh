#!/bin/bash
#SBATCH --job-name=PressMint
#SBATCH --output=logs/process_%A_%a.out
#SBATCH --error=logs/process_%A_%a.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1          # Adjust if your process uses multi-threading
#SBATCH --mem=4G                   # Adjust memory per line/task

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

# Extract the specific line matching this Slurm task index
# $SLURM_ARRAY_TASK_ID will be 1, 2, 3... up to your max lines
UUID_PATH=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$TASKS_FILE")

# 3. Prevent running empty tasks if file has trailing empty lines
if [ -z "$UUID_PATH" ]; then
    echo "Task ID $SLURM_ARRAY_TASK_ID matched an empty line. Exiting."
    exit 0
fi

echo "Processing Task ID $SLURM_ARRAY_TASK_ID"
echo "PROCESSING: $MAKEFILE_TARGET with UUID_PATH: $UUID_PATH"
echo "DATADIR: $DATADIR"

# 4. Execute your existing Make command for this specific line
make $MAKEFILE_TARGET UUID_PATH="$UUID_PATH" DATADIR="$DATADIR"