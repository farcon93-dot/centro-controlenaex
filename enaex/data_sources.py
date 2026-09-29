from __future__ import annotations

import concurrent.futures
from io import BytesIO
import re
import time
from typing import Any, Iterable

import pandas as pd
import requests

from enaex.aliases import all_header_aliases
from enaex.normalize import clean_display, is_empty, normalize_text


USER_AGENT = "Enaex-Control-Flota/1.0"


def extract_google_file_id(url: str) -> str | None:
    patterns = (
        r"/d/([a-zA-Z0-9_-]+)",
        r"[?&]id=([a-zA-Z0-9_-]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def excel_download_candidates(url: str) -> list[str]:
    file_id = extract_google_file_id(url)
    candidates: list[str] = []
    if "docs.google.com/spreadsheets" in url and file_id:
        candidates.append(f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx")
    if file_id:
        candidates.append(f"https://drive.google.com/uc?export=download&id={file_id}")
    candidates.append(url)
    # Mantiene orden y elimina duplicados.
    return list(dict.fromkeys(candidates))


def _looks_like_excel(content: bytes, content_type: str) -> bool:
    lowered = (content_type or "").lower()
    return (
        content.startswith(b"PK")
        or "spreadsheet" in lowered
        or "excel" in lowered
        or "octet-stream" in lowered
    )


def download_excel(url: str, timeout: int = 35) -> tuple[bytes, str]:
    last_error = "No fue posible descargar el archivo."
    headers = {"User-Agent": USER_AGENT}
    for candidate in excel_download_candidates(url):
        try:
            response = requests.get(candidate, timeout=timeout, headers=headers, allow_redirects=True)
            if response.status_code != 200:
                last_error = f"HTTP {response.status_code} al descargar {candidate}"
                continue
            content_type = response.headers.get("content-type", "")
            if not _looks_like_excel(response.content, content_type):
                snippet = response.text[:120].replace("\n", " ") if response.text else "respuesta no Excel"
                last_error = f"El enlace devolvió contenido no Excel: {snippet}"
                continue
            return response.content, candidate
        except requests.RequestException as exc:
            last_error = str(exc)
    raise RuntimeError(last_error)


def _make_unique_headers(values: Iterable[Any]) -> list[str]:
    counts: dict[str, int] = {}
    headers: list[str] = []
    for index, value in enumerate(values):
        base = clean_display(value, default=f"Columna_{index + 1}")
        if normalize_text(base).startswith("unnamed") or is_empty(base):
            base = f"Columna_{index + 1}"
        count = counts.get(base, 0)
        counts[base] = count + 1
        headers.append(base if count == 0 else f"{base}__{count + 1}")
    return headers


def detect_header_row(raw: pd.DataFrame, max_rows: int = 20) -> int:
    if raw.empty:
        return 0
    aliases = all_header_aliases()
    best_index = 0
    best_score = -1.0
    for index in range(min(max_rows, len(raw))):
        values = [normalize_text(value) for value in raw.iloc[index].tolist() if not is_empty(value)]
        exact = sum(1 for value in values if value in aliases)
        partial = sum(
            1
            for value in values
            if len(value) >= 4 and any((alias in value or value in alias) for alias in aliases)
        )
        # Premia filas que parecen encabezados y no filas de datos repetitivos.
        unique_ratio = len(set(values)) / max(len(values), 1)
        score = exact * 3.0 + partial * 1.0 + unique_ratio
        if score > best_score:
            best_index = index
            best_score = score
    return best_index if best_score >= 2.0 else 0


def read_excel_workbook(content: bytes, source_name: str) -> tuple[list[pd.DataFrame], list[dict[str, Any]]]:
    frames: list[pd.DataFrame] = []
    sheet_diagnostics: list[dict[str, Any]] = []
    excel_file = pd.ExcelFile(BytesIO(content), engine="openpyxl")
    global_order = 0

    for sheet_name in excel_file.sheet_names:
        raw = pd.read_excel(excel_file, sheet_name=sheet_name, header=None, dtype=object)
        if raw.empty:
            sheet_diagnostics.append({"archivo": source_name, "hoja": sheet_name, "filas": 0, "encabezado": 0})
            continue

        header_row = detect_header_row(raw)
        headers = _make_unique_headers(raw.iloc[header_row].tolist())
        frame = raw.iloc[header_row + 1 :].copy()
        frame.columns = headers
        frame = frame.dropna(how="all").reset_index(drop=True)
        if frame.empty:
            sheet_diagnostics.append(
                {"archivo": source_name, "hoja": sheet_name, "filas": 0, "encabezado": header_row + 1}
            )
            continue

        frame["_source_file"] = source_name
        frame["_source_sheet"] = sheet_name
        frame["_source_row"] = frame.index + header_row + 2
        frame["_global_order"] = range(global_order, global_order + len(frame))
        global_order += len(frame)
        frames.append(frame)
        sheet_diagnostics.append(
            {
                "archivo": source_name,
                "hoja": sheet_name,
                "filas": len(frame),
                "encabezado": header_row + 1,
            }
        )

    return frames, sheet_diagnostics


def load_excel_sources(urls: tuple[str, ...]) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    frames: list[pd.DataFrame] = []
    diagnostics: dict[str, Any] = {"excel_sheets": [], "excel_files_ok": 0, "excel_files_total": len(urls)}
    errors: list[str] = []

    def load_one(position_url: tuple[int, str]) -> tuple[int, list[pd.DataFrame], list[dict[str, Any]], str | None]:
        position, url = position_url
        source_name = f"Excel_{position + 1}"
        try:
            content, final_url = download_excel(url)
            workbook_frames, workbook_diag = read_excel_workbook(content, source_name)
            for frame in workbook_frames:
                frame["_source_url"] = url
                frame["_download_url"] = final_url
            return position, workbook_frames, workbook_diag, None
        except Exception as exc:  # La aplicación continúa con las otras fuentes.
            return position, [], [], f"{source_name}: {exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, max(1, len(urls)))) as executor:
        results = list(executor.map(load_one, enumerate(urls)))

    # Mantiene el orden de los archivos aunque se descarguen en paralelo.
    for _, workbook_frames, workbook_diag, error in sorted(results, key=lambda item: item[0]):
        frames.extend(workbook_frames)
        diagnostics["excel_sheets"].extend(workbook_diag)
        if error:
            errors.append(error)
        else:
            diagnostics["excel_files_ok"] += 1

    if not frames:
        return pd.DataFrame(), diagnostics, errors

    # Recalcula el orden global después de unir archivos.
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined["_global_order"] = range(len(combined))
    diagnostics["excel_rows"] = len(combined)
    diagnostics["excel_columns"] = len(combined.columns)
    return combined, diagnostics, errors


def _unpack_json_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "results", "resultado", "result"):
            nested = payload.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        return [payload]
    return []


def load_gps_source(
    base_url: str,
    api_key: str,
    types: tuple[int, ...],
    zones: tuple[int, ...],
    timeout: int = 6,
    workers: int = 16,
) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    """Descarga la API de planificación con recuperación de endpoints intermitentes.

    El servidor puede responder lentamente cuando se consultan muchos tipo/zona en paralelo.
    Antes la aplicación aceptaba la foto parcial si un endpoint hacía timeout; eso podía
    dejar una faena (p. ej. Collahuasi) sin sus AUGER/QUADRA. Ahora se hace:
      1) primera pasada paralela con concurrencia moderada;
      2) reintentos por endpoint con timeouts crecientes;
      3) una pasada final de recuperación con muy baja concurrencia.
    Solo se informa como fallo lo que no respondió después de todos los intentos.
    """
    endpoints = [(gps_type, zone) for gps_type in types for zone in zones]
    diagnostics: dict[str, Any] = {
        "gps_requests_total": len(endpoints),
        "gps_requests_ok": 0,
        "gps_requests_failed": 0,
        "gps_requests_recovered": 0,
        "gps_retry_attempts": 0,
    }
    errors: list[str] = []
    if not api_key:
        return pd.DataFrame(), diagnostics, ["GPS: falta GPS_API_KEY en .streamlit/secrets.toml."]

    # No sobrecargar el servidor aunque el secret antiguo tenga GPS_WORKERS=16.
    primary_workers = max(1, min(int(workers or 1), 8))
    recovery_workers = max(1, min(2, primary_workers))
    base_timeout = max(6, int(timeout or 6))

    def request_once(gps_type: int, zone: int, request_timeout: int):
        url = f"{base_url}/{gps_type}/{zone}"
        response = requests.get(
            url,
            params={"key": api_key},
            timeout=request_timeout,
            headers={"User-Agent": USER_AGENT, "Connection": "close"},
        )
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        records = _unpack_json_payload(response.json())
        for order, record in enumerate(records):
            record["_gps_type"] = gps_type
            record["_gps_zone"] = zone
            record["_gps_response_order"] = order
        return records

    def fetch(endpoint: tuple[int, int], attempts: int = 2, slow: bool = False):
        gps_type, zone = endpoint
        last_error = "Error desconocido"
        for attempt in range(attempts):
            request_timeout = base_timeout if attempt == 0 and not slow else max(12, base_timeout * (attempt + 2))
            try:
                payload = request_once(gps_type, zone, request_timeout)
                return gps_type, zone, payload, None, attempt
            except Exception as exc:
                last_error = str(exc)
                if attempt + 1 < attempts:
                    time.sleep(0.20 * (attempt + 1))
        return gps_type, zone, [], last_error, attempts - 1

    records: list[dict[str, Any]] = []
    failed: dict[tuple[int, int], str] = {}

    # Primera pasada: hasta 2 intentos por endpoint, pero con concurrencia acotada.
    with concurrent.futures.ThreadPoolExecutor(max_workers=primary_workers) as executor:
        future_map = {executor.submit(fetch, endpoint, 2, False): endpoint for endpoint in endpoints}
        for future in concurrent.futures.as_completed(future_map):
            gps_type, zone, payload, error, retry_count = future.result()
            diagnostics["gps_retry_attempts"] += int(retry_count)
            if error:
                failed[(gps_type, zone)] = error
            else:
                diagnostics["gps_requests_ok"] += 1
                if retry_count:
                    diagnostics["gps_requests_recovered"] += 1
                records.extend(payload)

    # Segunda pasada solo para los que fallaron. Timeout más largo y 1-2 workers.
    if failed:
        to_recover = list(failed)
        failed_final: dict[tuple[int, int], str] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=recovery_workers) as executor:
            future_map = {executor.submit(fetch, endpoint, 3, True): endpoint for endpoint in to_recover}
            for future in concurrent.futures.as_completed(future_map):
                gps_type, zone, payload, error, retry_count = future.result()
                diagnostics["gps_retry_attempts"] += int(retry_count + 1)
                if error:
                    failed_final[(gps_type, zone)] = error
                else:
                    diagnostics["gps_requests_ok"] += 1
                    diagnostics["gps_requests_recovered"] += 1
                    records.extend(payload)
        failed = failed_final

    diagnostics["gps_requests_failed"] = len(failed)
    diagnostics["gps_partial_snapshot"] = bool(failed)

    if failed:
        examples = [f"tipo {t}, zona {z}: {err}" for (t, z), err in list(failed.items())[:8]]
        errors.append(
            f"GPS: {len(failed)} de {len(endpoints)} consultas no respondieron después de reintentos. "
            "Los conteos de faena pueden quedar incompletos mientras persista esta falla: "
            + " | ".join(examples)
        )

    frame = pd.DataFrame(records)
    diagnostics["gps_rows_raw"] = len(frame)
    diagnostics["gps_columns_raw"] = len(frame.columns)
    return frame, diagnostics, errors

