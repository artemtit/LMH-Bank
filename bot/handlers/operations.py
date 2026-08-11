"""Диалоговые операции: пополнение, снятие, перевод (через FSM)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ..database import Database
from ..keyboards import back_menu, cancel_menu
from ..states import DepositState, TransferState, WithdrawState
from ..utils import format_money, parse_amount

router = Router(name="operations")


# ------------------------------------------------------------- отмена
@router.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("Операция отменена.", reply_markup=back_menu())
    await call.answer()


# ------------------------------------------------------------- пополнение
@router.callback_query(F.data == "deposit")
async def cb_deposit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DepositState.amount)
    await call.message.edit_text(
        "📥 <b>Пополнение счёта</b>\n\nВведите сумму в рублях (например, 5000):",
        reply_markup=cancel_menu(),
    )
    await call.answer()


@router.message(DepositState.amount)
async def deposit_amount(message: Message, state: FSMContext, db: Database) -> None:
    try:
        amount = parse_amount(message.text or "")
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}\nПопробуйте ещё раз:", reply_markup=cancel_menu())
        return

    user = await db.get_user_by_tg(message.from_user.id)
    account = await db.get_primary_account(user.id)
    new_balance = await db.deposit(account.id, amount)
    await state.clear()
    await message.answer(
        f"✅ Счёт пополнен на <b>{format_money(amount)}</b>.\n"
        f"Текущий баланс: <b>{format_money(new_balance)}</b>",
        reply_markup=back_menu(),
    )


# ------------------------------------------------------------- снятие
@router.callback_query(F.data == "withdraw")
async def cb_withdraw(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(WithdrawState.amount)
    await call.message.edit_text(
        "📤 <b>Снятие средств</b>\n\nВведите сумму в рублях:",
        reply_markup=cancel_menu(),
    )
    await call.answer()


@router.message(WithdrawState.amount)
async def withdraw_amount(message: Message, state: FSMContext, db: Database) -> None:
    try:
        amount = parse_amount(message.text or "")
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}\nПопробуйте ещё раз:", reply_markup=cancel_menu())
        return

    user = await db.get_user_by_tg(message.from_user.id)
    account = await db.get_primary_account(user.id)
    try:
        new_balance = await db.withdraw(account.id, amount)
    except ValueError as exc:
        await state.clear()
        await message.answer(f"❌ {exc}", reply_markup=back_menu())
        return

    await state.clear()
    await message.answer(
        f"✅ Снято <b>{format_money(amount)}</b>.\n"
        f"Текущий баланс: <b>{format_money(new_balance)}</b>",
        reply_markup=back_menu(),
    )


# ------------------------------------------------------------- перевод
@router.callback_query(F.data == "transfer")
async def cb_transfer(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TransferState.account)
    await call.message.edit_text(
        "💸 <b>Перевод по номеру счёта</b>\n\n"
        "Введите 20-значный номер счёта получателя:",
        reply_markup=cancel_menu(),
    )
    await call.answer()


@router.message(TransferState.account)
async def transfer_account(message: Message, state: FSMContext, db: Database) -> None:
    number = (message.text or "").strip().replace(" ", "")
    if not (number.isdigit() and len(number) == 20):
        await message.answer(
            "⚠️ Номер счёта должен состоять из 20 цифр. Попробуйте ещё раз:",
            reply_markup=cancel_menu(),
        )
        return

    to_account = await db.get_account_by_number(number)
    if to_account is None:
        await message.answer(
            "❌ Счёт с таким номером не найден. Проверьте номер и введите снова:",
            reply_markup=cancel_menu(),
        )
        return

    user = await db.get_user_by_tg(message.from_user.id)
    from_account = await db.get_primary_account(user.id)
    if to_account.id == from_account.id:
        await message.answer(
            "⚠️ Нельзя переводить на свой же счёт. Введите другой номер:",
            reply_markup=cancel_menu(),
        )
        return

    await state.update_data(to_number=number)
    await state.set_state(TransferState.amount)
    await message.answer(
        f"Получатель найден: <code>{number}</code>\n\nВведите сумму перевода в рублях:",
        reply_markup=cancel_menu(),
    )


@router.message(TransferState.amount)
async def transfer_amount(message: Message, state: FSMContext, db: Database) -> None:
    try:
        amount = parse_amount(message.text or "")
    except ValueError as exc:
        await message.answer(f"⚠️ {exc}\nПопробуйте ещё раз:", reply_markup=cancel_menu())
        return

    user = await db.get_user_by_tg(message.from_user.id)
    from_account = await db.get_primary_account(user.id)
    if from_account.balance < amount:
        await message.answer(
            f"❌ Недостаточно средств. Доступно: {format_money(from_account.balance)}.\n"
            "Введите меньшую сумму:",
            reply_markup=cancel_menu(),
        )
        return

    data = await state.get_data()
    to_number = data["to_number"]
    await state.update_data(amount=amount)
    await state.set_state(TransferState.confirm)

    confirm_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="transfer_ok"),
                InlineKeyboardButton(text="✖️ Отмена", callback_data="cancel"),
            ]
        ]
    )
    await message.answer(
        "🔎 <b>Проверьте перевод</b>\n\n"
        f"Получатель: <code>{to_number}</code>\n"
        f"Сумма: <b>{format_money(amount)}</b>\n\n"
        "Подтвердить операцию?",
        reply_markup=confirm_kb,
    )


@router.callback_query(TransferState.confirm, F.data == "transfer_ok")
async def transfer_confirm(call: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    to_number = data["to_number"]
    amount = data["amount"]

    user = await db.get_user_by_tg(call.from_user.id)
    from_account = await db.get_primary_account(user.id)
    try:
        new_balance, _to_account = await db.transfer(from_account.id, to_number, amount)
    except ValueError as exc:
        await state.clear()
        await call.message.edit_text(f"❌ {exc}", reply_markup=back_menu())
        await call.answer()
        return

    await state.clear()
    await call.message.edit_text(
        f"✅ Перевод на <b>{format_money(amount)}</b> выполнен.\n"
        f"Счёт получателя: <code>{to_number}</code>\n"
        f"Ваш баланс: <b>{format_money(new_balance)}</b>",
        reply_markup=back_menu(),
    )
    await call.answer("Готово!")
