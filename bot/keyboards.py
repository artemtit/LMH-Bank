"""Инлайн- и реплай-клавиатуры бота."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
                InlineKeyboardButton(text="📜 История", callback_data="history"),
            ],
            [
                InlineKeyboardButton(text="📥 Пополнить", callback_data="deposit"),
                InlineKeyboardButton(text="📤 Снять", callback_data="withdraw"),
            ],
            [
                InlineKeyboardButton(text="💸 Перевод", callback_data="transfer"),
                InlineKeyboardButton(text="💳 Карты", callback_data="cards"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Профиль", callback_data="profile"),
            ],
        ]
    )


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")]
        ]
    )


def cancel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel")]
        ]
    )


def cards_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Выпустить карту", callback_data="issue_card")],
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu")],
        ]
    )


def reply_menu() -> ReplyKeyboardMarkup:
    """Постоянная нижняя клавиатура с кнопкой открытия меню."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🏦 Меню")]],
        resize_keyboard=True,
        input_field_placeholder="Нажмите «Меню» или введите команду",
    )
