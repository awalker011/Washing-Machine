from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from openpyxl import load_workbook
except ImportError:  # pragma: no cover - optional dependency
    load_workbook = None

from .config_loader import load_named_configs
from .entity_rules import evaluate_entity_rules
from .transformers import apply_transformations, is_blank, normalize_loose_text
from .validators import comparable, validate_record, validate_relationship_rules

ERROR_LOG_FIELDS = [
    "timestamp",
    "entity",
    "source_file",
    "row_number",
    "field",
    "reason",
    "original_value",
    "raw_row",
]
RUN_LOG_FIELDS = [
    "timestamp",
    "entity",
    "files_processed",
    "rows_read",
    "rows_accepted",
    "rows_rejected",
    "duplicate_rows_flagged",
    "output_file",
    "error_file",
]
DUPLICATE_LOG_FIELDS = [
    "timestamp",
    "entity",
    "duplicate_type",
    "rule_name",
    "key_fields",
    "key_value",
    "source_file",
    "row_number",
    "action",
    "reason",
    "related_rows",
    "raw_row",
]


def process_all(
    input_path: str,
    schema_path: str,
    mapping_path: str,
    output_dir: str,
    logs_dir: str,
) -> dict[str, Any]:
    input_root = Path(input_path)
    output_root = Path(output_dir)
    logs_root = Path(logs_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)

    schemas = load_named_configs(schema_path)
    mappings = load_named_configs(mapping_path)
    if not mappings:
        raise ValueError("No mapping configuration files were found.")

    staged_entities: dict[str, dict[str, Any]] = {}
    relationship_index: dict[tuple[str, str], set[str]] = defaultdict(set)
    entity_row_index: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    total_rows_read = 0
    total_rows_accepted = 0
    total_rows_rejected = 0

    for entity_name, mapping in mappings.items():
        schema = _resolve_schema(entity_name, mapping, schemas)
        staged_rows, all_rows, entity_errors, processed_files, read_count = _stage_entity(
            input_root=input_root,
            entity_name=entity_name,
            mapping=mapping,
            schema=schema,
        )
        total_rows_read += read_count

        for staged_row in staged_rows:
            for field_name, value in staged_row["data"].items():
                normalized = comparable(value)
                if normalized is not None:
                    relationship_index[(entity_name, field_name)].add(normalized)
                    entity_row_index[(entity_name, field_name)][normalized].append(staged_row)

        staged_entities[entity_name] = {
            "schema": schema,
            "mapping": mapping,
            "rows": staged_rows,
            "all_rows": all_rows,
            "errors": entity_errors,
            "processed_files": processed_files,
            "rows_read": read_count,
        }

    entity_rule_issues = evaluate_entity_rules(staged_entities)
    entity_summaries: list[dict[str, Any]] = []
    duplicate_log_rows: list[dict[str, Any]] = []

    for entity_name, entity_state in staged_entities.items():
        schema = entity_state["schema"]
        mapping = entity_state["mapping"]
        final_rows: list[dict[str, Any]] = []
        errors = list(entity_state["errors"])

        duplicate_exclusions, entity_duplicate_logs = _detect_duplicates(
            entity_name=entity_name,
            staged_rows=entity_state.get("all_rows", entity_state["rows"]),
            schema=schema,
        )
        duplicate_log_rows.extend(entity_duplicate_logs)

        for staged_row in entity_state["rows"]:
            row_key = (staged_row["source_file"], staged_row["row_number"])
            if row_key in duplicate_exclusions:
                continue

            row_issues = list(
                entity_rule_issues.get((entity_name, staged_row["source_file"], staged_row["row_number"]), [])
            )
            row_issues.extend(
                validate_relationship_rules(
                    staged_row["data"],
                    schema.get("relationship_rules", []),
                    relationship_index,
                    entity_row_index,
                )
            )
            if row_issues:
                _append_row_issues(
                    errors=errors,
                    entity_name=entity_name,
                    source_file=staged_row["source_file"],
                    row_number=staged_row["row_number"],
                    issues=row_issues,
                    record=staged_row["data"],
                    raw_row=staged_row["raw_row"],
                )
            else:
                final_rows.append(staged_row["data"])

        output_columns = schema.get("output_columns") or list(schema.get("fields", {}).keys())
        target_file = mapping.get("target_file", f"{entity_name}_standardized.csv")
        error_file = mapping.get("error_file", f"{entity_name}_errors.csv")

        _write_csv(output_root / target_file, final_rows, output_columns)
        _write_csv(output_root / error_file, errors, ERROR_LOG_FIELDS)

        accepted = len(final_rows)
        rejected_keys = {(error["source_file"], error["row_number"]) for error in errors}
        rejected = len(rejected_keys | duplicate_exclusions)
        duplicate_rows_flagged = len(
            {(row["source_file"], row["row_number"]) for row in entity_duplicate_logs}
        )
        total_rows_accepted += accepted
        total_rows_rejected += rejected

        entity_summaries.append(
            {
                "entity": entity_name,
                "files_processed": entity_state["processed_files"],
                "rows_read": entity_state["rows_read"],
                "rows_accepted": accepted,
                "rows_rejected": rejected,
                "duplicate_rows_flagged": duplicate_rows_flagged,
                "output_file": str(output_root / target_file),
                "error_file": str(output_root / error_file),
            }
        )

    _append_run_log(logs_root / "run_log.csv", entity_summaries)
    _append_duplicate_log(logs_root / "duplicate_log.csv", duplicate_log_rows)

    return {
        "status": "completed",
        "entities": entity_summaries,
        "duplicate_log_file": str(logs_root / "duplicate_log.csv"),
        "totals": {
            "rows_read": total_rows_read,
            "rows_accepted": total_rows_accepted,
            "rows_rejected": total_rows_rejected,
        },
    }


def _resolve_schema(entity_name: str, mapping: dict, schemas: dict[str, dict]) -> dict:
    schema_name = mapping.get("schema") or entity_name
    schema = schemas.get(schema_name)
    if schema is None:
        raise ValueError(f"No schema found for entity '{entity_name}' (expected key '{schema_name}').")
    return schema


def _stage_entity(
    input_root: Path,
    entity_name: str,
    mapping: dict,
    schema: dict,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str], int]:
    staged_rows: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    processed_files: list[str] = []
    rows_read = 0

    input_files = _find_input_files(input_root, mapping.get("source_patterns"))
    if not input_files:
        patterns = list(mapping.get("source_patterns") or ["*.csv", "*.xlsx"])
        raise FileNotFoundError(
            f"No input files matched for entity '{entity_name}' under '{input_root}' using patterns: {patterns}"
        )

    for source_file in input_files:
        processed_files.append(source_file.name)
        for row_number, raw_row in _iter_input_rows(source_file, mapping.get("sheet_name")):
            rows_read += 1
            standardized = _map_row(raw_row, mapping, schema)
            transformed, transform_issues = apply_transformations(
                standardized,
                mapping.get("transformations", {}),
            )

            row_state = {
                "data": transformed,
                "source_file": source_file.name,
                "row_number": row_number,
                "raw_row": raw_row,
            }
            all_rows.append(row_state)

            if transform_issues:
                _append_row_issues(
                    errors=errors,
                    entity_name=entity_name,
                    source_file=source_file.name,
                    row_number=row_number,
                    issues=transform_issues,
                    record=standardized,
                    raw_row=raw_row,
                )
                continue

            row_issues = validate_record(transformed, schema)
            if row_issues:
                _append_row_issues(
                    errors=errors,
                    entity_name=entity_name,
                    source_file=source_file.name,
                    row_number=row_number,
                    issues=row_issues,
                    record=transformed,
                    raw_row=raw_row,
                )
                continue

            staged_rows.append(row_state)

    return staged_rows, all_rows, errors, processed_files, rows_read


def _find_input_files(input_root: Path, source_patterns: Iterable[str] | None) -> list[Path]:
    if input_root.is_file():
        return [input_root]

    patterns = list(source_patterns or ["*.csv", "*.xlsx"])
    matches: list[Path] = []

    for pattern in patterns:
        matches.extend(path for path in input_root.glob(pattern) if path.is_file())

    deduplicated = sorted({path.resolve() for path in matches})
    return [Path(path) for path in deduplicated]


def _iter_input_rows(file_path: Path, sheet_name: str | int | None):
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        yield from _iter_csv_rows(file_path)
        return

    if suffix == ".xlsx":
        yield from _iter_xlsx_rows(file_path, sheet_name)
        return

    raise ValueError(f"Unsupported input file type: {file_path}")


def _iter_csv_rows(file_path: Path):
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file '{file_path.name}' is empty or missing a header row.")

        reader.fieldnames = [_normalize_header(name) for name in reader.fieldnames]
        if not any(reader.fieldnames):
            raise ValueError(f"CSV file '{file_path.name}' does not contain any usable column headers.")

        for row_number, row in enumerate(reader, start=2):
            cleaned = {
                _normalize_header(key): value
                for key, value in row.items()
                if key is not None and _normalize_header(key)
            }
            if any(not is_blank(value) for value in cleaned.values()):
                yield row_number, cleaned


def _iter_xlsx_rows(file_path: Path, sheet_name: str | int | None):
    if load_workbook is None:
        raise RuntimeError("XLSX support requires openpyxl to be installed.")

    workbook = load_workbook(file_path, read_only=True, data_only=True)
    try:
        if sheet_name is None:
            worksheet = workbook.worksheets[0]
        elif isinstance(sheet_name, int):
            if sheet_name < 0 or sheet_name >= len(workbook.worksheets):
                available_sheets = ", ".join(workbook.sheetnames)
                raise ValueError(
                    f"Worksheet index {sheet_name} is out of range for '{file_path.name}'. Available sheets: {available_sheets}"
                )
            worksheet = workbook.worksheets[sheet_name]
        else:
            if str(sheet_name) not in workbook.sheetnames:
                available_sheets = ", ".join(workbook.sheetnames)
                raise ValueError(
                    f"Worksheet '{sheet_name}' was not found in '{file_path.name}'. Available sheets: {available_sheets}"
                )
            worksheet = workbook[str(sheet_name)]

        rows = worksheet.iter_rows(values_only=True)
        header_row = next(rows, None)
        if header_row is None:
            raise ValueError(
                f"Worksheet '{worksheet.title}' in '{file_path.name}' is empty or missing a header row."
            )

        headers = [_normalize_header(value) for value in header_row]
        if not any(headers):
            raise ValueError(
                f"Worksheet '{worksheet.title}' in '{file_path.name}' does not contain any usable column headers."
            )

        for row_number, values in enumerate(rows, start=2):
            cleaned = {}
            for header, value in zip(headers, values):
                if header:
                    cleaned[header] = value
            if any(not is_blank(value) for value in cleaned.values()):
                yield row_number, cleaned
    finally:
        workbook.close()


def _map_row(raw_row: dict[str, Any], mapping: dict, schema: dict) -> dict[str, Any]:
    output_columns = schema.get("output_columns") or list(schema.get("fields", {}).keys())
    field_mappings = mapping.get("field_mappings", {})
    mapping_defaults = mapping.get("defaults", {})
    schema_fields = schema.get("fields", {})

    standardized = {column: None for column in output_columns}
    
    # Build case-insensitive lookup for raw_row
    raw_row_lookup = _build_header_lookup(list(raw_row.keys()), case_sensitive=False)

    # Apply explicit field mappings
    for source_column, target_field in field_mappings.items():
        normalized_source = _normalize_header(source_column, case_sensitive=False)
        matched_source = raw_row_lookup.get(normalized_source)
        if matched_source:
            standardized[target_field] = raw_row.get(matched_source)

    # Apply column matching with fallback strategies
    for target_field in output_columns:
        if not is_blank(standardized.get(target_field)):
            continue  # Already found value via field mapping
            
        # Strategy 1: Direct key match with normalization
        normalized_target = _normalize_header(target_field, case_sensitive=False)
        matched = raw_row_lookup.get(normalized_target)
        if matched:
            standardized[target_field] = raw_row.get(matched)
            continue

        # Strategy 2: Try without trailing asterisk (for required field indicators)
        if target_field.endswith('*'):
            field_without_asterisk = target_field[:-1]
            normalized_without_asterisk = _normalize_header(field_without_asterisk, case_sensitive=False)
            matched = raw_row_lookup.get(normalized_without_asterisk)
            if matched:
                standardized[target_field] = raw_row.get(matched)
                continue

        # Strategy 3: Use mapping defaults
        if target_field in mapping_defaults:
            standardized[target_field] = mapping_defaults[target_field]
            continue

        # Strategy 4: Use schema defaults
        field_config = schema_fields.get(target_field, {})
        if "default" in field_config:
            standardized[target_field] = field_config["default"]

    return standardized


def _normalize_header(value: Any, *, case_sensitive: bool = False) -> str:
    """
    Normalize a header name for consistent matching.
    
    Handles:
    - None/empty values
    - Leading/trailing whitespace
    - Internal whitespace (multiple spaces, tabs, newlines)
    - Case normalization (optional)
    
    Args:
        value: The header name to normalize
        case_sensitive: If False, convert to lowercase for matching
    
    Returns:
        Normalized header string
    """
    if value is None:
        return ""
    
    # Convert to string and handle common separators
    text = str(value).strip()
    
    # Replace various whitespace characters (newlines, tabs, etc.) with single space
    text = re.sub(r'[\r\n\t]+', ' ', text)
    
    # Collapse multiple spaces into single space
    text = re.sub(r' +', ' ', text).strip()

    # Canonicalize common State/Province variants so mappings stay consistent.
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\bprovince/state\b", "state/province", text, flags=re.IGNORECASE)
    text = re.sub(
        r"\b(address\s*\d*\s*:\s*)state\b(?!\s*/\s*province)",
        r"\1state/province",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r":\s*state$", ": state/province", text, flags=re.IGNORECASE)
    if re.fullmatch(r"state", text, flags=re.IGNORECASE):
        text = "state/province"
    
    # Optionally normalize case
    if not case_sensitive:
        text = text.casefold()
    
    return text


def _build_header_lookup(headers: list[str], case_sensitive: bool = False) -> dict[str, str]:
    """
    Build a lookup map from normalized headers to original headers.
    
    Helps identify cases where headers differ only by normalization issues.
    """
    lookup = {}
    for header in headers:
        normalized = _normalize_header(header, case_sensitive=case_sensitive)
        if normalized:
            lookup[normalized] = header
    return lookup


def _find_matching_headers(source_headers: list[str], expected_headers: list[str], case_sensitive: bool = False) -> dict[str, str | None]:
    """
    Match source headers to expected headers, handling normalization.
    
    Returns:
        Dict mapping expected header names to found source headers (or None if not found)
    """
    source_lookup = _build_header_lookup(source_headers, case_sensitive=case_sensitive)
    matches = {}
    
    for expected in expected_headers:
        normalized_expected = _normalize_header(expected, case_sensitive=case_sensitive)
        matches[expected] = source_lookup.get(normalized_expected)
    
    return matches


def _validate_columns(
    source_headers: list[str],
    expected_headers: list[str] | None,
    entity_name: str,
    file_name: str,
    case_sensitive: bool = False,
) -> tuple[dict[str, str | None], list[str]]:
    """
    Validate that expected columns exist in source headers.
    
    Returns:
        Tuple of (matches dict, list of warnings)
    """
    warnings = []
    
    if not expected_headers:
        return {}, warnings
    
    matches = _find_matching_headers(source_headers, expected_headers, case_sensitive=case_sensitive)
    
    # Find missing required columns
    missing = [h for h, match in matches.items() if match is None and h.endswith('*')]
    if missing:
        warnings.append(
            f"Entity '{entity_name}' in '{file_name}': "
            f"Missing required columns: {', '.join(missing)}"
        )
    
    # Find unmapped source columns (optional warning)
    matched_sources = set(m for m in matches.values() if m is not None)
    normalized_sources = set(_normalize_header(h, case_sensitive=case_sensitive) for h in source_headers)
    matched_normalized = set(_normalize_header(h, case_sensitive=case_sensitive) for h in matched_sources)
    unmapped = normalized_sources - matched_normalized
    
    if unmapped:
        warnings.append(
            f"Entity '{entity_name}' in '{file_name}': "
            f"Source columns not used in schema: {', '.join(unmapped)}"
        )
    
    return matches, warnings


def _detect_duplicates(
    entity_name: str,
    staged_rows: list[dict[str, Any]],
    schema: dict,
) -> tuple[set[tuple[str, int]], list[dict[str, Any]]]:
    duplicate_rules = schema.get("duplicate_rules", [])
    excluded_rows: set[tuple[str, int]] = set()
    log_rows: list[dict[str, Any]] = []

    for rule in duplicate_rules:
        fields = [str(field) for field in rule.get("fields", []) if str(field).strip()]
        if not fields:
            continue

        duplicate_type = str(rule.get("type", "exact"))
        rule_name = str(rule.get("name") or f"{duplicate_type}_{'_'.join(fields)}")
        normalization = str(rule.get("normalization") or ("strict" if duplicate_type == "exact" else "loose"))
        exclude = bool(rule.get("exclude", duplicate_type == "exact"))
        require_all_fields = bool(rule.get("require_all_fields", True))
        message = str(
            rule.get(
                "message",
                "Exact duplicate detected." if duplicate_type == "exact" else "Potential duplicate detected.",
            )
        )

        grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for staged_row in staged_rows:
            key_parts = [
                _normalize_duplicate_value(staged_row["data"].get(field), normalization)
                for field in fields
            ]
            if require_all_fields and any(not part for part in key_parts):
                continue
            if not any(key_parts):
                continue
            grouped_rows[" | ".join(key_parts)].append(staged_row)

        for key_value, matches in grouped_rows.items():
            if len(matches) < 2:
                continue

            related_rows = "; ".join(f"{match['source_file']}:{match['row_number']}" for match in matches)
            action = "excluded_from_output" if exclude else "logged_only"

            for match in matches:
                row_key = (match["source_file"], match["row_number"])
                if exclude:
                    excluded_rows.add(row_key)

                log_rows.append(
                    {
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "entity": entity_name,
                        "duplicate_type": duplicate_type,
                        "rule_name": rule_name,
                        "key_fields": "; ".join(fields),
                        "key_value": key_value,
                        "source_file": match["source_file"],
                        "row_number": match["row_number"],
                        "action": action,
                        "reason": message,
                        "related_rows": related_rows,
                        "raw_row": _serialize_row(match["raw_row"]),
                    }
                )

    return excluded_rows, log_rows


def _normalize_duplicate_value(value: Any, normalization: str = "strict") -> str:
    if is_blank(value):
        return ""

    text = str(value).strip()
    if normalization == "strict":
        return text

    return normalize_loose_text(value, strip_punctuation=normalization == "loose")


def _append_row_issues(
    errors: list[dict[str, Any]],
    entity_name: str,
    source_file: str,
    row_number: int,
    issues: list[tuple[str, str]],
    record: dict[str, Any],
    raw_row: dict[str, Any],
):
    for field_name, reason in issues:
        errors.append(
            _build_error_row(
                entity_name=entity_name,
                source_file=source_file,
                row_number=row_number,
                field_name=field_name,
                reason=reason,
                original_value=record.get(field_name),
                raw_row=raw_row,
            )
        )


def _serialize_row(raw_row: dict[str, Any]) -> str:
    return json.dumps(raw_row, ensure_ascii=False, default=str, sort_keys=True)


def _build_error_row(
    entity_name: str,
    source_file: str,
    row_number: int,
    field_name: str,
    reason: str,
    original_value: Any,
    raw_row: dict[str, Any],
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "entity": entity_name,
        "source_file": source_file,
        "row_number": row_number,
        "field": field_name,
        "reason": reason,
        "original_value": "" if original_value is None else str(original_value),
        "raw_row": _serialize_row(raw_row),
    }


def _write_csv(file_path: Path, rows: list[dict[str, Any]], fieldnames: list[str]):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _append_run_log(log_path: Path, summaries: list[dict[str, Any]]):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = log_path.exists()
    with log_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RUN_LOG_FIELDS)
        if not file_exists:
            writer.writeheader()

        timestamp = datetime.now().isoformat(timespec="seconds")
        for summary in summaries:
            writer.writerow(
                {
                    "timestamp": timestamp,
                    "entity": summary["entity"],
                    "files_processed": "; ".join(summary["files_processed"]),
                    "rows_read": summary["rows_read"],
                    "rows_accepted": summary["rows_accepted"],
                    "rows_rejected": summary["rows_rejected"],
                    "duplicate_rows_flagged": summary.get("duplicate_rows_flagged", 0),
                    "output_file": summary["output_file"],
                    "error_file": summary["error_file"],
                }
            )


def _append_duplicate_log(log_path: Path, rows: list[dict[str, Any]]):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = log_path.exists()
    with log_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DUPLICATE_LOG_FIELDS)
        if not file_exists:
            writer.writeheader()

        for row in rows:
            writer.writerow({field: row.get(field, "") for field in DUPLICATE_LOG_FIELDS})
