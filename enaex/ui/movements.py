from __future__ import annotations

import pandas as pd
import streamlit as st

from enaex.ai_service import suggest_workshop_capacity
from enaex.configuration import Settings
from enaex.models import ApplicationData
from enaex.normalize import format_date
from enaex.processing import (
    build_rebalancing_recommendations,
    build_weekly_workshop_projection,
)


CAPACITY_AI_KEY = "enaex_capacity_ai_result"
CAPACITY_AI_WEEK_KEY = "enaex_capacity_ai_week"


def _movement_display(frame: pd.DataFrame, date_column: str, destination_column: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame[["equipment", date_column, destination_column, "status", "comments"]].copy()
    display[date_column] = display[date_column].map(format_date)
    return display.rename(
        columns={
            "equipment": "Equipo",
            date_column: "Fecha",
            destination_column: "Destino",
            "status": "Estatus",
            "comments": "Comentario / Trabajo",
        }
    )


def _projection_display(projection: pd.DataFrame) -> pd.DataFrame:
    display = projection[
        ["workshop", "limit", "opening", "downs", "ups", "peak", "closing", "status"]
    ].copy()
    return display.rename(
        columns={
            "workshop": "Taller",
            "limit": "Capacidad máxima",
            "opening": "Equipos al inicio",
            "downs": "Bajan en la semana",
            "ups": "Suben en la semana",
            "peak": "Máximo proyectado",
            "closing": "Cierre de semana",
            "status": "Estado",
        }
    )


def render_movements_page(
    data: ApplicationData,
    settings: Settings,
    ai_model: str | None,
) -> None:
    st.header("📅 Control semanal de Subidas, Bajadas y Capacidad")
    st.caption(
        "Las fechas de esta pantalla provienen únicamente del Excel de planificación semanal, "
        "pestaña **Mov. equipos**. Se muestra una sola bajada y una sola subida por camión."
    )

    selected_day = pd.Timestamp(
        st.date_input(
            "Selecciona cualquier día de la semana que deseas analizar",
            value=pd.Timestamp.now().date(),
        )
    ).normalize()
    week_start = selected_day - pd.Timedelta(days=int(selected_day.weekday()))
    week_end = week_start + pd.Timedelta(days=6)
    st.info(f"Semana analizada: **{format_date(week_start)} al {format_date(week_end)}**")

    if data.movements.empty:
        st.warning(
            "No se detectaron movimientos válidos en una hoja llamada “Mov. equipos”. "
            "Revisa en la barra lateral → Hojas Excel cargadas que esa pestaña esté presente."
        )
        return

    date_issues = data.movements[data.movements.get("date_issue", "").astype(str).ne("")]
    if not date_issues.empty:
        st.warning(
            f"Se detectaron {len(date_issues)} equipo(s) con fecha de subida anterior a la bajada. "
            "Estos registros deben revisarse en Mov. equipos."
        )

    down = data.movements[
        data.movements["start_date"].notna()
        & data.movements["start_date"].between(week_start, week_end, inclusive="both")
    ].sort_values(["start_date", "equipment"])
    up = data.movements[
        data.movements["end_date"].notna()
        & data.movements["end_date"].between(week_start, week_end, inclusive="both")
    ].sort_values(["end_date", "equipment"])

    left, right = st.columns(2)
    with left:
        st.subheader("📉 Bajan a taller")
        if down.empty:
            st.success("No hay bajadas registradas para esta semana.")
        else:
            st.dataframe(
                _movement_display(down, "start_date", "workshop"),
                hide_index=True,
                use_container_width=True,
            )

    with right:
        st.subheader("⛰️ Suben o se entregan a faena")
        if up.empty:
            st.info("No hay subidas registradas para esta semana.")
        else:
            st.dataframe(
                _movement_display(up, "end_date", "faena"),
                hide_index=True,
                use_container_width=True,
            )

    st.divider()
    st.subheader("⚖️ Proyección de capacidad de talleres para la semana")
    projection = build_weekly_workshop_projection(data.movements, week_start)

    if projection.empty:
        st.info("No fue posible calcular la proyección de capacidad.")
        return

    st.dataframe(
        _projection_display(projection),
        hide_index=True,
        use_container_width=True,
    )

    columns = st.columns(3)
    for index, row in projection.iterrows():
        with columns[index % 3]:
            label = str(row["workshop"])
            peak = int(row["peak"])
            limit = int(row["limit"])
            closing = int(row["closing"])
            downs = int(row["downs"])
            ups = int(row["ups"])
            status = str(row["status"])
            detail = (
                f"Máximo: **{peak}/{limit}** · Cierre: **{closing}**\n\n"
                f"Bajan: {downs} · Suben: {ups}"
            )
            if status == "Sobrepasado":
                st.error(f"**{label}**\n\n🔴 SOBREPASADO\n\n{detail}")
            elif status == "Al límite":
                st.warning(f"**{label}**\n\n🟡 AL LÍMITE\n\n{detail}")
            else:
                st.success(f"**{label}**\n\n🟢 CON ESPACIO\n\n{detail}")

    st.divider()
    st.subheader("🧭 Recomendaciones de redistribución")
    deterministic = build_rebalancing_recommendations(projection)
    if deterministic:
        for recommendation in deterministic:
            st.warning(recommendation)
    else:
        st.success(
            "No se proyectan talleres sobre su capacidad máxima durante esta semana. "
            "Mantén seguimiento de cambios de última hora en Mov. equipos."
        )

    st.markdown("#### 🤖 Recomendación asistida por IA")
    st.caption(
        "Gemini no calcula las capacidades: solo analiza las cifras ya calculadas por la app y propone una redistribución breve."
    )

    week_key = week_start.strftime("%Y-%m-%d")
    if st.session_state.get(CAPACITY_AI_WEEK_KEY) != week_key:
        st.session_state.pop(CAPACITY_AI_KEY, None)
        st.session_state[CAPACITY_AI_WEEK_KEY] = week_key

    if not settings.gemini_api_key:
        st.info("La recomendación IA está desactivada porque falta GEMINI_API_KEY.")
    elif not ai_model:
        st.warning("No se encontró un modelo Gemini compatible con la clave configurada.")
    elif st.button("Generar sugerencia de capacidad con IA", type="primary"):
        with st.spinner("Gemini está analizando la capacidad semanal..."):
            result, error = suggest_workshop_capacity(
                settings.gemini_api_key,
                ai_model,
                projection,
                data.movements,
                week_start,
                week_end,
            )
        st.session_state[CAPACITY_AI_KEY] = {"result": result, "error": error}

    ai_state = st.session_state.get(CAPACITY_AI_KEY)
    if ai_state:
        if ai_state.get("error"):
            st.warning(ai_state["error"])
        elif ai_state.get("result"):
            st.info(ai_state["result"])
