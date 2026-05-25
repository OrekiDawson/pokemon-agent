# Repository instructions for Codex

## Project goal

This repository drives Pokémon Red through official pokemon-agent.

## Hard rules

1. Only use official endpoints: GET /state, GET /screenshot, POST /action.
2. Do not add wrappers, proxy servers, temporary endpoints, GUI automation, xdotool, direct keyboard input, or direct external PyBoy controllers.
3. Do not add new endpoints.
4. Do not memory patch the game.
5. Do not edit savestates to skip progress.
6. GB context uses PyBoy inside official pokemon-agent. PyBoy is allowed only as internal backend.
7. Preserve local TAC/VBlank/null-window fixes; do not revert to upstream if that removes null-window progress.
8. Run `scripts/check_red_only_drift_guard.sh` before proposing changes.

## Current task

Fix `dialog_clear_gap:pyboy_null_window_oak_cutscene_freeze` from checkpoint `has_pokedex_nballs_working.state`.

## Review guidelines

Flag any code that:
- bypasses official pokemon-agent endpoints,
- changes game memory or savestate contents to skip dialog,
- introduces an external emulator bridge,
- introduces new endpoint routes,
- hides runtime/parser/screenshot errors,
- breaks Pokémon Red / DMG / Squirtle verified anchor checks.
