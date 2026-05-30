# 小呦的后端 / pokemon-agent by Xiaoyou

> 小呦帮 Oreki 玩宝可梦红的后端服务。基于 FastAPI + PyBoy，无窗口后台运行。

## 小呦在用这个做什么？

小呦是一个 AI agent，负责在 Pokemon Red 里推进主线。
pokemon-agent 就是小呦的手和眼睛——通过 HTTP API 读取游戏状态、发送按键、执行存档。

```
┌──────────────────────┐
│      Oreki           │  Oreki 下指令
│      小呦             │  小呦做执行
└─────────┬────────────┘
          │ HTTP API
┌─────────▼────────────┐
│   pokemon-agent      │  小呦的后端：
│   ┌────────────────┐ │  - 后台模拟器（PyBoy）
│   │ Game Server    │ │  - 读游戏状态（RAM parser）
│   │ (FastAPI)      │ │  - REST API（state/screenshot/action）
│   ├────────────────┤ │  - 可选仪表盘
│   │ Emulator       │ │
│   │ (PyBoy)        │ │
└───┴────────────────┘ │
```

## 小呦的安全原则

- 不搜索、不下载、不传播任何盗版 ROM
- 所有操作基于真实 state 证据，不凭猜测按键
- 不擅自删除存档或覆盖 checkpoint
- 不把"计划"当"完成"

## 核心 API

小呦通过这些端点和游戏说话：

| 端点 | 方法 | 小呦用来 |
|------|------|---------|
| `/state` | GET | 读当前坐标、队伍、战斗状态 |
| `/screenshot` | GET | 看画面有没有 freeze |
| `/screenshot/raw` | GET | 读 PPU 寄存器（lcdc/stat/ly） |
| `/action` | POST | 发送按键（walk_up/press_a/wait_60） |
| `/save` | POST | 保存 checkpoint |
| `/load` | POST | 加载 checkpoint |

## 技术栈

- **模拟器**: PyBoy（无窗口后台模式）
- **框架**: FastAPI
- **内存读取**: 基于 pret/pokered 反编译的 RAM 地址表
- **游戏类型**: Pokemon Red / Blue（Gen1 GB）

## 小呦怎么用这个服务

### 1. 启动服务

```bash
python -m pokemon_agent.cli serve --rom ./roms/PokemonRed.gb --port 9876 --data-dir ~/.pokemon-agent
```

### 2. 读 state

```bash
curl http://localhost:9876/state | python -m json.tool
```

返回内容：
- `map` / `player.position` / `facing`
- `party[]`（名字、等级、HP、技能）
- `battle`（是否在战斗）
- `dialog`（是否有文本框）
- `keys[]`（当前按住的方向键）

### 3. 发动作

```bash
curl -X POST http://localhost:9876/action \
  -H "Content-Type: application/json" \
  -d '{"actions": ["walk_up", "walk_up", "wait_60"]}'
```

### 4. 保存/加载 checkpoint

```bash
curl -X POST http://localhost:9876/save -d '{"name": "cp10_forest_entry"}'
curl -X POST http://localhost:9876/load -d '{"name": "cp10_forest_entry"}'
```

## 小呦的 checkpoint 命名

小呦的存档点用 `cp<数字>_<描述>` 格式：

```
cp08_route2_to_viridian_forest_gate   — 从 Route 2 进入森林
cp09_viridian_forest_south_entrance    — 森林南入口
cp10_forest_entry_step_17_44           — 森林里走了几步
```

存档在 `~/.pokemon-agent/saves/`（符号链接到项目 evidence/ 目录）。

## 已知问题（Gen1）

### Battle Render Freeze

当战斗画面卡在 intro_or_text 且 `screen_health=blank` 时，parser 所有 trust gate 关闭，无法继续。
此时 `hjoy_input` 经常显示 207（A+B+SELECT+START+UP+DOWN 全按住），但 `keys=[]`。
这是 PyBoy HRAM 闩锁问题，不是小呦代码 bug。
freeze_count >= 2 时触发 hard_stop，必须受控重启到锚点。

### PPU 寄存器

| 地址 | 名称 | 小呦用这个判断 |
|------|------|--------------|
| 0xFF40 | lcdc | LCD 控制器是否启用 |
| 0xFF41 | stat | PPU 模式（0= HBlank, 1= VBlank, 2= OAM, 3= VRAM） |
| 0xFF44 | ly | 当前扫描线（freeze 时经常 ly=0） |
| 0xFF4A | wy | 文本框 Y 坐标 |
| 0xFF4B | wx | 文本框 X 坐标 |

## 架构

```
pokemon_agent/
├── __init__.py          # 版本号
├── cli.py               # 命令行入口（serve/eval）
├── server.py            # FastAPI 游戏服务器
├── emulator.py          # PyBoy 包装器（无窗口后台模式）
├── memory/
│   └── red.py           # Pokemon Red RAM 解析器（基于 pret/pokered）
└── state/
    └── builder.py       # 结构化 state 构造器
```

## 小呦学到的教训

- `hjoy_input=207` 时 PyBoy HRAM 闩锁，release_all_keys 无法清除
- battle=true 时立即停，不能继续走导航
- screenshot 返回 503 时可能是 freeze，不是服务挂了
- numpy.uint8 必须 `int()` 才能 JSON 序列化

---

小呦正在努力学会用这个工具更稳地推进主线。加油！