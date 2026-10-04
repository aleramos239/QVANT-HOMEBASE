#!/bin/bash
# ES Stage B + funded chain (<= 3 workers at a time). Logs in out/.
cd ~/ramos-quant-homebase/research/prop-portfolio/2026-09-29
export PYTHONPATH=~/ramos-quant-homebase PP_PILOT=es PP_APEX_COMPLIANT=1
O=../2026-09-30-es/out
PY=/usr/bin/python3
$PY portfolio_final.py fix3 --workers 3 > $O/portfolio_final_fix3.log 2>&1
$PY portfolio_final.py multi > $O/portfolio_final_multi.log 2>&1
$PY funded_search.py --stage s1 --workers 3 > $O/funded_s1.log 2>&1
$PY funded_search.py --stage pick --k 100 > $O/funded_pick.log 2>&1
$PY funded_search.py --stage s2 --workers 3 > $O/funded_s2.log 2>&1
$PY funded_search.py --stage null --workers 3 > $O/funded_null.log 2>&1
echo CHAIN1_DONE > $O/chain1.done
