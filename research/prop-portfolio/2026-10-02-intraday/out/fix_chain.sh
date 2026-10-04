#!/bin/zsh
# fix round heavy chain (<= 4 workers; every task checks the compute windows itself)
cd ~/ramos-quant-homebase/research/prop-portfolio/2026-10-02-intraday
for st in eval_p2x funded_nwf funded_pick2 funded_s2b; do
  echo "=== $st $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
  /usr/bin/python3 rerank.py --stage $st --workers 3 >> out/heavy_fix.log 2>&1 || echo "!!! $st failed" >> out/heavy_fix.log
done
echo "=== wf_p2 $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
/usr/bin/python3 rerank.py --stage wf_p2 --kc 5 --workers 3 >> out/heavy_fix.log 2>&1 || echo "!!! wf_p2 failed" >> out/heavy_fix.log
echo "=== fix chain done $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
