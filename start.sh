#!/usr/bin/env bash
# Starts DocuInsights on this machine (macOS, Linux). The first run makes .venv and installs into it.
# Extra arguments go to the server:  ./start.sh --port 8091    ./start.sh --root-path /docuinsights
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if [ ! -f .venv/.installed ] || [ pyproject.toml -nt .venv/.installed ]; then   # first run, or the requirements changed
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e ".[server,pdf]"
  touch .venv/.installed
fi
export DOCUINSIGHTS_DATA_DIR="${DOCUINSIGHTS_DATA_DIR:-$PWD/data}"
exec .venv/bin/python -m docuinsights serve "$@"
