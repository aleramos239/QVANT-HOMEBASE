#!/bin/bash
# 'fast' objective (mean of P1,P2,P3,P5) A-phase only (no >=3 restarts: members collapse to singles), 1 worker while funded s1 runs; then FX/RS walk-forwards after chain1.
cd ~/ramos-quant-homebase/research/prop-portfolio/2026-09-29
export PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es PP_APEX_COMPLIANT=1
O=../2026-09-30-es/out
PY=/usr/bin/python3
$PY portfolio_final.py run --no-wf --obj fast --tag _finalfast --workers 1 > $O/portfolio_finalfast_run.log 2>&1
$PY portfolio_final.py multi --tag _finalfast > $O/portfolio_finalfast_multi.log 2>&1
while [ ! -f $O/chain1.done ]; do sleep 30; done
$PY portfolio_final.py fx --workers 3 > $O/portfolio_final_fx.log 2>&1
$PY portfolio_final.py rs --workers 3 > $O/portfolio_final_rs.log 2>&1
echo CHAIN2_DONE > $O/chain2.done
