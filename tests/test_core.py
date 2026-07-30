from __future__ import annotations

import pandas as pd

from enaex.configuration import Settings
from enaex.data_sources import detect_header_row
from enaex.normalize import format_date, normalize_identifier, normalize_workshop, parse_date
from enaex.processing import (
    build_application_data,
    canonical_contract,
    search_equipment_ids,
)


def settings() -> Settings:
    return Settings(
        excel_urls=(),
        gps_base_url="http://example.test",
        gps_api_key="x",
        gemini_api_key="",
        gemini_model="",
        cache_ttl_seconds=300,
        gps_timeout_seconds=6,
        gps_workers=4,
    )


def test_identifier_normalization() -> None:
    assert normalize_identifier(" Quádra-70 ") == "quadra70"


def test_excel_serial_date() -> None:
    assert format_date(45292) == "01/01/2024"


def test_text_date() -> None:
    assert format_date("31/12/2026T00:00:00") == "31/12/2026"


def test_workshop_normalization() -> None:
    assert normalize_workshop("SKC Alto Hospicio") == "SKC ALTO HOSPICIO"
    assert normalize_workshop("Full RPM Antofagasta") == "FULL RPM"


def test_contract_separates_new_centinela() -> None:
    assert canonical_contract("Minera Centinela") == "Centinela"
    assert canonical_contract("Proyecto Nueva Centinela") == "Nueva Centinela"


def test_header_detection() -> None:
    raw = pd.DataFrame(
        [
            ["PLANIFICACIÓN GENERAL", None, None],
            ["Equipo", "Patente", "Fecha Inicio"],
            ["Quadra-70", "ABCD12", "01/01/2026"],
        ]
    )
    assert detect_header_row(raw) == 1


def test_consolidation_across_sheets_and_latest_values() -> None:
    excel = pd.DataFrame(
        [
            {
                "Equipo": "Quadra-70",
                "Patente": "ABCD12",
                "Marca": "Marca A",
                "Fecha actualización": "01/01/2026",
                "_source_file": "Excel_1",
                "_source_sheet": "Maestro",
                "_source_row": 2,
                "_global_order": 0,
            },
            {
                "Placa": "ABCD12",
                "Estatus MP": "En taller",
                "Taller destino": "SKC Calama",
                "Comentario": "Cambio de bomba",
                "Fecha Inicio": "10/07/2026",
                "Fecha Entrega": "20/07/2026",
                "Fecha actualización": "02/07/2026",
                "_source_file": "Excel_2",
                "_source_sheet": "Plan",
                "_source_row": 5,
                "_global_order": 1,
            },
        ]
    )
    gps = pd.DataFrame(
        [
            {
                "nombre": "Quadra-70",
                "nombre_faena": "Centinela",
                "horas_ult": 1234,
                "Estado_Deducido": "Operativo",
                "_gps_response_order": 0,
            }
        ]
    )
    data = build_application_data(excel, gps, settings())
    assert len(data.equipment) == 1
    row = data.equipment.iloc[0]
    assert row["plate"] == "ABCD12"
    assert row["status"] == "En taller"
    assert row["workshop"] == "SKC Calama"
    assert row["gps_contract"] == "Centinela"


def test_gps_is_deduplicated_before_contract_count() -> None:
    excel = pd.DataFrame()
    gps = pd.DataFrame(
        [
            {"nombre": "Quadra-70", "nombre_faena": "Centinela", "horas_ult": 100, "_gps_response_order": 0},
            {"nombre": "Quadra 70", "nombre_faena": "Centinela", "horas_ult": 100, "_gps_response_order": 1},
        ]
    )
    data = build_application_data(excel, gps, settings())
    centinela = data.contracts[data.contracts["contract"] == "Centinela"].iloc[0]
    assert centinela["actual"] == 1


def test_certification_uses_most_recent_valid_date() -> None:
    excel = pd.DataFrame(
        [
            {
                "Equipo": "Auger-165",
                "Revisión Técnica": "01/01/2024",
                "_source_file": "Excel_1",
                "_source_sheet": "Historial",
                "_source_row": 2,
                "_global_order": 0,
            },
            {
                "Equipo": "Auger-165",
                "Revisión Técnica": "01/01/2028",
                "_source_file": "Excel_1",
                "_source_sheet": "Historial",
                "_source_row": 3,
                "_global_order": 1,
            },
        ]
    )
    data = build_application_data(excel, pd.DataFrame(), settings())
    row = data.equipment.iloc[0]
    assert pd.Timestamp(row["revision_tecnica"]) == pd.Timestamp("2028-01-01")


def test_active_capacity_excludes_completed_status() -> None:
    today = pd.Timestamp.now().normalize()
    excel = pd.DataFrame(
        [
            {
                "Equipo": "E-1",
                "Fecha Inicio": today - pd.Timedelta(days=2),
                "Fecha Entrega": today + pd.Timedelta(days=2),
                "Taller": "SKC Calama",
                "Estado": "En proceso",
                "_source_file": "Excel_1",
                "_source_sheet": "Plan",
                "_source_row": 2,
                "_global_order": 0,
            },
            {
                "Equipo": "E-2",
                "Fecha Inicio": today - pd.Timedelta(days=2),
                "Fecha Entrega": today + pd.Timedelta(days=2),
                "Taller": "SKC Calama",
                "Estado": "Finalizado",
                "_source_file": "Excel_1",
                "_source_sheet": "Plan",
                "_source_row": 3,
                "_global_order": 1,
            },
        ]
    )
    data = build_application_data(excel, pd.DataFrame(), settings())
    calama = data.workshop_capacity[data.workshop_capacity["workshop"] == "SKC CALAMA"].iloc[0]
    assert calama["occupied"] == 1


def test_search_by_plate() -> None:
    aliases = {"EQ00001": ["Quadra-70", "ABCD12"], "EQ00002": ["Auger-165", "WXYZ99"]}
    assert search_equipment_ids("ABCD-12", aliases)[0] == "EQ00001"
