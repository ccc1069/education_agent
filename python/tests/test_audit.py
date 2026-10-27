"""core.crypto + core.pii + AuditService 单元测试。"""

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.crypto import (
    CryptoError,
    decrypt_field,
    decrypt_dict,
    encrypt_field,
    encrypt_dict,
)
from core.pii import (
    mask_bank_card,
    mask_dict,
    mask_email,
    mask_id_card,
    mask_name,
    mask_phone,
    mask_text,
)
from db.models import AuditLogORM, UserORM, UserRole
from services.audit_service import (
    AuditService,
    _get_hmac_secret,
    _reset_hmac_secret_for_test,
    compute_hash,
)


# ---------- crypto: 加密可逆性 ----------


def test_encrypt_then_decrypt_roundtrip():
    plaintext = "13800138000"
    ct = encrypt_field(plaintext)
    assert ct != plaintext
    assert decrypt_field(ct) == plaintext


def test_encrypt_none_returns_none():
    assert encrypt_field(None) is None
    assert decrypt_field(None) is None


def test_encrypt_different_iv_each_call():
    """每次加密生成独立 IV,密文不同。"""
    pt = "same_input"
    ct1 = encrypt_field(pt)
    ct2 = encrypt_field(pt)
    assert ct1 != ct2
    assert decrypt_field(ct1) == pt
    assert decrypt_field(ct2) == pt


def test_decrypt_tampered_ciphertext_fails():
    """GCM 自带完整性校验,密文被篡改应报错。"""
    ct = encrypt_field("secret_value")
    # 翻转 1 字节
    import base64

    raw = bytearray(base64.b64decode(ct))
    raw[-1] ^= 0x01
    tampered = base64.b64encode(bytes(raw)).decode("ascii")
    with pytest.raises(CryptoError):
        decrypt_field(tampered)


def test_decrypt_invalid_base64_fails():
    with pytest.raises(CryptoError):
        decrypt_field("not_base64!!!")


def test_encrypt_dict_only_encrypts_specified_fields():
    data = {"name": "Alice", "email": "a@b.com", "age": 30}
    encrypted = encrypt_dict(data, {"name", "email"})
    assert encrypted["name"] != "Alice"
    assert encrypted["email"] != "a@b.com"
    assert encrypted["age"] == 30  # 未指定字段不变
    # 解密回来
    decrypted = decrypt_dict(encrypted, {"name", "email"})
    assert decrypted["name"] == "Alice"
    assert decrypted["email"] == "a@b.com"
    assert decrypted["age"] == 30


def test_encrypt_field_rejects_non_string():
    with pytest.raises(CryptoError):
        encrypt_field(12345)


# ---------- pii: 脱敏格式 ----------


def test_mask_phone_format():
    assert mask_phone("13800138000") == "138****8000"
    assert mask_phone("138-0013-8000") == "138****8000"


def test_mask_phone_short_input():
    assert mask_phone("12345") == "*****"
    assert mask_phone("") == ""


def test_mask_email_format():
    assert mask_email("alice@example.com") == "a***@example.com"
    assert mask_email("a@b.com") == "a***@b.com"


def test_mask_email_invalid_input():
    assert mask_email("not_an_email") == "not_an_email"
    assert mask_email("") == ""


def test_mask_id_card_format():
    assert mask_id_card("110101199001011234") == "110101********1234"


def test_mask_bank_card_format():
    assert mask_bank_card("6222021234567890123") == "6222****0123"


def test_mask_name_chinese():
    assert mask_name("张三") == "张*"
    assert mask_name("张三丰") == "张**"
    assert mask_name("张") == "张"


def test_mask_text_detects_multiple_pii():
    """一段文本中含手机号+邮箱+身份证,全部脱敏。"""
    text = "电话13800138000邮箱alice@example.com身份证110101199001011234"
    masked = mask_text(text)
    assert "13800138000" not in masked
    assert "alice@example.com" not in masked
    assert "110101199001011234" not in masked
    assert "138****8000" in masked
    assert "a***@example.com" in masked


def test_mask_dict_by_key_name():
    data = {
        "name": "张三",
        "phone": "13800138000",
        "email": "alice@example.com",
        "id_card": "110101199001011234",
        "note": "普通文本",
    }
    masked = mask_dict(data, {"name", "phone", "email", "id_card", "note"})
    assert masked["name"] == "张*"
    assert masked["phone"] == "138****8000"
    assert masked["email"] == "a***@example.com"
    assert masked["id_card"] == "110101********1234"
    assert masked["note"] == "普通文本"  # 无 PII 的文本不变


def test_mask_dict_skips_none():
    data = {"name": None, "phone": "13800138000"}
    masked = mask_dict(data, {"name", "phone"})
    assert masked["name"] is None
    assert masked["phone"] == "138****8000"


# ---------- AuditService: HMAC 链 ----------


@pytest_asyncio.fixture
async def audit_secret():
    """设置测试用 HMAC secret,用完还原。"""
    os.environ["AUDIT_HMAC_SECRET"] = "test-audit-secret-not-for-prod"
    _reset_hmac_secret_for_test()
    yield
    os.environ.pop("AUDIT_HMAC_SECRET", None)
    _reset_hmac_secret_for_test()


def test_compute_hash_deterministic(audit_secret):
    """相同输入 -> 相同 hash。"""
    from datetime import datetime

    ts = datetime(2026, 1, 1, 12, 0, 0)
    h1 = compute_hash(1, "alice", "login", "user:1", ts, "")
    h2 = compute_hash(1, "alice", "login", "user:1", ts, "")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_compute_hash_changes_on_field_modification(audit_secret):
    """任一字段变化 -> hash 变化。"""
    from datetime import datetime

    ts = datetime(2026, 1, 1, 12, 0, 0)
    h1 = compute_hash(1, "alice", "login", "user:1", ts, "")
    h2 = compute_hash(1, "bob", "login", "user:1", ts, "")
    h3 = compute_hash(1, "alice", "logout", "user:1", ts, "")
    h4 = compute_hash(1, "alice", "login", "user:2", ts, "")
    h5 = compute_hash(2, "alice", "login", "user:1", ts, "")
    assert len({h1, h2, h3, h4, h5}) == 5  # 全部不同


def test_compute_hash_chains_correctly(audit_secret):
    """prev_hash 改变 -> curr_hash 改变(链依赖)。"""
    from datetime import datetime

    ts = datetime(2026, 1, 1, 12, 0, 0)
    h_a = compute_hash(1, "alice", "login", "user:1", ts, "")
    h_b = compute_hash(2, "bob", "login", "user:2", ts, h_a)
    h_b2 = compute_hash(2, "bob", "login", "user:2", ts, "tampered")
    assert h_b != h_b2


@pytest.mark.asyncio
async def test_audit_log_appends_to_chain(test_engine, audit_secret):
    """连续写入多条日志,链尾 prev_hash 自动接续。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        service = AuditService(s)
        log1 = await service.log_action("alice@x.com", "login", "user:1")
        log2 = await service.log_action("bob@x.com", "login", "user:2")
        log3 = await service.log_action("alice@x.com", "export_data", "user:1")

    assert log1["prev_hash"] == ""
    assert log2["prev_hash"] == log1["curr_hash"]
    assert log3["prev_hash"] == log2["curr_hash"]
    assert log1["curr_hash"]
    assert log2["curr_hash"]
    assert log3["curr_hash"]


@pytest.mark.asyncio
async def test_audit_chain_verifies_clean(test_engine, audit_secret):
    """未篡改的链验证通过。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        service = AuditService(s)
        for i in range(5):
            await service.log_action(f"user{i}@x.com", "action", f"target:{i}")

    async with async_session() as s:
        service = AuditService(s)
        result = await service.verify_chain(1)
        assert result["valid"] is True
        assert result["checked"] == 5
        assert result["broken_at"] is None


@pytest.mark.asyncio
async def test_audit_chain_detects_tampering(test_engine, audit_secret):
    """修改任一字段 -> 链验证失败。"""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        service = AuditService(s)
        await service.log_action("alice@x.com", "login", "user:1")
        await service.log_action("bob@x.com", "login", "user:2")
        # 篡改第一条日志的 actor
        from sqlalchemy import update
        await s.execute(
            update(AuditLogORM)
            .where(AuditLogORM.id == 1)
            .values(actor="tampered@x.com")
        )
        await s.commit()

    async with async_session() as s:
        service = AuditService(s)
        result = await service.verify_chain(1)
        assert result["valid"] is False
        assert result["broken_at"] == 1


@pytest.mark.asyncio
async def test_audit_list_recent_filters(test_engine, audit_secret):
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as s:
        service = AuditService(s)
        await service.log_action("alice@x.com", "login", "user:1")
        await service.log_action("bob@x.com", "login", "user:2")
        await service.log_action("alice@x.com", "export_data", "user:1")

    async with async_session() as s:
        service = AuditService(s)
        # 按 actor 过滤
        alice_logs = await service.list_recent(actor="alice@x.com")
        assert len(alice_logs) == 2
        # 按 action 过滤
        login_logs = await service.list_recent(action="login")
        assert len(login_logs) == 2
        # 全部
        all_logs = await service.list_recent(limit=10)
        assert len(all_logs) == 3
        # 倒序: 最新在前
        assert all_logs[0]["actor"] == "alice@x.com"
        assert all_logs[0]["action"] == "export_data"


@pytest.mark.asyncio
async def test_audit_secret_isolated_from_jwt(test_engine):
    """AUDIT_HMAC_SECRET 与 JWT_SECRET_KEY 独立,优先取 AUDIT。"""
    os.environ["AUDIT_HMAC_SECRET"] = "audit_specific_secret"
    os.environ["JWT_SECRET_KEY"] = "jwt_secret"
    _reset_hmac_secret_for_test()
    audit_secret = _get_hmac_secret()
    _reset_hmac_secret_for_test()
    os.environ.pop("AUDIT_HMAC_SECRET", None)
    _reset_hmac_secret_for_test()

    assert audit_secret == b"audit_specific_secret"
    # 清理
    _reset_hmac_secret_for_test()
