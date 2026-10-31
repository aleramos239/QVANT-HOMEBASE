# VWAP hunt 2026-10-20: status

- 23:05 ET: the old-lane run (PREREG.md, 9 taught cells a sheet) PAUSED after 35 of 143 jobs. The owner wants hm40 + the fixed 3:1
  blocks ("Yes: redo the VWAP hunt on hm40 and the fixed 3:1 blocks once feat/hm40-fixed-wf is merged. In-sample table and
  selection first, out-of-sample only for the picked boxes on my word."). The old stores stay on file, unused; no test month of
  them was read.
- The redo: hm40/PREREG_HM40.md (74 specs in hm40/specs/, 51 already pass the branch's spec check). It starts when
  feat/hm40-fixed-wf is merged into main (the owner's other chat merges it; a watcher waits for it).
- Built on the way and committed (33637a38): engine/families/avwap.py (avwap_touch, avwap_flip, orb_vwap_pb; 10 VWAP lines),
  engine/tests/test_avwap.py (30 tests). Vault: 30-Projects/Onyx-Trading/avwap-blocks-2026-10-20.md.
