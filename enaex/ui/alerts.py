from __future__ import annotations

import pandas as pd
import streamlit as st

from enaex.models import ApplicationData
from enaex.processing import build_contracts
from enaex.ui.common import render_contract_card


def render_alerts_page(data: ApplicationData) -> None:
    st.header("🚨 Panel de Alertas Tempranas")
    st.subheader("⚖️ Estado de Cumplimiento de Contratos — SOLO AUGER / QUADRA")
    st.caption("AFI, PMO/PMOCAM, camionetas y cualquier otro equipo quedan excluidos del cálculo contractual.")

    # Recalcula en la propia pantalla desde los nombres actuales de la API.
    # Así una tabla data.contracts cacheada de una versión anterior no puede inflar el conteo.
    contracts = build_contracts(data.gps)
    if contracts.empty:
        st.info("No hay datos GPS suficientes para calcular contratos.")
    else:
        columns = st.columns(6)
        for index, row in contracts.iterrows():
            with columns[index % 6]:
                render_contract_card(
                    str(row["contract"]), int(row["actual"]), int(row["target"]), str(row["status"])
                )

    st.divider()
    st.subheader("⚠️ Certificaciones críticas")
    if data.certifications.empty:
        st.info("No hay equipos del Excel para revisar certificaciones.")
        return

    critical = data.certifications[data.certifications["status"].isin(["Vencida", "Vence pronto", "Fecha inválida"])].copy()
    if critical.empty:
        st.success("No se detectaron certificaciones vencidas ni próximas a vencer en 30 días.")
    else:
        display = critical[["equipment", "document", "expiration_text", "days", "status"]].rename(
            columns={
                "equipment": "Equipo",
                "document": "Documento",
                "expiration_text": "Vencimiento",
                "days": "Días restantes",
                "status": "Estado",
            }
        )
        st.dataframe(display, hide_index=True, use_container_width=True)

    missing = data.certifications[data.certifications["status"] == "Sin fecha"]
    with st.expander(f"Documentos sin fecha registrada ({len(missing)})"):
        if missing.empty:
            st.write("No hay documentos sin fecha.")
        else:
            st.dataframe(
                missing[["equipment", "document"]].rename(columns={"equipment": "Equipo", "document": "Documento"}),
                hide_index=True,
                use_container_width=True,
            )
