from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

from enaex.normalize import format_date


PREFERRED_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
)


@st.cache_resource(show_spinner=False)
def get_gemini_client(api_key: str) -> genai.Client | None:
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


@st.cache_data(ttl=3600, show_spinner=False)
def resolve_gemini_model(api_key: str, requested_model: str = "") -> tuple[str | None, str | None]:
    """Selecciona el modelo sin bloquear la app por una validación previa frágil.

    La disponibilidad real se valida al generar contenido. Esto evita falsos
    negativos de ``models.get/list`` entre versiones del SDK o proyectos nuevos.
    """
    if not api_key:
        return None, "Falta GEMINI_API_KEY. La aplicación funciona sin IA."

    requested_short = str(requested_model or "").removeprefix("models/").strip()
    if requested_short:
        return requested_short, None
    # Modelo estable recomendado actualmente para proyectos nuevos.
    return PREFERRED_MODELS[0], None



def _generation_candidates(model_name: str) -> list[str]:
    candidates: list[str] = []
    for candidate in (model_name, *PREFERRED_MODELS):
        short = str(candidate or "").removeprefix("models/").strip()
        if short and short not in candidates:
            candidates.append(short)
    return candidates


def _generate_text(
    api_key: str,
    model_name: str,
    prompt: str,
    *,
    system_instruction: str,
    max_output_tokens: int,
) -> tuple[str | None, str | None]:
    """Genera texto y prueba modelos de respaldo solo ante error de modelo.

    No reintenta frente a cuota 429 ni claves inválidas para evitar consumir más
    solicitudes de las necesarias.
    """
    client = get_gemini_client(api_key)
    if client is None:
        return None, "No fue posible crear el cliente de IA."

    last_exc: Exception | None = None
    for candidate in _generation_candidates(model_name):
        try:
            response = client.models.generate_content(
                model=candidate,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=max_output_tokens,
                    system_instruction=system_instruction,
                ),
            )
            text = (response.text or "").strip()
            return (text or None), (None if text else "Gemini respondió sin texto.")
        except Exception as exc:
            last_exc = exc
            lowered = str(exc).lower()
            # Solo pasar al siguiente modelo si el problema es de modelo/no encontrado.
            if "404" in lowered or "not found" in lowered or "model" in lowered and "unsupported" in lowered:
                continue
            return None, friendly_ai_error(exc)

    return None, friendly_ai_error(last_exc or RuntimeError("No hay modelos Gemini disponibles"))

def _record_for_ai(row: pd.Series) -> dict[str, Any]:
    return {
        "equipo": row.get("equipment"),
        "patente": row.get("plate"),
        "vin": row.get("vin"),
        "marca": row.get("brand"),
        "modelo": row.get("model"),
        "sistema_control": row.get("control_system"),
        "faena_actual": row.get("gps_faena"),
        "lugar_actual": row.get("gps_place"),
        "condicion_actual": row.get("gps_condition"),
        "estado_actual": row.get("gps_state"),
        "horas_km_desde_preventivo": row.get("gps_hours"),
        "detalle_estado_equipos": row.get("status_detail"),
        "estatus_movimiento": row.get("movement_status"),
        "taller_planificado": row.get("planned_workshop"),
        "faena_planificada": row.get("planned_faena"),
        "bajada_taller": format_date(row.get("start_date")),
        "subida_faena": format_date(row.get("end_date")),
        "trabajo_movimiento": row.get("movement_comments"),
        "revision_tecnica": format_date(row.get("revision_tecnica")),
        "dias_rt": row.get("revision_tecnica_days"),
        "sernageomin": format_date(row.get("sernageomin")),
        "dias_sernageomin": row.get("sernageomin_days"),
        "dgmn": format_date(row.get("dgmn")),
        "dias_dgmn": row.get("dgmn_days"),
        "ultimos_trabajos": row.get("recent_works", []),
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
Compara el estado actual del sistema de planificación con Mov. equipos y certificaciones.
Si el estado es En proceso, usa obligatoriamente el detalle de Estado de equipos.
Resume también el último trabajo relevante sin inventar ni mezclar otros camiones.
Entrega como máximo 3 líneas por equipo, usando uno de estos estados:
- OK: no se observa una incongruencia evidente.
- REVISAR: explica brevemente la incongruencia o dato crítico.
- SIN DATOS: no hay información suficiente.

Datos ya mostrados en la aplicación:
{json.dumps(payload, ensure_ascii=False, default=str)}
""".strip()

    return _generate_text(
        api_key,
        model_name,
        prompt,
        system_instruction="Eres un auditor técnico. Sé breve, conservador y no inventes información.",
        max_output_tokens=450,
    )



def summarize_work_history(
    api_key: str,
    model_name: str,
    equipment_row: pd.Series,
) -> tuple[str | None, str | None]:
    """Resume únicamente los trabajos históricos ya asociados al camión."""
    if not api_key:
        return None, "La IA está desactivada porque falta GEMINI_API_KEY."
    if not model_name:
        return None, "No existe un modelo Gemini disponible."

    recent = equipment_row.get("recent_works", [])
    if not isinstance(recent, list) or not recent:
        return None, "No hay trabajos históricos suficientes para resumir."

    payload = {
        "equipo": equipment_row.get("equipment"),
        "estado_actual": equipment_row.get("gps_state"),
        "comentario_estado_actual": equipment_row.get("status_detail"),
        "trabajos_historicos": recent,
    }
    prompt = f"""
Analiza exclusivamente el historial técnico del equipo indicado.
No inventes trabajos, causas, repuestos ni fechas.
Agrupa registros repetidos o equivalentes y entrega un punteo claro de 3 a 8 viñetas.
Prioriza: mantenimientos preventivos, correctivos, trabajos documentales, reparaciones y traslados.
Cuando exista fecha válida, inclúyela.
No menciones archivos, hojas, fuentes ni nombres internos de columnas.
Si un texto está incompleto, indícalo como registro incompleto en vez de asumir.

Datos:
{json.dumps(payload, ensure_ascii=False, default=str)}
""".strip()

    return _generate_text(
        api_key,
        model_name,
        prompt,
        system_instruction="Eres un analista de mantenimiento. Resume solo hechos presentes en el historial.",
        max_output_tokens=500,
    )


def analyze_cross_source_discrepancies(
    api_key: str,
    model_name: str,
    discrepancies: pd.DataFrame,
) -> tuple[str | None, str | None]:
    """Prioriza inconsistencias ya calculadas entre planificación/API y Excel."""
    if not api_key:
        return None, "La IA está desactivada porque falta GEMINI_API_KEY."
    if not model_name:
        return None, "No existe un modelo Gemini disponible."
    if discrepancies.empty:
        return None, "No existen discrepancias para analizar."

    safe_columns = [
        column for column in (
            "equipment", "faena", "issue_type", "system_place", "excel_place",
            "system_return_date", "excel_return_date", "date_difference_days", "detail",
        ) if column in discrepancies.columns
    ]
    payload = discrepancies[safe_columns].head(80).to_dict(orient="records")
    prompt = f"""
Actúa como auditor de mantenimiento y consistencia de datos.
La aplicación YA calculó las discrepancias entre el sistema de planificación y el Excel semanal.
Tu tarea es interpretarlas y priorizarlas, no volver a calcularlas.

Reglas obligatorias:
- No inventes fechas, ubicaciones, talleres, estados ni causas.
- Si Sistema = Faena y Excel = Taller, indícalo como posible desalineación operativa.
- Si Sistema = Taller y Excel = Faena, indícalo también como posible desalineación.
- Si las fechas de retorno/entrega son distintas, menciona la diferencia de días entregada por la app.
- Agrupa casos repetidos cuando sea útil.
- Prioriza primero ubicaciones contradictorias y después diferencias de fecha.
- Entrega entre 3 y 12 viñetas, concretas y accionables.
- Recomienda verificar el dato en origen; no decidas cuál fuente es correcta si la evidencia no lo permite.

Discrepancias detectadas:
{json.dumps(payload, ensure_ascii=False, default=str)}
""".strip()

    return _generate_text(
        api_key,
        model_name,
        prompt,
        system_instruction=(
            "Eres un auditor técnico conservador. Solo interpretas discrepancias previamente calculadas y nunca inventas datos."
        ),
        max_output_tokens=800,
    )

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


def suggest_workshop_capacity(
    api_key: str,
    model_name: str,
    projection: pd.DataFrame,
    movements: pd.DataFrame,
    week_start: pd.Timestamp,
    week_end: pd.Timestamp,
) -> tuple[str | None, str | None]:
    """Pide a Gemini una recomendación breve sin permitir que altere las cifras calculadas."""
    if not api_key:
        return None, "La IA está desactivada porque falta GEMINI_API_KEY."
    if not model_name:
        return None, "No existe un modelo Gemini disponible."
    if projection.empty:
        return None, "No existe una proyección de capacidad para analizar."

    capacity_payload = []
    for _, row in projection.iterrows():
        limit = row.get("limit")
        available = row.get("available_at_peak")
        capacity_payload.append(
            {
                "taller": row.get("workshop"),
                "capacidad_maxima": None if pd.isna(limit) else int(limit),
                "equipos_actuales_segun_lugar_api": int(row.get("current", 0)),
                "equipos_al_inicio_proyectado": int(row.get("opening", 0)),
                "bajadas_semana": int(row.get("downs", 0)),
                "subidas_semana": int(row.get("ups", 0)),
                "maximo_proyectado": int(row.get("peak", 0)),
                "cierre_semana": int(row.get("closing", 0)),
                "sobre_capacidad": int(row.get("over_capacity", 0)),
                "cupos_libres_en_peak": None if pd.isna(available) else int(available),
                "equipos_actuales": row.get("current_equipment", []),
                "equipos_en_peak": row.get("peak_equipment", []),
                "lugares_externos_detectados": row.get("external_locations", []),
            }
        )

    movement_payload = []
    if not movements.empty:
        mask = (
            movements["start_date"].between(week_start, week_end, inclusive="both")
            | movements["end_date"].between(week_start, week_end, inclusive="both")
        )
        for _, row in movements.loc[mask].iterrows():
            movement_payload.append(
                {
                    "equipo": row.get("equipment"),
                    "bajada": format_date(row.get("start_date")),
                    "taller": row.get("workshop"),
                    "subida": format_date(row.get("end_date")),
                    "faena": row.get("faena"),
                    "estatus": row.get("status"),
                    "trabajo": row.get("comments"),
                }
            )

    prompt = f"""
Actúa como planificador de mantenimiento de flota minera.
Analiza exclusivamente las cifras calculadas por la aplicación para la semana
{format_date(week_start)} al {format_date(week_end)}.

Reglas obligatorias:
- No inventes capacidades, fechas, talleres, distancias ni disponibilidad.
- No propongas enviar equipos a un taller que tenga 0 cupos libres en el peak.
- La ocupación actual proviene de la columna Lugar de la API y debe tratarse como fuente de verdad de hoy.
- “TALLERES EXTERNOS” no tiene capacidad máxima configurada: menciónalo, pero no lo uses como destino sugerido.
- Si un taller queda sobre capacidad, indica cuántos equipos conviene evaluar para reasignar.
- Prioriza una solución práctica y breve, pero aclara que debe validarse compatibilidad técnica,
  distancia, repuestos y autorización operacional.
- Si no existe sobrecapacidad, indica que no se requiere redistribución y menciona el principal riesgo de la semana.
- Entrega como máximo 8 líneas y usa viñetas.

Proyección por taller:
{json.dumps(capacity_payload, ensure_ascii=False, default=str)}

Movimientos de la semana, provenientes únicamente de la hoja Mov. equipos:
{json.dumps(movement_payload, ensure_ascii=False, default=str)}
""".strip()

    return _generate_text(
        api_key,
        model_name,
        prompt,
        system_instruction="Eres un planificador técnico conservador. No alteres cifras ni inventes datos.",
        max_output_tokens=550,
    )
