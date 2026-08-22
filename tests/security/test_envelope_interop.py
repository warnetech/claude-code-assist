"""Cross-language checks: the Python envelope must be byte-compatible with the
JavaScript implementations.

Finding 4 in this repo was two implementations of one wire contract that were
never tested against each other and were silently broken for the project's
entire life. These tests exist so that cannot recur across the Python/JS
boundary.
"""

import json
import shutil
import subprocess

import pytest

from warnetech_envelope import decrypt_data, derive_key, encrypt_data, generate_hmac_signature

API_KEY = "dev-key"
MESSAGE = '{"command":"ping"}'

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def _node(expr: str) -> str:
    """Evaluate a JS expression against the legacy CLI crypto module."""
    script = f"import('./warnetech_cli_legacy/crypto.js').then(m=>{{{expr}}})"
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        pytest.fail(f"node failed: {result.stderr.strip()}")
    return result.stdout.strip()


def test_derived_keys_are_identical():
    js_key = _node("console.log(m.deriveKey('dev-key').toString('hex'))")
    assert derive_key(API_KEY).hex() == js_key


def test_python_encrypt_javascript_decrypt():
    packet = encrypt_data(MESSAGE, API_KEY)
    assert _node(f"console.log(m.decryptData('{packet}','dev-key'))") == MESSAGE


def test_javascript_encrypt_python_decrypt():
    packet = _node(
        "console.log(m.encryptData(JSON.stringify({command:'ping'}),'dev-key'))"
    )
    assert decrypt_data(packet, API_KEY) == MESSAGE


def test_hmac_signatures_agree():
    packet = encrypt_data(MESSAGE, API_KEY)
    js_sig = _node(
        f"console.log(m.generateHmacSignature({{encrypted_data:'{packet}'}},'dev-key'))"
    )
    assert generate_hmac_signature({"encrypted_data": packet}, API_KEY) == js_sig


def test_wire_layouts_are_the_same_length():
    py_len = len(json.loads(json.dumps(encrypt_data(MESSAGE, API_KEY))))
    js_len = int(
        _node(f"console.log(m.encryptData({json.dumps(MESSAGE)},'dev-key').length)")
    )
    assert py_len == js_len
