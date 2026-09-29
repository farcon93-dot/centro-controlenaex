from __future__ import annotations

import pandas as pd
import streamlit as st

from enaex.configuration import CONTRACT_TARGETS
from enaex.models import ApplicationData
from enaex.normalize import clean_display, format_date
from enaex.processing import (
    FACTORY_TRUCK_LABEL,
    POLVORIN_LABEL,
    OTHER_EQUIPMENT_LABEL,
    equipment_category,
    is_factory_truck,
    is_polvorin,
)


def _classify(frame: pd.DataFrame) -> pd.Series:
    """Recalcula la categoría desde el NOMBRE del equipo; no confía en caché previa."""
    if frame.empty or "equipment" not in frame.columns:
        return pd.Series(index=frame.index, dtype="object")
    return frame["equipment"].map(equipment_category)


def render_faenas_page(data: ApplicationData) -> None:
    st.header("📍 Vista Global de Faenas")
    st.caption("Contrato = SOLO camiones fábrica cuyo código comienza por AUGER o QUADRA. AFI, PMO/PMOCAM y otros equipos no suman al objetivo.")

    active = sorted(data.gps["canonical_contract"].dropna().astype(str).unique().tolist()) if not data.gps.empty else []
    options = sorted(set(CONTRACT_TARGETS) | set(active))
    selected = st.selectbox("Selecciona la Faena / Contrato", ["(Elige una Faena)"] + options)
    if selected == "(Elige una Faena)":
        return

    gps_filtered = data.gps[data.gps["canonical_contract"] == selected].copy() if not data.gps.empty else pd.DataFrame()
    if not gps_filtered.empty:
        gps_filtered["equipment_category"] = _classify(gps_filtered)

    factory_mask = gps_filtered["equipment"].map(is_factory_truck).fillna(False) if not gps_filtered.empty and "equipment" in gps_filtered.columns else pd.Series(False, index=gps_filtered.index)
    polvorin_mask = gps_filtered["equipment"].map(is_polvorin).fillna(False) if not gps_filtered.empty and "equipment" in gps_filtered.columns else pd.Series(False, index=gps_filtered.index)
    factory = gps_filtered.loc[factory_mask].copy() if not gps_filtered.empty else pd.DataFrame()
    polvorines = gps_filtered.loc[polvorin_mask].copy() if not gps_filtered.empty else pd.DataFrame()
    others = gps_filtered.loc[~factory_mask & ~polvorin_mask].copy() if not gps_filtered.empty else pd.DataFrame()

    # Un camión fábrica se cuenta una sola vez aunque la API lo entregue duplicado.
    if not factory.empty:
        if "equipment_key" in factory.columns:
            factory = factory.drop_duplicates(subset=["equipment_key"], keep="last")
        else:
            factory = factory.drop_duplicates(subset=["equipment"], keep="last")

    actual_contract = len(factory)
    target = CONTRACT_TARGETS.get(selected)

    st.subheader(f"Análisis de contrato: {selected}")
    first, second, third, fourth = st.columns(4)
    first.metric("🚛 Camiones fábrica (AUGER/QUADRA)", actual_contract)
    second.metric("Objetivo contractual", target if target is not None else "Sin objetivo")
    third.metric("Diferencia", actual_contract - target if target is not None else "N/A")
    fourth.metric("🧨 Polvorines PMO / PMOCAM", len(polvorines))

    if target is not None:
        if actual_contract < target:
            st.error(f"Faltan {target - actual_contract} camiones fábrica AUGER/QUADRA para cumplir el objetivo.")
        elif actual_contract == target:
            st.warning("El contrato de camiones fábrica está cumplido exactamente.")
        else:
            st.success(f"El contrato tiene {actual_contract - target} camiones fábrica sobre el objetivo.")

    st.caption(
        f"Inventario visible en esta faena: {len(gps_filtered)} equipos = "
        f"{actual_contract} camiones fábrica + {len(polvorines)} polvorines + {len(others)} otros. "
        "Solo el primer grupo cuenta para el contrato."
    )

    if gps_filtered.empty:
        st.info(f"No hay equipos GPS reportando en {selected}.")
        return

    st.markdown("### Equipos reportados en la faena")
    display = pd.DataFrame(
        {
            "Tipo": gps_filtered["equipment_category"],
            "Equipo": gps_filtered.get("equipment", pd.Series(index=gps_filtered.index, dtype="object")),
            "Patente": gps_filtered.get("plate", pd.Series(index=gps_filtered.index, dtype="object")),
            "Marca": gps_filtered.get("brand", pd.Series(index=gps_filtered.index, dtype="object")),
            "Modelo": gps_filtered.get("model", pd.Series(index=gps_filtered.index, dtype="object")),
            "Horómetro": gps_filtered.get("hours", pd.Series(index=gps_filtered.index, dtype="object")),
            "Estado": gps_filtered.get("status", pd.Series(index=gps_filtered.index, dtype="object")),
            "Lugar": gps_filtered.get("place", pd.Series(index=gps_filtered.index, dtype="object")).map(
                lambda value: clean_display(value, default="N/A")
            ),
            "Fecha retorno a operación": gps_filtered.get(
                "return_operation_date", pd.Series(index=gps_filtered.index, dtype="object")
            ).map(format_date),
        }
    )
    display = display.dropna(axis=1, how="all")
    order = {FACTORY_TRUCK_LABEL: 0, POLVORIN_LABEL: 1, OTHER_EQUIPMENT_LABEL: 2}
    display["_orden"] = display["Tipo"].map(order).fillna(9)
    display = display.sort_values(["_orden", "Equipo"], na_position="last").drop(columns=["_orden"])
    st.dataframe(display.reset_index(drop=True), hide_index=True, use_container_width=True)
