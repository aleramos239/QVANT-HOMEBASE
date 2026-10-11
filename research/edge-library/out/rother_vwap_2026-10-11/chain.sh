#!/bin/bash
# usage: chain.sh <tag> <sheet>...
cd ~/ramos-quant-homebase/research/edge-library
tag=$1; shift
for s in "$@"; do
  ../../.venv-research/bin/python bp.py taught run taught/rother_vwap_${s}.json --workers=4 > out/rother_vwap_2026-10-11/${s}.log 2>&1
done
echo done > out/rother_vwap_2026-10-11/CHAIN_${tag}_DONE
