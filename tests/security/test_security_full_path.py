"""End-to-end coverage of the warnetech_cli security path.

SecurityManager exposes encrypt_data(data, key) / decrypt_data(encrypted, key).
The aes_gcm_encrypt/aes_gcm_decrypt names live in warnetech_control_plane.utils
and have a different contract (they return and take the nonce separately).
"""

import pytest

from warnetech_cli.security import SecurityManager

pytestmark = pytest.mark.filterwarnings(
    "ignore:SecurityManager is deprecated:DeprecationWarning"
)


def test_key_derivation_round_trip():
    sm = SecurityManager()
    k1 = sm.derive_key("password", b"salt")
    k2 = sm.derive_key("password", b"salt")
    assert k1 == k2


def test_encrypt_decrypt_round_trip():
    sm = SecurityManager()
    key, _ = sm.derive_key("password", b"salt")

    plaintext = b"warnetech-test"
    ciphertext = sm.encrypt_data(plaintext, key)
    decrypted = sm.decrypt_data(ciphertext, key)

    assert decrypted == plaintext


def test_encrypt_changes_ciphertext():
    """A fresh random IV per call must make repeat encryptions differ."""
    sm = SecurityManager()
    key, _ = sm.derive_key("password", b"salt")

    pt = b"same-plaintext"
    c1 = sm.encrypt_data(pt, key)
    c2 = sm.encrypt_data(pt, key)

    assert c1 != c2
    assert sm.decrypt_data(c1, key) == sm.decrypt_data(c2, key) == pt


def test_decrypt_invalid_ciphertext_raises():
    sm = SecurityManager()
    key, _ = sm.derive_key("password", b"salt")

    # Narrow to the real failure: pytest.raises(Exception) would also swallow
    # an AttributeError and pass without exercising any decryption at all.
    with pytest.raises(RuntimeError, match="Decryption failed"):
        sm.decrypt_data(b"not-a-valid-gcm-packet", key * 1)
