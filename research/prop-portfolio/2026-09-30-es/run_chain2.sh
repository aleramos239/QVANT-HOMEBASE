#!/bin/bash
# after chain1: 'fast' objective (P1/P2/P3/P5 mean) portfolios, then portfolio walk-forwards (fixed-set, reselect). <= 3 workers.
cd ~/ramos-quant-homebase/research/prop-portfolio/2026-09-29
export PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es PP_APEX_COMPLIANT=1
O=../2026-09-30-es/out
PY=/usr/bin/python3
while [ ! -f $O/chain1.done ]; do sleep 30; done
$PY portfolio_final.py run --no-wf --obj fast --tag _finalfast --workers 3 > $O/portfolio_finalfast_run.log 2>&1
$PY portfolio_final.py fix3 --obj fast --tag _finalfast --workers 3 > $O/portfolio_finalfast_fix3.log 2>&1
$PY portfolio_final.py multi --tag _finalfast > $O/portfolio_finalfast_multi.log 2>&1
$PY portfolio_final.py fx --workers 3 > $O/portfolio_final_fx.log 2>&1
$PY portfolio_final.py rs --workers 3 > $O/portfolio_final_rs.log 2>&1
echo CHAIN2_DONE > $O/chain2.done
