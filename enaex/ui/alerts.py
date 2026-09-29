from __future__ import annotations

import pandas as pd
import streamlit as st

from enaex.models import ApplicationData
from enaex.processing import (
    CERT_AUXILIARY_LABEL,
    CERT_FACTORY_LABEL,
    CERT_POLVORIN_LABEL,
    CERT_RENTAL_LABEL,
    build_contracts,
    build_critical_certifications_all_equipment,
)
from enaex.ui.common import render_contract_card


def _render_certification_group(critical: pd.DataFrame, equipment_type: str, icon: str) -> None:
    subset = critical[critical["equipment_type"].eq(equipment_type)].copy()
    st.markdown(f"#### {icon} {equipment_type} ({len(subset)})")
    if subset.empty:
        st.caption("Sin certificaciones amarillas o rojas en esta categoría.")
        return
    display = subset[["equipment", "faena", "document", "days", "status"]].rename(
        columns={
            "equipment": "Equipo",
            "faena": "Faena",
            "document": "Documento",
            "days": "Días restantes",
            "status": "Estado",
        }
    )
    st.dataframe(display, hide_index=True, use_container_width=True)


def render_alerts_page(data: ApplicationData) -> None:
    st.header("🚨 Panel de Alertas Tempranas")
    st.subheader("⚖️ Estado de Cumplimiento de Contratos — SOLO AUGER / QUADRA")
    st.caption("AFI, PMO/PMOCAM, camionetas y cualquier otro equipo quedan excluidos del cálculo contractual.")
    if data.diagnostics.get("gps_partial_snapshot"):
        st.warning(
            "⚠️ El sistema de planificación no respondió a todos los endpoints después de los reintentos. "
            "Mientras exista este aviso, un contrato puede verse con menos equipos de los reales."
        )

    contracts = build_contracts(data.gps)
    if contracts.empty:
        st.info("No hay datos del sistema de planificación suficientes para calcular contratos.")
    else:
        columns = st.columns(6)
        for index, row in contracts.iterrows():
            with columns[index % 6]:
                render_contract_card(
                    str(row["contract"]), int(row["actual"]), int(row["target"]), str(row["status"])
                )

    st.divider()
    st.subheader("⚠️ Certificaciones críticas")
    st.caption(
        "RT, Sernageomin y DGMN vencidas o con 30 días o menos. Se revisa toda la flota y se diferencia "
        "entre camiones fábrica, polvorines, auxiliares Enaex y equipos en arriendo. Los documentos sin "
        "fecha/días válidos no se muestran."
    )

    # Se usa la ficha consolidada para no perder certificaciones cuando un tipo de
    # endpoint API entrega las columnas con otro nombre. La consolidación prioriza
    # la API y usa la fecha válida de planificación como respaldo.
    critical = build_critical_certifications_all_equipment(data.equipment)
    if critical.empty:
        if data.diagnostics.get("gps_partial_snapshot"):
            st.warning(
                "No se detectaron alertas con los datos recibidos, pero la API está incompleta. "
                "No se puede asegurar que toda la flota esté al día hasta que la fuente responda completa."
            )
        else:
            st.success("No se detectaron RT, Sernageomin o DGMN en amarillo/rojo.")
        return

    counts = critical["equipment_type"].value_counts()
    metric_cols = st.columns(4)
    labels = [
        (CERT_FACTORY_LABEL, "🚛"),
        (CERT_POLVORIN_LABEL, "🧨"),
        (CERT_AUXILIARY_LABEL, "🛠️"),
        (CERT_RENTAL_LABEL, "🏷️"),
    ]
    for col, (label, icon) in zip(metric_cols, labels):
        col.metric(f"{icon} {label}", int(counts.get(label, 0)))

    tabs = st.tabs([f"{icon} {label}" for label, icon in labels])
    for tab, (label, icon) in zip(tabs, labels):
        with tab:
            _render_certification_group(critical, label, icon)
