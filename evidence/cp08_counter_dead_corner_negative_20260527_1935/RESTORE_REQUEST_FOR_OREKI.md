# RESTORE_REQUEST_FOR_OREKI

## current_live_status
- decision: STOP_NO_BUTTONS
- reason: Viridian Forest South Gate (2,2) counter dead corner
- current_state_path: evidence/cp08_counter_dead_corner_negative_20260527_1935/state.json
- current_screenshot_path: evidence/cp08_counter_dead_corner_negative_20260527_1935/screenshot.png
- negative_report_path: evidence/cp08_counter_dead_corner_negative_20260527_1935/NEGATIVE_REPORT.md
- no_buttons_since_stop: yes

## why_live_runtime_cannot_continue
- map: Viridian Forest South Gate
- xy: (2,2)
- four_direction_probe:
  - up: blocked 0x0A
  - down: blocked 0x15
  - left: blocked 0x38
  - right: blocked 0x33
- nearest_warp: warp=0 / not reachable
- conclusion: movement unrecoverable from live runtime without unauthorized reload/reset/patch

## requested_manual_authorization
I request Oreki manual authorization to restore candidate anchor:
cp08_route2_to_viridian_forest_gate
This is NOT self-authorized. No reload will be performed until Oreki explicitly approves.

## anchor_gate_required_after_authorization
After Oreki approval, before any route action:
1. restore candidate anchor cp08_route2_to_viridian_forest_gate
2. GET /state
3. GET /screenshot
4. verify:
   - game is Pokemon Red, not Yellow/Blue/other
   - color mode is DMG
   - keys == []
   - frame increases across two state reads
   - GET /screenshot works and screen_health=ok
   - POST /action schema accepts lower-case payload only, using harmless wait if allowed by restore protocol
   - party[0] == Squirtle / 杰尼龟
   - battle == false
   - dialog == false
   - menu == false
   - map == Viridian Forest South Gate or Route 2 gate approach as anchor manifest says
   - xy/facing match anchor manifest
5. only if all pass: mark anchor usable
6. if any fail: STOP_NO_BUTTONS again

## safe_route_after_authorized_anchor
Goal: enter Viridian Forest from south gate without touching counter dead corner.
Mandatory route style:
- screenshot first
- never walk behind counter
- no exploratory lateral movement near desk/counter
- action batches are 2-4 lower-case actions
- after warp/door: wait_60, wait_60, then GET /state + GET /screenshot
- every batch must verify map/xy/facing plus screenshot
Expected completion:
- map = Viridian Forest
- xy = (17,47) or (18,47)
- battle = false
- dialog = false
- screen_health = ok
