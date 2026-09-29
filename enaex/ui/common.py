from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from enaex.models import ApplicationData
from enaex.normalize import format_date, normalize_text


CSS = """
<style>
    .block-container {padding-top: 1.6rem; padding-bottom: 3rem;}
    .enaex-title {font-size: 2.4rem; font-weight: 800; color: #24418f; margin: 0;}
    .enaex-subtitle {color: #98a2b3; margin-top: .2rem;}
    .brand-fallback {font-size: 1.25rem; font-weight: 900; letter-spacing: .08em; color: #ffffff;}
    .contract-card {border-radius: 10px; padding: 16px; min-height: 132px; margin-bottom: 12px; border: 1px solid rgba(255,255,255,.08);}
    .contract-card h4 {margin: 0 0 14px 0; font-size: 1rem;}
    .contract-card p {margin: 5px 0;}
    .card-danger {background: rgba(145, 36, 53, .32);}
    .card-warning {background: rgba(137, 102, 22, .30);}
    .card-success {background: rgba(23, 111, 72, .30);}
    .metric-note {font-size: .86rem; opacity: .85;}
    .small-muted {color: #98a2b3; font-size: .86rem;}
    div[data-testid="stExpander"] {border-radius: 8px;}
    div[data-testid="stExpander"] summary {padding: .45rem .65rem; font-size: .82rem;}
    div[data-testid="stExpander"] details[open] summary {margin-bottom: .25rem;}
</style>
"""


def apply_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def render_header() -> None:
    root = Path(__file__).resolve().parents[2]
    logo_path = root / "assets" / "enaex_logo.png"
    left, right = st.columns([1, 8], vertical_alignment="center")
    with left:
        if logo_path.exists():
            st.image(str(logo_path), use_container_width=True)
        else:
            st.markdown('<div class="brand-fallback">ENAEX</div>', unsafe_allow_html=True)
    with right:
        st.markdown('<div class="enaex-title">🚛 Centro de Control: Flota y Auditoría</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="enaex-subtitle">Planificación, GPS, contratos, certificaciones y auditoría asistida por IA</div>',
            unsafe_allow_html=True,
        )
    st.divider()


def _format_mapping(mapping: dict[str, list[str]]) -> pd.DataFrame:
    rows = []
    for field, columns in mapping.items():
        rows.append({"Campo interno": field, "Columnas detectadas": ", ".join(columns) if columns else "No detectada"})
    return pd.DataFrame(rows)


def render_sidebar(data: ApplicationData, ai_model: str | None, ai_error: str | None, refresh_callback: Any) -> None:
    with st.sidebar:
        st.header("Estado del sistema")
        st.caption("Versión 2026.09.29.4.3 · LUGAR VACÍO = FAENA")
        st.metric("Equipos consolidados", len(data.equipment))
        st.metric("Equipos GPS únicos", len(data.gps))
        st.metric("Camiones fábrica GPS", int(data.diagnostics.get("gps_factory_trucks", 0)))
        st.metric("Polvorines GPS", int(data.diagnostics.get("gps_polvorines", 0)))
        recovered = int(data.diagnostics.get("gps_requests_recovered", 0) or 0)
        failed = int(data.diagnostics.get("gps_requests_failed", 0) or 0)
        if recovered or failed:
            st.caption(f"API planificación: {recovered} consultas recuperadas · {failed} fallidas")
        st.metric("Filas útiles del Excel", len(data.history))
        st.caption(f"Última carga: {data.loaded_at.strftime('%d/%m/%Y %H:%M:%S')}")

        if st.button("🔄 Recargar Excel y GPS", use_container_width=True):
            refresh_callback()

        if data.errors:
            with st.expander(f"⚠️ Avisos de carga ({len(data.errors)})"):
                for error in data.errors:
                    st.warning(error)
        else:
            st.success("Fuentes cargadas sin avisos.")

        st.subheader("Inteligencia artificial")
        if ai_model:
            st.success(f"Modelo configurado: {ai_model}")
        elif ai_error:
            st.info(ai_error)
        else:
            st.info("IA desactivada. El resto de la app funciona normalmente.")

        with st.expander("Diagnóstico de columnas Excel"):
            mapping = data.diagnostics.get("excel_column_mapping", {})
            st.dataframe(_format_mapping(mapping), hide_index=True, use_container_width=True)

        with st.expander("Diagnóstico de columnas GPS"):
            mapping = data.diagnostics.get("gps_column_mapping", {})
            st.dataframe(_format_mapping(mapping), hide_index=True, use_container_width=True)

        with st.expander("Hojas Excel cargadas"):
            sheets = data.diagnostics.get("excel_sheets", [])
            if sheets:
                st.dataframe(pd.DataFrame(sheets), hide_index=True, use_container_width=True)
            else:
                st.write("No se cargaron hojas.")


def render_contract_card(contract: str, actual: int, target: int, status: str) -> None:
    if status == "Faltan":
        css_class = "card-danger"
        symbol = "🔴"
        detail = f"Faltan {target - actual}"
    elif status == "Cumplido":
        css_class = "card-warning"
        symbol = "🟡"
        detail = "Cumplido exacto"
    else:
        css_class = "card-success"
        symbol = "🟢"
        detail = f"Sobre objetivo: +{actual - target}"
    st.markdown(
        f"""
        <div class="contract-card {css_class}">
          <h4>{contract}</h4>
          <p>{symbol} <strong>{detail}</strong></p>
          <p class="metric-note">{actual} de {target} camiones fábrica</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _certificate_label(row: pd.Series, date_field: str, days_field: str) -> str:
    date_text = format_date(row.get(date_field))
    days = row.get(days_field)
    if days is None or pd.isna(days):
        return date_text
    try:
        days_int = int(days)
        suffix = "día restante" if abs(days_int) == 1 else "días restantes"
        if days_int < 0:
            suffix = "días vencida"
        return f"{date_text} · {days_int} {suffix}"
    except (TypeError, ValueError):
        return date_text


def render_equipment_card(row: pd.Series) -> None:
    with st.container(border=True):
        st.subheader(f"🚛 Ficha Técnica: {row.get('equipment', 'Equipo')}")
        current_col, plan_col = st.columns(2)

        with current_col:
            st.markdown("#### 📡 Sistema de planificación — estado actual")
            st.info(
                f"📍 **Faena:** {row.get('gps_faena', 'N/A')}  |  "
                f"🏭 **Lugar:** {row.get('gps_place', 'N/A')}  |  "
                f"🧭 **Condición:** {row.get('gps_condition', 'N/A')}  |  "
                f"⚙️ **Estado:** {row.get('gps_state', 'N/A')}"
            )
            c1, c2 = st.columns(2)
            c1.markdown(f"**Patente:** {row.get('plate', 'N/A')}")
            c1.markdown(f"**VIN/Chasis:** {row.get('vin', 'N/A')}")
            c1.markdown(f"**Marca:** {row.get('brand', 'N/A')}")
            c1.markdown(f"**Modelo:** {row.get('model', 'N/A')}")
            c2.markdown(f"**Sistema de control:** {row.get('control_system', 'N/A')}")
            c2.markdown(f"**Hrs/Kms desde último preventivo:** {row.get('gps_hours', 'N/A')}")
            c2.markdown(f"**Próxima mantención:** {format_date(row.get('next_maintenance_date'))}")
            c2.markdown(f"**Retorno a operación:** {format_date(row.get('return_operation_date'))}")

            st.markdown("**🗓️ Certificaciones del sistema de planificación**")
            st.caption(
                f"RT: {_certificate_label(row, 'revision_tecnica', 'revision_tecnica_days')} | "
                f"Sernageomin: {_certificate_label(row, 'sernageomin', 'sernageomin_days')} | "
                f"DGMN: {_certificate_label(row, 'dgmn', 'dgmn_days')}"
            )

        with plan_col:
            st.markdown("#### 🗓️ Planificación semanal")
            st.success(
                f"📋 **Estatus en Mov. equipos:** {row.get('movement_status', 'N/A')}  |  "
                f"🔧 **Taller planificado:** {row.get('planned_workshop', 'N/A')}"
            )

            status_detail = str(row.get("status_detail", "N/A"))
            if "en proceso" in normalize_text(row.get("gps_state")):
                st.warning(f"**Comentario del estado En proceso:** {status_detail}")
            else:
                st.markdown(f"**Estado de equipos (planificación semanal):** {status_detail}")

            st.markdown(f"**Faena planificada:** {row.get('planned_faena', 'N/A')}")
            st.markdown(f"**Bajada a taller:** {format_date(row.get('start_date'))}")
            st.markdown(f"**Subida/entrega a faena:** {format_date(row.get('end_date'))}")
            st.markdown(f"**Trabajo/comentario de Mov. equipos:** {row.get('movement_comments', 'N/A')}")

        recent = row.get("recent_works", [])
        with st.expander("🧰 Últimos trabajos, estados y bajadas registradas"):
            if isinstance(recent, list) and recent:
                history = pd.DataFrame(recent)
                preferred = ["fecha", "estado", "taller", "detalle"]
                columns = [column for column in preferred if column in history.columns]
                st.dataframe(
                    history[columns],
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("No se detectaron comentarios históricos asociados a este equipo.")

