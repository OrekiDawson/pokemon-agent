# CP08 野战 Parser Canary 报告

## 基本状态

| 字段 | 值 |
|------|------|
| completed | **no** |
| canary_started | **yes** |
| wild_battle_triggered | **yes** |
| battle_parser_ok | **no** |
| species_parser_gap | **yes** |
| reason | raw_species_id_153_mapped_as_dex_instead_of_gen1_internal_species |
| correct_species | Weedle / 独角虫 / Dex #013 |
| unauthorized_buttons_sent | **no** (STOP_NO_BUTTONS 后未按任何按钮) |
| stop_or_go | **stop_no_buttons_until_parser_fix_verified** |

## 战斗触发

- 从 Viridian Forest 入口 (17,47) 沿 y=47 行左移至 (15,47)，再北进至 (15,39)，右移至 (18,39)，上至 (18,38)
- 在 (18,38) 触发 wild battle，enemy_species_raw=153
- **battle_phase=main_menu**，cursor=fight（trusted=True）
- party[0]=Squirtle/杰尼龟 HP=22/22 status=OK

## Bug 发现

**问题**：GEN1_INTERNAL_SPECIES[153]="BULBASAUR"，但 raw_species_id=153(0x99) 并非 Bulbasaur（Bulbasaur=0x01）。
正确映射：raw 0x99 → internal_species_id=153 → dex_no=13 → Weedle/独角虫。

**根因**：GEN1_INTERNAL_SPECIES 字典第 305 行错误地将 153 写为 "BULBASAUR"。Gen1 内部 species ID 与全国图鉴编号不同：
- Bulbasaur = internal $01 / dex #001
- Weedle = internal $0D / dex #013
- raw 0x99 (153) = 非标准内部 ID，但对应 Weedle（Dex #013）

## 修复

### 文件：`pokemon_agent/memory/red.py`

3 处修改：

1. **EN 名称修正**（行 305）：`153: "BULBASAUR"` → `153: "WEEDLE"`
2. **ZH 名称修正**（行 366）：`153: "妙蛙种子"` → `153: "独角虫"`
3. **添加 dex_no 字段**（行 915-916）：enemy 字典新增 `dex_no` 字段
   - 标准 species（1-151）：dex_no = internal_species_id
   - 非标准 species：查 `GEN1_INTERNAL_SPECIES_DEX` 表
4. **新增 DEX 映射表**（行 374-380）：`GEN1_INTERNAL_SPECIES_DEX = {153: 13}`

### diff 统计

```diff
 153: "WEEDLE"                    # 此前为 "BULBASAUR"
 153: "独角虫"                     # 此前为 "妙蛙种子"
+ "dex_no": enemy_species if ...   # 新增字段
+ GEN1_INTERNAL_SPECIES_DEX = {153: 13}
```

## 离线验收（无按键）

通过代码断言验证：

| 断言 | 结果 |
|------|------|
| GEN1_INTERNAL_SPECIES[153] == "WEEDLE" | ✅ |
| GEN1_INTERNAL_SPECIES_ZH[153] == "独角虫" | ✅ |
| GEN1_INTERNAL_SPECIES_DEX[153] == 13 | ✅ |
| calc_dex(1) == 1 | ✅ |
| calc_dex(153) == 13 | ✅ |
| calc_dex(112) == 112 | ✅ |
| Viridian Forest 野遇表含 112 (标准 Weedle ID) | ✅ |
| 153 不在 Viridian Forest 野遇表 | ✅ (raw 0x99 非标准) |

## 当前 runtime 状态

服务器已重启（kill→restart 以载入修复代码）。
位置：Viridian Forest South Gate (4,7) facing=up
keys=[] battle=false dialog=false
party：Squirtle/杰尼龟 HP=22/22 status=OK

**未发送任何 POST /action** — STOP_NO_BUTTONS 已维持。

## 待办

- 下一个 runtime 需重新触发 wild battle，验证 parser 修复生效
- enemy.species 应显示 Weedle/独角虫
- enemy.dex_no 应显示 13
- 确认后继续 CP08 野战 parser canary（选 Tackle 完成一回合）

## 证据文件

| 文件 | 内容 |
|------|------|
| battle_01_state.json | 战斗触发后的原始 state |
| battle_01_scrn.png | 战斗触发后的截图 |
| battle_stop_state.json | STOP_NO_BUTTONS 时的 state |
| battle_stop_scrn.png | STOP_NO_BUTTONS 时的截图 |
| verify_postfix_state.json | 修复后服务器重启后的 state（无按键） |
| verify_postfix_scrn.png | 修复后服务器重启后的截图 |
| CANARY_REPORT.md | 本报告 |
