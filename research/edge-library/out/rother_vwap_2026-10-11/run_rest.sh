#!/bin/bash
cd ~/ramos-quant-homebase/research/edge-library
for s in london_a24 day_a24 us_a12 us_a40 london_a12 london_a40 day_a12 day_a40; do
  ../../.venv-research/bin/python bp.py taught run taught/rother_vwap_${s}.json --workers=4 > out/rother_vwap_2026-10-11/${s}.log 2>&1
done
echo done > out/rother_vwap_2026-10-11/ALL_DONE
