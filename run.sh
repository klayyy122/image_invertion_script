#!/bin/bash

THREADS=4
FILES=()

for arg in "$@"; do
    if [[ "$arg" =~ ^[0-9]+$ ]]; then
        THREADS=$arg
    else
        filename=$(basename "$arg" .cpp)
        FILES+=("$filename")
    fi
done

mkdir -p build results

echo "Starting with $THREADS threads..."

PYTHON_ARGS="--threads $THREADS"

if [ ${#FILES[@]} -gt 0 ]; then
    echo "Running specific files: ${FILES[@]}"
    for file in "${FILES[@]}"; do
        PYTHON_ARGS="$PYTHON_ARGS --file $file"
    done
else
    echo "Running all files from cpp/"
fi

python3 python/controller.py $PYTHON_ARGS

echo ""