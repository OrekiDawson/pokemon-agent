# Task: Fix Pokémon Red PyBoy null-window Oak dialog freeze

## Current verified anchor

Launch only through official pokemon-agent:
```bash
.venv/bin/python -m pokemon --load-state has_pokedex_nballs_working
```

API base:
```
http://127.0.0.1:9876
```

Allowed endpoints only:
- GET /state
- GET /screenshot
- POST /action

### Verified baseline

- backend: PyBoyEmulator null window
- parser: PokemonRedReader
- ROM: Pokémon Red, DMG mode, ROM header 0x143=0x00
- checkpoint: `has_pokedex_nballs_working.state`
- map_id=40 Oak's Lab
- position=(5,3), facing=up
- keys=[]
- party[0].raw_species_id=0xB1 = Squirtle / 杰尼龟
- has_pokedex=True
- bag contains 5x Poke Ball and 2x Antidote
- frame grows under wait_N
- screenshot after tick is DMG 4-gray, not all-white

## Bug

Oak dialog cannot clear in PyBoy null-window mode.

Observed sequence:
- before: text_box_id=13, dialog.active=true
- first press_a: text_box_id changes 13 -> 1
- further press_a attempts do not change text_box_id
- bounded 12 press_a failed
- hold_b_60, hold_b_120, press_b+press_a variants all failed
- frame advances normally
- keys=[]
- battle=false
- party remains Squirtle
- action schema accepts lower-case actions
- screenshot can become black/stale while frame advances

### Gap

```
dialog_clear_gap:pyboy_null_window_oak_cutscene_freeze
```

## Important constraints

- Do not add wrappers.
- Do not add external emulator bridges.
- Do not add endpoints.
- Do not use direct PyBoy controller outside official pokemon-agent.
- Do not use GUI / keyboard / xdotool.
- Do not memory patch.
- Do not edit savestate to skip flags/dialog.
- Do not bypass checkpoint by setting game memory.
- Only fix official pokemon-agent internals.

### Preserve local fixes

Local commits ahead of upstream are necessary. Do not revert them.

Known important local behavior:
- TAC timer 0xFF07 init/load_state restore
- VBlank IF 0xFF0F injection during tick
- Red PPU/screen refresh work in `pokemon_agent/emulator.py`

Upstream parity is not a fix; upstream lacks needed null-window fixes.

## Suspected area

Investigate:
- `pokemon_agent/emulator.py`
- `pokemon_agent/server.py` action execution path, without adding endpoints
- screenshot provider
- PyBoy.tick(render=True) behavior
- screen.image / screen.ndarray refresh behavior
- VBlank / IF 0xFF0F injection
- LCD/STAT behavior around dialog/cutscene
- load_state restoring timer / interrupt state
- whether screenshot provider reads stale screen buffer
- whether action success hides render/tick failure

## Reproduction

1. Start server:
```bash
.venv/bin/python -m pokemon --load-state has_pokedex_nballs_working
```

2. Check:
```bash
curl http://127.0.0.1:9876/health
curl http://127.0.0.1:9876/state
```

3. Try one dialog advance:
```bash
curl -sS -X POST http://127.0.0.1:9876/action \
  -H 'Content-Type: application/json' \
  -d '{"actions":["press_a","wait_60"]}'
```

4. Repeat bounded press_a.

Expected: Oak dialog clears, dialog.active=false.
Actual: text_box_id stays 1, dialog.active=true.

## Acceptance

From `--load-state has_pokedex_nballs_working`:
- health ok
- frame grows
- keys=[]
- party[0].raw_species_id remains 0xB1
- bounded press_a through POST /action clears Oak dialog to dialog.active=false
- no memory patch
- no savestate editing
- no external bridge
- no new endpoint
- screenshot/state evidence remains available
- add regression test or diagnostic script if feasible
