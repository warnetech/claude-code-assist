import base64
import json

import pytest

from warnetech_envelope import (
    IV_LENGTH,
    PBKDF2_ITERATIONS,
    PBKDF2_SALT,
    EnvelopeError,
    decrypt_data,
    derive_key,
    encrypt_data,
    generate_hmac_signature,
    is_envelope,
    seal,
    unseal,
    verify_hmac_signature,
)

API_KEY = "dev-key"


def test_wire_parameters_are_pinned():
    # These are the JS-compatible constants. Changing one breaks every client.
    assert IV_LENGTH == 12
    assert PBKDF2_ITERATIONS == 100_000
    assert PBKDF2_SALT == b"claude-command-cli"
    assert len(derive_key(API_KEY)) == 32


def test_encrypt_decrypt_round_trip():
    assert decrypt_data(encrypt_data("hello", API_KEY), API_KEY) == "hello"


def test_wire_layout_is_iv12_then_ct_and_tag():
    raw = base64.b64decode(encrypt_data("hello", API_KEY))
    assert len(raw) == IV_LENGTH + len("hello") + 16


def test_iv_is_random_per_call():
    a = encrypt_data("same", API_KEY)
    b = encrypt_data("same", API_KEY)
    assert a != b
    assert decrypt_data(a, API_KEY) == decrypt_data(b, API_KEY) == "same"


def test_wrong_key_fails():
    packet = encrypt_data("secret", API_KEY)
    with pytest.raises(EnvelopeError, match="Decryption failed"):
        decrypt_data(packet, "wrong-key")


def test_tampered_tag_fails():
    raw = bytearray(base64.b64decode(encrypt_data("secret", API_KEY)))
    raw[-1] ^= 0x01
    with pytest.raises(EnvelopeError, match="Decryption failed"):
        decrypt_data(base64.b64encode(bytes(raw)).decode(), API_KEY)


@pytest.mark.parametrize("bad", ["", "!!!not base64!!!", base64.b64encode(b"short").decode()])
def test_malformed_packets_rejected(bad):
    with pytest.raises(EnvelopeError):
        decrypt_data(bad, API_KEY)


def test_hmac_uses_javascript_json_separators():
    # JSON.stringify emits no spaces; json.dumps defaults to ', ' and ': '.
    # The signature must be taken over the compact form.
    payload = {"a": 1, "b": 2}
    compact = json.dumps(payload, separators=(",", ":"))
    assert compact == '{"a":1,"b":2}'
    import hashlib
    import hmac as _hmac

    expected = _hmac.new(API_KEY.encode(), compact.encode(), hashlib.sha256).hexdigest()
    assert generate_hmac_signature(payload, API_KEY) == expected


def test_hmac_verify_rejects_wrong_signature():
    assert verify_hmac_signature({"x": 1}, generate_hmac_signature({"x": 1}, API_KEY), API_KEY)
    assert not verify_hmac_signature({"x": 1}, "deadbeef", API_KEY)


def test_seal_unseal_round_trip():
    body = {"command": "ping", "args": [1, 2, 3], "nested": {"ok": True}}
    envelope = seal(body, API_KEY)
    assert is_envelope(envelope)
    assert set(envelope) == {"encrypted_data", "signature"}
    assert "ping" not in json.dumps(envelope)  # plaintext must not leak
    assert unseal(envelope, API_KEY) == body


def test_unseal_rejects_tampered_signature():
    envelope = seal({"command": "ping"}, API_KEY)
    envelope["signature"] = "0" * 64
    with pytest.raises(EnvelopeError, match="signature mismatch"):
        unseal(envelope, API_KEY)


def test_is_envelope_discriminates():
    assert is_envelope({"encrypted_data": "x"})
    assert not is_envelope({"command": "ping"})
    assert not is_envelope({"encrypted_data": 123})
    assert not is_envelope("string")
    assert not is_envelope(None)
