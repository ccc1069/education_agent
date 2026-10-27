"""PII 脱敏: 日志/LLM 上传前对敏感字段做不可逆遮蔽。

设计:
- 输入明文 -> 输出脱敏字符串(不可逆)
- 用于: 日志输出、LLM prompt 上传、监控指标 label
- 与 crypto.encrypt_field 区别: 脱敏不可逆,加密可逆
"""

from __future__ import annotations

import re
from typing import Any

# 中国手机号: 1[3-9]xxxxxxxxx
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")

# 邮箱: 保留首字符 + 域名(lookbehind/lookahead 只看 ASCII,避免被中文字符干扰)
_EMAIL_RE = re.compile(
    r"(?<![a-zA-Z0-9._%+-])([a-zA-Z0-9._%+-])[a-zA-Z0-9._%+-]*"
    r"@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})(?![a-zA-Z0-9.])"
)

# 身份证: 18 位,保留前 6 位(地区码)+ 后 1 位(校验码)
_ID_CARD_RE = re.compile(r"(?<!\d)(\d{6})\d{8}(\d{3}[0-9Xx])(?!\d)")

# 银行卡: 保留前 4 + 后 4
_BANK_CARD_RE = re.compile(r"(?<!\d)(\d{4})\d{8,11}(\d{4})(?!\d)")


def mask_phone(phone: str) -> str:
    """138****1234"""
    if not phone:
        return phone
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 7:
        return "*" * len(phone)
    return f"{digits[:3]}****{digits[-4:]}"


def mask_email(email: str) -> str:
    """a***@example.com"""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    if not local:
        return email
    return f"{local[0]}***@{domain}"


def mask_id_card(id_card: str) -> str:
    """110101********1234"""
    if not id_card or len(id_card) < 10:
        return "*" * len(id_card) if id_card else id_card
    return f"{id_card[:6]}{'*' * (len(id_card) - 10)}{id_card[-4:]}"


def mask_bank_card(card: str) -> str:
    """6222****1234"""
    if not card or len(card) < 8:
        return "*" * len(card) if card else card
    return f"{card[:4]}****{card[-4:]}"


def mask_name(name: str) -> str:
    """张** / 欧**"""
    if not name:
        return name
    if len(name) == 1:
        return name
    if len(name) == 2:
        return f"{name[0]}*"
    return f"{name[0]}{'*' * (len(name) - 1)}"


def mask_text(text: str) -> str:
    """对一段文本中所有 PII 做脱敏(用于日志/LLM 上传)。"""
    if not text:
        return text
    result = _PHONE_RE.sub(lambda m: f"{m.group(1)}****{m.group(2)}", text)
    result = _EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", result)
    result = _ID_CARD_RE.sub(lambda m: f"{m.group(1)}********{m.group(2)}", result)
    result = _BANK_CARD_RE.sub(lambda m: f"{m.group(1)}****{m.group(2)}", result)
    return result


def mask_dict(fields: dict[str, Any], sensitive_keys: set[str]) -> dict[str, Any]:
    """对字典中敏感 key 做脱敏,返回新字典。

    敏感 key 命中时,根据 key 名选合适脱敏函数:
        phone/tel/mobile -> mask_phone
        email/mail -> mask_email
        id_card/id_number -> mask_id_card
        bank_card/card_number -> mask_bank_card
        name/real_name -> mask_name
        其他 -> mask_text
    """
    result = dict(fields)
    for key, value in result.items():
        if key not in sensitive_keys or value is None:
            continue
        s = str(value)
        lower = key.lower()
        if any(k in lower for k in ("phone", "tel", "mobile")):
            result[key] = mask_phone(s)
        elif "email" in lower or "mail" in lower:
            result[key] = mask_email(s)
        elif "id_card" in lower or "id_number" in lower:
            result[key] = mask_id_card(s)
        elif "bank" in lower or "card_number" in lower:
            result[key] = mask_bank_card(s)
        elif "name" in lower:
            result[key] = mask_name(s)
        else:
            result[key] = mask_text(s)
    return result
