#!/bin/bash
# one box: own store folder (symlinks to the parent's in-sample files), pick, then the test months once
set -e
STORE=$1; BOX=$2
R=~/ramos-quant-homebase/research/edge-library
PY=~/ramos-quant-homebase/.venv-research/bin/python
P=$R/runs_wf/$STORE-NQ-tf5; N=$STORE-NQ-tf5__$BOX; D=$R/runs_wf/$N
SAID="run all the structure stops and fixed stops and run them OOS, then give me the new html for each on their OOS metrics heatmap"
if [ ! -d "$D" ]; then
  mkdir "$D"
  for f in "$P"/is "$P"/is-*-worse "$P"/*.lock; do [ -e "$f" ] || continue; case "$f" in */lock.json|*/oos) continue;; esac; ln -s "$f" "$D/$(basename "$f")"; done
fi
L=$R/out/breakout100_2026-10-28/oos/logs
cd $R
$PY bp.py wf pick "$N" "$BOX" --who claude >/dev/null
$PY bp.py wf oos "$N" "$BOX" --who claude --owner-said "$SAID" --workers 4 --wait 3000 --json > $L/$N.json 2> $L/$N.err
