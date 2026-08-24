# Running on a phone: Termux + proot-distro Debian

llmforge runs on an Android phone. The core has no runtime dependencies, the
tests are offline, and `llmforge doctor` tells you what is wrong — which is
most of what you need on a device you cannot easily attach a debugger to.

`scripts/bootstrap_llmforge_debian.sh` does the whole install. Run it **inside
Debian**, not in Termux itself.

```bash
# Termux — install from F-Droid or GitHub. The Play Store build is deprecated
# and cannot install current packages.
pkg update && pkg install -y proot-distro
proot-distro install debian
proot-distro login debian

# now inside Debian
bash bootstrap_llmforge_debian.sh
```

## Why Debian rather than native Termux

llmforge itself would install on either — the core imports nothing. The
difference is the *optional* Anthropic SDK, which pulls `pydantic-core`, which
is Rust.

| | native Termux | proot-distro Debian |
|---|---|---|
| libc | bionic | glibc |
| manylinux wheels | not compatible | compatible |
| installing a compiled dep | builds from source on the phone | downloads a wheel |
| needs `rust` + `binutils` | yes | no |

That last row is the practical one. A Rust build on a phone is slow, is the
step most likely to fail, and is entirely avoidable.

The tradeoff proot asks for in return is syscall interception, so everything is
somewhat slower and there is no systemd. Neither matters for a library whose
hot path is waiting on an HTTPS response.

## The failure everyone hits first

Debian 12+ marks the system Python **externally-managed** (PEP 668), so:

```
error: externally-managed-environment
```

A virtualenv is the fix, and the bootstrap script makes one. Do not reach for
`--break-system-packages` — it puts pip and apt in conflict over the same
files, and you will meet that again later at a worse moment.

## Termux specifics

```bash
termux-wake-lock                                       # Android kills long runs otherwise
proot-distro login debian --bind /sdcard:/mnt/sdcard   # if you need shared storage
```

No systemd inside proot. Use `tmux` or `nohup` for anything long-running.

## Credentials

The script creates `~/.llmforge.env` at mode 600 and sources it from
`.bashrc`. Put the key there, not in a shell history or a committed file.

```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.llmforge.env
exec bash
llmforge doctor          # credential check should now pass
llmforge doctor --live   # one real call on the cheapest model
```

`doctor` exits 1 when it finds something and 2 when it could not run — a
missing credential is a finding, not a crash, so a fresh box reporting exit 1
is working correctly.

## Running alongside another project

Keep separate virtualenvs. llmforge needs nothing; a project that needs
`cryptography` or `pydantic` should not make its dependency problems into
llmforge's, and sharing one environment guarantees that it does.

## What is not verified

The bootstrap is syntax-checked and shellcheck-clean in CI, and the install
path it uses (venv → editable install → console script → test suite) is
exercised on every run. **It has not been executed on aarch64 hardware.** The
version gates are checks inside the script rather than assumptions, so a
mismatch reports itself instead of failing obscurely — but treat the first run
on a real device as the actual test.
