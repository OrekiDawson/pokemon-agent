# Repository instructions for Codex
## Project goal
This repository drives Pokémon Red through official pokemon-agent.
## Hard rules
- Only use official endpoints: GET /state, GET /screenshot, POST /action.
- Do not add wrappers, proxy servers, temporary endpoints, GUI automation, xdotool, direct keyboard input, or direct external PyBoy controllers.
- Do not memory patch the game.
- Do not edit savestates to skip progress.
- GB context uses PyBoy inside official pokemon-agent. PyBoy is allowed only as internal backend.
- Preserve local TAC/VBlank fixes; do not revert to upstream if that removes null-window progress.
## Current task
Fix `dialog_clear_gap:pyboy_null_window_oak_cutscene_freeze` from checkpoint `has_pokedex_nballs_working.state`.
## Review guidelines
Flag any code that:
- bypasses official pokemon-agent endpoints,
- changes game memory or savestate contents to skip dialog,
- introduces an external emulator bridge,
- hides runtime/parser/screenshot errors,
- breaks Pokémon Red / DMG / Squirtle verified anchor checks.
