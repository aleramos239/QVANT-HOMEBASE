#!/bin/zsh
# fix round heavy chain, part 2: takes over from fix_chain.sh once eval_p2x is done, with 4 workers (the light stages run after it)
cd ~/ramos-quant-homebase/research/prop-portfolio/2026-10-02-intraday
until grep -q "^=== funded_nwf" out/heavy_fix.log; do sleep 5; done
pkill -f "out/fix_chain.sh"
pgrep -f "rerank.py --stage funded_nwf" | while read p; do pkill -P "$p"; kill "$p"; done
sleep 3
echo "--- chain part 2: 4 workers $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
for st in funded_nwf funded_pick2 funded_s2b; do
  echo "=== $st $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
  /usr/bin/python3 rerank.py --stage $st --workers 4 >> out/heavy_fix.log 2>&1 || echo "!!! $st failed" >> out/heavy_fix.log
done
echo "=== fix chain done $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
