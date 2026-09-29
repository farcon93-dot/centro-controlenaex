from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
import re
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






FACTORY_TRUCK_LABEL = "Camión fábrica"
POLVORIN_LABEL = "Polvorín"
OTHER_EQUIPMENT_LABEL = "Otro equipo"


def equipment_category(value: Any) -> str:
    """Clasifica equipos usando SOLO el código/nombre del equipo.

    Regla contractual estricta:
    - Camión fábrica: el identificador comienza por QUADRA o AUGER.
    - Polvorín: el identificador comienza por PMO o PMOCAM.
    - Todo lo demás (AFI, camionetas, auxiliares, etc.) es Otro equipo.

    Esta función NO usa marca, tipo GPS ni ninguna otra columna para decidir el contrato.
    """
    text = normalize_text(value)
    if not text:
        return OTHER_EQUIPMENT_LABEL

    # Acepta formatos reales como "QUADRA-79 UB", "QUADRA 1003",
    # "AUGER-168 AT Ex" y evita que "AFI 2815400" cuente por contrato.
    if re.match(r"^(quadra|auger)(?:\b|[-_ ])", text):
        return FACTORY_TRUCK_LABEL
    if re.match(r"^(pmocam|pmo)(?:\b|[-_ ])", text):
        return POLVORIN_LABEL
    return OTHER_EQUIPMENT_LABEL


def is_factory_truck(value: Any) -> bool:
    return equipment_category(value) == FACTORY_TRUCK_LABEL


def is_polvorin(value: Any) -> bool:
    return equipment_category(value) == POLVORIN_LABEL


def parse_days_remaining(value: Any) -> int | None:
    """Extrae días restantes desde valores como 140, -5 o "🟢 31"."""
    if is_empty(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
        number = int(float(value))
        return number if -5000 <= number <= 5000 else None
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    number = int(float(match.group(0).replace(",", ".")))
    return number if -5000 <= number <= 5000 else None


def expiration_from_api(date_value: Any, days_value: Any, today: pd.Timestamp | None = None) -> tuple[pd.Timestamp | None, int | None, str]:
    """Prioriza fecha explícita; si la API entrega días, calcula su fecha de vencimiento."""
    today = (today or pd.Timestamp.now()).normalize()
    explicit = parse_date(date_value)
    days = parse_days_remaining(days_value)
    if explicit is not None:
        return explicit, int((explicit - today).days), "api_date"
    if days is not None:
        return today + pd.Timedelta(days=days), days, "api_days"
    return None, None, "missing"


def _valid_entity_key(key: str, minimum_length: int = 4) -> bool:
    """Evita unir equipos mediante textos genéricos sin números."""
    return bool(key) and len(key) >= minimum_length and any(character.isdigit() for character in key)


def _sheet_name(value: Any) -> str:
    return normalize_text(value)


def _latest_nonempty_preferred(
    group: pd.DataFrame,
    field: str,
    preferred_sheet_tokens: tuple[str, ...] = (),
    rejected_sheet_tokens: tuple[str, ...] = (),
) -> Any:
    candidates = group
    if "_source_sheet" in group.columns:
        sheet_norm = group["_source_sheet"].map(_sheet_name)
        if rejected_sheet_tokens:
            rejected = sheet_norm.map(lambda text: any(token in text for token in rejected_sheet_tokens))
            candidates = group.loc[~rejected]
            if candidates.empty:
                return pd.NA
        if preferred_sheet_tokens:
            preferred = candidates["_source_sheet"].map(_sheet_name).map(
                lambda text: any(token in text for token in preferred_sheet_tokens)
            )
            preferred_rows = candidates.loc[preferred]
            if not preferred_rows.empty:
                candidates = preferred_rows
    return _latest_nonempty(candidates, field)


def _identifier_alias_variants(value: Any) -> set[str]:
    display = clean_display(value, default="")
    if not display:
        return set()
    variants = {display}
    normalized = normalize_text(display)
    # Los nombres de la API suelen venir como "QUADRA-1029 AT Ex". Se agrega
    # una variante limpia para que "Quadra-1029" sea una coincidencia exacta.
    match = re.search(r"\b(quadra|auger|camion|camión|unidad|equipo)[\s_-]*([a-z0-9-]+)", normalized)
    if match:
        prefix = match.group(1)
        code = match.group(2)
        variants.add(f"{prefix}-{code}")
        variants.add(f"{prefix} {code}")
    return variants


def _build_recent_work_history(group: pd.DataFrame, limit: int = 10) -> list[dict[str, Any]]:
    """Recupera últimos trabajos/estados sin inventar ni mezclar otros equipos."""
    if group.empty:
        return []
    ordered = group.sort_values(
        ["_has_update", "_update_parsed", "_global_order"],
        ascending=False,
        na_position="last",
    )
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for _, row in ordered.iterrows():
        detail = clean_display(row.get("equipment_status_detail"), default="")
        comments = clean_display(row.get("comments"), default="")
        status = clean_display(row.get("status"), default="")
        workshop = clean_display(row.get("workshop"), default="")
        if not detail and not comments:
            continue
        event_date = (
            parse_date(row.get("end_date"))
            or parse_date(row.get("start_date"))
            or parse_date(row.get("update_date"))
        )
        text_parts: list[str] = []
        for candidate in (detail, comments):
            if candidate and normalize_text(candidate) not in {normalize_text(item) for item in text_parts}:
                text_parts.append(candidate)
        text = " | ".join(text_parts)
        key = (format_date(event_date), normalize_text(text), normalize_text(workshop))
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "fecha": format_date(event_date),
                "estado": status or "N/A",
                "taller": workshop or "N/A",
                "detalle": text,
            }
        )
        if len(results) >= max(limit * 3, limit):
            break

    def sort_key(item: dict[str, Any]) -> tuple[int, pd.Timestamp]:
        parsed = parse_date(item.get("fecha"))
        return (1 if parsed is not None else 0, parsed or pd.Timestamp.min)

    return sorted(results, key=sort_key, reverse=True)[:limit]


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

    # Soporta celdas combinadas sin propagar patente/VIN a equipos distintos.
    # Solo el nombre del equipo puede heredarse y con un límite corto.
    grouping = [column for column in ("_source_file", "_source_sheet") if column in history.columns]
    if grouping:
        history["equipment"] = history.groupby(grouping, dropna=False)["equipment"].ffill(limit=12)

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


def _valid_gps_field_value(field: str, value: Any) -> bool:
    """Descarta valores incompatibles con el campo antes de consolidar la API."""
    if is_empty(value):
        return False
    text = clean_display(value, default="")
    normalized = normalize_text(text)
    if field in {"status", "condition", "place", "faena", "brand", "model", "control_system"}:
        # Un Estado 47/109 es realmente un día de certificación mal asociado.
        if re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", text.strip()):
            return False
    if field == "status":
        rejected = ("sernageomin", "sngm", "dgmn", "revision tecnica", "dias", "mantencion")
        if any(token in normalized for token in rejected):
            return False
    if field in {"revision_tecnica_days", "sernageomin_days", "dgmn_days", "days_out_service"}:
        return parse_days_remaining(value) is not None
    if field in {
        "revision_tecnica_date", "sernageomin_date", "dgmn_date",
        "return_operation_date", "next_maintenance_date", "timestamp",
    }:
        return parse_date(value) is not None
    return True


def _pick_gps_group_value(group: pd.DataFrame, field: str) -> Any:
    """Obtiene el dato más confiable de todos los registros API del mismo camión."""
    ordered = group.sort_values(
        ["_has_timestamp", "timestamp_parsed", "_completeness", "_gps_response_order"],
        ascending=True,
        na_position="first",
    )
    for value in reversed(ordered[field].tolist()):
        if _valid_gps_field_value(field, value):
            return value
    return pd.NA


def canonicalize_gps(gps_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    if gps_raw.empty:
        return pd.DataFrame(), {"gps_column_mapping": {}, "gps_column_candidates": {}}

    mapping, details = match_columns(gps_raw.columns, GPS_FIELD_ALIASES, threshold=80.0)
    gps_rows = pd.DataFrame(index=gps_raw.index)
    for field in GPS_CANONICAL_FIELDS:
        columns = mapping.get(field, [])
        # En la API puede coexistir, por ejemplo, `Lugar` con `nombre_lugar`.
        # El primero puede venir vacío para algunos equipos mientras el segundo
        # contiene el texto visible en el sistema de planificación. Se toman
        # todas las columnas válidas detectadas y se usa la primera con dato
        # compatible para cada fila.
        result = pd.Series(pd.NA, index=gps_raw.index, dtype="object")
        for column in columns:
            values = gps_raw[column]
            valid = values.map(lambda value: _valid_gps_field_value(field, value))
            fill_mask = result.map(is_empty) & valid
            if fill_mask.any():
                result.loc[fill_mask] = values.loc[fill_mask]
        gps_rows[field] = result

    for column in ("_gps_type", "_gps_zone", "_gps_response_order"):
        if column in gps_raw.columns:
            gps_rows[column] = gps_raw[column]
    if "_gps_response_order" not in gps_rows.columns:
        gps_rows["_gps_response_order"] = range(len(gps_rows))

    gps_rows["equipment_key"] = gps_rows["equipment"].map(normalize_identifier)
    gps_rows["plate_key"] = gps_rows["plate"].map(normalize_identifier)
    gps_rows["vin_key"] = gps_rows["vin"].map(normalize_identifier)
    gps_rows["gps_identity_key"] = gps_rows.apply(_gps_identity, axis=1)
    gps_rows = gps_rows[gps_rows["gps_identity_key"].ne("")].copy()

    gps_rows["timestamp_parsed"] = gps_rows["timestamp"].map(parse_date)
    gps_rows["_has_timestamp"] = gps_rows["timestamp_parsed"].notna().astype(int)
    completeness_fields = [
        "equipment", "plate", "vin", "faena", "place", "condition", "brand", "model",
        "control_system", "hours", "status", "return_operation_date", "days_out_service",
        "next_maintenance_date", "revision_tecnica_date", "sernageomin_date", "dgmn_date",
        "revision_tecnica_days", "sernageomin_days", "dgmn_days",
    ]
    gps_rows["_completeness"] = gps_rows[completeness_fields].apply(
        lambda row: sum(_valid_gps_field_value(field, row.get(field)) for field in completeness_fields),
        axis=1,
    )

    # Un camión puede llegar repetido desde varios tipos/zonas de la API. En vez
    # de elegir una sola fila (y perder Lugar, Estado o certificaciones), se unen
    # campo por campo todos sus registros válidos.
    consolidated: list[dict[str, Any]] = []
    rejected_numeric_status = 0
    for identity, group in gps_rows.groupby("gps_identity_key", sort=False):
        record: dict[str, Any] = {"gps_identity_key": identity}
        for field in GPS_CANONICAL_FIELDS:
            record[field] = _pick_gps_group_value(group, field)
        numeric_statuses = [
            value for value in group["status"].tolist()
            if not is_empty(value) and re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", str(value).strip())
        ]
        rejected_numeric_status += len(numeric_statuses)
        best_row = group.sort_values(
            ["_has_timestamp", "timestamp_parsed", "_completeness", "_gps_response_order"],
            ascending=True,
            na_position="first",
        ).iloc[-1]
        record["equipment_key"] = normalize_identifier(record.get("equipment"))
        record["plate_key"] = normalize_identifier(record.get("plate"))
        record["vin_key"] = normalize_identifier(record.get("vin"))
        record["timestamp_parsed"] = parse_date(record.get("timestamp")) or best_row.get("timestamp_parsed")
        record["_has_timestamp"] = int(record["timestamp_parsed"] is not None and not pd.isna(record["timestamp_parsed"]))
        record["_completeness"] = sum(
            _valid_gps_field_value(field, record.get(field)) for field in completeness_fields
        )
        record["_gps_response_order"] = best_row.get("_gps_response_order", 0)
        record["_gps_type"] = best_row.get("_gps_type")
        record["_gps_zone"] = best_row.get("_gps_zone")
        consolidated.append(record)

    gps = pd.DataFrame(consolidated)
    if gps.empty:
        return gps, {
            "gps_column_mapping": mapping,
            "gps_column_candidates": details,
            "gps_rows_unique": 0,
        }
    gps["canonical_contract"] = gps["faena"].map(canonical_contract)
    gps["equipment_category"] = gps["equipment"].map(equipment_category)

    category_counts = gps["equipment_category"].value_counts().to_dict()
    diagnostics = {
        "gps_column_mapping": mapping,
        "gps_column_candidates": {
            field: [{"columna": column, "puntaje": round(score, 1)} for column, score in candidates]
            for field, candidates in details.items()
        },
        "gps_rows_received": len(gps_rows),
        "gps_rows_unique": len(gps),
        "gps_numeric_status_values_rejected": rejected_numeric_status,
        "gps_equipment_category_counts": category_counts,
        "gps_factory_trucks": int(category_counts.get(FACTORY_TRUCK_LABEL, 0)),
        "gps_polvorines": int(category_counts.get(POLVORIN_LABEL, 0)),
    }
    return gps.reset_index(drop=True), diagnostics

def assign_entities(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return history.assign(entity_id=pd.Series(dtype="object"))

    union_find = UnionFind(len(history))
    seen: dict[str, int] = {}
    for position, row in enumerate(history[["equipment_key", "plate_key", "vin_key"]].itertuples(index=False)):
        keys = [
            f"equipment:{row.equipment_key}" if _valid_entity_key(row.equipment_key) else "",
            f"plate:{row.plate_key}" if _valid_entity_key(row.plate_key, minimum_length=5) else "",
            f"vin:{row.vin_key}" if _valid_entity_key(row.vin_key, minimum_length=6) else "",
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
    """Consolida cada camión sin mezclar identidades ni confundir datos técnicos."""
    records: list[dict[str, Any]] = []
    aliases_by_entity: dict[str, list[str]] = {}
    gps_used: set[str] = set()
    today = pd.Timestamp.now().normalize()

    def certificate_values(
        group: pd.DataFrame,
        gps_row: pd.Series | None,
        excel_field: str,
        api_date_field: str,
        api_days_field: str,
    ) -> tuple[pd.Timestamp | None, str, int | None, str]:
        api_date = gps_row.get(api_date_field) if gps_row is not None else None
        api_days = gps_row.get(api_days_field) if gps_row is not None else None
        expiration, days, source = expiration_from_api(api_date, api_days, today=today)
        if expiration is not None:
            return expiration, "ok", days, source
        excel_date, excel_quality = _cert_summary(group, excel_field)
        if excel_date is not None:
            return excel_date, excel_quality, int((excel_date - today).days), "excel"
        return None, excel_quality, None, "missing"

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
        gps_status = clean_display(gps_row.get("status"), default="") if gps_row is not None else ""
        gps_condition = clean_display(gps_row.get("condition"), default="") if gps_row is not None else ""

        # Los datos técnicos no se toman desde hojas de movimientos, neumáticos o repuestos.
        technical_preferred = ("maestro", "ficha", "flota", "base", "datos", "inventario")
        technical_rejected = (
            "mov equipos", "movimiento", "en proceso", "neumatic", "repuesto", "bodega",
            "componente", "mantencion semanal", "planificacion semanal",
        )
        excel_brand = _latest_nonempty_preferred(
            group, "brand", technical_preferred, technical_rejected
        )
        excel_model = _latest_nonempty_preferred(
            group, "model", technical_preferred, technical_rejected
        )
        excel_control = _latest_nonempty_preferred(
            group, "control_system", technical_preferred, technical_rejected
        )

        status_detail = _latest_nonempty_preferred(
            group,
            "equipment_status_detail",
            preferred_sheet_tokens=("en proceso",) if "en proceso" in normalize_text(gps_status) else (),
        )
        recent_works = _build_recent_work_history(group)

        rt_date, rt_quality, rt_days, rt_source = certificate_values(
            group, gps_row, "revision_tecnica", "revision_tecnica_date", "revision_tecnica_days"
        )
        sngm_date, sngm_quality, sngm_days, sngm_source = certificate_values(
            group, gps_row, "sernageomin", "sernageomin_date", "sernageomin_days"
        )
        dgmn_date, dgmn_quality, dgmn_days, dgmn_source = certificate_values(
            group, gps_row, "dgmn", "dgmn_date", "dgmn_days"
        )

        excel_name = clean_display(latest["equipment"], default="")
        gps_name = clean_display(gps_row.get("equipment"), default="") if gps_row is not None else ""
        name = gps_name or excel_name
        plate = clean_display(latest["plate"], default="")
        vin = clean_display(latest["vin"], default="")
        if gps_row is not None:
            plate = plate or clean_display(gps_row.get("plate"), default="")
            vin = vin or clean_display(gps_row.get("vin"), default="")
        if not name:
            name = plate or vin or entity_id

        display_aliases: set[str] = set()
        for field in ("equipment", "plate", "vin"):
            for value in group[field].tolist():
                if not is_empty(value):
                    display_aliases.update(_identifier_alias_variants(value))
        if gps_row is not None:
            for field in ("equipment", "plate", "vin"):
                if not is_empty(gps_row.get(field)):
                    display_aliases.update(_identifier_alias_variants(gps_row.get(field)))
        display_aliases.discard("")
        aliases_by_entity[entity_id] = sorted(display_aliases)

        api_brand = clean_display(gps_row.get("brand"), default="") if gps_row is not None else ""
        api_model = clean_display(gps_row.get("model"), default="") if gps_row is not None else ""
        api_control = clean_display(gps_row.get("control_system"), default="") if gps_row is not None else ""
        excel_status = clean_display(latest["status"], default="")

        records.append(
            {
                "entity_id": entity_id,
                "equipment": name,
                "plate": plate or "N/A",
                "vin": vin or "N/A",
                "brand": api_brand or clean_display(excel_brand),
                "model": api_model or clean_display(excel_model),
                "year": clean_display(latest["year"]),
                "capacity": clean_display(latest["capacity"]),
                "control_system": api_control or clean_display(excel_control),
                "excel_hours": clean_display(latest["hours"]),
                # Estado actual exacto del sistema de planificación/API.
                "status": gps_status or "N/A",
                "condition": gps_condition or "N/A",
                "planning_status": excel_status or "N/A",
                "status_detail": clean_display(status_detail),
                "workshop": clean_display(latest["workshop"]),
                "comments": clean_display(latest["comments"]),
                "recent_works": recent_works,
                "start_date": parse_date(latest["start_date"]),
                "end_date": parse_date(latest["end_date"]),
                "planned_faena": clean_display(latest["faena"]),
                "last_excel_update": parse_date(latest["update_date"]),
                "movement_status": "N/A",
                "movement_comments": "N/A",
                "planned_workshop": "N/A",
                "revision_tecnica": rt_date,
                "revision_tecnica_quality": rt_quality,
                "revision_tecnica_days": rt_days,
                "revision_tecnica_source": rt_source,
                "sernageomin": sngm_date,
                "sernageomin_quality": sngm_quality,
                "sernageomin_days": sngm_days,
                "sernageomin_source": sngm_source,
                "dgmn": dgmn_date,
                "dgmn_quality": dgmn_quality,
                "dgmn_days": dgmn_days,
                "dgmn_source": dgmn_source,
                "gps_faena": clean_display(gps_row.get("faena")) if gps_row is not None else "No reporta GPS",
                "gps_place": clean_display(gps_row.get("place")) if gps_row is not None else "N/A",
                "gps_contract": str(gps_row.get("canonical_contract")) if gps_row is not None else "Sin faena",
                "gps_state": gps_status or "N/A",
                "gps_condition": gps_condition or "N/A",
                "gps_hours": clean_display(gps_row.get("hours")) if gps_row is not None else "N/A",
                "gps_brand": api_brand or "N/A",
                "gps_model": api_model or "N/A",
                "gps_control_system": api_control or "N/A",
                "return_operation_date": parse_date(gps_row.get("return_operation_date")) if gps_row is not None else pd.NaT,
                "days_out_service": parse_days_remaining(gps_row.get("days_out_service")) if gps_row is not None else None,
                "next_maintenance_date": parse_date(gps_row.get("next_maintenance_date")) if gps_row is not None else pd.NaT,
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

    # Equipos presentes en API pero aún no identificados en Excel.
    for _, gps_row in gps.iterrows():
        identity = str(gps_row["gps_identity_key"])
        if identity in gps_used:
            continue
        entity_id = f"GPS{len(records) + 1:05d}"
        name = clean_display(gps_row.get("equipment"), default="")
        plate = clean_display(gps_row.get("plate"), default="")
        vin = clean_display(gps_row.get("vin"), default="")
        name = name or plate or vin or entity_id
        aliases: set[str] = set()
        for value in (name, plate, vin):
            aliases.update(_identifier_alias_variants(value))
        aliases_by_entity[entity_id] = sorted(alias for alias in aliases if alias)

        rt_date, rt_days, rt_source = expiration_from_api(
            gps_row.get("revision_tecnica_date"), gps_row.get("revision_tecnica_days"), today=today
        )
        sngm_date, sngm_days, sngm_source = expiration_from_api(
            gps_row.get("sernageomin_date"), gps_row.get("sernageomin_days"), today=today
        )
        dgmn_date, dgmn_days, dgmn_source = expiration_from_api(
            gps_row.get("dgmn_date"), gps_row.get("dgmn_days"), today=today
        )

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
                "control_system": clean_display(gps_row.get("control_system")),
                "excel_hours": "N/A",
                "status": clean_display(gps_row.get("status"), default="N/A"),
                "condition": clean_display(gps_row.get("condition")),
                "planning_status": "N/A",
                "status_detail": "N/A",
                "workshop": "N/A",
                "comments": "N/A",
                "recent_works": [],
                "start_date": pd.NaT,
                "end_date": pd.NaT,
                "planned_faena": "N/A",
                "last_excel_update": pd.NaT,
                "movement_status": "N/A",
                "movement_comments": "N/A",
                "planned_workshop": "N/A",
                "revision_tecnica": rt_date,
                "revision_tecnica_quality": "ok" if rt_date is not None else "missing",
                "revision_tecnica_days": rt_days,
                "revision_tecnica_source": rt_source,
                "sernageomin": sngm_date,
                "sernageomin_quality": "ok" if sngm_date is not None else "missing",
                "sernageomin_days": sngm_days,
                "sernageomin_source": sngm_source,
                "dgmn": dgmn_date,
                "dgmn_quality": "ok" if dgmn_date is not None else "missing",
                "dgmn_days": dgmn_days,
                "dgmn_source": dgmn_source,
                "gps_faena": clean_display(gps_row.get("faena")),
                "gps_place": clean_display(gps_row.get("place")),
                "gps_contract": str(gps_row.get("canonical_contract")),
                "gps_state": clean_display(gps_row.get("status"), default="N/A"),
                "gps_condition": clean_display(gps_row.get("condition")),
                "gps_hours": clean_display(gps_row.get("hours")),
                "gps_brand": clean_display(gps_row.get("brand")),
                "gps_model": clean_display(gps_row.get("model")),
                "gps_control_system": clean_display(gps_row.get("control_system")),
                "return_operation_date": parse_date(gps_row.get("return_operation_date")),
                "days_out_service": parse_days_remaining(gps_row.get("days_out_service")),
                "next_maintenance_date": parse_date(gps_row.get("next_maintenance_date")),
                "gps_last_update": gps_row.get("timestamp_parsed"),
                "history_rows": 0,
                "sources": "Solo API",
            }
        )

    equipment = pd.DataFrame(records)
    if not equipment.empty:
        equipment = equipment.sort_values(
            "equipment", key=lambda series: series.astype(str).str.lower()
        ).reset_index(drop=True)
    return equipment, aliases_by_entity

def build_planning_critical_certifications(
    gps: pd.DataFrame,
    today: pd.Timestamp | None = None,
    warning_days: int = 30,
) -> pd.DataFrame:
    """Devuelve SOLO certificaciones amarillas/rojas del sistema de planificación.

    Esta vista se construye directamente desde la API de planificación ya
    canonicalizada (``gps``), sin depender del Excel ni de la categoría del
    equipo. Por lo tanto incluye camiones fábrica, polvorines, auxiliares Enaex,
    equipos en arriendo y cualquier otro equipo que reporte RT/Sernageomin/DGMN.

    Convención observada en el sistema:
    - rojo: vencido (días < 0)
    - amarillo: vence dentro de ``warning_days`` (0..30 por defecto)
    - verde: más de ``warning_days``; no se muestra en alertas críticas

    Registros sin valor/fecha válida se omiten, porque no representan una alerta
    amarilla o roja del sistema de planificación.
    """
    columns = [
        "equipment", "document", "expiration", "expiration_text",
        "days", "status", "priority", "faena", "place",
    ]
    if gps.empty:
        return pd.DataFrame(columns=columns)

    today = (today or pd.Timestamp.now()).normalize()
    docs = (
        ("Revisión Técnica", "revision_tecnica_date", "revision_tecnica_days"),
        ("Sernageomin", "sernageomin_date", "sernageomin_days"),
        ("DGMN", "dgmn_date", "dgmn_days"),
    )

    rows: list[dict[str, Any]] = []
    for _, row in gps.iterrows():
        equipment_name = clean_display(row.get("equipment"), default="")
        if not equipment_name:
            continue
        for document, date_field, days_field in docs:
            expiration, days, _source = expiration_from_api(
                row.get(date_field), row.get(days_field), today=today
            )
            if days is None:
                continue
            if days < 0:
                status = "🔴 Vencida"
                priority = 0
            elif days <= warning_days:
                status = "🟡 Vence pronto"
                priority = 1
            else:
                continue

            rows.append(
                {
                    "equipment": equipment_name,
                    "document": document,
                    "expiration": expiration,
                    "expiration_text": format_date(expiration),
                    "days": int(days),
                    "status": status,
                    "priority": priority,
                    "faena": clean_display(row.get("faena"), default="N/A"),
                    "place": clean_display(row.get("place"), default="N/A"),
                }
            )

    if not rows:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(rows)
    return result.sort_values(
        ["priority", "days", "equipment", "document"],
        ascending=[True, True, True, True],
        na_position="last",
    ).reset_index(drop=True)


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


def _is_movement_sheet(value: Any) -> bool:
    """Acepta únicamente la hoja semanal destinada a movimientos de equipos."""
    normalized = normalize_text(value)
    valid_names = {
        "mov equipos",
        "movimiento equipos",
        "movimientos equipos",
        "movimientos de equipos",
    }
    return normalized in valid_names or normalized.startswith("mov equipos ")


def _latest_movement_value(group: pd.DataFrame, field: str) -> Any:
    """Último valor no vacío dentro de la hoja Mov. equipos."""
    ordered = group.sort_values(
        ["_has_update", "_update_parsed", "_global_order"],
        ascending=True,
        na_position="first",
    )
    for value in reversed(ordered[field].tolist()):
        if not is_empty(value):
            return value
    return pd.NA


def build_movements(history: pd.DataFrame, equipment: pd.DataFrame) -> pd.DataFrame:
    """
    Construye una sola planificación vigente por camión.

    Reglas:
    - Solo usa la pestaña ``Mov. equipos`` del Excel de planificación semanal.
    - Ignora fechas detectadas en hojas como ``En proceso`` u otras hojas.
    - Devuelve una única fecha de bajada y una única fecha de subida por equipo.
    """
    if history.empty or "_source_sheet" not in history.columns:
        return pd.DataFrame()

    movement_history = history[history["_source_sheet"].map(_is_movement_sheet)].copy()
    if movement_history.empty:
        return pd.DataFrame()

    movement_history["_movement_start"] = movement_history["start_date"].map(parse_date)
    movement_history["_movement_end"] = movement_history["end_date"].map(parse_date)
    movement_history = movement_history[
        movement_history["_movement_start"].notna() | movement_history["_movement_end"].notna()
    ].copy()
    if movement_history.empty:
        return pd.DataFrame()

    fallback = equipment.set_index("entity_id").to_dict("index") if not equipment.empty else {}
    rows: list[dict[str, Any]] = []

    for entity_id, group in movement_history.groupby("entity_id", sort=False):
        group = group.copy()
        group["_has_both_dates"] = (
            group["_movement_start"].notna() & group["_movement_end"].notna()
        ).astype(int)
        group["_movement_completeness"] = group[
            ["start_date", "end_date", "workshop", "faena", "status", "comments"]
        ].apply(lambda row: sum(not is_empty(value) for value in row), axis=1)

        # Se prioriza un registro que tenga ambas fechas. En empate, gana la
        # actualización/fila más reciente de la hoja Mov. equipos.
        ordered = group.sort_values(
            [
                "_has_both_dates",
                "_has_update",
                "_update_parsed",
                "_movement_completeness",
                "_global_order",
            ],
            ascending=True,
            na_position="first",
        )
        anchor = ordered.iloc[-1]

        start = anchor.get("_movement_start")
        end = anchor.get("_movement_end")
        if pd.isna(start):
            start = parse_date(_latest_movement_value(group, "start_date"))
        if pd.isna(end):
            end = parse_date(_latest_movement_value(group, "end_date"))

        equipment_data = fallback.get(str(entity_id), {})

        def movement_value(field: str, fallback_field: str, default: str = "N/A") -> str:
            value = anchor.get(field)
            if is_empty(value):
                value = _latest_movement_value(group, field)
            if is_empty(value):
                value = equipment_data.get(fallback_field)
            return clean_display(value, default=default)

        workshop = movement_value("workshop", "workshop")
        faena = movement_value("faena", "planned_faena")
        status = movement_value("status", "status")
        comments = movement_value("comments", "comments")
        source_file = clean_display(anchor.get("_source_file"))
        source_sheet = clean_display(anchor.get("_source_sheet"))

        date_issue = ""
        if start is not None and end is not None and end < start:
            date_issue = "La fecha de subida es anterior a la fecha de bajada."

        rows.append(
            {
                "entity_id": str(entity_id),
                "equipment": equipment_data.get("equipment", str(entity_id)),
                "start_date": start,
                "end_date": end,
                "workshop": workshop,
                "workshop_canonical": normalize_workshop(workshop),
                "faena": faena,
                "faena_canonical": canonical_contract(faena),
                "status": status,
                "comments": comments,
                "update_date": anchor.get("_update_parsed"),
                "source": f"{source_file}/{source_sheet}",
                "source_file": source_file,
                "source_sheet": source_sheet,
                "source_row": anchor.get("_source_row"),
                "date_issue": date_issue,
                "_global_order": anchor.get("_global_order", 0),
            }
        )

    movements = pd.DataFrame(rows)
    if movements.empty:
        return movements
    # Garantía final: un solo registro por camión.
    movements = movements.sort_values(
        ["update_date", "_global_order"], ascending=True, na_position="first"
    ).drop_duplicates("entity_id", keep="last")
    return movements.sort_values(
        ["start_date", "end_date", "equipment"], na_position="last"
    ).reset_index(drop=True)


def apply_movement_plan_to_equipment(
    equipment: pd.DataFrame,
    movements: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega el plan semanal sin reemplazar el estado actual de la API."""
    if equipment.empty:
        return equipment

    result = equipment.copy()
    result["start_date"] = pd.NaT
    result["end_date"] = pd.NaT
    result["movement_source"] = "Sin planificación en Mov. equipos"
    result["movement_status"] = "N/A"
    result["movement_comments"] = "N/A"
    result["planned_workshop"] = "N/A"

    if movements.empty:
        return result

    movement_by_entity = movements.set_index("entity_id")
    for index, row in result.iterrows():
        entity_id = str(row["entity_id"])
        if entity_id not in movement_by_entity.index:
            continue
        movement = movement_by_entity.loc[entity_id]
        if isinstance(movement, pd.DataFrame):
            movement = movement.iloc[-1]
        result.at[index, "start_date"] = movement.get("start_date")
        result.at[index, "end_date"] = movement.get("end_date")
        result.at[index, "movement_source"] = movement.get("source", "Mov. equipos")
        result.at[index, "movement_status"] = clean_display(movement.get("status"))
        result.at[index, "movement_comments"] = clean_display(movement.get("comments"))
        result.at[index, "planned_workshop"] = clean_display(movement.get("workshop"))
        faena = movement.get("faena")
        if not is_empty(faena):
            result.at[index, "planned_faena"] = faena
    return result


EXTERNAL_WORKSHOPS = "TALLERES EXTERNOS"


def classify_current_workshop(value: Any) -> str | None:
    """Clasifica la columna Lugar de la API como taller conocido, externo o no-taller."""
    text = normalize_text(value)
    if not text:
        return None

    non_workshop_values = {
        "faena", "en faena", "operacion", "operativo", "ruta", "en ruta",
        "transito", "en transito", "sin informacion", "sin ubicacion",
    }
    if text in non_workshop_values or text.startswith("faena "):
        return None

    canonical = normalize_workshop(value)
    if canonical in WORKSHOP_CAPACITY:
        return canonical
    return EXTERNAL_WORKSHOPS


def build_current_workshops(equipment: pd.DataFrame) -> pd.DataFrame:
    """Snapshot actual de talleres usando exclusivamente la columna Lugar de la API."""
    columns = [
        "entity_id", "equipment", "plate", "current_place", "workshop_bucket",
        "external_workshop", "gps_state", "gps_faena", "gps_last_update",
    ]
    if equipment.empty or "gps_place" not in equipment.columns:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for _, row in equipment.iterrows():
        current_place = clean_display(row.get("gps_place"), default="")
        bucket = classify_current_workshop(current_place)
        if bucket is None:
            continue
        rows.append(
            {
                "entity_id": str(row.get("entity_id")),
                "equipment": clean_display(row.get("equipment")),
                "plate": clean_display(row.get("plate")),
                "current_place": current_place,
                "workshop_bucket": bucket,
                "external_workshop": current_place if bucket == EXTERNAL_WORKSHOPS else "",
                "gps_state": clean_display(row.get("gps_state")),
                "gps_faena": clean_display(row.get("gps_faena")),
                "gps_last_update": row.get("gps_last_update"),
            }
        )

    snapshot = pd.DataFrame(rows, columns=columns)
    if snapshot.empty:
        return snapshot
    return (
        snapshot.sort_values(["workshop_bucket", "equipment"])
        .drop_duplicates("entity_id", keep="last")
        .reset_index(drop=True)
    )


def _planned_workshop_bucket(value: Any) -> str | None:
    text = normalize_text(value)
    if not text or text in {"n a", "na", "faena"}:
        return None
    canonical = normalize_workshop(value)
    if canonical in WORKSHOP_CAPACITY:
        return canonical
    return EXTERNAL_WORKSHOPS


def build_workshop_capacity(current_workshops: pd.DataFrame) -> pd.DataFrame:
    """Capacidad actual basada en la ubicación Lugar reportada por la API."""
    rows: list[dict[str, Any]] = []
    for workshop, limit in WORKSHOP_CAPACITY.items():
        occupied = int((current_workshops["workshop_bucket"] == workshop).sum()) if not current_workshops.empty else 0
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

    external_count = (
        int((current_workshops["workshop_bucket"] == EXTERNAL_WORKSHOPS).sum())
        if not current_workshops.empty else 0
    )
    if external_count:
        rows.append(
            {
                "workshop": EXTERNAL_WORKSHOPS,
                "occupied": external_count,
                "limit": pd.NA,
                "available": pd.NA,
                "status": "Sin límite configurado",
            }
        )
    return pd.DataFrame(rows)


def _apply_movement_events(
    state: dict[str, str],
    movements: pd.DataFrame,
    day: pd.Timestamp,
) -> tuple[dict[str, str], dict[str, str]]:
    """Aplica bajadas primero (peak conservador) y luego subidas para obtener el cierre."""
    if movements.empty:
        return state.copy(), state.copy()

    day = pd.Timestamp(day).normalize()
    working = state.copy()
    starts = movements[movements["start_date"].eq(day)].sort_values(["equipment", "_global_order"])
    for _, row in starts.iterrows():
        if is_terminal_status(row.get("status")):
            continue
        bucket = _planned_workshop_bucket(row.get("workshop"))
        if bucket:
            working[str(row.get("entity_id"))] = bucket

    peak_state = working.copy()
    ends = movements[movements["end_date"].eq(day)].sort_values(["equipment", "_global_order"])
    for _, row in ends.iterrows():
        working.pop(str(row.get("entity_id")), None)
    return peak_state, working


def build_weekly_workshop_projection(
    movements: pd.DataFrame,
    current_workshops: pd.DataFrame | None = None,
    week_start: pd.Timestamp | None = None,
    today: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Proyecta capacidad desde el snapshot actual de la API.

    La columna Lugar es la verdad para la ocupación de hoy. Los movimientos futuros de
    la hoja Mov. equipos agregan bajadas y descuentan subidas. De esta forma, un camión
    que ya está en taller se cuenta aunque no tenga una bajada dentro de la semana.
    """
    today = (today or pd.Timestamp.now()).normalize()
    selected = (week_start or today).normalize()
    monday = selected - pd.Timedelta(days=int(selected.weekday()))
    sunday = monday + pd.Timedelta(days=6)

    current_workshops = current_workshops if current_workshops is not None else pd.DataFrame()
    state: dict[str, str] = {}
    name_by_entity: dict[str, str] = {}
    if not current_workshops.empty:
        for _, row in current_workshops.iterrows():
            entity_id = str(row.get("entity_id"))
            state[entity_id] = str(row.get("workshop_bucket"))
            name_by_entity[entity_id] = clean_display(row.get("equipment"), default=entity_id)

    if not movements.empty:
        for _, row in movements.iterrows():
            entity_id = str(row.get("entity_id"))
            name_by_entity.setdefault(entity_id, clean_display(row.get("equipment"), default=entity_id))

    # La API ya representa la situación de hoy. Para no duplicar movimientos del mismo día,
    # la simulación comienza mañana y avanza hasta el cierre de la semana seleccionada.
    simulation_day = today + pd.Timedelta(days=1)
    if simulation_day <= sunday:
        while simulation_day < monday:
            _, state = _apply_movement_events(state, movements, simulation_day)
            simulation_day += pd.Timedelta(days=1)

    opening_state = state.copy()
    daily_snapshots: list[tuple[pd.Timestamp, dict[str, str], dict[str, str]]] = []

    for day in pd.date_range(max(monday, today), sunday, freq="D"):
        day = pd.Timestamp(day).normalize()
        if day <= today:
            peak_state = state.copy()
            closing_state = state.copy()
        else:
            peak_state, closing_state = _apply_movement_events(state, movements, day)
            state = closing_state.copy()
        daily_snapshots.append((day, peak_state, closing_state))

    if not daily_snapshots:
        daily_snapshots.append((today, state.copy(), state.copy()))

    movement_buckets: set[str] = set()
    if not movements.empty:
        movement_buckets = {
            bucket
            for bucket in movements["workshop"].map(_planned_workshop_bucket).tolist()
            if bucket
        }
    buckets = list(WORKSHOP_CAPACITY.keys())
    if (
        EXTERNAL_WORKSHOPS in set(state.values())
        or EXTERNAL_WORKSHOPS in movement_buckets
        or (not current_workshops.empty and (current_workshops["workshop_bucket"] == EXTERNAL_WORKSHOPS).any())
    ):
        buckets.append(EXTERNAL_WORKSHOPS)

    rows: list[dict[str, Any]] = []
    for workshop in buckets:
        limit = WORKSHOP_CAPACITY.get(workshop)
        current_ids = {entity for entity, bucket in (
            (str(row.get("entity_id")), str(row.get("workshop_bucket")))
            for _, row in current_workshops.iterrows()
        ) if bucket == workshop} if not current_workshops.empty else set()
        current = len(current_ids)
        opening_ids = {entity for entity, bucket in opening_state.items() if bucket == workshop}

        workshop_movements = movements.copy() if not movements.empty else pd.DataFrame()
        if not workshop_movements.empty:
            workshop_movements["_projection_bucket"] = workshop_movements["workshop"].map(_planned_workshop_bucket)
            workshop_movements = workshop_movements[workshop_movements["_projection_bucket"].eq(workshop)]

        downs = 0
        ups = 0
        if not workshop_movements.empty:
            downs = int(workshop_movements.loc[
                workshop_movements["start_date"].between(monday, sunday, inclusive="both"),
                "entity_id",
            ].nunique())
            ups = int(workshop_movements.loc[
                workshop_movements["end_date"].between(monday, sunday, inclusive="both"),
                "entity_id",
            ].nunique())

        peak_day = daily_snapshots[0][0]
        peak_ids: set[str] = set()
        closing_ids: set[str] = set()
        for day, peak_state, closing_state in daily_snapshots:
            day_peak_ids = {entity for entity, bucket in peak_state.items() if bucket == workshop}
            if len(day_peak_ids) > len(peak_ids):
                peak_ids = day_peak_ids
                peak_day = day
            closing_ids = {entity for entity, bucket in closing_state.items() if bucket == workshop}

        peak = len(peak_ids)
        closing = len(closing_ids)
        if limit is None:
            status = "Sin límite configurado"
            available_at_peak: int | None = None
            over_capacity = 0
        elif peak > limit:
            status = "Sobrepasado"
            available_at_peak = 0
            over_capacity = peak - limit
        elif peak == limit:
            status = "Al límite"
            available_at_peak = 0
            over_capacity = 0
        else:
            status = "Con espacio"
            available_at_peak = limit - peak
            over_capacity = 0

        external_locations: list[str] = []
        if workshop == EXTERNAL_WORKSHOPS and not current_workshops.empty:
            external_locations = sorted(
                current_workshops.loc[
                    current_workshops["workshop_bucket"].eq(EXTERNAL_WORKSHOPS),
                    "current_place",
                ].dropna().astype(str).unique().tolist()
            )

        rows.append(
            {
                "workshop": workshop,
                "limit": limit if limit is not None else pd.NA,
                "current": current,
                "opening": len(opening_ids),
                "downs": downs,
                "ups": ups,
                "peak": peak,
                "peak_date": peak_day,
                "closing": closing,
                "available_at_peak": available_at_peak if available_at_peak is not None else pd.NA,
                "over_capacity": over_capacity,
                "status": status,
                "current_equipment": sorted(name_by_entity.get(entity, entity) for entity in current_ids),
                "peak_equipment": sorted(name_by_entity.get(entity, entity) for entity in peak_ids),
                "closing_equipment": sorted(name_by_entity.get(entity, entity) for entity in closing_ids),
                "external_locations": external_locations,
                "week_start": monday,
                "week_end": sunday,
                "snapshot_date": today,
            }
        )
    return pd.DataFrame(rows)


WORKSHOP_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "RIO LOA": ("SKC CALAMA", "SKC ANTOFAGASTA", "SKC ALTO HOSPICIO", "FULL RPM"),
    "SKC CALAMA": ("RIO LOA", "SKC ANTOFAGASTA", "SKC ALTO HOSPICIO", "FULL RPM"),
    "SKC ANTOFAGASTA": ("FULL RPM", "SKC CALAMA", "RIO LOA", "SKC ALTO HOSPICIO"),
    "SKC ALTO HOSPICIO": ("SKC CALAMA", "RIO LOA", "SKC ANTOFAGASTA", "FULL RPM"),
    "SKC COPIAPO": ("SKC ANTOFAGASTA", "FULL RPM", "SKC CALAMA"),
    "FULL RPM": ("SKC ANTOFAGASTA", "SKC CALAMA", "RIO LOA", "SKC ALTO HOSPICIO"),
}


def build_rebalancing_recommendations(projection: pd.DataFrame) -> list[str]:
    """Recomendaciones determinísticas; la IA puede refinarlas sin alterar cifras."""
    if projection.empty:
        return []
    indexed = projection.set_index("workshop")
    recommendations: list[str] = []

    overloaded = projection[projection["over_capacity"] > 0].sort_values(
        ["over_capacity", "peak"], ascending=False
    )
    for _, row in overloaded.iterrows():
        workshop = str(row["workshop"])
        remaining = int(row["over_capacity"])
        allocations: list[str] = []
        for alternative in WORKSHOP_ALTERNATIVES.get(workshop, tuple(indexed.index)):
            if alternative not in indexed.index or remaining <= 0:
                continue
            available = int(indexed.at[alternative, "available_at_peak"])
            if available <= 0:
                continue
            moved = min(remaining, available)
            allocations.append(f"{moved} a {alternative}")
            remaining -= moved

        base = (
            f"{workshop} proyecta un máximo de {int(row['peak'])}/{int(row['limit'])} equipos "
            f"(+{int(row['over_capacity'])} sobre capacidad)."
        )
        if allocations:
            recommendation = base + " Opción de redistribución: " + ", ".join(allocations) + "."
            if remaining > 0:
                recommendation += f" Aún quedarían {remaining} equipo(s) sin cupo dentro de los talleres configurados."
        else:
            recommendation = base + " No se detectó capacidad libre suficiente en los talleres alternativos configurados."
        recommendation += " Validar distancia, especialidad técnica, repuestos y autorización operacional antes de reasignar."
        recommendations.append(recommendation)
    return recommendations

def build_contracts(gps: pd.DataFrame) -> pd.DataFrame:
    """Calcula cumplimiento contractual contando EXCLUSIVAMENTE AUGER / QUADRA.

    La clasificación se recalcula desde ``equipment`` cada vez para que una columna
    ``equipment_category`` antigua o cacheada nunca pueda hacer que AFI/PMO sumen al contrato.
    """
    if gps.empty or "equipment" not in gps.columns:
        counts: dict[str, int] = {}
    else:
        factory_mask = gps["equipment"].map(is_factory_truck).fillna(False)
        factory = gps.loc[factory_mask].copy()
        # Protección adicional frente a duplicados inesperados de la API.
        if "equipment_key" in factory.columns:
            factory = factory.drop_duplicates(subset=["canonical_contract", "equipment_key"], keep="last")
        else:
            factory["_contract_equipment_key"] = factory["equipment"].map(normalize_identifier)
            factory = factory.drop_duplicates(subset=["canonical_contract", "_contract_equipment_key"], keep="last")
        counts = factory["canonical_contract"].value_counts().to_dict()
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
    max_results: int = 1,
) -> list[str]:
    """Busca un equipo de forma conservadora para evitar fichas incorrectas."""
    normalized_term = normalize_identifier(term)
    if not normalized_term:
        return []

    normalized_by_entity: dict[str, set[str]] = {}
    for entity_id, aliases in aliases_by_entity.items():
        normalized_by_entity[entity_id] = {
            normalize_identifier(alias) for alias in aliases if normalize_identifier(alias)
        }

    exact = [entity_id for entity_id, aliases in normalized_by_entity.items() if normalized_term in aliases]
    if len(exact) == 1:
        return exact
    if len(exact) > 1:
        return exact[:max_results]

    # Coincidencia parcial solo cuando identifica un único camión.
    contains = [
        entity_id
        for entity_id, aliases in normalized_by_entity.items()
        if len(normalized_term) >= 5 and any(normalized_term in alias for alias in aliases)
    ]
    if len(contains) == 1:
        return contains

    scored: list[tuple[str, float]] = []
    for entity_id, aliases in normalized_by_entity.items():
        if not aliases:
            continue
        score = max(float(WRatio(normalized_term, alias)) for alias in aliases)
        if score >= 88.0:
            scored.append((entity_id, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    if not scored:
        return []

    # No entrega un resultado difuso si hay otra alternativa casi igual.
    best_id, best_score = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0
    if best_score < 92.0 or best_score - second_score < 6.0:
        return []
    return [best_id]


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
    movements = build_movements(history, equipment)
    equipment = apply_movement_plan_to_equipment(equipment, movements)
    certifications = build_certifications(equipment)
    current_workshops = build_current_workshops(equipment)
    workshop_capacity = build_workshop_capacity(current_workshops)
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
            "current_workshop_equipment": len(current_workshops),
            "external_workshops": sorted(
                current_workshops.loc[
                    current_workshops.get("workshop_bucket", pd.Series(dtype="object")).eq(EXTERNAL_WORKSHOPS),
                    "current_place",
                ].dropna().astype(str).unique().tolist()
            ) if not current_workshops.empty else [],
            "movement_source_sheets": sorted(movements["source"].dropna().unique().tolist()) if not movements.empty else [],
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
        current_workshops=current_workshops,
        search_aliases=search_aliases,
        diagnostics=diagnostics,
        errors=list(source_errors or []),
        loaded_at=datetime.now(),
    )
