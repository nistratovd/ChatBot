from html import escape
from re import Pattern, compile
from typing import Any

CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
SENSITIVE_URL_RE: Pattern[str] = compile(r"(postgres(?:ql)?://[^:/\s]+:)([^@\s]+)(@)")


def escape_html_text(value: str) -> str:
    """Экранирует пользовательский/контентный текст перед отправкой в Telegram HTML."""

    return escape(value, quote=False)


def sanitize_csv_cell(value: Any) -> str:
    """Готовит значение для CSV и блокирует spreadsheet formula injection."""

    text = format_plain_value(value)
    if text.startswith(CSV_FORMULA_PREFIXES):
        return f"'{text}"
    return text


def format_plain_value(value: Any) -> str:
    """Преобразует значение в однострочный безопасный текст для отчётов."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat(timespec="seconds")
        except TypeError:
            return value.isoformat()
    return str(value).replace("\r", " ").replace("\n", " ")


def mask_sensitive_text(value: str) -> str:
    """Маскирует пароль в PostgreSQL DSN внутри диагностического текста."""

    return SENSITIVE_URL_RE.sub(r"\1***\3", value)
