from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

from enaex.normalize import format_date


PREFERRED_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
)


@st.cache_resource(show_spinner=False)
def get_gemini_client(api_key: str) -> genai.Client | None:
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


@st.cache_data(ttl=3600, show_spinner=False)
def resolve_gemini_model(api_key: str, requested_model: str = "") -> tuple[str | None, str | None]:
    if not api_key:
        return None, "Falta GEMINI_API_KEY. La aplicación funciona sin IA."
    try:
        client = genai.Client(api_key=api_key)
        available: list[str] = []
        for model in client.models.list(config={"page_size": 100}):
            name = str(getattr(model, "name", ""))
            short_name = name.removeprefix("models/")
            actions = [str(action).lower() for action in (getattr(model, "supported_actions", None) or [])]
            supports_generation = not actions or any("generate" in action for action in actions)
            if "gemini" in short_name.lower() and supports_generation and "embedding" not in short_name.lower():
                available.append(short_name)
        client.close()

        if requested_model:
            requested_short = requested_model.removeprefix("models/")
            if requested_short in available:
                return requested_short, None
            return None, f"El modelo configurado '{requested_model}' no está disponible para esta API key."

        for preferred in PREFERRED_MODELS:
            if preferred in available:
                return preferred, None
        flash_models = sorted(model for model in available if "flash" in model.lower() and "image" not in model.lower())
        if flash_models:
            return flash_models[-1], None
        return (available[0], None) if available else (None, "La API key no tiene modelos Gemini de texto disponibles.")
    except Exception as exc:
        return None, friendly_ai_error(exc)


def _record_for_ai(row: pd.Series) -> dict[str, Any]:
    return {
        "equipo": row.get("equipment"),
        "patente": row.get("plate"),
        "vin": row.get("vin"),
        "ubicacion_gps": row.get("gps_faena"),
        "estado_gps": row.get("gps_state"),
        "horometro_gps": row.get("gps_hours"),
        "estatus_planificacion": row.get("status"),
        "taller_planificado": row.get("workshop"),
        "faena_planificada": row.get("planned_faena"),
        "bajada_taller": format_date(row.get("start_date")),
        "subida_faena": format_date(row.get("end_date")),
        "revision_tecnica": format_date(row.get("revision_tecnica")),
        "sernageomin": format_date(row.get("sernageomin")),
        "dgmn": format_date(row.get("dgmn")),
        "comentarios": row.get("comments"),
    }


def audit_equipment(
    api_key: str,
    model_name: str,
    equipment_rows: pd.DataFrame,
) -> tuple[str | None, str | None]:
    if not api_key:
        return None, "La IA está desactivada porque falta GEMINI_API_KEY."
    if not model_name:
        return None, "No existe un modelo Gemini disponible."
    if equipment_rows.empty:
        return None, "No hay equipos para auditar."

    payload = [_record_for_ai(row) for _, row in equipment_rows.iterrows()]
    prompt = f"""
Actúa exclusivamente como auditor de consistencia de una flota minera.
No inventes datos, no completes valores faltantes y no repitas toda la ficha.
Compara la planificación Excel con la ubicación/estado GPS y revisa fechas/certificaciones.
Entrega como máximo 2 líneas por equipo, usando uno de estos estados:
- OK: no se observa una incongruencia evidente.
- REVISAR: explica brevemente la incongruencia o dato crítico.
- SIN DATOS: no hay información suficiente.

Datos ya mostrados en la aplicación:
{json.dumps(payload, ensure_ascii=False, default=str)}
""".strip()

    try:
        client = get_gemini_client(api_key)
        if client is None:
            return None, "No fue posible crear el cliente de IA."
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=450,
                system_instruction=(
                    "Eres un auditor técnico. Sé breve, conservador y no inventes información."
                ),
            ),
        )
        text = (response.text or "").strip()
        return (text or None), (None if text else "Gemini respondió sin texto.")
    except Exception as exc:
        return None, friendly_ai_error(exc)


def friendly_ai_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "429" in lowered or "quota" in lowered or "resource_exhausted" in lowered:
        return "Gemini alcanzó su cuota o límite temporal. Los datos de Excel y GPS siguen funcionando normalmente."
    if "404" in lowered or "not found" in lowered:
        return "El modelo Gemini configurado ya no está disponible. Recarga la app para que detecte otro modelo."
    if "api key" in lowered or "permission" in lowered or "403" in lowered:
        return "La clave Gemini no es válida o no tiene permiso para usar el modelo."
    if "timeout" in lowered or "timed out" in lowered:
        return "Gemini demoró demasiado en responder. Intenta nuevamente más tarde."
    return f"La auditoría IA no pudo ejecutarse: {text[:220]}"
