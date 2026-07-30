from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from rapidfuzz.fuzz import ratio

from enaex.normalize import normalize_text


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "equipment": (
        "equipo", "nombre equipo", "codigo equipo", "código equipo", "id equipo",
        "unidad", "maquina", "máquina", "camion", "camión", "nombre activo",
        "identificacion equipo", "identificación equipo", "asset", "equipment",
    ),
    "plate": (
        "patente", "ppu", "placa", "placa patente", "patente equipo", "license plate",
    ),
    "vin": (
        "vin", "chasis", "numero chasis", "número chasis", "serie chasis", "nro serie",
        "numero serie", "número serie", "serial",
    ),
    "brand": (
        "marca", "marca equipo", "fabricante", "brand", "marca nombre", "marca_nombre",
    ),
    "model": (
        "modelo", "modelo equipo", "model", "tipo modelo",
    ),
    "year": (
        "año", "ano", "año equipo", "year", "modelo año", "modelo ano",
    ),
    "hours": (
        "horometro", "horómetro", "horas", "horas equipo", "horas ult", "horas_ult",
        "hourmeter", "hm",
    ),
    "capacity": (
        "capacidad", "capacidad equipo", "tonelaje", "toneladas", "tons", "carga util",
        "carga útil",
    ),
    "control_system": (
        "sistema control", "sistema de control", "control", "control system", "sistema",
    ),
    "status": (
        "estatus mp", "estado mp", "estatus mantenimiento", "estado mantenimiento",
        "estatus taller", "estado taller", "status", "estado", "situacion", "situación",
    ),
    "workshop": (
        "taller", "taller destino", "ubicacion taller", "ubicación taller",
        "lugar mantenimiento", "proveedor taller", "centro reparacion", "centro reparación",
    ),
    "comments": (
        "comentarios", "comentario", "observaciones", "observacion", "observación",
        "motivo", "trabajos", "trabajo", "detalle trabajos", "alcance", "descripcion",
        "descripción",
    ),
    "start_date": (
        "fecha inicio", "inicio planificado", "fecha inicio planificado", "fecha bajada",
        "bajada", "fecha ingreso taller", "ingreso taller", "inicio mp", "f inicio",
        "fecha inicial", "inici",
    ),
    "end_date": (
        "fecha entrega", "entrega planificada", "fecha fin", "fin planificado",
        "fecha subida", "subida", "fecha salida taller", "salida taller", "fin mp",
        "f termino", "f término", "fecha termino", "fecha término", "fina",
    ),
    "faena": (
        "faena", "faena destino", "contrato", "contrato destino", "mina", "operacion",
        "operación", "ubicacion faena", "ubicación faena", "destino faena",
    ),
    "update_date": (
        "fecha actualizacion", "fecha actualización", "actualizado", "ultima actualizacion",
        "última actualización", "fecha registro", "timestamp", "fecha carga", "fecha reporte",
        "fecha modificacion", "fecha modificación",
    ),
    "revision_tecnica": (
        "vencimiento revision tecnica", "vencimiento revisión técnica", "revision tecnica vence",
        "revisión técnica vence", "fecha revision tecnica", "fecha revisión técnica",
        "revision tecnica", "revisión técnica", "vigencia rt", "vencimiento rt", "rt",
    ),
    "sernageomin": (
        "vencimiento sernageomin", "sernageomin vence", "fecha sernageomin",
        "vigencia sernageomin", "sernageomin", "sngm",
    ),
    "dgmn": (
        "vencimiento dgmn", "dgmn vence", "fecha dgmn", "vigencia dgmn", "dgmn",
    ),
}

GPS_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "equipment": (
        "nombre", "equipo", "nombre equipo", "codigo", "código", "unidad", "asset",
    ),
    "plate": ("patente", "ppu", "placa"),
    "vin": ("vin", "chasis", "serie"),
    "faena": (
        "nombre faena", "nombre_faena", "faena", "contrato", "zona nombre", "ubicacion",
        "ubicación",
    ),
    "brand": ("marca nombre", "marca_nombre", "marca", "fabricante"),
    "model": ("modelo nombre", "modelo_nombre", "modelo"),
    "hours": ("horas ult", "horas_ult", "horometro", "horómetro", "horas"),
    "status": ("estado deducido", "estado_deducido", "estado", "status", "condicion"),
    "timestamp": (
        "fecha ultima", "fecha_ultima", "ultima fecha", "timestamp", "fecha gps",
        "fecha reporte", "fecha actualizacion", "updated at", "last update",
    ),
}

# Los alias se evalúan desde los más específicos a los más generales.
CONTRACT_ALIASES: dict[str, tuple[str, ...]] = {
    "Nueva Centinela": ("nueva centinela", "centinela nueva"),
    "Centinela": ("minera centinela", "centinela"),
    "Collahuasi": ("collahuasi",),
    "Los Bronces": ("los bronces", "bronces"),
    "Los Pelambres": ("los pelambres", "pelambres"),
    "Radomiro Tomic": ("radomiro tomic", "radomiro", "codelco rt"),
    "Sierra Gorda": ("sierra gorda",),
    "Spence": ("spence",),
    "Andina": ("division andina", "división andina", "andina"),
    "Antucoya": ("antucoya",),
    "Chuquicamata": ("chuquicamata", "chuqui"),
    "Lomas Bayas": ("lomas bayas",),
    "Los Colorados": ("los colorados", "colorados"),
    "Salvador": ("el salvador", "salvador"),
    "Teniente": ("el teniente", "teniente"),
    "Zaldivar": ("zaldivar", "zaldívar"),
    "Cerro Negro": ("cerro negro",),
    "El Soldado": ("el soldado", "soldado"),
    "Michilla": ("michilla",),
    "Pleito": ("el pleito", "pleito"),
    "Romeral": ("romeral",),
    "Salares Norte": ("salares norte", "salares"),
}


def all_header_aliases() -> set[str]:
    return {
        normalize_text(alias)
        for aliases in FIELD_ALIASES.values()
        for alias in aliases
        if normalize_text(alias)
    }


def _score_header(header: str, alias: str) -> float:
    h = normalize_text(header)
    a = normalize_text(alias)
    if not h or not a:
        return 0.0
    if h == a:
        return 100.0
    if h in {"nombre"} or a in {"nombre"}:
        return 0.0
    if len(a) >= 4 and a in h:
        return 94.0 - min(15.0, float(len(h) - len(a)))
    if len(h) >= 4 and h in a and (len(h) >= 7 or " " in h):
        return 84.0 - min(12.0, float(len(a) - len(h)))
    return float(ratio(h, a))


def match_columns(
    columns: Iterable[object],
    aliases_by_field: dict[str, tuple[str, ...]] = FIELD_ALIASES,
    threshold: float = 72.0,
    max_per_field: int = 8,
) -> tuple[dict[str, list[str]], dict[str, list[tuple[str, float]]]]:
    """Devuelve candidatos de columna ordenados por confiabilidad para cada campo."""
    mapping: dict[str, list[str]] = defaultdict(list)
    details: dict[str, list[tuple[str, float]]] = defaultdict(list)
    string_columns = [str(column) for column in columns]

    for field, aliases in aliases_by_field.items():
        candidates: list[tuple[str, float]] = []
        for column in string_columns:
            best = max((_score_header(column, alias) for alias in aliases), default=0.0)
            # Evita aceptar encabezados demasiado genéricos por coincidencia difusa.
            if best >= threshold:
                candidates.append((column, best))
        candidates.sort(key=lambda item: (-item[1], len(item[0])))
        details[field] = candidates[:max_per_field]
        mapping[field] = [column for column, _ in candidates[:max_per_field]]

    return dict(mapping), dict(details)
