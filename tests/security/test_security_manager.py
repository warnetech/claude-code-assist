import pytest

from warnetech_cli.security import SecurityManager

pytestmark = pytest.mark.filterwarnings(
    "ignore:SecurityManager is deprecated:DeprecationWarning"
)


def test_derive_key_round_trip():
    sm = SecurityManager()
    key1 = sm.derive_key("password", b"salt")
    key2 = sm.derive_key("password", b"salt")
    assert key1 == key2


def test_derive_key_returns_32_byte_key_and_echoes_salt():
    key, salt = SecurityManager.derive_key("password", b"salt")
    assert len(key) == 32
    assert salt == b"salt"


def test_derive_key_generates_salt_when_omitted():
    key, salt = SecurityManager.derive_key("password")
    assert len(salt) == SecurityManager.SALT_LENGTH
    assert len(key) == 32


def test_derive_key_is_salt_dependent():
    key_a, _ = SecurityManager.derive_key("password", b"salt-a")
    key_b, _ = SecurityManager.derive_key("password", b"salt-b")
    assert key_a != key_b


def test_encrypt_decrypt_round_trip():
    key, _ = SecurityManager.derive_key("password", b"salt")
    encrypted = SecurityManager.encrypt_data(b"warnetech payload", key)
    assert encrypted != b"warnetech payload"
    assert SecurityManager.decrypt_data(encrypted, key) == b"warnetech payload"


def test_decrypt_with_wrong_key_raises():
    key, _ = SecurityManager.derive_key("password", b"salt")
    wrong, _ = SecurityManager.derive_key("not-the-password", b"salt")
    encrypted = SecurityManager.encrypt_data(b"warnetech payload", key)
    with pytest.raises(RuntimeError, match="Decryption failed"):
        SecurityManager.decrypt_data(encrypted, wrong)


def test_tampered_ciphertext_fails_authentication():
    key, _ = SecurityManager.derive_key("password", b"salt")
    encrypted = bytearray(SecurityManager.encrypt_data(b"warnetech payload", key))
    encrypted[-1] ^= 0x01
    with pytest.raises(RuntimeError, match="Decryption failed"):
        SecurityManager.decrypt_data(bytes(encrypted), key)


@pytest.mark.parametrize("bad_key", [b"", b"short", b"x" * 31, b"x" * 33])
def test_encrypt_rejects_non_256_bit_keys(bad_key):
    with pytest.raises(ValueError, match="32 bytes"):
        SecurityManager.encrypt_data(b"data", bad_key)
