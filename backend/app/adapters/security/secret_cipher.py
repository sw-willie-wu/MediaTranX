"""At-rest encryption for stored secrets (remote API keys).

Platform-selected cipher with marker-tagged ciphertext `enc:<scheme>:<b64>`.
See core/.claude/specs/2026-05-28-remote-api-key-encryption-design.md.
"""
from __future__ import annotations
import base64
import hashlib
import logging
import os
import sys
from typing import Callable, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)
_PREFIX = "enc:"


class SecretDecryptError(Exception):
    """A present, marked value could not be decrypted by the active cipher
    (wrong scheme / corrupt / different machine). Never coerced to None."""


@runtime_checkable
class SecretCipher(Protocol):
    scheme: str
    def encrypt(self, plaintext: str) -> str: ...
    def decrypt(self, token: str) -> str: ...


def _marker(scheme: str) -> str:
    return f"{_PREFIX}{scheme}:"


def _decrypt_common(token: str, my_scheme: str, decode: Callable[[str], str]) -> str:
    if not token:
        return token                                  # empty / None -> as-is
    if not token.startswith(_PREFIX):
        return token                                  # legacy plaintext
    scheme, _, payload = token[len(_PREFIX):].partition(":")
    if not scheme or scheme != my_scheme:
        raise SecretDecryptError(
            f"value scheme {scheme!r} != active cipher {my_scheme!r}")
    try:
        return decode(payload)
    except SecretDecryptError:
        raise
    except Exception as e:                            # noqa: BLE001
        raise SecretDecryptError(f"{my_scheme} decrypt failed: {e}") from e


class NullCipher:
    scheme = "null"
    def encrypt(self, plaintext: str) -> str:
        return plaintext                              # passthrough, NO marker
    def decrypt(self, token: str) -> str:
        return _decrypt_common(token, self.scheme, lambda p: p)


class FernetCipher:
    scheme = "fernet"
    def __init__(self, env_key: str):
        from cryptography.fernet import Fernet        # lazy: only this branch
        key = base64.urlsafe_b64encode(
            hashlib.sha256(env_key.encode("utf-8")).digest())
        self._f = Fernet(key)
    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return plaintext
        tok = self._f.encrypt(plaintext.encode("utf-8")).decode("ascii")
        return _marker(self.scheme) + tok
    def decrypt(self, token: str) -> str:
        return _decrypt_common(
            token, self.scheme,
            lambda p: self._f.decrypt(p.encode("ascii")).decode("utf-8"))


class DpapiCipher:
    scheme = "dpapi"
    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return plaintext
        blob = _dpapi("CryptProtectData", plaintext.encode("utf-8"))
        return _marker(self.scheme) + base64.b64encode(blob).decode("ascii")
    def decrypt(self, token: str) -> str:
        return _decrypt_common(
            token, self.scheme,
            lambda p: _dpapi("CryptUnprotectData", base64.b64decode(p)).decode("utf-8"))


def _dpapi(func_name: str, data: bytes) -> bytes:
    """Windows DPAPI protect/unprotect (user-scoped). ctypes discipline mirrors
    app/adapters/binary/_proc_lifetime.py: pinned argtypes/restype, use_last_error,
    LocalFree on the output blob (avoid a per-call heap leak).
    (arg #2 is nominally LPWSTR* for CryptUnprotectData and LPCWSTR for
    CryptProtectData; we pass None either way, so the shared LPCWSTR argtype is
    harmless. Verified empirically: round-trip passes on Windows.)"""
    import ctypes
    from ctypes import wintypes

    class _BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    func = getattr(crypt32, func_name)
    func.argtypes = [ctypes.POINTER(_BLOB), wintypes.LPCWSTR,
                     ctypes.POINTER(_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                     wintypes.DWORD, ctypes.POINTER(_BLOB)]
    func.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = _BLOB()
    CRYPTPROTECT_UI_FORBIDDEN = 0x01
    if not func(ctypes.byref(blob_in), None, None, None, None,
                CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


# ── Factory: lazy first-CALL memoization (not import-time) ──────────────────
_cipher: Optional[SecretCipher] = None


def get_secret_cipher() -> SecretCipher:
    global _cipher
    if _cipher is None:
        _cipher = _select_cipher()
    return _cipher


def _select_cipher() -> SecretCipher:
    if sys.platform == "win32":
        return DpapiCipher()
    env_key = os.environ.get("MTX_SECRET_KEY")
    if env_key:
        return FernetCipher(env_key)
    logger.warning(
        "MTX_SECRET_KEY not set on non-Windows: stored API keys are NOT "
        "encrypted at rest (set MTX_SECRET_KEY to enable Fernet encryption).")
    return NullCipher()


def _reset_secret_cipher() -> None:
    """Test hook — clears the memoized cipher."""
    global _cipher
    _cipher = None
