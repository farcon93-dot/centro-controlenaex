from __future__ import annotations

import pandas as pd
import streamlit as st

from enaex.configuration import CONTRACT_TARGETS
from enaex.models import ApplicationData
from enaex.normalize import format_date


def render_faenas_page(data: ApplicationData) -> None:
    st.header("📍 Vista Global de Faenas")
    active = sorted(data.gps["canonical_contract"].dropna().astype(str).unique().tolist()) if not data.gps.empty else []
    options = sorted(set(CONTRACT_TARGETS) | set(active))
    selected = st.selectbox("Selecciona la Faena / Contrato", ["(Elige una Faena)"] + options)
    if selected == "(Elige una Faena)":
        return

    gps_filtered = data.gps[data.gps["canonical_contract"] == selected].copy() if not data.gps.empty else pd.DataFrame()
    actual = len(gps_filtered)
    target = CONTRACT_TARGETS.get(selected)

    st.subheader(f"Análisis de contrato: {selected}")
    first, second, third = st.columns(3)
    first.metric("Equipos GPS únicos", actual)
    second.metric("Objetivo contractual", target if target is not None else "Sin objetivo")
    if target is None:
        third.metric("Diferencia", "N/A")
    else:
        third.metric("Diferencia", actual - target)
        if actual < target:
            st.error(f"Faltan {target - actual} equipos para cumplir el objetivo.")
        elif actual == target:
            st.warning("El contrato está cumplido exactamente.")
        else:
            st.success(f"El contrato está {actual - target} equipos sobre el objetivo.")

    if gps_filtered.empty:
        st.info(f"No hay equipos GPS reportando en {selected}.")
        return

    display = pd.DataFrame(
        {
            "Equipo": gps_filtered.get("equipment", pd.Series(index=gps_filtered.index, dtype="object")),
            "Patente": gps_filtered.get("plate", pd.Series(index=gps_filtered.index, dtype="object")),
            "Marca": gps_filtered.get("brand", pd.Series(index=gps_filtered.index, dtype="object")),
            "Modelo": gps_filtered.get("model", pd.Series(index=gps_filtered.index, dtype="object")),
            "Horómetro": gps_filtered.get("hours", pd.Series(index=gps_filtered.index, dtype="object")),
            "Estado": gps_filtered.get("status", pd.Series(index=gps_filtered.index, dtype="object")),
            "Última actualización": gps_filtered.get(
                "timestamp_parsed", pd.Series(index=gps_filtered.index, dtype="datetime64[ns]")
            ).map(format_date),
            "Faena reportada": gps_filtered.get("faena", pd.Series(index=gps_filtered.index, dtype="object")),
        }
    )
    # Elimina columnas completamente vacías sin provocar KeyError.
    display = display.dropna(axis=1, how="all")
    st.dataframe(display.reset_index(drop=True), hide_index=True, use_container_width=True)
