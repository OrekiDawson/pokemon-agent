# Species Parser Fix — 验收报告

## 三门验证

### official_pokemon_agent_gate
- path: `/home/oreki/pokemon-agent`
- git_head: `a9b5210` (fix/red-oak-dialog-null-window-005034)
- launch_command: (running since previous session)
- api_base: `http://192.168.1.135:9876`
- health_status: `{"status":"ok","emulator_ready":true}`
- runtime_backend: PyBoy (official pokemon-agent)
- state_parser: RedBlueMemoryReader (已更新 species 可信度逻辑)
- input_api: POST /action (lower-case actions)
- status: ✅ PASS

### color_mode_gate
- mode: DMG (Game Boy)
- source: ROM = PokemonRed.gb, screen_health=ok, PPU LCDC=227
- status: ✅ PASS

### model_gate
- model_name: deepseek-v4-flash (Kimi/Moonshot/MiniMax not used)
- source: session config
- status: ✅ PASS

---

## species_parser_fix_verify

### files_changed
| File | Change |
|------|--------|
| `pokemon_agent/dashboard/static/app.js` | +3/-1 (moves display bugfix, pre-existing) |
| `pokemon_agent/memory/red.py` | +165/-14 (新增 species 表+可信度逻辑+中文名) |

### diff_stat
- total: 2 files, +165/-14 insertions/deletions

### internal_species_source
`pret/pokered/constants/pokemon_constants.asm`
→ 已解析全部 155 条 `const` 条目映射到 `GEN1_INTERNAL_SPECIES`

### raw_153_mapping
153 (0x99) → `BULBASAUR` (妙蛙种子) ✅

### viridian_forest_expected_internal_ids
`{112: WEEDLE, 113: KAKUNA, 123: CATERPIE, 124: METAPOD, 84: PIKACHU}` ✅

### trusted_rule (三条件与门)
```python
species_trusted = (
    battle_phase == "main_menu"       # 条件1: 战斗已进入主菜单
    and species_in_table               # 条件2: 物种在 GEN1_INTERNAL_SPECIES 内
    and species_in_encounter_table     # 条件3: 野生战匹配当前地图野遇表
)
```

| 场景 | 条件1 (phase) | 条件2 (table) | 条件3 (encounter) | trusted |
|------|:---:|:---:|:---:|:---:|
| 森林·153(BULBASAUR) | ✅ main_menu | ✅ 合法 | ❌ 不在野遇表 | **false** ❌ |
| 森林·112(WEEDLE) | ✅ main_menu | ✅ | ✅ 在野遇表 | **true** ✅ |
| 训练家·153(BULBASAUR) | ✅ main_menu | ✅ | ✅ 跳过野遇检查 | **true** ✅ |
| 未知地图·36(PIDGEY) | ✅ main_menu | ✅ | ❌ 未知→保守 | **false** ❌ |

### wild_known_map_requires_encounter_match
**yes** — 已知地图的野生战必须匹配野遇表。

### trainer_battle_skips_encounter_table
**yes** — 训练家对战跳过野遇表检查（`battle_type != 1` → 默认 trusted）。

### unknown_map_policy
**false (conservative)** — 未录入的地图，野生战 `species_in_encounter_table = False`，使 `trusted=false`。

---

## current_anchor_state

| Field | Value |
|-------|-------|
| map_id | null (Viridian Forest South Gate, map=?) |
| xy | (4,7) |
| facing | up |
| party[0] species | Squirtle / 杰尼龟 |
| hp | 22/22 |
| status | OK |
| keys | [] |
| dialog | false |
| battle | false |
| screen_health | ok |
| species_zh | 杰尼龟 ✅ |

---

## stop_or_go
**GO** → 受控 canary（进入森林短批，遇到战斗立即停）

## 代码验收结论
所有 parser 改动已安装且生效：
- `GEN1_INTERNAL_SPECIES` 155条（pokered 源）✅
- `GEN1_INTERNAL_SPECIES_ZH` 151条（52poke 源）✅
- `MAP_WILD_ENCOUNTERS` 当前含 51(Viridian Forest) 和 12(Route 1) ✅
- `read_battle()` 三条件可信度门已生效 ✅
- `read_party_member()` 已有 `species_zh` 字段 ✅
- state JSON 实时返回 `species_zh=杰尼龟` ✅
- 映射正确：153=BULBASAUR，不在森林野遇表 ✅
