from __future__ import annotations

import pandas as pd
import streamlit as st

from enaex.models import ApplicationData
from enaex.normalize import format_date


def _movement_display(frame: pd.DataFrame, date_column: str, destination_column: str) -> pd.DataFrame:
    if frame.empty:
        return frame
    display = frame[["equipment", date_column, destination_column, "status", "comments", "source"]].copy()
    display[date_column] = display[date_column].map(format_date)
    return display.rename(
        columns={
            "equipment": "Equipo",
            date_column: "Fecha",
            destination_column: "Destino",
            "status": "Estatus",
            "comments": "Comentario / Trabajo",
            "source": "Origen",
        }
    )


def render_movements_page(data: ApplicationData) -> None:
    st.header("📅 Control de Subidas, Bajadas y Capacidad")
    window_days = st.number_input("Ventana de análisis (días hacia atrás y hacia adelante)", 1, 90, 15)
    today = pd.Timestamp.now().normalize()
    lower = today - pd.Timedelta(days=int(window_days))
    upper = today + pd.Timedelta(days=int(window_days))

    if data.movements.empty:
        st.info("No se detectaron fechas de movimiento en las columnas del Excel.")
    else:
        down = data.movements[
            data.movements["start_date"].notna()
            & (data.movements["start_date"] >= lower)
            & (data.movements["start_date"] <= upper)
        ].sort_values("start_date")
        up = data.movements[
            data.movements["end_date"].notna()
            & (data.movements["end_date"] >= lower)
            & (data.movements["end_date"] <= upper)
        ].sort_values("end_date")

        left, right = st.columns(2)
        with left:
            st.subheader("📉 Bajan a taller")
            if down.empty:
                st.success("No hay bajadas en esta ventana.")
            else:
                st.dataframe(
                    _movement_display(down, "start_date", "workshop"),
                    hide_index=True,
                    use_container_width=True,
                )
        with right:
            st.subheader("⛰️ Suben o se entregan a faena")
            if up.empty:
                st.info("No hay subidas en esta ventana.")
            else:
                st.dataframe(
                    _movement_display(up, "end_date", "faena"),
                    hide_index=True,
                    use_container_width=True,
                )

    st.divider()
    st.subheader("⚖️ Capacidad actual de talleres")
    if data.workshop_capacity.empty:
        st.info("No fue posible calcular la capacidad.")
        return
    columns = st.columns(3)
    for index, row in data.workshop_capacity.iterrows():
        with columns[index % 3]:
            label = str(row["workshop"])
            occupied = int(row["occupied"])
            limit = int(row["limit"])
            status = str(row["status"])
            if status == "Sobrepasado":
                st.error(f"**{label}**\n\n🔴 SOBREPASADO\n\n{occupied} / {limit} equipos")
            elif status == "Al límite":
                st.warning(f"**{label}**\n\n🟡 AL LÍMITE\n\n{occupied} / {limit} equipos")
            else:
                st.success(f"**{label}**\n\n🟢 CON ESPACIO\n\n{occupied} / {limit} equipos")
