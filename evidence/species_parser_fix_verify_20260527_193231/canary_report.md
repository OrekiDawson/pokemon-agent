# 金丝雀验收报告 — canary_no_battle_yet + stuck_in_gate_building

## canary 历程

| 步骤 | 位置 | 动作 | 结果 |
|------|------|------|------|
| 1 | (4,7) | wait_60×3 | 南门内部稳定 |
| 2 | (4,7)→(4,3) | walk_up×4 | 穿过大堂走到柜台前 |
| 3 | (4,3)→(4,1) | walk_up×3+wait_60 | 走到北门下方(4,1) |
| 4 | (4,1)→(4,1) | walk_up×4 | 北门door tile(0x0A)不通 |
| 5 | (4,1)→(4,1) | press_a+wait×3 | A键不触发门 |
| 6 | (4,1)→(6,1) | walk_right×2 | 绕右边找路→死角(6,1)全方向堵 |
| 7 | (6,1)→(4,1) | walk_left×2 | 退回北门 |
| 8 | (4,1)→(4,5) | walk_down×4 | 回到南侧大堂 |
| 9 | (4,5)→(2,5) | walk_left×2 | 绕左 |
| 10 | (2,5)→(2,4) | walk_up×2 | 全部堵住 |
| 11 | (2,4)→(5,5) | walk_down+right×3 | 回右路 |
| 12 | (5,5)→(5,2) | walk_up×3 | 到柜台后(5,2) |
| 13 | (5,2)→(2,2) | walk_left×3 | ALL方向堵住→**卡死** |

## canary 结果

- battle: false (从未触发战斗)
- battle_reached: false
- screen_health: ok (全程)
- parser_trusted: 未验证（未遇到野战）
- player_stuck: true (2,2 全方向 blocked)

## 发现的问题

1. **Viridian Forest 南门建筑内部导航复杂**：柜台+NPC布局，walk_up 的碰撞数据不一致（显示 block 但能走），Warp 未出现在 forest_debug 中（num_warps=0）
2. **北门无法触发出口**：从(4,1)walk_up和press_a均未触发warp到Viridian Forest (map_id=51)，可能需要特定位置或条件
3. **卡住位置(2,2)**：柜台后方死角，无法自救

## 结论

**canary_no_battle_yet** — 未到达森林，未触发野战。Parser fix 可信度功能未能在本canary中实战验证。

## 建议下一步

- 从原锚点(4,7)重新进入，系统性地测绘南门建筑的可行路径
- 或使用cp08_route2_to_viridian_forest_gate.state重新加载（需要Oreki授权）
- 或先解决南门建筑到森林的warp触发问题
