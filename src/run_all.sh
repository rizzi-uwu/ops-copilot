#!/bin/sh
# Run the agent on every sample transcript.
# Usage: sh src/run_all.sh [en|de] [extra agent flags, e.g. --finance]
lang="${1:-en}"
[ $# -gt 0 ] && shift
for f in data/transcripts/*.txt; do
  echo "=== $f"
  python src/agent.py "$f" --lang "$lang" "$@" || exit 1
done
