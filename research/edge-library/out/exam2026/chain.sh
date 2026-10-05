#!/bin/zsh
# EXAM (2026) read of the allowed units: whole menu + stress + 10-seed control. Restartable: a store on disk is skipped (one read).
cd "$(dirname "$0")/../.." || exit 1
PY="$HOME/ONYX TRADING/.venv/bin/python"
LOG=out/exam2026/run.log
echo "CHAIN START $(date -u +%FT%TZ)" >> $LOG
"$PY" out/exam2026/run_exam.py run out/exam2026/jobs_exam.json >> $LOG 2>&1
echo "CHAIN DONE $(date -u +%FT%TZ)" >> $LOG
