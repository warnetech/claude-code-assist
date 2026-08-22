"""Canonical Warnetech AES-256-GCM request/response envelope.

Single source of truth for the wire format, shared by the Python CLI
(warnetech_cli.server_client) and the server (warnetech_server.middleware).
Neither owns it: it is the protocol between them.

WIRE FORMAT
    base64( iv(12) || ciphertext || tag(16) )

  * 96-bit IV per NIST SP 800-38D.
  * The tag trails the ciphertext because WebCrypto's subtle.encrypt does not
    expose it separately, so this is the only layout every runtime can emit.

KEY DERIVATION
    PBKDF2-HMAC-SHA256(api_key, salt=b"claude-command-cli", 100_000) -> 32 bytes

These parameters are byte-compatible with worker/utils/crypto.js and
warnetech_cli_legacy/crypto.js. Changing any of them breaks every client, so
they are pinned here and asserted by the cross-language tests in
tests/security/test_envelope_interop.py.

NOTE ON THE ITERATION COUNT: 100_000 is deliberately NOT the 480_000 used by
warnetech_cli.security.SecurityManager. That module is a separate, unwired
local-storage path (see its docstring); this one must match the JavaScript
implementations byte for byte, and raising it here would break them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

__all__ = [
    "IV_LENGTH",
    "TAG_LENGTH",
    "PBKDF2_ITERATIONS",
    "PBKDF2_SALT",
    "EnvelopeError",
    "aes_gcm_encrypt",
    "aes_gcm_decrypt",
    "derive_key",
    "encrypt_data",
    "decrypt_data",
    "generate_hmac_signature",
    "verify_hmac_signature",
    "seal",
    "unseal",
    "is_envelope",
]

IV_LENGTH = 12
TAG_LENGTH = 16
KEY_LENGTH = 32
PBKDF2_ITERATIONS = 100_000
PBKDF2_SALT = b"claude-command-cli"


class EnvelopeError(RuntimeError):
    """Raised when an envelope cannot be produced or opened."""


def _aesgcm(key: bytes):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise EnvelopeError(
            "the 'cryptography' package is required: pip install cryptography"
        ) from exc
    return AESGCM(key)


def aes_gcm_encrypt(
    key: bytes, plaintext: bytes, associated_data: bytes | None = None
) -> tuple[bytes, bytes]:
    """Low-level primitive: returns (nonce, ciphertext_with_tag).

    Used for at-rest encryption (see warnetech_control_plane.slice_engine),
    where the nonce is stored alongside the ciphertext rather than prefixed
    to it. The channel envelope uses :func:`encrypt_data` instead.
    """
    nonce = os.urandom(IV_LENGTH)
    return nonce, _aesgcm(key).encrypt(nonce, plaintext, associated_data)


def aes_gcm_decrypt(
    key: bytes, nonce: bytes, ciphertext: bytes, associated_data: bytes | None = None
) -> bytes:
    """Inverse of :func:`aes_gcm_encrypt`."""
    return _aesgcm(key).decrypt(nonce, ciphertext, associated_data)


def derive_key(api_key: str) -> bytes:
    """Derive the 256-bit channel key from the API key."""
    return hashlib.pbkdf2_hmac(
        "sha256", api_key.encode("utf-8"), PBKDF2_SALT, PBKDF2_ITERATIONS, dklen=KEY_LENGTH
    )


def encrypt_data(plaintext: str, api_key: str) -> str:
    """Encrypt a UTF-8 string, returning base64 of iv || ciphertext+tag."""
    iv = os.urandom(IV_LENGTH)
    ct_with_tag = _aesgcm(derive_key(api_key)).encrypt(iv, plaintext.encode("utf-8"), None)
    return base64.b64encode(iv + ct_with_tag).decode("ascii")


def decrypt_data(payload: str, api_key: str) -> str:
    """Reverse of :func:`encrypt_data`. Raises EnvelopeError on any failure."""
    try:
        combined = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise EnvelopeError(f"Decryption failed: malformed base64: {exc}") from exc

    if len(combined) <= IV_LENGTH + TAG_LENGTH:
        raise EnvelopeError("Decryption failed: packet too short")

    iv, ct_with_tag = combined[:IV_LENGTH], combined[IV_LENGTH:]
    try:
        return _aesgcm(derive_key(api_key)).decrypt(iv, ct_with_tag, None).decode("utf-8")
    except EnvelopeError:
        raise
    except Exception as exc:
        raise EnvelopeError(f"Decryption failed: {exc}") from exc


def _canonical_json(payload: Any) -> str:
    """Serialise the way JSON.stringify does.

    Python's json.dumps defaults to ', ' and ': ' separators; JavaScript emits
    none. The HMAC is taken over these bytes, so a mismatch here silently
    invalidates every signature crossing the language boundary.
    """
    return json.dumps(payload, separators=(",", ":"))


def generate_hmac_signature(payload: Any, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), _canonical_json(payload).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_hmac_signature(payload: Any, signature: str, secret: str) -> bool:
    return hmac.compare_digest(generate_hmac_signature(payload, secret), signature)


def seal(body: Any, api_key: str) -> dict:
    """Wrap a JSON-serialisable body into a signed encrypted envelope."""
    encrypted = encrypt_data(_canonical_json(body), api_key)
    return {
        "encrypted_data": encrypted,
        "signature": generate_hmac_signature({"encrypted_data": encrypted}, api_key),
    }


def unseal(envelope: dict, api_key: str) -> Any:
    """Verify and open an envelope produced by :func:`seal`."""
    if not is_envelope(envelope):
        raise EnvelopeError("not an envelope: missing 'encrypted_data'")

    encrypted = envelope["encrypted_data"]
    signature = envelope.get("signature")
    if signature is not None and not verify_hmac_signature(
        {"encrypted_data": encrypted}, signature, api_key
    ):
        raise EnvelopeError("Decryption failed: signature mismatch")

    return json.loads(decrypt_data(encrypted, api_key))


def is_envelope(body: Any) -> bool:
    return isinstance(body, dict) and isinstance(body.get("encrypted_data"), str)
