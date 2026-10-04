#!/bin/zsh
# when the heavy chain reaches its walk-forward stage (started with --top 10 --kc 3), stop it and run the stage with R's settings
cd ~/ramos-quant-homebase/research/prop-portfolio/2026-10-02-intraday
until grep -q "^=== wf" out/heavy.log || ! pgrep -f "rerank.py --stage heavy" >/dev/null; do sleep 3; done
pgrep -f "rerank.py --stage heavy" | while read p; do pkill -P "$p"; kill "$p"; done
sleep 3
rm -f out/wf_intraday_part.jsonl
echo "=== wf (R settings: top 12, kc 5) $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy.log
/usr/bin/python3 rerank.py --stage wf --top 12 --kc 5 --workers 4 >> out/heavy.log 2>&1
echo "=== heavy chain done $(TZ=America/New_York date +%H:%M:%S) ET" >> out/heavy.log
