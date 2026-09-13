from __future__ import annotations

import csv
import io
import json
import re

import openpyxl

_FORMULA_PREFIXES = ("=", "+", "-", "@")
_ILLEGAL_XML_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _defuse_formula(value):
    """Prefix a leading `=`/`+`/`-`/`@` with a single quote so spreadsheet
    apps (Excel, LibreOffice) render the cell as text instead of executing
    it as a formula -- a document's text or an LLM's rationale can
    start with any of these by pure chance, not just from an attacker, and
    CSV injection (CWE-1236) is a real code-execution vector once someone
    opens the export.

    Checks after stripping leading whitespace/control characters, not the
    raw value -- Excel and LibreOffice both skip leading spaces/tabs when
    deciding whether a cell is a formula, so a value like `" =cmd|..."`
    would otherwise slip past a bare `.startswith()` check unquoted."""
    if isinstance(value, str) and value.lstrip(" \t\r\n\x0b\x0c").startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _strip_illegal_xlsx_chars(value):
    """openpyxl raises IllegalCharacterError for ASCII control characters
    XML 1.0 forbids (anything but tab/newline/CR) -- real corpus text or a
    CLI provider's raw_response can contain these and crash the whole
    export otherwise."""
    if isinstance(value, str):
        return _ILLEGAL_XML_CHARS_RE.sub("", value)
    return value


def results_to_csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows({k: _defuse_formula(v) for k, v in row.items()} for row in rows)
    # utf-8-sig (BOM) so Excel on Windows doesn't fall back to ANSI and
    # garble non-ASCII text (this project's rationale fields are
    # routinely Portuguese, e.g. "não", "codificação").
    return buffer.getvalue().encode("utf-8-sig")


def results_to_xlsx_bytes(rows: list[dict]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    if rows:
        headers = list(rows[0].keys())
        sheet.append(headers)
        for row in rows:
            sheet.append([_strip_illegal_xlsx_chars(_defuse_formula(row.get(h))) for h in headers])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def results_to_json_bytes(rows: list[dict]) -> bytes:
    return json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
