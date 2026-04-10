#!/bin/bash
# Wrapper to run Bible data converters

if [ "$#" -lt 1 ]; then
    echo "Usage: ./run_converter.sh <script_name.py> [arguments]"
    echo "Example: ./run_converter.sh xml_to_json.py input.xml output.json"
    echo ""
    echo "Available converters:"
    ls *.py | grep -v "run_converter"
    exit 1
fi

SCRIPT=$1
shift
python3 "$SCRIPT" "$@"
