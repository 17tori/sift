"""Telegram WebApp initData validation and HMAC helpers.

Spec: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

import orjson


class InitDataError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TelegramWebAppUser:
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None
    is_premium: bool
    photo_url: str | None


@dataclass(frozen=True, slots=True)
class ValidatedInitData:
    user: TelegramWebAppUser
    auth_date: int
    start_param: str | None
    query_id: str | None


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Builds a valid initData string. Used by tests and local tooling only."""
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    digest = hmac.new(_secret_key(bot_token), check.encode(), hashlib.sha256).hexdigest()
    from urllib.parse import urlencode

    return urlencode({**fields, "hash": digest})


def validate_init_data(raw: str, bot_token: str, max_age_seconds: int, now: float | None = None) -> ValidatedInitData:
    if not raw or not bot_token:
        raise InitDataError("missing init data")
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=False)
    data = dict(pairs)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InitDataError("hash missing")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    expected = hmac.new(_secret_key(bot_token), check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise InitDataError("bad signature")
    try:
        auth_date = int(data.get("auth_date", "0"))
    except ValueError as e:
        raise InitDataError("bad auth_date") from e
    current = now if now is not None else time.time()
    if auth_date <= 0 or current - auth_date > max_age_seconds or auth_date - current > 300:
        raise InitDataError("init data expired")
    try:
        u = orjson.loads(data.get("user", "{}"))
        user = TelegramWebAppUser(
            id=int(u["id"]),
            first_name=str(u.get("first_name", "")),
            last_name=u.get("last_name"),
            username=u.get("username"),
            language_code=u.get("language_code"),
            is_premium=bool(u.get("is_premium", False)),
            photo_url=u.get("photo_url"),
        )
    except (KeyError, ValueError, TypeError, orjson.JSONDecodeError) as e:
        raise InitDataError("bad user payload") from e
    return ValidatedInitData(user=user, auth_date=auth_date, start_param=data.get("start_param"), query_id=data.get("query_id"))


def hmac_sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()[:32]


def hmac_verify(secret: str, message: str, signature: str) -> bool:
    return hmac.compare_digest(hmac_sign(secret, message), signature)
