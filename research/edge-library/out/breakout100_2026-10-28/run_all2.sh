#!/bin/bash
# Second batch (brk100 families) after the first queue is done. Owner's words: "run full que" (2026-10-28).
cd ~/ramos-quant-homebase/research/edge-library
PY=~/ramos-quant-homebase/.venv-research/bin/python
L=out/breakout100_2026-10-28/logs
until grep -q "QUEUE DONE" $L/queue.log; do sleep 60; done
for f in out/breakout100_2026-10-28/specs2/*.json; do
  n=$(basename $f .json)
  echo "$(date +%T) START $n" >> $L/queue2.log
  $PY bp.py wf run $n --owner-said="run full que" --workers 12 --no-worse --wait 86400 > $L/$n.txt 2>&1
  echo "$(date +%T) END $n rc=$?" >> $L/queue2.log
done
echo "$(date +%T) QUEUE2 DONE" >> $L/queue2.log
