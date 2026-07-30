from __future__ import annotations

import pandas as pd
import streamlit as st

from enaex.ai_service import suggest_workshop_capacity
from enaex.configuration import Settings
from enaex.models import ApplicationData
from enaex.normalize import format_date
from enaex.processing import (
    EXTERNAL_WORKSHOPS,
    build_rebalancing_recommendations,
    build_weekly_workshop_projection,
    classify_current_workshop,
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


def _current_detail(current_workshops: pd.DataFrame, workshop: str) -> pd.DataFrame:
    if current_workshops.empty:
        return pd.DataFrame()
    detail = current_workshops[current_workshops["workshop_bucket"].eq(workshop)].copy()
    if detail.empty:
        return detail
    columns = ["equipment", "plate", "current_place", "gps_state", "gps_faena"]
    display = detail[columns].rename(
        columns={
            "equipment": "Equipo",
            "plate": "Patente",
            "current_place": "Lugar API",
            "gps_state": "Estado",
            "gps_faena": "Faena",
        }
    )
    return display.sort_values("Equipo").reset_index(drop=True)


def _planned_detail(
    movements: pd.DataFrame,
    workshop: str,
    week_start: pd.Timestamp,
    week_end: pd.Timestamp,
) -> pd.DataFrame:
    if movements.empty:
        return pd.DataFrame()
    frame = movements.copy()
    frame["_bucket"] = frame["workshop"].map(classify_current_workshop)
    frame = frame[frame["_bucket"].eq(workshop)]
    if frame.empty:
        return pd.DataFrame()
    mask = (
        frame["start_date"].between(week_start, week_end, inclusive="both")
        | frame["end_date"].between(week_start, week_end, inclusive="both")
    )
    frame = frame.loc[mask, ["equipment", "start_date", "end_date", "workshop", "faena", "comments"]].copy()
    if frame.empty:
        return frame
    frame["start_date"] = frame["start_date"].map(format_date)
    frame["end_date"] = frame["end_date"].map(format_date)
    return frame.rename(
        columns={
            "equipment": "Equipo",
            "start_date": "Bajada",
            "end_date": "Subida",
            "workshop": "Taller planificado",
            "faena": "Faena destino",
            "comments": "Trabajo",
        }
    ).sort_values(["Bajada", "Equipo"]).reset_index(drop=True)


def _status_icon(status: str) -> str:
    return {
        "Sobrepasado": "🔴",
        "Al límite": "🟡",
        "Con espacio": "🟢",
        "Sin límite configurado": "⚪",
    }.get(status, "⚪")


def _compact_label(row: pd.Series) -> str:
    workshop = str(row["workshop"])
    current = int(row.get("current", 0))
    peak = int(row.get("peak", 0))
    status = str(row.get("status", ""))
    limit = row.get("limit")
    if pd.isna(limit):
        capacity = f"Hoy {current} · Peak {peak}"
    else:
        capacity = f"Hoy {current}/{int(limit)} · Peak {peak}/{int(limit)}"
    return f"{_status_icon(status)} {workshop} · {capacity}"


def render_movements_page(
    data: ApplicationData,
    settings: Settings,
    ai_model: str | None,
) -> None:
    st.header("📅 Control semanal de Subidas, Bajadas y Capacidad")
    st.caption(
        "Las bajadas y subidas provienen únicamente de la pestaña **Mov. equipos**. "
        "La ocupación actual se obtiene desde la columna **Lugar** de la API del sistema de planificación."
    )

    today = pd.Timestamp.now().normalize()
    selected_day = pd.Timestamp(
        st.date_input(
            "Selecciona cualquier día de la semana que deseas analizar",
            value=today.date(),
            min_value=today.date(),
        )
    ).normalize()
    week_start = selected_day - pd.Timedelta(days=int(selected_day.weekday()))
    week_end = week_start + pd.Timedelta(days=6)
    st.info(
        f"Semana analizada: **{format_date(week_start)} al {format_date(week_end)}** · "
        f"Base actual de talleres: **API al {format_date(today)}**"
    )

    gps_mapping = data.diagnostics.get("gps_column_mapping", {})
    if not gps_mapping.get("place"):
        st.error(
            "La API respondió, pero no se detectó la columna **Lugar**. "
            "Abre la barra lateral → Diagnóstico de columnas GPS y verifica que aparezca `place → Lugar`."
        )

    if data.movements.empty:
        st.warning(
            "No se detectaron movimientos válidos en una hoja llamada “Mov. equipos”. "
            "Revisa en la barra lateral → Hojas Excel cargadas que esa pestaña esté presente."
        )
    else:
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
    st.subheader("⚖️ Capacidad actual y proyección semanal")
    st.caption(
        "Los recuadros son desplegables. Haz clic en un taller para ver los equipos que la API ubica allí hoy "
        "y sus movimientos programados para la semana."
    )

    projection = build_weekly_workshop_projection(
        data.movements,
        data.current_workshops,
        week_start,
        today=today,
    )
    if projection.empty:
        st.info("No fue posible calcular la proyección de capacidad.")
        return

    columns = st.columns(4)
    for index, row in projection.iterrows():
        workshop = str(row["workshop"])
        with columns[index % 4]:
            with st.expander(_compact_label(row), expanded=False):
                current = int(row.get("current", 0))
                downs = int(row.get("downs", 0))
                ups = int(row.get("ups", 0))
                peak = int(row.get("peak", 0))
                closing = int(row.get("closing", 0))
                limit = row.get("limit")
                status = str(row.get("status", ""))

                if pd.isna(limit):
                    st.caption("Capacidad máxima no configurada para este grupo.")
                else:
                    st.caption(f"Capacidad máxima: {int(limit)} · Estado proyectado: {status}")
                st.markdown(
                    f"**Hoy:** {current}  ·  **Bajan:** {downs}  ·  **Suben:** {ups}  "
                    f"·  **Peak:** {peak}  ·  **Cierre:** {closing}"
                )

                if workshop == EXTERNAL_WORKSHOPS:
                    locations = row.get("external_locations", []) or []
                    if locations:
                        st.caption("Lugares externos detectados: " + ", ".join(map(str, locations)))

                st.markdown("**Equipos actualmente en el taller (API)**")
                current_detail = _current_detail(data.current_workshops, workshop)
                if current_detail.empty:
                    st.write("No hay equipos reportados actualmente.")
                else:
                    st.dataframe(
                        current_detail,
                        hide_index=True,
                        use_container_width=True,
                        height=min(260, 36 * (len(current_detail) + 1) + 4),
                    )

                st.markdown("**Movimientos programados de la semana**")
                planned_detail = _planned_detail(data.movements, workshop, week_start, week_end)
                if planned_detail.empty:
                    st.write("No hay movimientos programados para este taller.")
                else:
                    st.dataframe(
                        planned_detail,
                        hide_index=True,
                        use_container_width=True,
                        height=min(260, 36 * (len(planned_detail) + 1) + 4),
                    )

    st.divider()
    st.subheader("🧭 Recomendaciones de redistribución")
    deterministic = build_rebalancing_recommendations(projection)
    if deterministic:
        for recommendation in deterministic:
            st.warning(recommendation)
    else:
        st.success(
            "No se proyectan talleres configurados sobre su capacidad máxima durante esta semana. "
            "Mantén seguimiento de cambios de última hora en Mov. equipos y de la columna Lugar de la API."
        )

    st.markdown("#### 🤖 Recomendación asistida por IA")
    st.caption(
        "Gemini no calcula las capacidades: analiza el inventario actual informado por Lugar, las bajadas/subidas "
        "de Mov. equipos y los cupos calculados por la aplicación."
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
