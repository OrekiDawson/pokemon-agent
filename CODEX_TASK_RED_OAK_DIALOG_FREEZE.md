# Task: Fix Pokémon Red PyBoy null-window Oak dialog freeze
## Current verified anchor
Use official pokemon-agent only.
Launch:
.venv/bin/python -m pokemon --load-state has_pokedex_nballs_working
API:
http://127.0.0.1:9876
Allowed endpoints only:
- GET /state
- GET /screenshot
- POST /action
## Verified baseline
- git_head before task: 6e7b7982
- backend: PyBoyEmulator null window
- parser: PokemonRedReader
- ROM: Pokémon Red, DMG mode, header 0x143=0x00
- checkpoint: has_pokedex_nballs_working.state
- map_id=40 Oak's Lab
- position=(5,3), facing=up
- keys=[]
- party[0].raw_species_id=0xB1 = Squirtle / 杰尼龟
- has_pokedex=True
- bag contains 5x Poke Ball and 2x Antidote
- screenshot after tick is non-white 4-gray DMG
## Bug
Oak dialog cannot clear in PyBoy null-window mode.
Observed:
- before: text_box_id=13, dialog_active=true
- first press_a: text_box_id changes 13 -> 1
- further press_a attempts do not change text_box_id
- bounded 12 press_a failed
- hold_b_60, hold_b_120, press_b+press_a variants all failed
- frame advances normally, keys=[]
- battle=false
- party remains Squirtle
- action schema accepts lower-case actions
- screenshot path returns 4-gray image but visual content can be all black/stale
Gap:
dialog_clear_gap:pyboy_null_window_oak_cutscene_freeze
## Important constraints
Do not add wrapper.
Do not add external emulator bridge.
Do not use direct PyBoy controller outside official pokemon-agent.
Do not use GUI / keyboard / xdotool.
Do not memory patch.
Do not edit savestate to skip flags/dialog.
Do not bypass checkpoint by setting game memory.
Only fix official pokemon-agent internals.
## Suspected area
Investigate:
- pokemon_agent/emulator.py
- server.py action execution path
- screenshot provider
- PyBoy.tick(render=True) behavior
- screen.image / screen.ndarray refresh behavior
- VBlank / IF 0xFF0F injection
- LCD/STAT behavior around dialog/cutscene
- load_state restoring timer / interrupt state
- whether screenshot provider reads stale screen buffer
- whether action success hides render/tick failure
Local commits ahead of upstream are necessary:
- TAC timer 0xFF07 init/load_state restore
- VBlank injection 0xFF0F during tick
Do not revert to upstream.
## Reproduction
1. Start server:
.venv/bin/python -m pokemon --load-state has_pokedex_nballs_working
2. Check:
curl http://127.0.0.1:9876/health
curl http://127.0.0.1:9876/state
3. Try:
curl -sS -X POST http://127.0.0.1:9876/action \
-H 'Content-Type: application/json' \
-d '{"actions":["press_a","wait_60"]}'
4. Repeat bounded press_a. Expected dialog clears. Actual: text_box_id stays 1, dialog.active remains true.
## Required fix
Make Oak dialog progress in null-window PyBoy through official pokemon-agent actions.
Acceptance:
- Launch from has_pokedex_nballs_working
- frame grows
- keys=[]
- party[0].raw_species_id remains 0xB1
- repeated bounded press_a clears dialog.active=false
- no memory patch
- no savestate editing
- no external bridge
- screenshot remains readable or any screenshot gap is explicitly explained
- add regression test or diagnostic script if feasible
