"""Конфигурация приложения, читается из переменных окружения."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _parse_admin_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return ids


@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str = "data/bank.db"
    admin_ids: set[int] = field(default_factory=set)


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задан. Скопируйте .env.example в .env и укажите токен от @BotFather."
        )
    return Config(
        bot_token=token,
        db_path=os.getenv("DB_PATH", "data/bank.db").strip() or "data/bank.db",
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")),
    )
