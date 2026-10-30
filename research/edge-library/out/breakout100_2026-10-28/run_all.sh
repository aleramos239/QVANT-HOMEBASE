#!/bin/bash
# One in-sample 3:1 table per idea (hm60 cells, fixed-point rows read later), screening pass without worse fills. Owner's words: "run them all" (2026-10-28).
cd ~/ramos-quant-homebase/research/edge-library
PY=~/ramos-quant-homebase/.venv-research/bin/python
for f in out/breakout100_2026-10-28/specs/*.json; do
  n=$(basename $f .json)
  [ "$n" = nq_b016_pd_bracket ] && continue   # already running as its own job
  echo "$(date +%T) START $n" >> out/breakout100_2026-10-28/logs/queue.log
  $PY bp.py wf run $n --owner-said="run them all" --workers 12 --no-worse --wait 86400 > out/breakout100_2026-10-28/logs/$n.txt 2>&1
  echo "$(date +%T) END $n rc=$?" >> out/breakout100_2026-10-28/logs/queue.log
done
echo "$(date +%T) QUEUE DONE" >> out/breakout100_2026-10-28/logs/queue.log
