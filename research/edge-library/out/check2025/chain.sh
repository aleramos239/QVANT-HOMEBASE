#!/bin/zsh
# CHECK-year (2025) menus + controls and the F2 extra seeds. usage: chain.sh A|B   (A = NQ jobs, B = ES + GC jobs)
# Restartable: a store already on disk is skipped (its ledger row is completed if missing). Never names a 2026 date.
cd "$(dirname "$0")/../.." || exit 1
PY="$HOME/ONYX TRADING/.venv/bin/python"
C=$1
LOG=out/check2025/run_$C.log
echo "CHAIN $C START $(date -u +%FT%TZ)" >> $LOG
if [ "$C" = "A" ]; then
  "$PY" out/v2/run_v2.py run out/check2025/jobs_donchian_pick_stress.json >> $LOG 2>&1
fi
for f in menus controls2 extra_seeds; do
  "$PY" out/check2025/run_check.py run out/check2025/jobs_${f}_$C.json >> $LOG 2>&1
done
echo "CHAIN $C DONE $(date -u +%FT%TZ)" >> $LOG
