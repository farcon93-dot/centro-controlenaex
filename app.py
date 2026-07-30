from __future__ import annotations

import streamlit as st

from enaex.ai_service import resolve_gemini_model
from enaex.configuration import load_settings
from enaex.pipeline import load_application_snapshot
from enaex.ui.alerts import render_alerts_page
from enaex.ui.common import apply_css, render_header, render_sidebar
from enaex.ui.equipment import render_equipment_page
from enaex.ui.faenas import render_faenas_page
from enaex.ui.movements import render_movements_page


def _read_secrets():
    try:
        return st.secrets
    except Exception:
        return {}


def main() -> None:
    st.set_page_config(
        page_title="Control Flota Enaex",
        page_icon="🚛",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_css()
    settings = load_settings(_read_secrets())

    render_header()
    with st.spinner("Cargando Excel, GPS y construyendo el índice de equipos..."):
        data = load_application_snapshot(settings)

    ai_model, ai_error = resolve_gemini_model(settings.gemini_api_key, settings.gemini_model)

    def refresh() -> None:
        load_application_snapshot.clear()
        resolve_gemini_model.clear()
        st.session_state.pop("enaex_search_entity_ids", None)
        st.session_state.pop("enaex_search_not_found", None)
        st.session_state.pop("enaex_ai_result", None)
        st.rerun()

    render_sidebar(data, ai_model, ai_error, refresh)

    tab_alerts, tab_equipment, tab_movements, tab_faenas = st.tabs(
        ["🚨 Alertas", "🔍 Buscar Equipo", "📅 Movimientos de Equipos", "📍 Ver por Faena"]
    )
    with tab_alerts:
        render_alerts_page(data)
    with tab_equipment:
        render_equipment_page(data, settings, ai_model)
    with tab_movements:
        render_movements_page(data)
    with tab_faenas:
        render_faenas_page(data)


if __name__ == "__main__":
    main()
