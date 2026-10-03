#!/usr/bin/env bash
# Writ bootstrap for Mistral Vibe. Creates the mistty Vibe home (default ~/.mistty) with
# Writ's hooks and links the `mistty` launcher. Reuses the Writ daemon the Claude plugin
# already runs. Does not touch ~/.vibe beyond reading .env and config.toml.
#
# Usage:
#   bash scripts/bootstrap-vibe.sh
#   bash scripts/bootstrap-vibe.sh --help   # --home, --source-home, --bin-dir, --no-check
set -euo pipefail

WRIT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHONPATH="$WRIT_DIR${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m writ.harness.vibe_install "$@"
