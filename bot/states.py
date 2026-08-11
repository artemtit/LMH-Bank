"""FSM-состояния диалогов бота."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class DepositState(StatesGroup):
    amount = State()


class WithdrawState(StatesGroup):
    amount = State()


class TransferState(StatesGroup):
    account = State()
    amount = State()
    confirm = State()
