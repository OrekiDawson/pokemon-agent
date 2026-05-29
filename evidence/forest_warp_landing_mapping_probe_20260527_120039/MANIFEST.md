# evidence: forest_warp_landing_mapping_gap
ts: 
mode: OBSERVE_ONLY (stop_no_buttons)

## Files
- verdict_gap_report.txt — root cause analysis
- state_dump.json — full state snapshot
- screenshot.png — visual snapshot
- logs/ — source probes and grep outputs
  - warp_map_constants.txt
  - warp_engine.txt
  - reader_coords.txt
  - south_gate_data.txt
  - source_warp_probe.txt

## Root Cause
wTilesetBlocksPtr (0xD529) stale after savestate. _decompose_tile returns
wrong tile IDs for block 0x58 (should be 0x20, got 0x0D/0x0A/0x99).
Fix: use ROM tileset table lookup instead of WRAM pointer.

## Settlement: warp landing coordinates CORRECT
Runtime (x=17, y=47) matches source warp_event (17,47) for Forest entry #4.
Tilesets table at ROM 0xC7BE confirmed correct.
Forest_Block at flat ROM 0x6A9FF, Forest_Coll at 0x1765 ✓

## Exit: stop_no_buttons
No canary, no actions.
