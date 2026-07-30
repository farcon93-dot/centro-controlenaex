from __future__ import annotations

import streamlit as st

from enaex.ai_service import audit_equipment
from enaex.configuration import Settings
from enaex.models import ApplicationData
from enaex.processing import search_equipment_ids
from enaex.ui.common import render_equipment_card


SEARCH_STATE_KEY = "enaex_search_entity_ids"
SEARCH_NOT_FOUND_KEY = "enaex_search_not_found"
AI_RESULT_KEY = "enaex_ai_result"
SEARCH_QUERY_KEY = "enaex_search_query"


def render_equipment_page(
    data: ApplicationData,
    settings: Settings,
    ai_model: str | None,
) -> None:
    st.header("🔍 Búsqueda y Auditoría Individual")
    st.caption("Puedes buscar por nombre de equipo, patente o VIN. Para varios equipos, sepáralos por comas.")

    with st.form("equipment_search_form", clear_on_submit=False):
        query = st.text_input("Ejemplo: Quadra-70, Auger-165")
        submitted = st.form_submit_button("Consultar fichas técnicas", type="primary")

    if submitted:
        terms = [term.strip() for term in query.split(",") if term.strip()]
        selected_ids: list[str] = []
        st.session_state[SEARCH_STATE_KEY] = []
        st.session_state[SEARCH_NOT_FOUND_KEY] = []
        st.session_state[SEARCH_QUERY_KEY] = query.strip()
        not_found: list[str] = []
        for term in terms:
            matches = search_equipment_ids(term, data.search_aliases)
            if matches:
                # Una búsqueda exacta normalmente devuelve un resultado; los resultados cercanos se conservan sin duplicar.
                for entity_id in matches:
                    if entity_id not in selected_ids:
                        selected_ids.append(entity_id)
            else:
                not_found.append(term)
        st.session_state[SEARCH_STATE_KEY] = selected_ids
        st.session_state[SEARCH_NOT_FOUND_KEY] = not_found
        st.session_state.pop(AI_RESULT_KEY, None)

    selected_ids = st.session_state.get(SEARCH_STATE_KEY, [])
    not_found = st.session_state.get(SEARCH_NOT_FOUND_KEY, [])

    if not_found:
        st.warning("No se encontraron: " + ", ".join(not_found))
    if not selected_ids:
        st.info("Escribe uno o más equipos y pulsa “Consultar fichas técnicas”.")
        return

    searched_query = st.session_state.get(SEARCH_QUERY_KEY, "")
    if searched_query:
        st.caption(f"Resultado para: {searched_query}")

    selected = data.equipment[data.equipment["entity_id"].isin(selected_ids)].copy()
    selected["_order"] = selected["entity_id"].map({entity_id: index for index, entity_id in enumerate(selected_ids)})
    selected = selected.sort_values("_order").drop(columns="_order")

    for _, row in selected.iterrows():
        render_equipment_card(row)

    st.subheader("🤖 Auditoría automática opcional")
    st.caption("La IA solo analiza las fichas que ya ves. Excel y GPS no dependen de Gemini.")
    if not settings.gemini_api_key:
        st.info("Agrega GEMINI_API_KEY en .streamlit/secrets.toml para activar esta función.")
    elif not ai_model:
        st.warning("No se encontró un modelo Gemini compatible con tu clave.")
    elif st.button("Auditar estado e historial de los equipos con IA"):
        with st.spinner("Gemini está comparando planificación, GPS y certificaciones..."):
            result, error = audit_equipment(settings.gemini_api_key, ai_model, selected)
        st.session_state[AI_RESULT_KEY] = {"result": result, "error": error}

    ai_state = st.session_state.get(AI_RESULT_KEY)
    if ai_state:
        if ai_state.get("error"):
            st.warning(ai_state["error"])
        elif ai_state.get("result"):
            st.info(ai_state["result"])
