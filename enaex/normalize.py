from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime
from typing import Any

import pandas as pd

EMPTY_MARKERS = {"", "nan", "nat", "none", "null", "n/a", "na", "-", "--"}


def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def normalize_text(value: Any) -> str:
    """Texto comparable: minúsculas, sin tildes y con espacios uniformes."""
    if is_empty(value):
        return ""
    text = strip_accents(str(value)).lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_identifier(value: Any) -> str:
    """Identificador compacto para equipos, patentes y VIN."""
    return re.sub(r"[^a-z0-9]", "", normalize_text(value))


def clean_display(value: Any, default: str = "N/A") -> str:
    if is_empty(value):
        return default
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def is_empty(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    text = str(value).strip().lower()
    return text in EMPTY_MARKERS


def parse_date(value: Any) -> pd.Timestamp | None:
    """Convierte fechas de Excel, datetime o texto a Timestamp normalizado."""
    if is_empty(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.tz_localize(None).normalize() if value.tzinfo else value.normalize()
    if isinstance(value, datetime):
        return pd.Timestamp(value).tz_localize(None).normalize() if value.tzinfo else pd.Timestamp(value).normalize()
    if isinstance(value, date):
        return pd.Timestamp(value).normalize()

    # Fechas seriales de Excel: 1 = 01/01/1900 (con ajuste histórico de Excel).
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if math.isfinite(number) and 20_000 <= number <= 80_000:
            return (pd.Timestamp("1899-12-30") + pd.to_timedelta(number, unit="D")).normalize()

    text = str(value).strip()
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        number = float(text)
        if 20_000 <= number <= 80_000:
            return (pd.Timestamp("1899-12-30") + pd.to_timedelta(number, unit="D")).normalize()

    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    parsed = pd.Timestamp(parsed)
    if parsed.tzinfo:
        parsed = parsed.tz_localize(None)
    return parsed.normalize()


def format_date(value: Any, default: str = "N/A") -> str:
    parsed = parse_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed is not None else default


def normalize_workshop(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return "N/A"
    if "hospicio" in text:
        return "SKC ALTO HOSPICIO"
    if "calama" in text or "mecanical" in text or "mechanical" in text:
        return "SKC CALAMA"
    if "full" in text or "rpm" in text:
        return "FULL RPM"
    if "antofagasta" in text:
        return "SKC ANTOFAGASTA"
    if "rio loa" in text or text == "loa" or "r loa" in text:
        return "RIO LOA"
    if "copiapo" in text:
        return "SKC COPIAPO"
    return clean_display(value).upper()


TERMINAL_STATUS_WORDS = {
    "finalizado",
    "finalizada",
    "terminado",
    "terminada",
    "cerrado",
    "cerrada",
    "cancelado",
    "cancelada",
    "anulado",
    "anulada",
    "entregado",
    "entregada",
    "liberado",
    "liberada",
    "completado",
    "completada",
}


def is_terminal_status(value: Any) -> bool:
    text = normalize_text(value)
    return any(word in text for word in TERMINAL_STATUS_WORDS)
