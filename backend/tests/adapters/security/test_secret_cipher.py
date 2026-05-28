import base64
import sys
import pytest
from app.adapters.security.secret_cipher import (
    NullCipher, FernetCipher, DpapiCipher, SecretDecryptError,
    get_secret_cipher, _reset_secret_cipher,
)


def test_null_passthrough_roundtrip():
    c = NullCipher()
    assert c.encrypt("sk-abc") == "sk-abc"      # no marker added
    assert c.decrypt("sk-abc") == "sk-abc"      # legacy plaintext passthrough
    assert c.encrypt("") == ""
    assert c.decrypt("") == ""


def test_fernet_roundtrip_and_marker():
    c = FernetCipher("a-test-master-key")
    token = c.encrypt("sk-secret")
    assert token.startswith("enc:fernet:")
    assert "sk-secret" not in token
    assert c.decrypt(token) == "sk-secret"
    assert c.encrypt("") == ""


def test_legacy_plaintext_passthrough_on_decrypt():
    c = FernetCipher("k")
    assert c.decrypt("sk-plain-legacy") == "sk-plain-legacy"  # no marker -> as-is


def test_cross_scheme_raises_secret_decrypt_error():
    fernet = FernetCipher("k")
    null = NullCipher()
    dpapi_like = "enc:dpapi:Zm9v"
    with pytest.raises(SecretDecryptError):
        fernet.decrypt(dpapi_like)
    with pytest.raises(SecretDecryptError):
        null.decrypt(dpapi_like)


def test_corrupt_payload_raises():
    c = FernetCipher("k")
    with pytest.raises(SecretDecryptError):
        c.decrypt("enc:fernet:not-valid-fernet")


def test_factory_lazy_call_selection(monkeypatch):
    _reset_secret_cipher()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("MTX_SECRET_KEY", raising=False)
    assert get_secret_cipher().scheme == "null"
    _reset_secret_cipher()
    monkeypatch.setenv("MTX_SECRET_KEY", "x")
    assert get_secret_cipher().scheme == "fernet"
    _reset_secret_cipher()
    monkeypatch.setattr(sys, "platform", "win32")
    assert get_secret_cipher().scheme == "dpapi"
    _reset_secret_cipher()


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_roundtrip_windows():
    c = DpapiCipher()
    token = c.encrypt("sk-windows-secret")
    assert token.startswith("enc:dpapi:")
    assert "sk-windows-secret" not in token
    assert c.decrypt(token) == "sk-windows-secret"
    assert c.encrypt("") == ""
