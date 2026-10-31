#!/bin/zsh
# runs every spec one after another; the 5m control pool is built by the first 5m run
cd ~/ramos-quant-homebase/research/edge-library
PY=~/ramos-quant-homebase/.venv-research/bin/python
for f in out/fvg100_2026-10-28/specs/f100_plain.json out/fvg100_2026-10-28/specs/f100_*.json; do
  n=$(basename $f .json)
  [[ $n == f100_t0_odir_15 ]] && continue
  [[ -f out/fvg100_2026-10-28/done_$n ]] && continue
  echo "== $n $(date +%T)"
  $PY bp.py wf run $f --no-worse --workers 12 --wait 7200 --owner-said "run them all, let me know if one shows potential, only use set sl and tp to fit the prop firms, flat by 4pm, aim for minimum trade frequency once per day" > out/fvg100_2026-10-28/log_$n.txt 2>&1 && touch out/fvg100_2026-10-28/done_$n
done
echo ALLDONE $(date +%T)
