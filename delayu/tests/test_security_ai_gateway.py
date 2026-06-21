import pytest
from django.contrib.auth import get_user_model

try:
    import pyotp
except ImportError:
    pyotp = None

from delayu.models import AiRequestLog, ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule, UserProfile
from delayu.services.ai_gateway import AiGatewayError, contains_pii, invoke, redact_pii
from delayu.services.totp import generate_secret, verify_code

User = get_user_model()


@pytest.fixture
def sec_sub(db):
    sub = Subsystem.objects.create(code="sec_test", name="Sec", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="user", name="User")
    mod, _ = ModuleCatalog.objects.get_or_create(code="M47", defaults={"name": "AI", "group": "ai"})
    RoleModulePermission.objects.create(role=role, module=mod, can_view=True)
    SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    user = User.objects.create_user("sec_user", password="x")
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role, is_default=True)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.active_subsystem = sub
    profile.save()
    return sub, user, profile


@pytest.mark.django_db
def test_totp_generate_and_verify():
    secret = generate_secret()
    if pyotp is not None:
        code = pyotp.TOTP(secret).now()
    else:
        import base64
        import hashlib
        import hmac
        import struct
        import time

        key = base64.b32decode(secret.upper() + "=" * ((8 - len(secret) % 8) % 8))
        counter = int(time.time()) // 30
        msg = struct.pack(">Q", counter)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        start = digest[-1] & 0x0F
        token = struct.unpack(">I", digest[start : start + 4])[0] & 0x7FFFFFFF
        code = f"{token % 1_000_000:06d}"
    assert verify_code(secret, code)


@pytest.mark.django_db
def test_ai_gateway_redacts_pii(sec_sub):
    sub, user, _profile = sec_sub
    from delayu.services.ai import get_or_create_policy

    policy = get_or_create_policy(sub)
    policy.allow_pii = False
    policy.save()
    prompt = "Связаться user@test.ru +79991234567"
    result = invoke(sub, user, "M47", prompt, lambda: "ok")
    assert result == "ok"
    log = AiRequestLog.objects.latest("pk")
    assert "[email]" in log.prompt
    assert log.meta.get("pii_redacted") is True


@pytest.mark.django_db
def test_ai_gateway_limit(sec_sub):
    sub, user, _profile = sec_sub
    from delayu.services.ai import get_or_create_policy

    policy = get_or_create_policy(sub)
    policy.max_requests_per_day = 1
    policy.save()
    invoke(sub, user, "M47", "q1", lambda: "a")
    with pytest.raises(AiGatewayError) as exc:
        invoke(sub, user, "M47", "q2", lambda: "b")
    assert exc.value.code == "limit_exceeded"


def test_contains_pii_helpers():
    assert contains_pii("test@mail.ru")
    assert not contains_pii("просто текст")
    assert "[email]" in redact_pii("a@b.c")
