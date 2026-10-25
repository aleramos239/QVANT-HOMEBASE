#!/bin/zsh
# run_all.sh run|wf names.txt: every name (one a line) through one.sh, 4 at a time (3 workers each).
HERE=${0:A:h}
grep -v '^[[:space:]]*$' $2 | xargs -P 4 -n 1 $HERE/one.sh $1
