#!/bin/zsh
# runs every spec one after another on the Mac (never the server); a finished spec leaves done_<name>
cd ~/ramos-quant-homebase/research/edge-library
PY=~/ramos-quant-homebase/.venv-research/bin/python
D=out/eve_ideas_2026-10-29
for f in $D/specs/ctl_c18_all_nights.json $D/specs/i*.json; do
  n=$(basename $f .json)
  [[ -f $D/done_$n ]] && continue
  echo "== $n $(date +%T)"
  $PY bp.py wf run $f --no-worse --workers 12 --wait 7200 --owner-said "test all of A,B,C,D let me know if any show potential; run heatmap on each; also try atr stops" > $D/log_$n.txt 2>&1 && touch $D/done_$n
done
echo ALLDONE $(date +%T)
