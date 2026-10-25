#!/bin/zsh
# one.sh run|wf <name>: one taught build run or walk-forward (see run_all.sh). Nothing new starts in desk hours (weekday 07:45-16:15 ET).
MODE=$1; n=$2
HERE=${0:A:h}; EL=${HERE:h:h}; PY=${EL:h:h}/.venv-research/bin/python
hm=$(TZ=America/New_York date +%H%M); wd=$(TZ=America/New_York date +%u)
if [[ $wd -le 5 && $hm -ge 0745 && $hm -lt 1615 ]]; then echo "SKIP desk hours $n"; exit 0; fi
mkdir -p $HERE/logs; cd $EL
if [[ $MODE == run ]]; then $PY bp.py taught run taught/$n.json --workers=3 > $HERE/logs/run_$n.log 2>&1
else $PY bp.py taught wf $n --workers=3 > $HERE/logs/wf_$n.log 2>&1; fi
echo "done $MODE $n exit=$? $(TZ=America/New_York date +%H:%M)"
