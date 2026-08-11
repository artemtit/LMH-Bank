"""Регистрация всех роутеров бота."""
from __future__ import annotations

from aiogram import Router

from . import common, operations


def get_router() -> Router:
    router = Router(name="root")
    router.include_router(operations.router)
    router.include_router(common.router)
    return router
