#!/usr/bin/env bash
# Runs the Ollama copy stored inside this project (.ollama/), with models stored there too.
# Nothing is written to ~/.ollama, so deleting the project folder removes everything.
#
#   scripts/ollama.sh serve          start the server (keep this terminal open)
#   scripts/ollama.sh pull <model>   download a model
#   scripts/ollama.sh list           show downloaded models

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLLAMA_DIR="$PROJECT_DIR/.ollama"

if [[ ! -x "$OLLAMA_DIR/program/bin/ollama" ]]; then
  echo "Ollama is not installed in $OLLAMA_DIR/program. See docs/setup.md (Ollama section)." >&2
  exit 1
fi

export OLLAMA_MODELS="$OLLAMA_DIR/models"
# Ollama keeps its key files in $HOME/.ollama, so HOME points inside the project as well.
export HOME="$OLLAMA_DIR/home"
export OLLAMA_HOST="${OLLAMA_HOST:-127.0.0.1:11434}"

exec "$OLLAMA_DIR/program/bin/ollama" "$@"
