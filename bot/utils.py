"""Вспомогательные функции: работа с деньгами, форматирование, маскировка."""
from __future__ import annotations

from datetime import datetime, timezone

KIND_LABELS = {
    "deposit": "📥 Пополнение",
    "withdraw": "📤 Снятие",
    "transfer_in": "⬅️ Входящий перевод",
    "transfer_out": "➡️ Исходящий перевод",
}

KIND_SIGN = {
    "deposit": "+",
    "withdraw": "−",
    "transfer_in": "+",
    "transfer_out": "−",
}


def parse_amount(text: str) -> int:
    """Парсит введённую пользователем сумму в рублях в копейки.

    Принимает "1000", "1000.50", "1000,50", "1 000". Бросает ValueError
    при некорректном или неположительном значении.
    """
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        raise ValueError("Пустая сумма.")
    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError("Не удалось распознать сумму. Введите число, например 1500.")
    if value <= 0:
        raise ValueError("Сумма должна быть больше нуля.")
    kopecks = round(value * 100)
    if kopecks <= 0:
        raise ValueError("Сумма слишком мала.")
    if kopecks > 10_000_000_000:  # 100 млн руб. — защита от опечаток
        raise ValueError("Сумма слишком велика.")
    return kopecks


def format_money(kopecks: int, currency: str = "RUB") -> str:
    """Форматирует копейки в вид '1 234.56 ₽'."""
    sign = "-" if kopecks < 0 else ""
    kopecks = abs(kopecks)
    rubles, coins = divmod(kopecks, 100)
    symbol = {"RUB": "₽", "USD": "$", "EUR": "€"}.get(currency, currency)
    rub_str = f"{rubles:,}".replace(",", " ")
    return f"{sign}{rub_str}.{coins:02d} {symbol}"


def mask_card(number: str) -> str:
    """Возвращает номер карты в виде '4111 •••• •••• 1234'."""
    if len(number) < 8:
        return number
    return f"{number[:4]} •••• •••• {number[-4:]}"


def group_card(number: str) -> str:
    """Разбивает номер карты по 4 цифры: '4111 1111 1111 1111'."""
    return " ".join(number[i : i + 4] for i in range(0, len(number), 4))


def format_dt(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d.%m.%Y %H:%M")
