# CP08 — Parser Fix 验收报告

## 完成状态

| 字段 | 值 |
|------|------|
| completed | **yes** |
| raw_species_id | **153** |
| internal_species_id | **153** |
| dex_no | **13** |
| name_en | **WEEDLE** |
| name_zh | **独角虫** |
| parser_fix_verified | **yes** |
| battle_parser_ok | **yes** |
| move_list_trusted | **yes** |
| pp_trusted | **yes** |
| cursor_trusted | **yes** |
| unauthorized_buttons_sent | **no** |
| evidence_dir | evidence/cp08_verify_parser_fix_153_20260527_2150 |
| state_sha256 | e79ae071a5d02da5b5dd98d6b617ab2e0c2707960c832dfd08b88c10174d3cf3 |
| screenshot_sha256 | b6caaf593bb83b5fec582b1190c415c3f3bbfdbb79cc141c6840cb953d7ee449 |
| stop_or_go | **go** — parser 修复已验证，CP08 主线可恢复 |

## 经过

1. **三验通过** → 初始验收通过 (South Gate xy=4,7)
2. **导航进入森林** 按源码门格路线：
   - (4,7)→R→(5,7)→U×6→(5,1)→warp→(17,47)
   - (17,47)→U×2→(17,45)→U×2→(17,43)→R→(18,43)→R→(20,43)→R→(21,43)→U×2→(21,41)→L×3→(18,41)→U×3→(18,38)→L×2→(16,38)→L→(15,38)→D×2→(15,40)→L×2→(13,40)
3. **战斗触发** 在 (12,40) — wild battle
4. **Parser 验证结果**：
   - `enemy_species_raw=153` ✅ 原始字节
   - `enemy.internal_species_id=153` ✅
   - `enemy.dex_no=13` ✅ 新字段
   - `enemy.species=WEEDLE` ✅ 修正后英文名
   - `enemy.species_zh=独角虫` ✅ 修正后中文名
   - `enemy_hp_trusted=True` ✅
   - `battle_cursor=fight (trusted=True)` ✅
   - `enemy.moves=['Tackle', 'Growl']` ✅
5. **战斗一回合**：Tackle PP 35→34 ✅，敌方 HP 0/20
6. **未按任何未授权按钮** — 所有 action 均通过 POST /action ✅

## 修正总结

只接受 153→Weedle/独角虫/Dex#013 局部映射：
- `GEN1_INTERNAL_SPECIES[153] = "WEEDLE"`
- `GEN1_INTERNAL_SPECIES_ZH[153] = "独角虫"`
- `GEN1_INTERNAL_SPECIES_DEX = {153: 13}`（新表，仅非标准 ID 覆写）
- `enemy.dex_no` 字段新增（enemy 字典）

**不假定 internal_id==dex_no** — 标准 species 也需后续补完整映射。

## 证据文件清单

| 文件 | 内容 |
|------|------|
| init_state.json / init_scrn.png | 初始状态（South Gate 4,7） |
| batch1~8_state.json | 逐批移动状态 |
| grass_step*.json | 草丛搜索逐步记录 |
| grass_try*.json | 草丛循环记录 |
| grass_loop_wide_state.json | 宽度优先寻找草丛 |
| battle_verify_state.json | 战斗状态（parser 验证） |
| battle_verify_scrn.png | 战斗截图 |
| battle_round1_state.json | 一回合后状态 |
| VERIFY_REPORT.md | 本报告 |
