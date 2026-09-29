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


def test_rajo_inca_is_canonicalized_as_salvador() -> None:
    assert canonical_contract("Rajo Inca") == "Salvador"
    assert canonical_contract("Codelco Rajo Inca") == "Salvador"
    assert canonical_contract("División Salvador") == "Salvador"


def test_salvador_contract_includes_rajo_inca_factory_trucks() -> None:
    gps = pd.DataFrame(
        [
            gps_row("QUADRA-1200", "Faena", 0, "Rajo Inca"),
            gps_row("AUGER-177", "Faena", 1, "Salvador"),
            gps_row("AFI 999999", "Faena", 2, "Rajo Inca"),
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    salvador = data.contracts[data.contracts["contract"] == "Salvador"].iloc[0]
    assert int(salvador["actual"]) == 2


def test_critical_certifications_use_planning_api_and_all_equipment_types() -> None:
    from enaex.processing import build_planning_critical_certifications

    today = pd.Timestamp("2026-09-28")
    gps_raw = pd.DataFrame(
        [
            {"Equipo": "QUADRA-1001", "Faena": "Centinela", "D. RT": 20, "D. Sernageomin": 45, "D. DGMN": -2},
            {"Equipo": "PMOCAM-12", "Faena": "Collahuasi", "D. RT": 10, "D. Sernageomin": 90, "D. DGMN": 90},
            {"Equipo": "AUX-ENAEX-7", "Faena": "Spence", "D. RT": 5, "D. Sernageomin": 80, "D. DGMN": 80},
            {"Equipo": "ARRIENDO-55", "Faena": "Andina", "D. RT": 29, "D. Sernageomin": 100, "D. DGMN": 100},
            {"Equipo": "AFI 123", "Faena": "Antucoya", "D. RT": None, "D. Sernageomin": None, "D. DGMN": None},
        ]
    )
    data = build_application_data(pd.DataFrame(), gps_raw, settings())
    critical = build_planning_critical_certifications(data.gps, today=today)
    assert set(critical["equipment"]) == {"QUADRA-1001", "PMOCAM-12", "AUX-ENAEX-7", "ARRIENDO-55"}
    assert "AFI 123" not in set(critical["equipment"])
    assert set(critical["status"]) == {"🟡 Vence pronto", "🔴 Vencida"}
    # Solo amarillo/rojo: el Sernageomin verde de 45 días no aparece.
    assert not ((critical["equipment"] == "QUADRA-1001") & (critical["document"] == "Sernageomin")).any()


def test_gps_place_falls_back_to_nombre_lugar_when_lugar_is_empty() -> None:
    gps = pd.DataFrame(
        [
            {
                "Equipo": "QUADRA-1052 MT EX",
                "Faena": "Lomas Bayas",
                "Lugar": None,
                "nombre_lugar": "Faena",
                "Estado": "OK",
                "Fecha Retorno Operacion": "02-10-2026",
            },
            {
                "Equipo": "QUADRA-88 AT Ex",
                "Faena": "Lomas Bayas",
                "Lugar": None,
                "nombre_lugar": "INDUMAR",
                "Estado": "CORRECTIVO-F",
                "Fecha Retorno Operacion": "01-10-2026",
            },
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    by_equipment = data.gps.set_index("equipment")
    assert by_equipment.loc["QUADRA-1052 MT EX", "place"] == "Faena"
    assert by_equipment.loc["QUADRA-88 AT Ex", "place"] == "INDUMAR"
    assert format_date(by_equipment.loc["QUADRA-1052 MT EX", "return_operation_date"]) == "02/10/2026"
    assert format_date(by_equipment.loc["QUADRA-88 AT Ex", "return_operation_date"]) == "01/10/2026"


def test_place_schema_fallback_detects_unknown_backend_key() -> None:
    gps = pd.DataFrame(
        [
            {
                "Equipo": "QUADRA-1019 AT Ex",
                "Faena": "Andina",
                "ubicacion_operativa_actual": "Faena",
                "Estado": "ALERTA 1",
            },
            {
                "Equipo": "QUADRA-75 AT Ex",
                "Faena": "Andina",
                "ubicacion_operativa_actual": "FullRPM",
                "Estado": "PREVENTIVO",
            },
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    by_equipment = data.gps.set_index("equipment")
    assert by_equipment.loc["QUADRA-1019 AT Ex", "place"] == "Faena"
    assert by_equipment.loc["QUADRA-75 AT Ex", "place"] == "FullRPM"


def test_return_operation_schema_fallback_detects_abbreviated_key() -> None:
    gps = pd.DataFrame(
        [
            {
                "Equipo": "QUADRA-74 AT Ex",
                "Faena": "Andina",
                "Lugar": "Faena",
                "fecha_estimada_retorno_operacion": "30-11-2026",
                "Estado": "CATASTROFICO",
            }
        ]
    )
    data = build_application_data(pd.DataFrame(), gps, settings())
    row = data.gps.iloc[0]
    assert format_date(row["return_operation_date"]) == "30/11/2026"


def test_gps_loader_retries_timeout_and_recovers(monkeypatch) -> None:
    import requests
    from enaex.data_sources import load_gps_source

    calls = {"count": 0}

    class Response:
        status_code = 200
        def json(self):
            return [{"Equipo": "QUADRA-1", "Faena": "Collahuasi", "Lugar": "Faena"}]

    def fake_get(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] < 2:
            raise requests.exceptions.ConnectTimeout("timeout de prueba")
        return Response()

    monkeypatch.setattr(requests, "get", fake_get)
    frame, diagnostics, errors = load_gps_source(
        "https://example.test/api/dashboard/estado", "key", (21,), (1,), timeout=6, workers=1
    )
    assert len(frame) == 1
    assert frame.iloc[0]["Equipo"] == "QUADRA-1"
    assert diagnostics["gps_requests_failed"] == 0
    assert diagnostics["gps_requests_recovered"] >= 1
    assert errors == []


def test_certificate_aliases_can_merge_multiple_api_schemas() -> None:
    from enaex.processing import build_critical_certifications_all_equipment

    gps_raw = pd.DataFrame(
        [
            {
                "Equipo": "QUADRA-1001",
                "Faena": "Centinela",
                "D. RT": 20,
                "D. Sernageomin": 45,
                "D. DGMN": 90,
                "dias_rt": None,
            },
            {
                "Equipo": "AFI 55555",
                "Faena": "Andina",
                "D. RT": None,
                "dias_rt": 8,
                "dias_sngm": -2,
                "dias_dgmn": 100,
            },
        ]
    )
    data = build_application_data(pd.DataFrame(), gps_raw, settings())
    by_name = data.gps.set_index("equipment")
    assert int(by_name.loc["QUADRA-1001", "revision_tecnica_days"]) == 20
    assert int(by_name.loc["AFI 55555", "revision_tecnica_days"]) == 8
    assert int(by_name.loc["AFI 55555", "sernageomin_days"]) == -2

    critical = build_critical_certifications_all_equipment(data.equipment, today=pd.Timestamp("2026-09-29"))
    afi = critical[critical["equipment"].eq("AFI 55555")]
    assert set(afi["document"]) == {"Revisión Técnica", "Sernageomin"}
    assert set(afi["equipment_type"]) == {"Equipo en arriendo"}


def test_critical_certifications_differentiate_all_requested_equipment_types() -> None:
    from enaex.processing import build_critical_certifications_all_equipment

    gps_raw = pd.DataFrame(
        [
            {"Equipo": "AUGER-1001", "Faena": "Centinela", "D. RT": 15},
            {"Equipo": "AFI 5718695_E-PMO", "Faena": "Collahuasi", "D. Sernageomin": -1},
            {"Equipo": "C GRUA - TZWS-80", "Faena": "Andina", "D. DGMN": 25},
            {"Equipo": "AFI 2817052", "Faena": "Antucoya", "D. RT": 5},
        ]
    )
    data = build_application_data(pd.DataFrame(), gps_raw, settings())
    critical = build_critical_certifications_all_equipment(data.equipment, today=pd.Timestamp("2026-09-29"))
    type_by_equipment = dict(zip(critical["equipment"], critical["equipment_type"]))
    assert type_by_equipment["AUGER-1001"] == "Camión fábrica"
    assert type_by_equipment["AFI 5718695_E-PMO"] == "Polvorín"
    assert type_by_equipment["C GRUA - TZWS-80"] == "Auxiliar Enaex"
    assert type_by_equipment["AFI 2817052"] == "Equipo en arriendo"


def test_critical_certifications_omit_missing_and_green_documents() -> None:
    from enaex.processing import build_critical_certifications_all_equipment

    gps_raw = pd.DataFrame(
        [
            {"Equipo": "QUADRA-1", "Faena": "Andina", "D. RT": 31, "D. Sernageomin": None, "D. DGMN": 0},
        ]
    )
    data = build_application_data(pd.DataFrame(), gps_raw, settings())
    critical = build_critical_certifications_all_equipment(data.equipment, today=pd.Timestamp("2026-09-29"))
    assert len(critical) == 1
    row = critical.iloc[0]
    assert row["document"] == "DGMN"
    assert int(row["days"]) == 0
    assert row["status"] == "🔴 Vence hoy"



def test_cross_audit_flags_faena_vs_active_workshop() -> None:
    from enaex.processing import build_cross_source_discrepancies

    equipment = pd.DataFrame(
        [
            {
                "equipment": "QUADRA-1",
                "gps_faena": "Andina",
                "gps_place": "Faena",
                "planned_workshop": "SKC Calama",
                "workshop": "SKC Calama",
                "planning_status": "En proceso",
                "status_detail": "Equipo en taller",
                "start_date": pd.Timestamp("2026-09-20"),
                "end_date": pd.Timestamp("2026-10-05"),
                "return_operation_date": pd.NaT,
            }
        ]
    )
    result = build_cross_source_discrepancies(equipment, today=pd.Timestamp("2026-09-29"))
    location = result[result["issue_type"].eq("Ubicación")]
    assert len(location) == 1
    assert location.iloc[0]["system_place"] == "Faena"
    assert location.iloc[0]["excel_place"] == "SKC Calama"


def test_cross_audit_flags_workshop_vs_completed_excel_plan() -> None:
    from enaex.processing import build_cross_source_discrepancies

    equipment = pd.DataFrame(
        [
            {
                "equipment": "QUADRA-2",
                "gps_faena": "Centinela",
                "gps_place": "Río Loa",
                "planned_workshop": "Río Loa",
                "workshop": "Río Loa",
                "planning_status": "Listo",
                "status_detail": "",
                "start_date": pd.Timestamp("2026-09-10"),
                "end_date": pd.Timestamp("2026-09-25"),
                "return_operation_date": pd.NaT,
            }
        ]
    )
    result = build_cross_source_discrepancies(equipment, today=pd.Timestamp("2026-09-29"))
    location = result[result["issue_type"].eq("Ubicación")]
    assert len(location) == 1
    assert location.iloc[0]["system_place"] == "Río Loa"
    assert location.iloc[0]["excel_place"] == "Faena"


def test_cross_audit_flags_return_date_difference() -> None:
    from enaex.processing import build_cross_source_discrepancies

    equipment = pd.DataFrame(
        [
            {
                "equipment": "QUADRA-3",
                "gps_faena": "Lomas Bayas",
                "gps_place": "Faena",
                "planned_workshop": "SKC Calama",
                "workshop": "N/A",
                "planning_status": "Pendiente",
                "status_detail": "",
                "start_date": pd.Timestamp("2026-10-01"),
                "end_date": pd.Timestamp("2026-10-10"),
                "return_operation_date": pd.Timestamp("2026-10-12"),
            }
        ]
    )
    result = build_cross_source_discrepancies(equipment, today=pd.Timestamp("2026-09-29"))
    dates = result[result["issue_type"].eq("Fecha retorno")]
    assert len(dates) == 1
    assert int(dates.iloc[0]["date_difference_days"]) == 2
    assert dates.iloc[0]["system_return_date"] == "12/10/2026"
    assert dates.iloc[0]["excel_return_date"] == "10/10/2026"


def test_cross_audit_ignores_unknowns_and_equal_values() -> None:
    from enaex.processing import build_cross_source_discrepancies

    equipment = pd.DataFrame(
        [
            {
                "equipment": "QUADRA-4",
                "gps_faena": "Andina",
                "gps_place": "Faena",
                "planned_workshop": "SKC Calama",
                "workshop": "N/A",
                "planning_status": "Pendiente",
                "status_detail": "",
                "start_date": pd.Timestamp("2026-10-10"),
                "end_date": pd.Timestamp("2026-10-20"),
                "return_operation_date": pd.Timestamp("2026-10-20"),
            },
            {
                "equipment": "QUADRA-5",
                "gps_faena": "Andina",
                "gps_place": "N/A",
                "planned_workshop": "N/A",
                "workshop": "N/A",
                "planning_status": "N/A",
                "status_detail": "",
                "start_date": pd.NaT,
                "end_date": pd.NaT,
                "return_operation_date": pd.NaT,
            },
        ]
    )
    result = build_cross_source_discrepancies(equipment, today=pd.Timestamp("2026-09-29"))
    assert result.empty
