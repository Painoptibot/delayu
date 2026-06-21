"""TOTP 2FA (Google Authenticator / Яндекс.Ключ и аналоги)."""
import base64
import hashlib
import hmac
import struct
import time

from django.conf import settings

try:
    import pyotp
except ImportError:  # pragma: no cover
    pyotp = None

ISSUER = getattr(settings, "DELAYU_TOTP_ISSUER", "Delayu")


class TotpUnavailableError(RuntimeError):
    pass


def _require_pyotp():
    if pyotp is None:
        raise TotpUnavailableError("Установите пакет pyotp для 2FA")


def generate_secret() -> str:
    if pyotp is not None:
        return pyotp.random_base32()
    return base64.b32encode(hashlib.sha256(str(time.time()).encode()).digest())[:16].decode()


def provisioning_uri(user, secret: str) -> str:
    label = user.get_username()
    if pyotp is not None:
        return pyotp.TOTP(secret).provisioning_uri(name=label, issuer_name=ISSUER)
    from urllib.parse import quote

    issuer = quote(ISSUER)
    name = quote(label)
    return f"otpauth://totp/{issuer}:{name}?secret={secret}&issuer={issuer}"


def _verify_fallback(secret: str, code: str) -> bool:
    """RFC6238 без pyotp — для dev/CI."""
    cleaned = "".join(ch for ch in str(code) if ch.isdigit())
    if len(cleaned) != 6:
        return False
    key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
    counter = int(time.time()) // 30
    for offset in (-1, 0, 1):
        msg = struct.pack(">Q", counter + offset)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        start = digest[-1] & 0x0F
        token = struct.unpack(">I", digest[start : start + 4])[0] & 0x7FFFFFFF
        if f"{token % 1_000_000:06d}" == cleaned:
            return True
    return False


def verify_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    if pyotp is not None:
        cleaned = "".join(ch for ch in str(code) if ch.isdigit())
        if len(cleaned) != 6:
            return False
        return pyotp.TOTP(secret).verify(cleaned, valid_window=1)
    return _verify_fallback(secret, code)


def profile_totp_enabled(profile) -> bool:
    return bool(profile and profile.two_factor_enabled and profile.totp_secret)
