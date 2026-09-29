from __future__ import annotations

import pandas as pd
import streamlit as st

from enaex.models import ApplicationData
from enaex.processing import build_contracts, build_planning_critical_certifications
from enaex.ui.common import render_contract_card


def render_alerts_page(data: ApplicationData) -> None:
    st.header("🚨 Panel de Alertas Tempranas")
    st.subheader("⚖️ Estado de Cumplimiento de Contratos — SOLO AUGER / QUADRA")
    st.caption("AFI, PMO/PMOCAM, camionetas y cualquier otro equipo quedan excluidos del cálculo contractual.")

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
        "Se muestran exclusivamente certificaciones que el sistema de planificación tiene en amarillo o rojo "
        "(30 días o menos, o vencidas). Incluye todos los tipos de equipos: camiones fábrica, polvorines, "
        "auxiliares Enaex y equipos en arriendo."
    )

    critical = build_planning_critical_certifications(data.gps)
    if critical.empty:
        st.success("No se detectaron certificaciones amarillas o rojas en el sistema de planificación.")
        return

    display = critical[[
        "equipment", "faena", "document", "expiration_text", "days", "status"
    ]].rename(
        columns={
            "equipment": "Equipo",
            "faena": "Faena",
            "document": "Documento",
            "expiration_text": "Vencimiento",
            "days": "Días restantes",
            "status": "Estado",
        }
    )
    st.dataframe(display, hide_index=True, use_container_width=True)
