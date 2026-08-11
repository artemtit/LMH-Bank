"""Слой доступа к данным на базе SQLite (aiosqlite).

Здесь описаны все таблицы и операции банка: пользователи, счета, карты,
транзакции. Денежные суммы хранятся в копейках (целые числа), чтобы
избежать проблем с округлением чисел с плавающей точкой.
"""
from __future__ import annotations

import os
import random
import secrets
import time
from dataclasses import dataclass

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id       INTEGER UNIQUE NOT NULL,
    username    TEXT,
    full_name   TEXT,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    number      TEXT UNIQUE NOT NULL,
    balance     INTEGER NOT NULL DEFAULT 0,
    currency    TEXT NOT NULL DEFAULT 'RUB',
    created_at  INTEGER NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS cards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL,
    number      TEXT UNIQUE NOT NULL,
    expiry      TEXT NOT NULL,
    holder      TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts (id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id    INTEGER NOT NULL,
    kind          TEXT NOT NULL,           -- deposit | withdraw | transfer_in | transfer_out
    amount        INTEGER NOT NULL,        -- в копейках, всегда > 0
    balance_after INTEGER NOT NULL,
    counterparty  TEXT,
    description   TEXT,
    created_at    INTEGER NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts (id)
);

CREATE INDEX IF NOT EXISTS idx_tx_account ON transactions (account_id, created_at DESC);
"""


@dataclass
class User:
    id: int
    tg_id: int
    username: str | None
    full_name: str | None


@dataclass
class Account:
    id: int
    user_id: int
    number: str
    balance: int
    currency: str


@dataclass
class Card:
    id: int
    account_id: int
    number: str
    expiry: str
    holder: str


@dataclass
class Transaction:
    id: int
    account_id: int
    kind: str
    amount: int
    balance_after: int
    counterparty: str | None
    description: str | None
    created_at: int


class Database:
    """Тонкая обёртка над aiosqlite с бизнес-операциями банка."""

    def __init__(self, path: str):
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("База данных не подключена. Вызовите connect() сначала.")
        return self._db

    # ----------------------------------------------------------------- users
    async def get_user_by_tg(self, tg_id: int) -> User | None:
        async with self.db.execute(
            "SELECT id, tg_id, username, full_name FROM users WHERE tg_id = ?",
            (tg_id,),
        ) as cur:
            row = await cur.fetchone()
        return User(**dict(row)) if row else None

    async def create_user(
        self, tg_id: int, username: str | None, full_name: str | None
    ) -> User:
        """Создаёт пользователя, его основной счёт и виртуальную карту."""
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO users (tg_id, username, full_name, created_at) VALUES (?, ?, ?, ?)",
            (tg_id, username, full_name, now),
        )
        await self.db.commit()
        user = await self.get_user_by_tg(tg_id)
        assert user is not None
        account = await self._create_account(user.id)
        await self._create_card(account.id, full_name or "CARD HOLDER")
        return user

    async def ensure_user(
        self, tg_id: int, username: str | None, full_name: str | None
    ) -> User:
        user = await self.get_user_by_tg(tg_id)
        if user is None:
            return await self.create_user(tg_id, username, full_name)
        # обновляем изменившиеся данные профиля
        if user.username != username or user.full_name != full_name:
            await self.db.execute(
                "UPDATE users SET username = ?, full_name = ? WHERE id = ?",
                (username, full_name, user.id),
            )
            await self.db.commit()
            user.username = username
            user.full_name = full_name
        return user

    # -------------------------------------------------------------- accounts
    async def _create_account(self, user_id: int) -> Account:
        number = await self._unique_account_number()
        now = int(time.time())
        cur = await self.db.execute(
            "INSERT INTO accounts (user_id, number, balance, currency, created_at) "
            "VALUES (?, ?, 0, 'RUB', ?)",
            (user_id, number, now),
        )
        await self.db.commit()
        return Account(
            id=cur.lastrowid, user_id=user_id, number=number, balance=0, currency="RUB"
        )

    async def _unique_account_number(self) -> str:
        while True:
            number = "40817" + "".join(str(random.randint(0, 9)) for _ in range(15))
            async with self.db.execute(
                "SELECT 1 FROM accounts WHERE number = ?", (number,)
            ) as cur:
                if await cur.fetchone() is None:
                    return number

    async def get_primary_account(self, user_id: int) -> Account | None:
        async with self.db.execute(
            "SELECT id, user_id, number, balance, currency FROM accounts "
            "WHERE user_id = ? ORDER BY id LIMIT 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        return Account(**dict(row)) if row else None

    async def get_account_by_number(self, number: str) -> Account | None:
        async with self.db.execute(
            "SELECT id, user_id, number, balance, currency FROM accounts WHERE number = ?",
            (number,),
        ) as cur:
            row = await cur.fetchone()
        return Account(**dict(row)) if row else None

    # ------------------------------------------------------------------ cards
    async def _create_card(self, account_id: int, holder: str) -> Card:
        number = await self._unique_card_number()
        # срок действия — примерно 4 года от текущей даты
        exp_month = random.randint(1, 12)
        exp_year = (time.gmtime().tm_year + 4) % 100
        expiry = f"{exp_month:02d}/{exp_year:02d}"
        now = int(time.time())
        holder_norm = _latinize_holder(holder)
        cur = await self.db.execute(
            "INSERT INTO cards (account_id, number, expiry, holder, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (account_id, number, expiry, holder_norm, now),
        )
        await self.db.commit()
        return Card(
            id=cur.lastrowid,
            account_id=account_id,
            number=number,
            expiry=expiry,
            holder=holder_norm,
        )

    async def _unique_card_number(self) -> str:
        while True:
            number = _generate_card_number()
            async with self.db.execute(
                "SELECT 1 FROM cards WHERE number = ?", (number,)
            ) as cur:
                if await cur.fetchone() is None:
                    return number

    async def get_cards(self, account_id: int) -> list[Card]:
        async with self.db.execute(
            "SELECT id, account_id, number, expiry, holder FROM cards "
            "WHERE account_id = ? ORDER BY id",
            (account_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [Card(**dict(r)) for r in rows]

    async def issue_card(self, account_id: int, holder: str) -> Card:
        return await self._create_card(account_id, holder)

    # ----------------------------------------------------------- operations
    async def deposit(self, account_id: int, amount: int, description: str = "") -> int:
        """Пополнение счёта. Возвращает новый баланс."""
        return await self._apply_delta(
            account_id, amount, "deposit", None, description or "Пополнение"
        )

    async def withdraw(self, account_id: int, amount: int, description: str = "") -> int:
        """Снятие со счёта. Возвращает новый баланс. Бросает ValueError при нехватке средств."""
        return await self._apply_delta(
            account_id, -amount, "withdraw", None, description or "Снятие наличных"
        )

    async def transfer(
        self, from_account_id: int, to_number: str, amount: int, description: str = ""
    ) -> tuple[int, Account]:
        """Перевод между счетами в одной транзакции.

        Возвращает (новый баланс отправителя, счёт получателя).
        """
        if amount <= 0:
            raise ValueError("Сумма перевода должна быть положительной.")

        to_account = await self.get_account_by_number(to_number)
        if to_account is None:
            raise ValueError("Счёт получателя не найден.")
        if to_account.id == from_account_id:
            raise ValueError("Нельзя переводить самому себе на тот же счёт.")

        now = int(time.time())
        try:
            await self.db.execute("BEGIN")
            from_acc = await self._locked_account(from_account_id)
            if from_acc.balance < amount:
                raise ValueError("Недостаточно средств на счёте.")

            from_after = from_acc.balance - amount
            to_after = to_account.balance + amount

            await self.db.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?", (from_after, from_acc.id)
            )
            await self.db.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?", (to_after, to_account.id)
            )
            await self._insert_tx(
                from_acc.id, "transfer_out", amount, from_after,
                to_account.number, description or "Перевод", now,
            )
            await self._insert_tx(
                to_account.id, "transfer_in", amount, to_after,
                from_acc.number, description or "Перевод", now,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return from_after, to_account

    async def _apply_delta(
        self,
        account_id: int,
        delta: int,
        kind: str,
        counterparty: str | None,
        description: str,
    ) -> int:
        if delta == 0:
            raise ValueError("Сумма должна быть положительной.")
        now = int(time.time())
        try:
            await self.db.execute("BEGIN")
            acc = await self._locked_account(account_id)
            new_balance = acc.balance + delta
            if new_balance < 0:
                raise ValueError("Недостаточно средств на счёте.")
            await self.db.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?", (new_balance, account_id)
            )
            await self._insert_tx(
                account_id, kind, abs(delta), new_balance, counterparty, description, now
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        return new_balance

    async def _locked_account(self, account_id: int) -> Account:
        async with self.db.execute(
            "SELECT id, user_id, number, balance, currency FROM accounts WHERE id = ?",
            (account_id,),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise ValueError("Счёт не найден.")
        return Account(**dict(row))

    async def _insert_tx(
        self,
        account_id: int,
        kind: str,
        amount: int,
        balance_after: int,
        counterparty: str | None,
        description: str,
        created_at: int,
    ) -> None:
        await self.db.execute(
            "INSERT INTO transactions "
            "(account_id, kind, amount, balance_after, counterparty, description, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (account_id, kind, amount, balance_after, counterparty, description, created_at),
        )

    async def get_transactions(
        self, account_id: int, limit: int = 10
    ) -> list[Transaction]:
        async with self.db.execute(
            "SELECT id, account_id, kind, amount, balance_after, counterparty, "
            "description, created_at FROM transactions "
            "WHERE account_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (account_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [Transaction(**dict(r)) for r in rows]


# --------------------------------------------------------------------- utils
def _generate_card_number() -> str:
    """Генерирует 16-значный номер карты, валидный по алгоритму Луна.

    Начинается с 4 (как у Visa) — исключительно для наглядности демо-карты.
    """
    prefix = [4] + [secrets.randbelow(10) for _ in range(14)]
    check = _luhn_check_digit(prefix)
    digits = prefix + [check]
    return "".join(str(d) for d in digits)


def _luhn_check_digit(digits: list[int]) -> int:
    total = 0
    # digits — 15 цифр, контрольная будет 16-й; нумерация чётности справа
    for i, d in enumerate(reversed(digits)):
        # позиция контрольной цифры = 0 справа, поэтому текущие начинаются с 1
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (10 - (total % 10)) % 10


def _latinize_holder(name: str) -> str:
    """Простейшая транслитерация имени в верхний регистр для «карты»."""
    table = {
        "а": "A", "б": "B", "в": "V", "г": "G", "д": "D", "е": "E", "ё": "E",
        "ж": "ZH", "з": "Z", "и": "I", "й": "Y", "к": "K", "л": "L", "м": "M",
        "н": "N", "о": "O", "п": "P", "р": "R", "с": "S", "т": "T", "у": "U",
        "ф": "F", "х": "H", "ц": "TS", "ч": "CH", "ш": "SH", "щ": "SCH",
        "ъ": "", "ы": "Y", "ь": "", "э": "E", "ю": "YU", "я": "YA",
    }
    result = []
    for ch in name.lower():
        if ch in table:
            result.append(table[ch])
        elif ch.isascii() and (ch.isalpha() or ch == " "):
            result.append(ch.upper())
        elif ch == " ":
            result.append(" ")
    holder = "".join(result).strip()
    return holder[:26] or "CARD HOLDER"
