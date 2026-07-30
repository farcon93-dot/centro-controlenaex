from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from typing import Any, Iterable

import pandas as pd
from rapidfuzz.fuzz import WRatio

from enaex.aliases import (
    CONTRACT_ALIASES,
    FIELD_ALIASES,
    GPS_FIELD_ALIASES,
    match_columns,
)
from enaex.configuration import CONTRACT_TARGETS, WORKSHOP_CAPACITY, Settings
from enaex.models import ApplicationData
from enaex.normalize import (
    clean_display,
    format_date,
    is_empty,
    is_terminal_status,
    normalize_identifier,
    normalize_text,
    normalize_workshop,
    parse_date,
)


CANONICAL_FIELDS = tuple(FIELD_ALIASES.keys())
GPS_CANONICAL_FIELDS = tuple(GPS_FIELD_ALIASES.keys())


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1


def canonical_contract(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return "Sin faena"
    candidates: list[tuple[int, str, str]] = []
    for contract, aliases in CONTRACT_ALIASES.items():
        for alias in aliases:
            normalized_alias = normalize_text(alias)
            candidates.append((len(normalized_alias), contract, normalized_alias))
    for _, contract, alias in sorted(candidates, reverse=True):
        if alias and alias in text:
            return contract
    return clean_display(value, default="Sin faena")


def _coalesce(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series(pd.NA, index=frame.index, dtype="object")
    for column in columns:
        if column not in frame.columns:
            continue
        values = frame[column]
        fill_mask = result.map(is_empty) & ~values.map(is_empty)
        if fill_mask.any():
            result.loc[fill_mask] = values.loc[fill_mask]
    return result


def canonicalize_excel(excel_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if excel_raw.empty:
        return pd.DataFrame(), {"excel_column_mapping": {}, "excel_column_candidates": {}}

    mapping, details = match_columns(excel_raw.columns, FIELD_ALIASES, threshold=80.0)
    history = pd.DataFrame(index=excel_raw.index)
    for field in CANONICAL_FIELDS:
        history[field] = _coalesce(excel_raw, mapping.get(field, []))

    metadata_columns = [
        "_source_file", "_source_sheet", "_source_row", "_source_url", "_download_url", "_global_order"
    ]
    for column in metadata_columns:
        if column in excel_raw.columns:
            history[column] = excel_raw[column]
    if "_global_order" not in history.columns:
        history["_global_order"] = range(len(history))

    # Soporta libros con celdas combinadas: el nombre del equipo suele estar solo en la primera fila.
    grouping = [column for column in ("_source_file", "_source_sheet") if column in history.columns]
    if grouping:
        for field in ("equipment", "plate", "vin"):
            history[field] = history.groupby(grouping, dropna=False)[field].ffill(limit=50)

    history["equipment_key"] = history["equipment"].map(normalize_identifier)
    history["plate_key"] = history["plate"].map(normalize_identifier)
    history["vin_key"] = history["vin"].map(normalize_identifier)
    history["_update_parsed"] = history["update_date"].map(parse_date)
    history["_has_update"] = history["_update_parsed"].notna().astype(int)

    has_identifier = (
        history["equipment_key"].ne("") | history["plate_key"].ne("") | history["vin_key"].ne("")
    )
    history = history.loc[has_identifier].copy().reset_index(drop=True)

    diagnostics = {
        "excel_column_mapping": mapping,
        "excel_column_candidates": {
            field: [{"columna": column, "puntaje": round(score, 1)} for column, score in candidates]
            for field, candidates in details.items()
        },
    }
    return history, diagnostics


def _gps_identity(row: pd.Series) -> str:
    if row.get("equipment_key"):
        return f"equipment:{row['equipment_key']}"
    if row.get("plate_key"):
        return f"plate:{row['plate_key']}"
    if row.get("vin_key"):
        return f"vin:{row['vin_key']}"
    return ""


def canonicalize_gps(gps_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if gps_raw.empty:
        return pd.DataFrame(), {"gps_column_mapping": {}, "gps_column_candidates": {}}

    mapping, details = match_columns(gps_raw.columns, GPS_FIELD_ALIASES, threshold=80.0)
    gps = pd.DataFrame(index=gps_raw.index)
    for field in GPS_CANONICAL_FIELDS:
        gps[field] = _coalesce(gps_raw, mapping.get(field, []))

    for column in ("_gps_type", "_gps_zone", "_gps_response_order"):
        if column in gps_raw.columns:
            gps[column] = gps_raw[column]
    if "_gps_response_order" not in gps.columns:
        gps["_gps_response_order"] = range(len(gps))

    gps["equipment_key"] = gps["equipment"].map(normalize_identifier)
    gps["plate_key"] = gps["plate"].map(normalize_identifier)
    gps["vin_key"] = gps["vin"].map(normalize_identifier)
    gps["gps_identity_key"] = gps.apply(_gps_identity, axis=1)
    gps = gps[gps["gps_identity_key"].ne("")].copy()

    gps["timestamp_parsed"] = gps["timestamp"].map(parse_date)
    gps["_has_timestamp"] = gps["timestamp_parsed"].notna().astype(int)
    completeness_fields = ["equipment", "plate", "vin", "faena", "brand", "model", "hours", "status"]
    gps["_completeness"] = gps[completeness_fields].apply(
        lambda row: sum(not is_empty(value) for value in row), axis=1
    )
    gps = gps.sort_values(
        ["gps_identity_key", "_has_timestamp", "timestamp_parsed", "_completeness", "_gps_response_order"],
        ascending=True,
        na_position="first",
    )
    gps = gps.drop_duplicates("gps_identity_key", keep="last").reset_index(drop=True)
    gps["canonical_contract"] = gps["faena"].map(canonical_contract)

    diagnostics = {
        "gps_column_mapping": mapping,
        "gps_column_candidates": {
            field: [{"columna": column, "puntaje": round(score, 1)} for column, score in candidates]
            for field, candidates in details.items()
        },
        "gps_rows_unique": len(gps),
    }
    return gps, diagnostics


def assign_entities(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history.assign(entity_id=pd.Series(dtype="object"))

    union_find = UnionFind(len(history))
    seen: dict[str, int] = {}
    for position, row in enumerate(history[["equipment_key", "plate_key", "vin_key"]].itertuples(index=False)):
        keys = [
            f"equipment:{row.equipment_key}" if row.equipment_key else "",
            f"plate:{row.plate_key}" if row.plate_key else "",
            f"vin:{row.vin_key}" if row.vin_key else "",
        ]
        for key in (key for key in keys if key):
            if key in seen:
                union_find.union(position, seen[key])
            else:
                seen[key] = position

    root_to_id: dict[int, str] = {}
    entity_ids: list[str] = []
    for position in range(len(history)):
        root = union_find.find(position)
        if root not in root_to_id:
            root_to_id[root] = f"EQ{len(root_to_id) + 1:05d}"
        entity_ids.append(root_to_id[root])

    assigned = history.copy()
    assigned["entity_id"] = entity_ids
    return assigned


def _latest_nonempty(group: pd.DataFrame, field: str) -> Any:
    ordered = group.sort_values(
        ["_has_update", "_update_parsed", "_global_order"], ascending=True, na_position="first"
    )
    for value in reversed(ordered[field].tolist()):
        if not is_empty(value):
            return value
    return pd.NA


def _cert_summary(group: pd.DataFrame, field: str) -> tuple[pd.Timestamp | None, str]:
    raw_values = [value for value in group[field].tolist() if not is_empty(value)]
    parsed_values = [parsed for parsed in (parse_date(value) for value in raw_values) if parsed is not None]
    if parsed_values:
        return max(parsed_values), "ok"
    if raw_values:
        return None, "invalid"
    return None, "missing"


def _gps_candidates_for_group(group: pd.DataFrame, gps: pd.DataFrame) -> pd.DataFrame:
    if gps.empty:
        return gps
    equipment_keys = set(key for key in group["equipment_key"].tolist() if key)
    plate_keys = set(key for key in group["plate_key"].tolist() if key)
    vin_keys = set(key for key in group["vin_key"].tolist() if key)
    mask = (
        gps["equipment_key"].isin(equipment_keys)
        | gps["plate_key"].isin(plate_keys)
        | gps["vin_key"].isin(vin_keys)
    )
    return gps.loc[mask]


def consolidate_equipment(history: pd.DataFrame, gps: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    records: list[dict[str, Any]] = []
    aliases_by_entity: dict[str, list[str]] = {}
    gps_used: set[str] = set()

    for entity_id, group in history.groupby("entity_id", sort=False):
        gps_candidates = _gps_candidates_for_group(group, gps)
        gps_row: pd.Series | None = None
        if not gps_candidates.empty:
            gps_candidates = gps_candidates.sort_values(
                ["_has_timestamp", "timestamp_parsed", "_completeness"],
                ascending=True,
                na_position="first",
            )
            gps_row = gps_candidates.iloc[-1]
            gps_used.add(str(gps_row["gps_identity_key"]))

        latest = {field: _latest_nonempty(group, field) for field in CANONICAL_FIELDS}
        rt_date, rt_quality = _cert_summary(group, "revision_tecnica")
        sngm_date, sngm_quality = _cert_summary(group, "sernageomin")
        dgmn_date, dgmn_quality = _cert_summary(group, "dgmn")

        name = clean_display(latest["equipment"], default="")
        plate = clean_display(latest["plate"], default="")
        vin = clean_display(latest["vin"], default="")
        if not name:
            name = plate or vin or entity_id

        display_aliases = {
            clean_display(value, default="")
            for field in ("equipment", "plate", "vin")
            for value in group[field].tolist()
            if not is_empty(value)
        }
        if gps_row is not None:
            display_aliases.update(
                clean_display(gps_row.get(field), default="")
                for field in ("equipment", "plate", "vin")
                if not is_empty(gps_row.get(field))
            )
        display_aliases.discard("")
        aliases_by_entity[entity_id] = sorted(display_aliases)

        records.append(
            {
                "entity_id": entity_id,
                "equipment": name,
                "plate": plate or "N/A",
                "vin": vin or "N/A",
                "brand": clean_display(latest["brand"]),
                "model": clean_display(latest["model"]),
                "year": clean_display(latest["year"]),
                "capacity": clean_display(latest["capacity"]),
                "control_system": clean_display(latest["control_system"]),
                "excel_hours": clean_display(latest["hours"]),
                "status": clean_display(latest["status"]),
                "workshop": clean_display(latest["workshop"]),
                "comments": clean_display(latest["comments"]),
                "start_date": parse_date(latest["start_date"]),
                "end_date": parse_date(latest["end_date"]),
                "planned_faena": clean_display(latest["faena"]),
                "last_excel_update": parse_date(latest["update_date"]),
                "revision_tecnica": rt_date,
                "revision_tecnica_quality": rt_quality,
                "sernageomin": sngm_date,
                "sernageomin_quality": sngm_quality,
                "dgmn": dgmn_date,
                "dgmn_quality": dgmn_quality,
                "gps_faena": clean_display(gps_row.get("faena")) if gps_row is not None else "No reporta GPS",
                "gps_contract": str(gps_row.get("canonical_contract")) if gps_row is not None else "Sin faena",
                "gps_state": clean_display(gps_row.get("status")) if gps_row is not None else "N/A",
                "gps_hours": clean_display(gps_row.get("hours")) if gps_row is not None else "N/A",
                "gps_brand": clean_display(gps_row.get("brand")) if gps_row is not None else "N/A",
                "gps_model": clean_display(gps_row.get("model")) if gps_row is not None else "N/A",
                "gps_last_update": gps_row.get("timestamp_parsed") if gps_row is not None else pd.NaT,
                "history_rows": len(group),
                "sources": ", ".join(
                    sorted(
                        {
                            f"{clean_display(row.get('_source_file'))}/{clean_display(row.get('_source_sheet'))}"
                            for _, row in group.iterrows()
                        }
                    )
                ),
            }
        )

    # Equipos que están en GPS pero todavía no existen en los Excel.
    for _, gps_row in gps.iterrows():
        identity = str(gps_row["gps_identity_key"])
        if identity in gps_used:
            continue
        entity_id = f"GPS{len(records) + 1:05d}"
        name = clean_display(gps_row.get("equipment"), default="")
        plate = clean_display(gps_row.get("plate"), default="")
        vin = clean_display(gps_row.get("vin"), default="")
        name = name or plate or vin or entity_id
        aliases = [alias for alias in (name, plate, vin) if alias]
        aliases_by_entity[entity_id] = sorted(set(aliases))
        records.append(
            {
                "entity_id": entity_id,
                "equipment": name,
                "plate": plate or "N/A",
                "vin": vin or "N/A",
                "brand": clean_display(gps_row.get("brand")),
                "model": clean_display(gps_row.get("model")),
                "year": "N/A",
                "capacity": "N/A",
                "control_system": "N/A",
                "excel_hours": "N/A",
                "status": "N/A",
                "workshop": "N/A",
                "comments": "N/A",
                "start_date": pd.NaT,
                "end_date": pd.NaT,
                "planned_faena": "N/A",
                "last_excel_update": pd.NaT,
                "revision_tecnica": pd.NaT,
                "revision_tecnica_quality": "missing",
                "sernageomin": pd.NaT,
                "sernageomin_quality": "missing",
                "dgmn": pd.NaT,
                "dgmn_quality": "missing",
                "gps_faena": clean_display(gps_row.get("faena")),
                "gps_contract": str(gps_row.get("canonical_contract")),
                "gps_state": clean_display(gps_row.get("status")),
                "gps_hours": clean_display(gps_row.get("hours")),
                "gps_brand": clean_display(gps_row.get("brand")),
                "gps_model": clean_display(gps_row.get("model")),
                "gps_last_update": gps_row.get("timestamp_parsed"),
                "history_rows": 0,
                "sources": "Solo GPS",
            }
        )

    equipment = pd.DataFrame(records)
    if not equipment.empty:
        equipment = equipment.sort_values("equipment", key=lambda series: series.astype(str).str.lower()).reset_index(drop=True)
    return equipment, aliases_by_entity


def build_certifications(equipment: pd.DataFrame, today: pd.Timestamp | None = None) -> pd.DataFrame:
    if equipment.empty:
        return pd.DataFrame()
    today = (today or pd.Timestamp.now()).normalize()
    document_fields = (
        ("Revisión Técnica", "revision_tecnica", "revision_tecnica_quality"),
        ("Sernageomin", "sernageomin", "sernageomin_quality"),
        ("DGMN", "dgmn", "dgmn_quality"),
    )
    rows: list[dict[str, Any]] = []
    for _, equipment_row in equipment.iterrows():
        for document, date_field, quality_field in document_fields:
            quality = equipment_row.get(quality_field, "missing")
            expiration = equipment_row.get(date_field)
            if quality == "invalid":
                status = "Fecha inválida"
                days = None
                priority = 1
            elif quality == "missing" or pd.isna(expiration):
                status = "Sin fecha"
                days = None
                priority = 2
            else:
                expiration = pd.Timestamp(expiration).normalize()
                days = int((expiration - today).days)
                if days < 0:
                    status = "Vencida"
                    priority = 0
                elif days <= 30:
                    status = "Vence pronto"
                    priority = 1
                else:
                    status = "Vigente"
                    priority = 3
            rows.append(
                {
                    "entity_id": equipment_row["entity_id"],
                    "equipment": equipment_row["equipment"],
                    "document": document,
                    "expiration": expiration,
                    "expiration_text": format_date(expiration),
                    "days": days,
                    "status": status,
                    "priority": priority,
                }
            )
    return pd.DataFrame(rows).sort_values(["priority", "days", "equipment"], na_position="last").reset_index(drop=True)


def build_movements(history: pd.DataFrame, equipment: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    fallback = equipment.set_index("entity_id").to_dict("index") if not equipment.empty else {}
    rows: list[dict[str, Any]] = []

    for _, row in history.iterrows():
        start = parse_date(row.get("start_date"))
        end = parse_date(row.get("end_date"))
        if start is None and end is None:
            continue
        entity_id = str(row["entity_id"])
        equipment_data = fallback.get(entity_id, {})
        workshop_raw = row.get("workshop")
        faena_raw = row.get("faena")
        status_raw = row.get("status")
        comments_raw = row.get("comments")
        rows.append(
            {
                "entity_id": entity_id,
                "equipment": equipment_data.get("equipment", entity_id),
                "start_date": start,
                "end_date": end,
                "workshop": clean_display(workshop_raw, default=equipment_data.get("workshop", "N/A")),
                "workshop_canonical": normalize_workshop(
                    workshop_raw if not is_empty(workshop_raw) else equipment_data.get("workshop")
                ),
                "faena": clean_display(faena_raw, default=equipment_data.get("planned_faena", "N/A")),
                "faena_canonical": canonical_contract(
                    faena_raw if not is_empty(faena_raw) else equipment_data.get("planned_faena")
                ),
                "status": clean_display(status_raw, default=equipment_data.get("status", "N/A")),
                "comments": clean_display(comments_raw, default=equipment_data.get("comments", "N/A")),
                "update_date": row.get("_update_parsed"),
                "source": f"{clean_display(row.get('_source_file'))}/{clean_display(row.get('_source_sheet'))}",
                "source_row": row.get("_source_row"),
                "_global_order": row.get("_global_order", 0),
            }
        )

    movements = pd.DataFrame(rows)
    if movements.empty:
        return movements
    dedupe_columns = ["entity_id", "start_date", "end_date", "workshop_canonical", "faena_canonical"]
    movements = movements.sort_values(["update_date", "_global_order"], na_position="first")
    movements = movements.drop_duplicates(dedupe_columns, keep="last")
    return movements.sort_values(["start_date", "end_date", "equipment"], na_position="last").reset_index(drop=True)


def build_workshop_capacity(
    movements: pd.DataFrame,
    today: pd.Timestamp | None = None,
) -> pd.DataFrame:
    today = (today or pd.Timestamp.now()).normalize()
    active = pd.DataFrame()
    if not movements.empty:
        active = movements[
            movements["start_date"].notna()
            & (movements["start_date"] <= today)
            & (movements["end_date"].isna() | (movements["end_date"] >= today))
            & ~movements["status"].map(is_terminal_status)
            & movements["workshop_canonical"].isin(WORKSHOP_CAPACITY)
        ].copy()
        if not active.empty:
            active = active.sort_values(["start_date", "update_date", "_global_order"], na_position="first")
            active = active.drop_duplicates("entity_id", keep="last")

    rows: list[dict[str, Any]] = []
    for workshop, limit in WORKSHOP_CAPACITY.items():
        occupied = int((active["workshop_canonical"] == workshop).sum()) if not active.empty else 0
        if occupied > limit:
            status = "Sobrepasado"
        elif occupied == limit:
            status = "Al límite"
        else:
            status = "Con espacio"
        rows.append(
            {
                "workshop": workshop,
                "occupied": occupied,
                "limit": limit,
                "available": max(limit - occupied, 0),
                "status": status,
            }
        )
    return pd.DataFrame(rows)


def build_contracts(gps: pd.DataFrame) -> pd.DataFrame:
    counts = gps["canonical_contract"].value_counts().to_dict() if not gps.empty else {}
    rows: list[dict[str, Any]] = []
    for contract, target in CONTRACT_TARGETS.items():
        actual = int(counts.get(contract, 0))
        difference = actual - target
        if difference < 0:
            status = "Faltan"
        elif difference == 0:
            status = "Cumplido"
        else:
            status = "Sobre objetivo"
        rows.append(
            {
                "contract": contract,
                "target": target,
                "actual": actual,
                "difference": difference,
                "status": status,
            }
        )
    return pd.DataFrame(rows)


def search_equipment_ids(
    term: str,
    aliases_by_entity: dict[str, list[str]],
    max_results: int = 8,
) -> list[str]:
    normalized_term = normalize_identifier(term)
    if not normalized_term:
        return []

    scored: list[tuple[str, float]] = []
    for entity_id, aliases in aliases_by_entity.items():
        normalized_aliases = [normalize_identifier(alias) for alias in aliases if normalize_identifier(alias)]
        if not normalized_aliases:
            continue
        if normalized_term in normalized_aliases:
            score = 100.0
        elif len(normalized_term) >= 4 and any(normalized_term in alias for alias in normalized_aliases):
            score = 94.0
        elif any(len(alias) >= 4 and alias in normalized_term for alias in normalized_aliases):
            score = 88.0
        else:
            score = max(float(WRatio(normalized_term, alias)) for alias in normalized_aliases)
        if score >= 72.0:
            scored.append((entity_id, score))

    scored.sort(key=lambda item: (-item[1], item[0]))
    if not scored:
        return []
    top_score = scored[0][1]
    if top_score >= 99.9:
        selected = [item for item in scored if item[1] >= 99.9]
    elif top_score >= 93.0:
        selected = [item for item in scored if item[1] >= top_score - 0.5]
    else:
        selected = scored[:3]
    return [entity_id for entity_id, _ in selected[:max_results]]


def build_application_data(
    excel_raw: pd.DataFrame,
    gps_raw: pd.DataFrame,
    settings: Settings,
    source_diagnostics: dict[str, Any] | None = None,
    source_errors: list[str] | None = None,
) -> ApplicationData:
    history, excel_diagnostics = canonicalize_excel(excel_raw)
    gps, gps_diagnostics = canonicalize_gps(gps_raw)
    history = assign_entities(history)
    equipment, search_aliases = consolidate_equipment(history, gps)
    certifications = build_certifications(equipment)
    movements = build_movements(history, equipment)
    workshop_capacity = build_workshop_capacity(movements)
    contracts = build_contracts(gps)

    diagnostics: dict[str, Any] = {}
    diagnostics.update(source_diagnostics or {})
    diagnostics.update(excel_diagnostics)
    diagnostics.update(gps_diagnostics)
    diagnostics.update(
        {
            "equipment_total": len(equipment),
            "history_rows_canonical": len(history),
            "movement_rows": len(movements),
            "settings": {
                **asdict(settings),
                "gps_api_key": "configurada" if settings.gps_api_key else "faltante",
                "gemini_api_key": "configurada" if settings.gemini_api_key else "faltante",
            },
        }
    )

    return ApplicationData(
        equipment=equipment,
        history=history,
        gps=gps,
        movements=movements,
        certifications=certifications,
        contracts=contracts,
        workshop_capacity=workshop_capacity,
        search_aliases=search_aliases,
        diagnostics=diagnostics,
        errors=list(source_errors or []),
        loaded_at=datetime.now(),
    )
