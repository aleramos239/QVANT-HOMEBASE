#!/bin/zsh
# fix round, part 3: unbiased day-matched control (RR_CTRL=overlap, see rerank.py) for the reported picks, the nested funded picks and the multi-trade walk-forward grids
cd ~/ramos-quant-homebase/research/prop-portfolio/2026-10-02-intraday
echo "=== lift (unbiased control) $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
RR_CTRL=overlap /usr/bin/python3 rerank.py --stage lift --workers 4 >> out/heavy_fix.log 2>&1 || echo "!!! lift_u failed" >> out/heavy_fix.log
echo "=== lift (R's control) $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
/usr/bin/python3 rerank.py --stage lift --workers 4 >> out/heavy_fix.log 2>&1 || echo "!!! lift failed" >> out/heavy_fix.log
echo "=== nwf_ctl (unbiased control) $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
RR_CTRL=overlap /usr/bin/python3 rerank.py --stage nwf_ctl --workers 4 >> out/heavy_fix.log 2>&1 || echo "!!! nwf_ctl_u failed" >> out/heavy_fix.log
echo "=== wf_u (unbiased control, multi-trade own-pool grids) $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
RR_CTRL=overlap /usr/bin/python3 rerank.py --stage wf_u --top 12 --kc 5 --workers 4 >> out/heavy_fix.log 2>&1 || echo "!!! wf_u failed" >> out/heavy_fix.log
echo "=== fix chain 3 done $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy_fix.log
