#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

REPO_URL="https://github.com/tewartech-node/claude-command-cli.git"
REPO_DIR="$HOME/claude-command-cli"
BRANCH="claude/termux-cli-cloudflare-nemotron-pve6ca"
RUNTIME="$HOME/.warnetech"

echo "[1] Updating Termux packages..."
pkg update -y
pkg upgrade -y

echo "[2] Installing core dependencies..."
# rust + binutils are required to build the `cryptography` wheel on Termux;
# without them pip falls back to a source build that fails.
pkg install -y python nodejs git openssl rust binutils

echo "[3] Creating Warnetech operator directories..."
mkdir -p "$RUNTIME/logs" "$RUNTIME/backups" "$RUNTIME/tmp"

STATE="$RUNTIME/state.json"
if [ ! -f "$STATE" ]; then
    echo '{"last_backup": null, "last_recall": null, "operator_events": []}' > "$STATE"
fi

echo "[4] Cloning Warnetech repo if missing..."
if [ ! -d "$REPO_DIR" ]; then
    git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"

echo "[5] Installing Python dependencies..."
# NOT stdlib-only: warnetech_envelope requires `cryptography` for AES-256-GCM.
pip install --upgrade pip
export CARGO_BUILD_TARGET="$(rustc -vV | sed -n 's/host: //p')"
pip install -e ".[dev]"

echo "[6] Installing Node dependencies..."
npm install --silent

echo "[7] Running Python + JS tests..."
PY_OK=1; JS_OK=1
python -m pytest -q || PY_OK=0
npm test || JS_OK=0

echo "[8] Verifying the encryption path..."
python - <<'PYCHECK' || echo "    WARNING: envelope unavailable — check the cryptography install"
from warnetech_envelope import decrypt_data, encrypt_data
assert decrypt_data(encrypt_data("bootstrap", "k"), "k") == "bootstrap"
print("    envelope round-trip OK")
PYCHECK

echo "[9] Bootstrap complete."
[ "$PY_OK" = 1 ] || echo "    Python tests FAILED"
[ "$JS_OK" = 1 ] || echo "    JS tests FAILED"
[ "$PY_OK" = 1 ] && [ "$JS_OK" = 1 ] && echo "    All tests passed."
