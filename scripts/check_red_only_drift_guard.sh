#!/usr/bin/env bash
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
EVD="$HOME/red_only_drift_guard_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$EVD"
git status --short | tee "$EVD/git_status_short.txt"
git diff --stat | tee "$EVD/git_diff_stat.txt"
git diff > "$EVD/git_diff.patch" || true
# Avoid self-matching this script.
A='Yell'; B='ow'
C='Pika'; D='chu'
E='safe'; F='tap'
G='safe'; H='step'
I='xiaoyou_'; J='pika'
K='/safe-'; L='tap'
M='/safe-'; N='step'
# Active-code scan: only block dangerous paths/endpoints, not legitimate Gen I species names.
ACTIVE_FORBIDDEN="${E}_${F}|${E}-${F}|${E}${F}|${G}_${H}|${G}-${H}|${G}${H}|${I}${J}${D}|${K}${L}|${M}${N}"
# Diff scan: stricter; any newly-added non-Red/safe/Pikachu/Yellow drift fails.
DIFF_FORBIDDEN="${A}${B}|${C}${D}|${E}_${F}|${E}-${F}|${E}${F}|${G}_${H}|${G}-${H}|${G}${H}|${I}${J}${D}|${K}${L}|${M}${N}"
echo "[1] scan active code for dangerous endpoint/project drift"
grep -RInE "$ACTIVE_FORBIDDEN" pokemon pokemon_agent . \
--exclude-dir=.git \
--exclude-dir=evidence \
--exclude-dir=scripts \
--exclude='README.md' \
--exclude='*.pyc' \
--exclude='*.png' \
--exclude='*.state' \
--exclude='*.sav' \
--exclude='*.patch' \
| tee "$EVD/forbidden_active_hits.txt" || true
echo "[2] scan diff for any newly-added drift"
grep -nE "$DIFF_FORBIDDEN" "$EVD/git_diff.patch" \
| tee "$EVD/forbidden_diff_hits.txt" || true
echo "[3] endpoint change check in server.py"
git diff -- pokemon_agent/server.py \
| grep -nE '^\+.*(@.*route|GET|POST|endpoint|/)' \
| tee "$EVD/server_endpoint_diff_hits.txt" || true
if [ -s "$EVD/forbidden_active_hits.txt" ] || [ -s "$EVD/forbidden_diff_hits.txt" ] || [ -s "$EVD/server_endpoint_diff_hits.txt" ]; then
echo "RED_ONLY_DRIFT_GUARD_FAIL"
echo "evidence_dir=$EVD"
exit 2
fi
echo "RED_ONLY_DRIFT_GUARD_PASS"
echo "evidence_dir=$EVD"
