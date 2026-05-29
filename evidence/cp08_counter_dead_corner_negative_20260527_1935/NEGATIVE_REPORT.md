# NEGATIVE — cp08_viridian_forest_south_gate_counter_dead_corner

## 三门验证

### official_pokemon_agent_gate
- path: `/home/oreki/pokemon-agent`
- git_head: `a9b5210` (fix/red-oak-dialog-null-window-005034)
- launch_command: `uv run pokemon-agent serve --rom PokemonRed.gb --port 9876 --load-state cp08_route2_to_viridian_forest_gate`
- api_base: `http://192.168.1.135:9876`
- health_status: `{"status":"ok","emulator_ready":true}`
- runtime_backend: PyBoy (official pokemon-agent internal)
- state_parser: RedBlueMemoryReader (pokemon_agent/memory/red.py)
- input_api: POST /action (lower-case)
- status: GATE_PASS

### color_mode_gate
- mode: DMG
- source: API/state (screen_health=ok, LCDC=227, frame=1960)
- status: GATE_PASS

### model_gate
- model_name: deepseek-v4-flash
- source: session config
- status: GATE_PASS

---

## STOP_NO_BUTTONS

### 当前状态
| Field | Value |
|-------|-------|
| map | Viridian Forest South Gate (50) |
| xy | (2,2) |
| facing | down |
| keys | [] |
| menu | (none) |
| dialog | false |
| battle | false |
| party[0] | Squirtle / 杰尼龟 Lv6 |
| hp | 22/22 |
| status | OK |
| screen_health | ok |
| play_time | 0:00:24 |
| frame | 1960 |

### 四方向阻塞确认
| Direction | Tile | Passable |
|-----------|------|----------|
| up | 0x0A | blocked |
| down | 0x15 | blocked |
| left | 0x38 | blocked |
| right | 0x33 | blocked |
| num_warps | — | 0 |

### 阻塞根因
- 位置：Viridian Forest South Gate 柜台后方死角 (2,2)
- 原因：上一轮探索时未先 screenshot 确认可通行格，盲目左右移动后卡入不可恢复位置
- 失败分支：`counter_dead_corner_route_error`
- 违反 RED HERMES：action batch 虽在 2-4 范围内，但未在柜台/门等场景前先 screenshot 看布局

### 可用锚点（只读列出，不得直接加载）
| 状态名 | 路径 | 大小 |
|--------|------|------|
| cp08_route2_to_viridian_forest_gate | ~/.pokemon-agent/saves/ | 167629 |
| cp09_viridian_forest_south_entrance | ~/.pokemon-agent/saves/ | 167629 |
| cp06_viridian_pokecenter_healed | ~/.pokemon-agent/saves/ | 167629 |
| post_cp06_viridian_south_arrival | ~/.pokemon-agent/saves/ | 167629 |

---

### objective
- 进入 Viridian Forest (map_id=51) 以验证野战 parser 可信度

### completion_condition
- map=Viridian Forest, battle=false, dialog=false, screen_health=ok

### actual_result
- 未进入森林，卡在 Viridian Forest South Gate (2,2) 柜台死角

### completed
- no

### if_no
- blocker: `south_gate_counter_dead_corner_stuck`
- action: STOP_NO_BUTTONS — 所有 POST /action、reload、fresh boot、ROM relaunch、PyBoy reset 均禁止

### evidence_dir
`evidence/cp08_counter_dead_corner_negative_20260527_1935/`

### negative_name
`cp08_viridian_forest_south_gate_counter_dead_corner.NEGATIVE`
