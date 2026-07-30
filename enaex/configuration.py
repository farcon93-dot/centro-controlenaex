from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Mapping


DEFAULT_EXCEL_URLS = (
    "https://docs.google.com/spreadsheets/d/1PUlnTUm_CpkvrpVoKJN_3nyD9khxITDV/edit?usp=sharing",
    "https://docs.google.com/spreadsheets/d/1VrDHEb-D7oeypyYdhUpd3_tw_jggTu3K/edit?usp=drive_link&ouid=112672268024787990541&rtpof=true&sd=true",
)

CONTRACT_TARGETS = {
    "Centinela": 13,
    "Collahuasi": 6,
    "Los Bronces": 7,
    "Los Pelambres": 5,
    "Nueva Centinela": 3,
    "Radomiro Tomic": 5,
    "Sierra Gorda": 6,
    "Spence": 5,
    "Andina": 5,
    "Antucoya": 3,
    "Chuquicamata": 2,
    "Lomas Bayas": 5,
    "Los Colorados": 3,
    "Salvador": 4,
    "Teniente": 1,
    "Zaldivar": 2,
    "Cerro Negro": 1,
    "El Soldado": 2,
    "Michilla": 1,
    "Pleito": 1,
    "Romeral": 1,
    "Salares Norte": 1,
}

WORKSHOP_CAPACITY = {
    "SKC ALTO HOSPICIO": 2,
    "SKC CALAMA": 4,
    "SKC ANTOFAGASTA": 2,
    "RIO LOA": 2,
    "SKC COPIAPO": 2,
    "FULL RPM": 4,
}

GPS_TYPES = (27, 26, 24, 21, 23, 41)
GPS_ZONES = tuple(range(1, 14))


@dataclass(frozen=True)
class Settings:
    excel_urls: tuple[str, ...]
    gps_base_url: str
    gps_api_key: str
    gemini_api_key: str
    gemini_model: str
    cache_ttl_seconds: int
    gps_timeout_seconds: int
    gps_workers: int


def _mapping_get(mapping: Mapping[str, Any] | None, key: str, default: Any = "") -> Any:
    if mapping is None:
        return default
    try:
        return mapping.get(key, default)
    except Exception:
        return default


def load_settings(secrets: Mapping[str, Any] | None = None) -> Settings:
    secret_urls = _mapping_get(secrets, "EXCEL_URLS", None)
    if secret_urls:
        excel_urls = tuple(str(url).strip() for url in secret_urls if str(url).strip())
    else:
        env_urls = os.getenv("EXCEL_URLS", "")
        excel_urls = tuple(url.strip() for url in env_urls.split("|") if url.strip()) or DEFAULT_EXCEL_URLS

    return Settings(
        excel_urls=excel_urls,
        gps_base_url=str(
            _mapping_get(secrets, "GPS_BASE_URL", os.getenv("GPS_BASE_URL", "http://40.65.224.42/api/dashboard/estado"))
        ).rstrip("/"),
        gps_api_key=str(_mapping_get(secrets, "GPS_API_KEY", os.getenv("GPS_API_KEY", ""))).strip(),
        gemini_api_key=str(_mapping_get(secrets, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))).strip(),
        gemini_model=str(_mapping_get(secrets, "GEMINI_MODEL", os.getenv("GEMINI_MODEL", ""))).strip(),
        cache_ttl_seconds=int(_mapping_get(secrets, "CACHE_TTL_SECONDS", os.getenv("CACHE_TTL_SECONDS", "300"))),
        gps_timeout_seconds=int(_mapping_get(secrets, "GPS_TIMEOUT_SECONDS", os.getenv("GPS_TIMEOUT_SECONDS", "6"))),
        gps_workers=int(_mapping_get(secrets, "GPS_WORKERS", os.getenv("GPS_WORKERS", "16"))),
    )
