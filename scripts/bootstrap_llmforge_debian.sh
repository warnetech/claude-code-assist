#!/usr/bin/env bash
# Bootstrap llmforge inside proot-distro Debian on Termux (arm64 / Galaxy S23).
#
# RUN THIS INSIDE DEBIAN, not in Termux itself:
#     proot-distro login debian
#     bash bootstrap_llmforge_debian.sh
#
# Why Debian and not native Termux: llmforge itself has zero runtime
# dependencies and would run fine either way, but the optional `anthropic` SDK
# pulls pydantic-core, which is Rust. Debian here is ordinary glibc aarch64, so
# pip finds a prebuilt manylinux wheel. Native Termux is bionic and has no
# manylinux compatibility, which is why your warnetech bootstrap has to install
# `rust` and `binutils` and build `cryptography` from source. This avoids that
# entirely.
set -euo pipefail

REPO_URL="https://github.com/warnetech/claude-code-assist.git"
REPO_DIR="${LLMFORGE_DIR:-$HOME/claude-code-assist}"
BRANCH="${LLMFORGE_BRANCH:-main}"
VENV="$HOME/.venvs/llmforge"

say() { printf '\n\033[1m[%s]\033[0m %s\n' "$1" "$2"; }
die() { printf '\n\033[31mFAILED:\033[0m %s\n' "$1" >&2; exit 1; }

# -- 0. confirm we are actually inside the Debian guest -----------------------
[ -f /etc/debian_version ] || die "not inside Debian. Run: proot-distro login debian"
say 0 "Debian $(cat /etc/debian_version), $(uname -m)"

# -- 1. base packages ---------------------------------------------------------
say 1 "Installing base packages"
apt-get update -qq
apt-get install -y -qq git curl ca-certificates python3 python3-venv python3-pip

# -- 2. version gates ---------------------------------------------------------
# llmforge needs Python >= 3.10. Bookworm ships 3.11, Trixie 3.13 -- both fine.
say 2 "Checking Python"
python3 - <<'PY' || die "Python 3.10+ required"
import sys
print(f"    python {sys.version.split()[0]}")
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY

# -- 3. clone -----------------------------------------------------------------
say 3 "Fetching the repository"
if [ ! -d "$REPO_DIR/.git" ]; then
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
else
    git -C "$REPO_DIR" fetch --depth 1 origin "$BRANCH"
    git -C "$REPO_DIR" checkout "$BRANCH"
    git -C "$REPO_DIR" reset --hard "origin/$BRANCH"
fi

# -- 4. virtualenv ------------------------------------------------------------
# Debian 12+ marks the system Python externally-managed (PEP 668), so a plain
# `pip install` into it aborts. A venv is the correct fix; never reach for
# --break-system-packages here.
say 4 "Creating the virtualenv"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip

say 5 "Installing llmforge (with the Anthropic SDK)"
# Drop [anthropic] for a fully offline install -- the core needs no deps at all.
"$VENV/bin/pip" install --quiet -e "$REPO_DIR/packages/python[anthropic,dev]"

# -- 6. verify ----------------------------------------------------------------
say 6 "Running the test suite"
( cd "$REPO_DIR/packages/python" && "$VENV/bin/python" -m pytest tests -q ) \
    || die "tests failed -- do not trust this install"

say 7 "Self-test"
# Exits 1 when no credential is configured. That is a finding, not a crash,
# so it is expected on a fresh box and must not abort the bootstrap.
"$VENV/bin/llmforge" doctor || true

# -- 8. shell wiring ----------------------------------------------------------
say 8 "Wiring up the shell"
LINE="export PATH=\"$VENV/bin:\$PATH\""
grep -qxF "$LINE" "$HOME/.bashrc" 2>/dev/null || echo "$LINE" >> "$HOME/.bashrc"

CREDS="$HOME/.llmforge.env"
if [ ! -f "$CREDS" ]; then
    cat > "$CREDS" <<'ENVFILE'
# Read by the line appended to ~/.bashrc. Keep this file 0600.
# export ANTHROPIC_API_KEY=sk-ant-...
ENVFILE
    chmod 600 "$CREDS"
fi
SRC="[ -f \"$CREDS\" ] && . \"$CREDS\""
grep -qxF "$SRC" "$HOME/.bashrc" 2>/dev/null || echo "$SRC" >> "$HOME/.bashrc"

cat <<DONE

  Done.

  Next:
    1. Put your key in $CREDS  (chmod 600, already set)
    2. exec bash                          # pick up PATH + the env file
    3. llmforge doctor                    # should now pass the credential check
    4. llmforge doctor --live             # one real API call, fractions of a cent

  The TypeScript package needs Node >= 20. Debian 12 ships 18, so if you want
  it:  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs

DONE
