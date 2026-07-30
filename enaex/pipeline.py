from __future__ import annotations

import concurrent.futures

import streamlit as st

from enaex.configuration import GPS_TYPES, GPS_ZONES, Settings
from enaex.data_sources import load_excel_sources, load_gps_source
from enaex.models import ApplicationData
from enaex.processing import build_application_data


@st.cache_data(ttl=300, show_spinner=False)
def load_application_snapshot(settings: Settings) -> ApplicationData:
    """Descarga y procesa todo una sola vez por ventana de caché."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        excel_future = executor.submit(load_excel_sources, settings.excel_urls)
        gps_future = executor.submit(
            load_gps_source,
            settings.gps_base_url,
            settings.gps_api_key,
            GPS_TYPES,
            GPS_ZONES,
            settings.gps_timeout_seconds,
            settings.gps_workers,
        )
        excel_raw, excel_diagnostics, excel_errors = excel_future.result()
        gps_raw, gps_diagnostics, gps_errors = gps_future.result()

    diagnostics = {**excel_diagnostics, **gps_diagnostics}
    errors = excel_errors + gps_errors
    return build_application_data(
        excel_raw=excel_raw,
        gps_raw=gps_raw,
        settings=settings,
        source_diagnostics=diagnostics,
        source_errors=errors,
    )
