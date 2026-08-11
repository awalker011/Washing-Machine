from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .transformers import (
    is_blank,
    normalize_country_code,
    normalize_loose_text,
    normalize_region_code,
)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
POSTAL_CODE_PATTERN = re.compile(r"(\d{5}(-\d{4})?)|([A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d)")
US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC",
}
CA_PROVINCE_CODES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}


def comparable(value: Any) -> str | None:
    if is_blank(value):
        return None
    return str(value).strip()


def _normalize_country(value: Any) -> str | None:
    text = comparable(value)
    if text is None:
        return None

    normalized = normalize_country_code(text, preserve_unrecognized=False)
    return normalized or text.upper()


def _matches_type(value: Any, expected_type: str, field_config: dict) -> bool:
    if expected_type == "string":
        return isinstance(value, (str, int, float, bool))

    text = str(value).strip()

    if expected_type == "integer":
        return re.fullmatch(r"[-+]?\d+", text) is not None

    if expected_type == "float":
        return re.fullmatch(r"[-+]?(\d+\.\d+|\d+)", text) is not None

    if expected_type == "boolean":
        return text.lower() in {"true", "false", "yes", "no", "1", "0", "y", "n"}

    if expected_type == "date":
        formats = field_config.get("formats") or [field_config.get("format", "%Y-%m-%d")]
        for fmt in formats:
            try:
                datetime.strptime(text, fmt)
                return True
            except ValueError:
                continue
        return False

    return True


def _coerce_number(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _matches_format(
    field_name: str,
    value: Any,
    field_config: dict,
    record: dict[str, Any] | None = None,
) -> bool:
    format_name = str(field_config.get("format", "")).strip()
    if not format_name:
        return True

    text = str(value).strip()

    if format_name == "email":
        return EMAIL_PATTERN.fullmatch(text) is not None

    if format_name == "email_or_name":
        if "@" not in text:
            return True
        return EMAIL_PATTERN.fullmatch(text) is not None

    if format_name == "phone":
        digits = re.sub(r"\D+", "", text)
        return 10 <= len(digits) <= 15

    if format_name == "postal_code_us_ca":
        return POSTAL_CODE_PATTERN.fullmatch(text) is not None

    if format_name == "region_code_by_country":
        country_field = str(field_config.get("country_field", "")).strip()
        country = _normalize_country(None if record is None else record.get(country_field))
        normalized_region = normalize_region_code(text, country=country, preserve_unrecognized=False)
        if country == "US":
            return normalized_region in US_STATE_CODES
        if country == "CA":
            return normalized_region in CA_PROVINCE_CODES
        return normalized_region is not None or True

    return True


def _format_message(field_name: str, field_config: dict) -> str:
    format_name = str(field_config.get("format", "")).strip()
    if format_name == "email":
        return f"{field_name} must contain a valid email address."
    if format_name == "email_or_name":
        return f"{field_name} looks like an email address but is not valid. Enter a valid email address, or a plain contact name if this isn't meant to be an email."
    if format_name == "phone":
        return f"{field_name} must contain a valid phone number with at least 10 digits."
    if format_name == "postal_code_us_ca":
        return f"{field_name} must contain a valid US ZIP or Canadian postal code."
    if format_name == "region_code_by_country":
        return f"{field_name} must contain a valid province/state code for the selected country."
    return f"{field_name} has an invalid format."


def validate_field(
    field_name: str,
    value: Any,
    field_config: dict,
    record: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []

    if field_config.get("required") and is_blank(value):
        issues.append((field_name, "Field is required."))
        return issues

    if is_blank(value):
        return issues

    expected_type = field_config.get("type")
    if expected_type and not _matches_type(value, expected_type, field_config):
        issues.append((field_name, f"Expected value of type '{expected_type}'."))

    if field_config.get("format") and not _matches_format(field_name, value, field_config, record):
        issues.append((field_name, _format_message(field_name, field_config)))

    regex_pattern = field_config.get("regex")
    if regex_pattern and re.fullmatch(regex_pattern, str(value).strip()) is None:
        issues.append((field_name, f"Value does not match regex '{regex_pattern}'."))

    allowed_values = field_config.get("allowed_values")
    if allowed_values and str(value) not in {str(item) for item in allowed_values}:
        issues.append((field_name, f"Value must be one of: {allowed_values}."))

    disallow_values = field_config.get("disallow_values")
    disallowed_lookup = {str(item).strip().casefold() for item in disallow_values or []}
    if disallowed_lookup and str(value).strip().casefold() in disallowed_lookup:
        issues.append((field_name, f"Value contains a disallowed placeholder: {value}."))

    min_length = field_config.get("min_length")
    if min_length is not None and len(str(value)) < int(min_length):
        issues.append((field_name, f"Value must be at least {min_length} characters long."))

    max_length = field_config.get("max_length")
    if max_length is not None and len(str(value)) > int(max_length):
        issues.append((field_name, f"Value must be at most {max_length} characters long."))

    numeric_value = _coerce_number(value)
    min_value = field_config.get("min_value")
    if min_value is not None and numeric_value is not None and numeric_value < float(min_value):
        issues.append((field_name, f"Value must be at least {min_value}."))

    max_value = field_config.get("max_value")
    if max_value is not None and numeric_value is not None and numeric_value > float(max_value):
        issues.append((field_name, f"Value must be at most {max_value}."))

    return issues


def validate_cross_field_rules(record: dict[str, Any], rules: list[dict]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []

    for rule in rules or []:
        rule_type = rule.get("type")
        fields = [str(field) for field in rule.get("fields", [])]
        message = str(rule.get("message", "Cross-field validation failed."))

        if rule_type == "at_least_one":
            if not any(not is_blank(record.get(field)) for field in fields):
                issues.append((", ".join(fields) or "record", message))

        elif rule_type == "fields_match":
            values = [comparable(record.get(field)) for field in fields]
            present_values = [value for value in values if value is not None]
            if present_values and len(set(present_values)) > 1:
                issues.append((", ".join(fields) or "record", message))

        elif rule_type == "fields_not_equal":
            if len(fields) >= 2:
                left_value = comparable(record.get(fields[0]))
                right_value = comparable(record.get(fields[1]))
                if left_value is not None and right_value is not None and left_value == right_value:
                    issues.append((", ".join(fields[:2]), message))

        elif rule_type == "required_if_any":
            trigger_fields = [str(field) for field in rule.get("trigger_fields", fields)]
            required_fields = [str(field) for field in rule.get("required_fields", fields)]
            if any(not is_blank(record.get(field)) for field in trigger_fields):
                for required_field in required_fields:
                    if is_blank(record.get(required_field)):
                        issues.append((required_field, message))

    return issues


def _find_similar_values(value: str, candidates: list[str] | set[str]) -> list[str]:
    normalized_value = normalize_loose_text(value)
    if not normalized_value:
        return []

    matches: list[str] = []
    for candidate in candidates:
        if normalize_loose_text(candidate) == normalized_value:
            matches.append(str(candidate))
    return matches[:3]


def _get_related_rows(
    candidate_map: dict[str, list[dict[str, Any]]],
    lookup_value: str,
) -> list[dict[str, Any]]:
    exact_match = candidate_map.get(lookup_value)
    if exact_match:
        return exact_match

    normalized_lookup = normalize_loose_text(lookup_value)
    if not normalized_lookup:
        return []

    fallback_matches: list[dict[str, Any]] = []
    for candidate_value, candidate_rows in candidate_map.items():
        if normalize_loose_text(candidate_value) == normalized_lookup:
            fallback_matches.extend(candidate_rows)

    return fallback_matches


def validate_relationship_rules(
    record: dict[str, Any],
    rules: list[dict],
    relationship_index: dict[tuple[str, str], set[str]],
    entity_row_index: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] | None = None,
    rejected_reference_index: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] | None = None,
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    entity_row_index = entity_row_index or {}
    rejected_reference_index = rejected_reference_index or {}

    for rule in rules or []:
        rule_type = str(rule.get("type", "must_exist_in_entity"))

        if rule_type == "must_exist_in_entity":
            field_name = rule.get("field")
            other_entity = rule.get("other_entity")
            other_field = rule.get("other_field")
            message = rule.get(
                "message",
                f"Value for '{field_name}' must exist in {other_entity}.{other_field}.",
            )

            value = comparable(record.get(field_name))
            if value is None:
                continue

            allowed_values = relationship_index.get((str(other_entity), str(other_field)), set())
            if value not in allowed_values:
                candidate_map = entity_row_index.get((str(other_entity), str(other_field)), {})
                rejected_candidate_map = rejected_reference_index.get(
                    (str(other_entity), str(other_field)),
                    {},
                )
                rejected_matches = _get_related_rows(rejected_candidate_map, value)
                if rejected_matches:
                    details = _summarize_rejected_reference(str(other_entity), rejected_matches)
                    issues.append((str(field_name), f"{message} {details}"))
                else:
                    similar_values = _find_similar_values(value, list(candidate_map.keys()))
                    if similar_values:
                        issues.append(
                            (str(field_name), f"{message} Similar existing value(s): {', '.join(similar_values)}.")
                        )
                    else:
                        issues.append((str(field_name), str(message)))

        elif rule_type == "related_field_equals":
            field_name = str(rule.get("field", "")).strip()
            lookup_field = str(rule.get("lookup_field") or field_name).strip()
            other_entity = str(rule.get("other_entity", "")).strip()
            other_lookup_field = str(rule.get("other_lookup_field", "")).strip()
            other_value_field = str(rule.get("other_value_field", "")).strip()
            message = str(
                rule.get(
                    "message",
                    f"{field_name} must match {other_entity}.{other_value_field} for the related {other_lookup_field}.",
                )
            )

            lookup_value = comparable(record.get(lookup_field))
            compare_value = comparable(record.get(field_name))
            if lookup_value is None or compare_value is None:
                continue

            candidate_map = entity_row_index.get((other_entity, other_lookup_field), {})
            related_rows = _get_related_rows(candidate_map, lookup_value)
            if not related_rows:
                continue

            expected_values = {
                comparable(candidate_row["data"].get(other_value_field))
                for candidate_row in related_rows
                if comparable(candidate_row["data"].get(other_value_field)) is not None
            }
            if expected_values and compare_value not in expected_values:
                expected_text = ", ".join(sorted(expected_values))
                issues.append((field_name, f"{message} Expected: {expected_text}."))

    return issues


def _summarize_rejected_reference(other_entity: str, rejected_matches: list[dict[str, Any]]) -> str:
    first_match = rejected_matches[0]
    source_file = str(first_match.get("source_file", "")).strip()
    row_number = first_match.get("row_number")
    reasons = [str(reason) for reason in first_match.get("reasons", []) if str(reason).strip()]
    reason_text = reasons[0] if reasons else "record failed validation"

    if source_file and row_number is not None:
        row_ref = f"{source_file}:{row_number}"
    else:
        row_ref = "upstream row"

    return (
        "Lookup dependency note: this value exists in source data but the referenced "
        f"{other_entity} row was rejected earlier (example {row_ref}: {reason_text})."
    )


def validate_record(record: dict[str, Any], schema: dict) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    fields = schema.get("fields", {})

    for field_name, field_config in fields.items():
        issues.extend(validate_field(field_name, record.get(field_name), field_config, record))

    issues.extend(validate_cross_field_rules(record, schema.get("cross_field_rules", [])))
    return issues
