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
        "modelo", "modelo equipo", "modelo camion", "modelo camión", "modelo vehiculo",
        "modelo vehículo", "model",
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
        "sistema control", "sistema de control", "control system", "sistema_control",
        "control equipo",
    ),
    "status": (
        "estatus mp", "estado mp", "estatus mantenimiento", "estado mantenimiento",
        "estatus taller", "estado taller", "status", "estado", "situacion", "situación",
    ),
    "equipment_status_detail": (
        "estado de equipos", "estado equipos", "estado del equipo", "detalle estado equipo",
        "detalle estado de equipos", "comentario estado equipo", "comentarios estado equipo",
        "estatus del equipo", "estatus equipos",
    ),
    "workshop": (
        "taller", "taller destino", "ubicacion taller", "ubicación taller",
        "lugar mantenimiento", "proveedor taller", "centro reparacion", "centro reparación",
    ),
    "comments": (
        "comentarios", "comentario", "observaciones", "observacion", "observación",
        "motivo", "trabajos", "trabajo", "detalle trabajos", "alcance", "descripcion",
        "descripción", "trabajo realizado", "trabajos realizados",
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
        "revision tecnica", "revisión técnica", "vigencia rt", "vencimiento rt", "fecha rt",
    ),
    "sernageomin": (
        "vencimiento sernageomin", "sernageomin vence", "fecha sernageomin",
        "vigencia sernageomin", "sernageomin", "sngm", "fecha sngm",
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
        "nombre faena", "nombre_faena", "faena", "contrato", "zona nombre",
    ),
    "place": (
        "lugar", "nombre lugar", "nombre_lugar", "lugar nombre", "lugar_nombre",
        "lugar actual", "lugar equipo", "lugar_actual", "lugar_equipo",
        "ubicacion", "ubicación", "ubicacion actual", "ubicación actual",
        "ubicacion nombre", "ubicación nombre", "ubicacion_nombre",
        "ubicacion fisica", "ubicación física", "ubicacion_fisica",
        "taller actual", "taller_actual", "localizacion", "localización",
        "localizacion nombre", "localizacion_nombre", "location", "place",
        "estado lugar", "estado_lugar", "sector actual", "sector_actual",
    ),
    "condition": (
        "condicion", "condición", "nombre condicion", "nombre condición",
        "nombre_condicion", "condicion nombre", "condición nombre", "condicion_nombre",
        "condicion equipo", "condición equipo", "tipo condicion", "tipo condición",
    ),
    "brand": ("marca nombre", "marca_nombre", "marca", "fabricante"),
    "model": (
        "modelo nombre", "modelo_nombre", "modelo equipo", "modelo camion", "modelo camión",
        "modelo vehiculo", "modelo vehículo", "modelo",
    ),
    "control_system": (
        "sistema control", "sistema de control", "sistema_control", "control system",
    ),
    "hours": (
        "horas ult", "horas_ult", "horometro", "horómetro", "horas",
        "hrs kms desde ultimo preventivo", "hrs kms desde último preventivo",
        "hrs desde ultimo preventivo", "kms desde ultimo preventivo",
    ),
    "status": (
        "estado deducido", "estado_deducido", "estado equipo deducido",
        "estado", "estado equipo", "estado actual", "nombre estado", "nombre_estado",
        "estatus actual", "status",
    ),
    "return_operation_date": (
        "fecha retorno operacion", "fecha retorno operación", "fecha_retorno_operacion",
        "fecha retorno a operacion", "fecha retorno a operación", "fecha_retorno_a_operacion",
        "fecha de retorno operacion", "fecha de retorno operación",
        "fecha estimada retorno operacion", "fecha estimada retorno operación",
        "fecha_estimada_retorno_operacion", "fecha retorno", "fecha_retorno",
        "retorno operacion", "retorno operación", "retorno_operacion",
        "retorno a operacion", "retorno a operación", "f retorno", "f. retorno",
        "fecha ret operacion", "fecha ret operación", "fecha_ret_operacion",
        "fecha regreso operacion", "fecha regreso operación", "fecha_regreso_operacion",
    ),
    "days_out_service": (
        "dias fuera de servicio", "días fuera de servicio", "dias fs", "días fs",
    ),
    "next_maintenance_date": (
        "fecha aprox proxima mantencion", "fecha aprox próxima mantención",
        "fecha_aprox_proxima_mantencion", "fecha aprox prox mantencion",
        "fecha_aprox_prox_mantencion", "fecha proxima mantencion",
        "fecha próxima mantención", "fecha_proxima_mantencion",
        "fecha mantencion", "fecha mantención", "fecha_mantencion",
        "fecha prox mantencion", "fecha_prox_mantencion",
        "proxima mantencion", "próxima mantención", "prox mantencion", "prox mant",
    ),
    "revision_tecnica_date": (
        "fecha rt", "fecha revision tecnica", "fecha revisión técnica",
        "vencimiento rt", "vencimiento revision tecnica", "vencimiento revisión técnica",
    ),
    "sernageomin_date": (
        "fecha sernageomin", "fecha sngm", "vencimiento sernageomin", "vencimiento sngm",
    ),
    "dgmn_date": ("fecha dgmn", "vencimiento dgmn"),
    "revision_tecnica_days": (
        "d rt", "d. rt", "d_rt", "rt", "dias rt", "días rt", "dias_rt",
        "dias restantes rt", "dias_restantes_rt",
        "rt dias", "rt_dias", "dias revision tecnica", "días revisión técnica",
        "dias revisión técnica", "dias_revision_tecnica",
    ),
    "sernageomin_days": (
        "d sernageomin", "d. sernageomin", "d_sernageomin", "sernageomin",
        "dias sernageomin", "días sernageomin", "dias_sernageomin",
        "sernageomin dias", "sernageomin_dias", "dias restantes sernageomin",
        "dias_restantes_sernageomin", "d sngm", "d. sngm", "d_sngm", "sngm",
        "dias sngm", "días sngm", "dias_sngm",
    ),
    "dgmn_days": (
        "d dgmn", "d. dgmn", "d_dgmn", "dgmn", "dias dgmn", "días dgmn",
        "dias restantes dgmn", "dias_restantes_dgmn",
        "dias_dgmn", "dgmn dias", "dgmn_dias",
    ),
    "timestamp": (
        "fecha ultima", "fecha_ultima", "ultima fecha", "timestamp", "fecha gps",
        "fecha reporte", "fecha actualizacion", "updated at", "last update",
    ),
}

# Encabezados que nunca deben aceptarse para ciertos campos. Evita, por ejemplo,
# usar "Modelo neumático" como modelo del camión o interpretar "D. RT" como fecha.
HEADER_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "model": (
        "neumatic", "neumático", "cubierta", "bateria", "batería", "motor", "bomba",
        "repuesto", "componente", "aceite", "filtro", "sensor", "katana",
    ),
    "brand": ("neumatic", "neumático", "bateria", "batería", "repuesto", "componente"),
    "faena": ("fecha", "retorno", "mantencion", "mantención"),
    "status": ("estado de equipos", "estado equipos", "detalle estado"),
    "revision_tecnica": ("dias", "días", "d rt"),
    "sernageomin": ("dias", "días", "d sernageomin", "d sngm"),
    "dgmn": ("dias", "días", "d dgmn"),
}

GPS_HEADER_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "model": ("neumatic", "neumático", "repuesto", "componente"),
    "faena": ("fecha", "retorno"),
    "place": ("fecha", "retorno", "mantencion", "mantención"),
    "condition": ("estado", "rt", "sernageomin", "sngm", "dgmn", "dias", "días"),
    "status": (
        "condicion", "condición", "rt", "revision", "revisión", "sernageomin",
        "sngm", "dgmn", "dias", "días", "mantencion", "mantención",
        "fuera de servicio", "hrs", "kms",
    ),
    "revision_tecnica_date": ("dias", "días", "d rt"),
    "sernageomin_date": ("dias", "días", "d sernageomin", "d sngm"),
    "dgmn_date": ("dias", "días", "d dgmn"),
}

# Para estos campos no se admite una columna “parecida” sin la palabra esencial.
# Esto evita, por ejemplo, interpretar D. Sernageomin como Estado.
GPS_REQUIRED_TOKENS: dict[str, tuple[str, ...]] = {
    "place": ("lugar", "ubicacion", "localizacion", "taller"),
    "condition": ("condicion",),
    "status": ("estado", "status", "estatus"),
    "revision_tecnica_days": ("rt", "revision tecnica"),
    "sernageomin_days": ("sernageomin", "sngm"),
    "dgmn_days": ("dgmn",),
    "next_maintenance_date": ("mantencion", "mantenimiento"),
    "return_operation_date": ("retorno",),
}

GPS_SINGLE_SOURCE_FIELDS = {
    "condition", "status", "return_operation_date", "days_out_service",
    "next_maintenance_date", "revision_tecnica_date", "sernageomin_date", "dgmn_date",
    "revision_tecnica_days", "sernageomin_days", "dgmn_days",
}

FIELD_MIN_SCORE: dict[str, float] = {
    "model": 94.5,
    "faena": 90.0,
    "revision_tecnica": 88.0,
    "sernageomin": 88.0,
    "dgmn": 88.0,
}

GPS_FIELD_MIN_SCORE: dict[str, float] = {
    "model": 94.5,
    "faena": 90.0,
    "revision_tecnica_date": 88.0,
    "sernageomin_date": 88.0,
    "dgmn_date": 88.0,
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
    "Salvador": (
        "el salvador", "salvador", "division salvador", "división salvador",
        "rajo inca", "proyecto rajo inca", "codelco rajo inca", "codelco salvador",
    ),
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


def _is_excluded(field: str, column: str, exclusions: dict[str, tuple[str, ...]]) -> bool:
    header = normalize_text(column)
    return any(normalize_text(token) in header for token in exclusions.get(field, ()))


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
    is_gps = aliases_by_field is GPS_FIELD_ALIASES
    exclusions = GPS_HEADER_EXCLUSIONS if is_gps else HEADER_EXCLUSIONS
    minimums = GPS_FIELD_MIN_SCORE if is_gps else FIELD_MIN_SCORE

    for field, aliases in aliases_by_field.items():
        candidates: list[tuple[str, float]] = []
        field_threshold = max(threshold, minimums.get(field, threshold))
        exact_candidates: list[tuple[str, float]] = []
        normalized_aliases = [normalize_text(alias) for alias in aliases]
        alias_priority = {alias: index for index, alias in enumerate(normalized_aliases)}
        required_tokens = GPS_REQUIRED_TOKENS.get(field, ()) if is_gps else ()
        for column in string_columns:
            if _is_excluded(field, column, exclusions):
                continue
            normalized_column = normalize_text(column)
            if required_tokens and not any(normalize_text(token) in normalized_column for token in required_tokens):
                continue
            if normalized_column in alias_priority:
                # Respeta el orden de alias: Estado_Deducido tiene prioridad sobre Estado.
                exact_candidates.append((column, 110.0 - alias_priority[normalized_column] * 0.1))
                continue
            best = max((_score_header(column, alias) for alias in aliases), default=0.0)
            if best >= field_threshold:
                candidates.append((column, best))

        # Una coincidencia exacta es fuente de verdad y no se mezcla con columnas
        # “parecidas”. Así Estado_Deducido no termina combinado con Estado_RT.
        selected = exact_candidates if exact_candidates else candidates
        selected.sort(key=lambda item: (-item[1], len(item[0])))
        limit = 1 if is_gps and field in GPS_SINGLE_SOURCE_FIELDS else max_per_field
        details[field] = selected[:limit]
        mapping[field] = [column for column, _ in selected[:limit]]

    return dict(mapping), dict(details)
