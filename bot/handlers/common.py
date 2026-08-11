"""Основные обработчики: старт, меню, баланс, история, карты, профиль."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..database import Database
from ..keyboards import back_menu, cards_menu, main_menu, reply_menu
from ..utils import (
    KIND_LABELS,
    KIND_SIGN,
    format_dt,
    format_money,
    group_card,
    mask_card,
)

router = Router(name="common")

WELCOME = (
    "🏦 <b>LMH Bank</b> — ваш банк в Telegram.\n\n"
    "Здесь вы можете управлять счётом: смотреть баланс, переводить деньги, "
    "пополнять и снимать средства, выпускать виртуальные карты и следить за историей операций.\n\n"
    "⚠️ Это демонстрационный проект: все счета, карты и деньги виртуальные."
)


async def _menu_text(db: Database, tg_id: int) -> str:
    user = await db.get_user_by_tg(tg_id)
    assert user is not None
    account = await db.get_primary_account(user.id)
    assert account is not None
    return (
        f"{WELCOME}\n\n"
        f"💳 Счёт: <code>{account.number}</code>\n"
        f"💰 Баланс: <b>{format_money(account.balance, account.currency)}</b>\n\n"
        "Выберите действие:"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, state: FSMContext) -> None:
    await state.clear()
    await db.ensure_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await message.answer(
        "Добро пожаловать! Ваш счёт и карта уже открыты. 🎉",
        reply_markup=reply_menu(),
    )
    await message.answer(
        await _menu_text(db, message.from_user.id),
        reply_markup=main_menu(),
    )


@router.message(Command("menu"))
@router.message(F.text == "🏦 Меню")
async def cmd_menu(message: Message, db: Database, state: FSMContext) -> None:
    await state.clear()
    await db.ensure_user(
        message.from_user.id, message.from_user.username, message.from_user.full_name
    )
    await message.answer(await _menu_text(db, message.from_user.id), reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "<b>Доступные команды:</b>\n"
        "/start — регистрация и главное меню\n"
        "/menu — открыть меню\n"
        "/balance — показать баланс\n"
        "/history — история операций\n"
        "/cards — ваши карты\n"
        "/help — эта справка\n\n"
        "Все основные действия удобнее выполнять через кнопки меню.",
        reply_markup=back_menu(),
    )


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery, db: Database, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(
        await _menu_text(db, call.from_user.id), reply_markup=main_menu()
    )
    await call.answer()


# ---------------------------------------------------------------- balance
async def _render_balance(db: Database, tg_id: int) -> str:
    user = await db.get_user_by_tg(tg_id)
    assert user is not None
    account = await db.get_primary_account(user.id)
    assert account is not None
    return (
        "💰 <b>Ваш баланс</b>\n\n"
        f"Счёт: <code>{account.number}</code>\n"
        f"Доступно: <b>{format_money(account.balance, account.currency)}</b>"
    )


@router.callback_query(F.data == "balance")
async def cb_balance(call: CallbackQuery, db: Database) -> None:
    await call.message.edit_text(
        await _render_balance(db, call.from_user.id), reply_markup=back_menu()
    )
    await call.answer()


@router.message(Command("balance"))
async def cmd_balance(message: Message, db: Database) -> None:
    await db.ensure_user(
        message.from_user.id, message.from_user.username, message.from_user.full_name
    )
    await message.answer(
        await _render_balance(db, message.from_user.id), reply_markup=back_menu()
    )


# ---------------------------------------------------------------- history
async def _render_history(db: Database, tg_id: int) -> str:
    user = await db.get_user_by_tg(tg_id)
    assert user is not None
    account = await db.get_primary_account(user.id)
    assert account is not None
    txs = await db.get_transactions(account.id, limit=10)
    if not txs:
        return "📜 <b>История операций</b>\n\nПока пусто. Пополните счёт, чтобы начать."

    lines = ["📜 <b>Последние операции</b>\n"]
    for tx in txs:
        label = KIND_LABELS.get(tx.kind, tx.kind)
        sign = KIND_SIGN.get(tx.kind, "")
        amount = format_money(tx.amount, account.currency)
        line = f"{label}\n{sign}{amount} · {format_dt(tx.created_at)}"
        if tx.counterparty:
            line += f"\nКонтрагент: <code>{tx.counterparty}</code>"
        if tx.description:
            line += f"\n<i>{tx.description}</i>"
        lines.append(line)
    return "\n\n".join(lines)


@router.callback_query(F.data == "history")
async def cb_history(call: CallbackQuery, db: Database) -> None:
    await call.message.edit_text(
        await _render_history(db, call.from_user.id), reply_markup=back_menu()
    )
    await call.answer()


@router.message(Command("history"))
async def cmd_history(message: Message, db: Database) -> None:
    await db.ensure_user(
        message.from_user.id, message.from_user.username, message.from_user.full_name
    )
    await message.answer(
        await _render_history(db, message.from_user.id), reply_markup=back_menu()
    )


# ------------------------------------------------------------------ cards
async def _render_cards(db: Database, tg_id: int) -> str:
    user = await db.get_user_by_tg(tg_id)
    assert user is not None
    account = await db.get_primary_account(user.id)
    assert account is not None
    cards = await db.get_cards(account.id)
    if not cards:
        return "💳 <b>Карты</b>\n\nУ вас пока нет карт."

    lines = ["💳 <b>Ваши карты</b>\n"]
    for card in cards:
        lines.append(
            f"<code>{group_card(card.number)}</code>\n"
            f"Срок: {card.expiry}   Держатель: {card.holder}"
        )
    return "\n\n".join(lines)


@router.callback_query(F.data == "cards")
async def cb_cards(call: CallbackQuery, db: Database) -> None:
    await call.message.edit_text(
        await _render_cards(db, call.from_user.id), reply_markup=cards_menu()
    )
    await call.answer()


@router.message(Command("cards"))
async def cmd_cards(message: Message, db: Database) -> None:
    await db.ensure_user(
        message.from_user.id, message.from_user.username, message.from_user.full_name
    )
    await message.answer(
        await _render_cards(db, message.from_user.id), reply_markup=cards_menu()
    )


@router.callback_query(F.data == "issue_card")
async def cb_issue_card(call: CallbackQuery, db: Database) -> None:
    user = await db.get_user_by_tg(call.from_user.id)
    assert user is not None
    account = await db.get_primary_account(user.id)
    assert account is not None
    cards = await db.get_cards(account.id)
    if len(cards) >= 3:
        await call.answer("Достигнут лимит: не более 3 карт.", show_alert=True)
        return
    card = await db.issue_card(account.id, user.full_name or "CARD HOLDER")
    await call.answer("Карта выпущена!")
    await call.message.edit_text(
        "✅ <b>Новая карта выпущена</b>\n\n"
        f"<code>{group_card(card.number)}</code>\n"
        f"Срок: {card.expiry}   Держатель: {card.holder}\n\n"
        + await _render_cards(db, call.from_user.id),
        reply_markup=cards_menu(),
    )


# ---------------------------------------------------------------- profile
@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery, db: Database) -> None:
    user = await db.get_user_by_tg(call.from_user.id)
    assert user is not None
    account = await db.get_primary_account(user.id)
    assert account is not None
    cards = await db.get_cards(account.id)
    username = f"@{user.username}" if user.username else "—"
    await call.message.edit_text(
        "⚙️ <b>Профиль</b>\n\n"
        f"Имя: {user.full_name or '—'}\n"
        f"Username: {username}\n"
        f"ID: <code>{user.tg_id}</code>\n\n"
        f"Счёт: <code>{account.number}</code>\n"
        f"Карт выпущено: {len(cards)}\n"
        f"Баланс: <b>{format_money(account.balance, account.currency)}</b>",
        reply_markup=back_menu(),
    )
    await call.answer()
