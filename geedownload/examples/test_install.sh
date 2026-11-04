#!/usr/bin/env bash
# Install geedownload from GitHub into a throw-away virtual environment and test it.
# Usage:  bash test_install.sh            (everything is deleted at the end)
set -euo pipefail
REPO="git+https://github.com/yamenetoo/RremoteSensing.git#subdirectory=geedownload"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
python3 -m venv "$TMP/venv"
"$TMP/venv/bin/pip" install -q --upgrade pip
"$TMP/venv/bin/pip" install -q "geedownload[all] @ $REPO"
cp "$(dirname "$0")/quickstart_check.py" "$TMP/"
( cd "$TMP" && "$TMP/venv/bin/python" quickstart_check.py )
"$TMP/venv/bin/geedownload" about | head -3
echo "OK - temporary environment removed"
