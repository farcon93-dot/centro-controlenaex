from __future__ import annotations

import pandas as pd
import streamlit as st

from enaex.ai_service import analyze_cross_source_discrepancies
from enaex.configuration import Settings
from enaex.models import ApplicationData
from enaex.processing import (
    CERT_AUXILIARY_LABEL,
    CERT_FACTORY_LABEL,
    CERT_POLVORIN_LABEL,
    CERT_RENTAL_LABEL,
    build_contracts,
    build_planning_critical_certifications,
    build_cross_source_discrepancies,
)
from enaex.ui.common import render_contract_card
from enaex.normalize import clean_display


CROSS_AI_RESULT_KEY = "enaex_cross_ai_result"


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


def _render_cross_audit(data: ApplicationData, settings: Settings, ai_model: str | None) -> None:
    st.divider()
    st.subheader("🤖 Auditoría cruzada — Sistema de planificación vs Excel")
    st.caption(
        "La app cruza el sistema de planificación exclusivamente contra la hoja En proceso del Excel. "
        "Estatus MP y Fecha Entrega determinan si el equipo debe estar en Faena o Taller. Gemini solo interpreta y prioriza."
    )

    try:
        discrepancies = build_cross_source_discrepancies(data.equipment, history=data.history)
    except Exception:
        # La auditoría cruzada es complementaria: nunca debe derribar Alertas.
        st.warning(
            "La auditoría cruzada no pudo procesar uno de los registros recibidos. "
            "El resto de la aplicación sigue operativo. Recarga los datos y vuelve a intentar."
        )
        return

    if discrepancies.empty:
        if data.diagnostics.get("gps_partial_snapshot"):
            st.warning(
                "No se detectaron discrepancias en los datos disponibles, pero la fotografía de la API está incompleta. "
                "Conviene repetir la revisión cuando la fuente vuelva a responder completa."
            )
        else:
            st.success("No se detectaron diferencias comparables de ubicación o fecha de retorno.")
        return

    location_count = int(discrepancies["issue_type"].eq("Ubicación").sum())
    date_count = int(discrepancies["issue_type"].eq("Fecha retorno").sum())
    c1, c2, c3 = st.columns(3)
    c1.metric("Discrepancias", len(discrepancies))
    c2.metric("Ubicación", location_count)
    c3.metric("Fechas", date_count)

    if data.diagnostics.get("gps_partial_snapshot"):
        st.warning(
            "⚠️ La API no respondió completa. La tabla evita marcar N/A como discrepancia, pero puede faltar algún equipo."
        )

    display = discrepancies.rename(
        columns={
            "equipment": "Equipo",
            "faena": "Faena",
            "issue_type": "Tipo",
            "system_place": "Sistema planificación",
            "excel_place": "Excel (En proceso)",
            "system_return_date": "Retorno sistema",
            "excel_return_date": "Fecha Entrega (En proceso)",
            "date_difference_days": "Diferencia días",
            "detail": "Detalle",
        }
    )
    visible_columns = [
        "Equipo", "Faena", "Tipo", "Sistema planificación", "Excel (En proceso)",
        "Retorno sistema", "Fecha Entrega (En proceso)", "Diferencia días", "Detalle",
    ]
    display = display.reindex(columns=visible_columns).copy()
    # Streamlit/Arrow puede fallar con columnas object que mezclan pd.NA e int.
    # Convertimos todo lo visible a texto seguro; los cálculos siguen usando el DF original.
    for column in visible_columns:
        display[column] = display[column].map(lambda value: clean_display(value, default=""))
    st.dataframe(display, hide_index=True, use_container_width=True)

    st.markdown("#### Análisis con Gemini")
    if not settings.gemini_api_key:
        st.info("Configura GEMINI_API_KEY en los Secrets de Streamlit para activar el análisis IA.")
        return
    if not ai_model:
        st.warning(
            "La clave Gemini está configurada, pero todavía no se pudo resolver un modelo compatible. "
            "Revisa GEMINI_MODEL en los Secrets."
        )
        return

    if st.button("Analizar discrepancias con Gemini", type="primary", use_container_width=True):
        with st.spinner("Gemini está priorizando las diferencias detectadas..."):
            result, error = analyze_cross_source_discrepancies(
                settings.gemini_api_key,
                ai_model,
                discrepancies,
            )
        st.session_state[CROSS_AI_RESULT_KEY] = {"result": result, "error": error}

    state = st.session_state.get(CROSS_AI_RESULT_KEY)
    if state:
        if state.get("error"):
            st.warning(state["error"])
        elif state.get("result"):
            st.info(state["result"])


def render_alerts_page(
    data: ApplicationData,
    settings: Settings,
    ai_model: str | None,
) -> None:
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
        "RT, Sernageomin y DGMN que el sistema de planificación muestra en rojo o amarillo "
        "(vencidas, vencen hoy o con 30 días o menos). Se revisa toda la flota y se diferencia "
        "entre camiones fábrica, polvorines, auxiliares Enaex y equipos en arriendo. "
        "Esta vista usa exclusivamente los días del sistema de planificación, no fechas históricas del Excel."
    )

    critical = build_planning_critical_certifications(data.gps)
    if critical.empty:
        if data.diagnostics.get("gps_partial_snapshot"):
            st.warning(
                "No se detectaron alertas con los datos recibidos, pero la API está incompleta. "
                "No se puede asegurar que toda la flota esté al día hasta que la fuente responda completa."
            )
        else:
            st.success("No se detectaron RT, Sernageomin o DGMN en amarillo/rojo.")
    else:
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

    _render_cross_audit(data, settings, ai_model)
