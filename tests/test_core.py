from __future__ import annotations

import pandas as pd

from enaex.configuration import Settings
from enaex.data_sources import detect_header_row
from enaex.normalize import format_date, normalize_identifier, normalize_workshop
from enaex.processing import (
    EXTERNAL_WORKSHOPS,
    build_application_data,
    build_weekly_workshop_projection,
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


def gps_row(equipment: str, place: str, order: int = 0, faena: str = "Centinela") -> dict:
    return {
        "Equipo": equipment,
        "Lugar": place,
        "Faena": faena,
        "Estado": "OK",
        "_gps_response_order": order,
    }


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
    gps = pd.DataFrame([gps_row("Quadra-70", "SKC Calama")])
    data = build_application_data(excel, gps, settings())
    assert len(data.equipment) == 1
    row = data.equipment.iloc[0]
    assert row["plate"] == "ABCD12"
    assert row["status"] == "OK"
    assert row["planning_status"] == "En taller"
    assert row["workshop"] == "SKC Calama"
    assert row["gps_contract"] == "Centinela"
    assert row["gps_place"] == "SKC Calama"


def test_gps_is_deduplicated_before_contract_count() -> None:
    gps = pd.DataFrame(
        [
            gps_row("Quadra-70", "Faena", 0),
            gps_row("Quadra 70", "Faena", 1),
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
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


def test_current_capacity_uses_api_lugar_and_ignores_faena() -> None:
    gps = pd.DataFrame(
        [
            gps_row("E-1", "Rio Loa", 0),
            gps_row("E-2", "Rio Loa", 1),
            gps_row("E-3", "Faena", 2),
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    rio_loa = data.workshop_capacity[data.workshop_capacity["workshop"] == "RIO LOA"].iloc[0]
    assert rio_loa["occupied"] == 2
    assert set(data.current_workshops["equipment"]) == {"E-1", "E-2"}


def test_search_by_plate() -> None:
    aliases = {"EQ00001": ["Quadra-70", "ABCD12"], "EQ00002": ["Auger-165", "WXYZ99"]}
    assert search_equipment_ids("ABCD-12", aliases)[0] == "EQ00001"


def test_movements_only_use_mov_equipos_and_one_row_per_truck() -> None:
    excel = pd.DataFrame(
        [
            {
                "Equipo": "Quadra-1029",
                "Fecha Inicio": "10/07/2026",
                "Fecha Entrega": "12/07/2026",
                "Taller": "Rio Loa",
                "Faena": "Centinela",
                "_source_file": "Excel_2",
                "_source_sheet": "En proceso",
                "_source_row": 2,
                "_global_order": 0,
            },
            {
                "Equipo": "Quadra-1029",
                "Fecha Inicio": "15/07/2026",
                "Fecha Entrega": "18/07/2026",
                "Taller": "SKC Calama",
                "Faena": "Sierra Gorda",
                "Fecha actualización": "01/07/2026",
                "_source_file": "Excel_2",
                "_source_sheet": "Mov. equipos",
                "_source_row": 3,
                "_global_order": 1,
            },
            {
                "Equipo": "Quadra-1029",
                "Fecha Inicio": "16/07/2026",
                "Fecha Entrega": "20/07/2026",
                "Taller": "SKC Antofagasta",
                "Faena": "Collahuasi",
                "Fecha actualización": "02/07/2026",
                "_source_file": "Excel_2",
                "_source_sheet": "Mov. equipos",
                "_source_row": 4,
                "_global_order": 2,
            },
        ]
    )
    data = build_application_data(excel, pd.DataFrame(), settings())
    assert len(data.movements) == 1
    movement = data.movements.iloc[0]
    assert movement["start_date"] == pd.Timestamp("2026-07-16")
    assert movement["end_date"] == pd.Timestamp("2026-07-20")
    assert movement["workshop_canonical"] == "SKC ANTOFAGASTA"


def test_weekly_projection_starts_with_api_inventory_and_adds_future_downs() -> None:
    today = pd.Timestamp("2026-07-27")
    excel = pd.DataFrame(
        [
            {
                "Equipo": "E-3",
                "Fecha Inicio": "29/07/2026",
                "Fecha Entrega": "31/07/2026",
                "Taller": "Rio Loa",
                "Faena": "Centinela",
                "Estado": "En proceso",
                "_source_file": "Excel_2",
                "_source_sheet": "Mov. equipos",
                "_source_row": 2,
                "_global_order": 0,
            }
        ]
    )
    gps = pd.DataFrame(
        [
            gps_row("E-1", "Rio Loa", 0),
            gps_row("E-2", "Rio Loa", 1),
            gps_row("E-3", "Faena", 2),
        ]
    )
    data = build_application_data(excel, gps, settings())
    projection = build_weekly_workshop_projection(
        data.movements,
        data.current_workshops,
        pd.Timestamp("2026-07-27"),
        today=today,
    )
    rio_loa = projection[projection["workshop"] == "RIO LOA"].iloc[0]
    assert rio_loa["current"] == 2
    assert rio_loa["downs"] == 1
    assert rio_loa["ups"] == 1
    assert rio_loa["peak"] == 3
    assert rio_loa["closing"] == 2
    assert rio_loa["status"] == "Sobrepasado"
    assert rio_loa["over_capacity"] == 1


def test_external_workshops_are_grouped_and_keep_real_places() -> None:
    gps = pd.DataFrame(
        [
            gps_row("E-1", "Indumar", 0),
            gps_row("E-2", "SKC Santiago", 1),
            gps_row("E-3", "Faena", 2),
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    external = data.current_workshops[
        data.current_workshops["workshop_bucket"] == EXTERNAL_WORKSHOPS
    ]
    assert len(external) == 2
    assert set(external["current_place"]) == {"Indumar", "SKC Santiago"}
    capacity = data.workshop_capacity[
        data.workshop_capacity["workshop"] == EXTERNAL_WORKSHOPS
    ].iloc[0]
    assert capacity["occupied"] == 2
    assert pd.isna(capacity["limit"])



def test_search_returns_requested_equipment_not_quadra_1029() -> None:
    aliases = {
        "EQ1": ["QUADRA-1029 AT Ex", "Quadra-1029"],
        "EQ2": ["AUGER-168 AT", "Auger-168"],
        "EQ3": ["QUADRA-1036 AT Ex", "Quadra-1036"],
    }
    assert search_equipment_ids("Auger-168", aliases) == ["EQ2"]
    assert search_equipment_ids("Quadra-1036", aliases) == ["EQ3"]
    assert search_equipment_ids("equipo inexistente", aliases) == []


def test_api_fields_control_status_and_certification_days_are_read() -> None:
    gps = pd.DataFrame(
        [
            {
                "Equipo": "QUADRA-1036 AT Ex",
                "Faena": "Collahuasi",
                "Condicion": "Catastrófico",
                "Estado": "CATASTROFICO",
                "Lugar": "SKC Alto Hospicio",
                "Hrs/Kms desde ultimo preventivo": 113,
                "Fecha Aprox. Proxima Mantencion": "04-02-2027",
                "D. RT": 140,
                "D. Sernageomin": 153,
                "D. DGMN": 161,
                "Marca": "ASTRA",
                "Sistema Control": "E-BLAST",
                "_gps_response_order": 0,
            }
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    row = data.equipment.iloc[0]
    assert row["status"] == "CATASTROFICO"
    assert row["condition"] == "Catastrófico"
    assert row["control_system"] == "E-BLAST"
    assert row["brand"] == "ASTRA"
    assert row["revision_tecnica_days"] == 140
    assert row["sernageomin_days"] == 153
    assert row["dgmn_days"] == 161
    today = pd.Timestamp.now().normalize()
    assert pd.Timestamp(row["revision_tecnica"]) == today + pd.Timedelta(days=140)


def test_tire_model_is_not_used_as_truck_model() -> None:
    excel = pd.DataFrame(
        [
            {
                "Equipo": "Quadra-70",
                "Modelo": "Katana",
                "_source_file": "Excel_1",
                "_source_sheet": "Neumaticos",
                "_source_row": 2,
                "_global_order": 0,
            }
        ]
    )
    gps = pd.DataFrame([gps_row("Quadra-70", "Faena")])
    data = build_application_data(excel, gps, settings())
    assert data.equipment.iloc[0]["model"] == "N/A"


def test_estado_de_equipos_and_recent_work_are_preserved() -> None:
    excel = pd.DataFrame(
        [
            {
                "Equipo": "Quadra-70",
                "Estado de equipos": "Cambio de bomba finalizado; pendiente prueba operacional",
                "Estado": "En proceso",
                "Taller": "SKC Calama",
                "Fecha actualización": "28/07/2026",
                "_source_file": "Excel_2",
                "_source_sheet": "En proceso",
                "_source_row": 2,
                "_global_order": 0,
            },
            {
                "Equipo": "Quadra-70",
                "Comentarios": "MP 900 y cambio de filtros",
                "Estado": "Listo",
                "Taller": "Rio Loa",
                "Fecha Entrega": "15/07/2026",
                "_source_file": "Excel_2",
                "_source_sheet": "Mov. equipos",
                "_source_row": 3,
                "_global_order": 1,
            },
        ]
    )
    gps = pd.DataFrame(
        [
            {
                **gps_row("Quadra-70", "SKC Calama"),
                "Estado": "En proceso",
                "Condicion": "Correctivo",
            }
        ]
    )
    data = build_application_data(excel, gps, settings())
    row = data.equipment.iloc[0]
    assert row["status"] == "En proceso"
    assert "Cambio de bomba" in row["status_detail"]
    details = " ".join(item["detalle"] for item in row["recent_works"])
    assert "Cambio de bomba" in details
    assert "MP 900" in details


def test_api_prefers_estado_deducido_and_never_uses_certification_number_as_status() -> None:
    gps = pd.DataFrame(
        [
            {
                "nombre": "QUADRA-1060 AT Ex",
                "nombre_faena": "Radomiro Tomic",
                "Estado": 109,
                "Estado_Deducido": "OK",
                "Lugar": "Faena",
                "Condicion": "Operativo",
                "D. RT": 17,
                "D. Sernageomin": 61,
                "D. DGMN": 67,
                "Fecha Aprox. Proxima Mantencion": "30-07-2026 (450)",
                "marca_nombre": "ASTRA",
                "Sistema Control": "E-BLAST",
                "horas_ult": 510,
            }
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    row = data.equipment.iloc[0]
    assert row["gps_state"] == "OK"
    assert row["gps_place"] == "Faena"
    assert row["gps_condition"] == "Operativo"
    assert row["revision_tecnica_days"] == 17
    assert row["sernageomin_days"] == 61
    assert row["dgmn_days"] == 67
    assert pd.Timestamp(row["next_maintenance_date"]) == pd.Timestamp("2026-07-30")


def test_api_duplicate_rows_are_merged_field_by_field() -> None:
    gps = pd.DataFrame(
        [
            {
                "nombre": "QUADRA-1060 AT Ex",
                "nombre_faena": "Radomiro Tomic",
                "Estado_Deducido": "OK",
                "Lugar": "Faena",
                "_gps_response_order": 0,
            },
            {
                "nombre": "QUADRA-1060 AT Ex",
                "D. RT": 17,
                "D. Sernageomin": 61,
                "D. DGMN": 67,
                "Fecha Aprox. Proxima Mantencion": "30-07-2026 (450)",
                "Sistema Control": "E-BLAST",
                "_gps_response_order": 1,
            },
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    assert len(data.gps) == 1
    row = data.equipment.iloc[0]
    assert row["gps_state"] == "OK"
    assert row["gps_place"] == "Faena"
    assert row["revision_tecnica_days"] == 17
    assert row["control_system"] == "E-BLAST"


def test_movement_status_does_not_replace_current_api_status() -> None:
    excel = pd.DataFrame(
        [
            {
                "Equipo": "QUADRA-1060 AT Ex",
                "Estado": "Pendiente",
                "Fecha Inicio": "01/08/2026",
                "Fecha Entrega": "10/08/2026",
                "Taller": "SKC Calama",
                "_source_file": "Excel_2",
                "_source_sheet": "Mov. equipos",
                "_source_row": 2,
                "_global_order": 0,
            }
        ]
    )
    gps = pd.DataFrame(
        [
            {
                "nombre": "QUADRA-1060 AT Ex",
                "Estado_Deducido": "OK",
                "Lugar": "Faena",
            }
        ]
    )
    data = build_application_data(excel, gps, settings())
    row = data.equipment.iloc[0]
    assert row["gps_state"] == "OK"
    assert row["status"] == "OK"
    assert row["movement_status"] == "Pendiente"


def test_date_with_maintenance_cycle_in_parentheses() -> None:
    assert format_date("30-07-2026 (450)") == "30/07/2026"


def test_contract_counts_only_factory_trucks() -> None:
    gps = pd.DataFrame(
        [
            gps_row("Quadra-70", "Faena", 0, "Michilla"),
            gps_row("Auger-165", "Faena", 1, "Michilla"),
            gps_row("AFI 2817496", "Faena", 2, "Michilla"),
            gps_row("PMO-101", "Faena", 3, "Michilla"),
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    michilla = data.contracts[data.contracts["contract"] == "Michilla"].iloc[0]
    assert michilla["actual"] == 2


def test_polvorin_is_visible_but_not_contractual() -> None:
    gps = pd.DataFrame(
        [
            gps_row("PMOCAM-12", "Faena", 0, "Collahuasi"),
            gps_row("PMO-22", "Faena", 1, "Collahuasi"),
            gps_row("Quadra-1030", "Faena", 2, "Collahuasi"),
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    assert set(data.gps["equipment_category"].tolist()) == {"Polvorín", "Camión fábrica"}
    collahuasi = data.contracts[data.contracts["contract"] == "Collahuasi"].iloc[0]
    assert collahuasi["actual"] == 1
    assert data.diagnostics["gps_polvorines"] == 2


def test_chuquicamata_sample_counts_three_quadra_and_excludes_afi() -> None:
    gps = pd.DataFrame(
        [
            gps_row("QUADRA-79 UB", "Faena", 0, "Chuquicamata"),
            gps_row("QUADRA-1003", "Faena", 1, "Chuquicamata"),
            gps_row("QUADRA-147 AT", "Faena", 2, "Chuquicamata"),
            gps_row("AFI 2815400", "Faena", 3, "Chuquicamata"),
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    chuqui = data.contracts[data.contracts["contract"] == "Chuquicamata"].iloc[0]
    assert chuqui["actual"] == 3
    assert chuqui["target"] == 2
    assert chuqui["difference"] == 1
    categories = dict(zip(data.gps["equipment"], data.gps["equipment_category"]))
    assert categories["QUADRA-79 UB"] == "Camión fábrica"
    assert categories["QUADRA-1003"] == "Camión fábrica"
    assert categories["QUADRA-147 AT"] == "Camión fábrica"
    assert categories["AFI 2815400"] == "Otro equipo"


def test_antucoya_contract_counts_only_factory_trucks():
    import pandas as pd
    from enaex.processing import build_contracts
    names = [
        "QUADRA-80 UIB", "QUADRA-83 UIB", "AUGER-150", "AUGER-1002 AT",
        "AFI 2817052", "AFI 2817053",
    ]
    gps = pd.DataFrame({
        "equipment": names,
        "equipment_key": names,
        "canonical_contract": ["Antucoya"] * len(names),
    })
    row = build_contracts(gps).query("contract == 'Antucoya'").iloc[0]
    assert int(row["actual"]) == 4
    assert int(row["target"]) == 3
    assert int(row["difference"]) == 1
