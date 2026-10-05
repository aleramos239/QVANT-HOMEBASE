#!/bin/sh
# ADMISSION v2: stress on 2024 -> test (6) -> BUILD stress of the survivors -> final verdict -> placebo (2024, stress)
PY="/Users/ramoscapital/ONYX TRADING/.venv/bin/python"
cd /Users/ramoscapital/ramos-quant-homebase/research/edge-library || exit 1
"$PY" out/v2/run_v2.py run out/v2/jobs_stress_pick.json > out/v2/run_stress_pick.log 2>&1 || exit 2
"$PY" out/v2/judge_pick.py stress > out/v2/judge_stress.log 2>&1 || exit 3
"$PY" out/v2/run_v2.py run out/v2/jobs_stress_build.json > out/v2/run_stress_build.log 2>&1 || exit 4
"$PY" out/v2/judge_pick.py final > out/v2/judge_final.log 2>&1 || exit 5
"$PY" out/v2/run_v2.py run out/v2/jobs_placebo_pick.json > out/v2/run_placebo_pick.log 2>&1 || exit 6
"$PY" out/v2/placebo.py pick > out/v2/placebo_pick.log 2>&1 || exit 7
"$PY" out/v2/run_v2.py run out/v2/jobs_placebo_stress.json > out/v2/run_placebo_stress.log 2>&1 || exit 8
"$PY" out/v2/placebo.py stress > out/v2/placebo_stress.log 2>&1 || exit 9
echo CHAIN DONE
