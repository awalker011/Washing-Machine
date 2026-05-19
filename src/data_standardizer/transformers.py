from __future__ import annotations

import re
from datetime import datetime
from typing import Any

NULL_LIKE_VALUES = {"", "-", "--", "---", "none", "null", "n/a", "na"}
NORMALIZATION_ALIASES = {
    "building": "bldg",
    "bldg": "bldg",
    "bld": "bldg",
    "corporation": "corp",
    "company": "co",
    "incorporated": "inc",
    "limited": "ltd",
}
COUNTRY_NAME_TO_CODE = {
    "us": "US",
    "usa": "US",
    "united states": "US",
    "united states of america": "US",
    "america": "US",
    "ca": "CA",
    "can": "CA",
    "canada": "CA",
}
US_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
CA_PROVINCE_NAME_TO_CODE = {
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB",
    "newfoundland and labrador": "NL", "nova scotia": "NS", "northwest territories": "NT",
    "nunavut": "NU", "ontario": "ON", "prince edward island": "PE", "quebec": "QC",
    "saskatchewan": "SK", "yukon": "YT",
}
POSTAL_CODE_PATTERN = re.compile(r"^((\d{5}(-\d{4})?)|([A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d))$")


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in NULL_LIKE_VALUES
    return False


def _as_text(value: Any) -> str:
    return "" if value is None else str(value)


def normalize_loose_text(value: Any, *, strip_punctuation: bool = True) -> str:
    if is_blank(value):
        return ""

    text = _as_text(value).strip().casefold().replace("&", " and ")
    for old_value, new_value in NORMALIZATION_ALIASES.items():
        text = re.sub(rf"\b{re.escape(old_value)}\b", new_value, text)

    text = re.sub(r"\s+", " ", text)
    return re.sub(r"[^a-z0-9]+", "", text) if strip_punctuation else text


def normalize_country_code(value: Any, *, preserve_unrecognized: bool = False) -> str | None:
    if is_blank(value):
        return None

    text = re.sub(r"\s+", " ", _as_text(value).replace("\u00a0", " ")).strip()
    lookup = text.casefold().replace(".", "")
    normalized = COUNTRY_NAME_TO_CODE.get(lookup)
    if normalized is not None:
        return normalized
    return text.upper() if preserve_unrecognized else None


def normalize_region_code(
    value: Any,
    *,
    country: Any | None = None,
    preserve_unrecognized: bool = False,
) -> str | None:
    if is_blank(value):
        return None

    text = re.sub(r"\s+", " ", _as_text(value).replace("\u00a0", " ")).strip()
    lookup = text.casefold().replace(".", "")
    normalized_country = normalize_country_code(country, preserve_unrecognized=False)

    if normalized_country == "CA":
        candidate_maps = [CA_PROVINCE_NAME_TO_CODE]
    elif normalized_country == "US":
        candidate_maps = [US_STATE_NAME_TO_CODE]
    else:
        candidate_maps = [US_STATE_NAME_TO_CODE, CA_PROVINCE_NAME_TO_CODE]

    for mapping in candidate_maps:
        if lookup in mapping:
            return mapping[lookup]

    upper_text = text.upper()
    valid_codes = {code for mapping in candidate_maps for code in mapping.values()}
    if upper_text in valid_codes:
        return upper_text

    return upper_text if preserve_unrecognized else None


def _normalize_postal_code(value: Any) -> str | None:
    if is_blank(value):
        return None

    text = re.sub(r"\s+", " ", _as_text(value).replace("\u00a0", " ")).strip().upper()
    if re.fullmatch(r"[A-Z]\d[A-Z]\d[A-Z]\d", text):
        return f"{text[:3]} {text[3:]}"
    return text


def _looks_like_postal_code(value: Any) -> bool:
    normalized = _normalize_postal_code(value)
    return bool(normalized and POSTAL_CODE_PATTERN.fullmatch(normalized))


def _looks_like_phone(value: Any) -> bool:
    if is_blank(value):
        return False
    digits = re.sub(r"\D+", "", _as_text(value))
    return 10 <= len(digits) <= 15


def _looks_like_postal_candidate(value: Any) -> bool:
    normalized = _normalize_postal_code(value)
    return bool(normalized and (POSTAL_CODE_PATTERN.fullmatch(normalized) or re.fullmatch(r"\d{4,5}", normalized)))


def _infer_country_from_region_or_postal(region_value: Any, postal_value: Any) -> str | None:
    us_region = normalize_region_code(region_value, country="US", preserve_unrecognized=False)
    if us_region in set(US_STATE_NAME_TO_CODE.values()):
        return "US"

    ca_region = normalize_region_code(region_value, country="CA", preserve_unrecognized=False)
    if ca_region in set(CA_PROVINCE_NAME_TO_CODE.values()):
        return "CA"

    normalized_postal = _normalize_postal_code(postal_value)
    if normalized_postal and re.fullmatch(r"\d{4,5}(-\d{4})?", normalized_postal):
        return "US"
    if normalized_postal and re.fullmatch(r"[A-Z]\d[A-Z][ -]?\d[A-Z]\d", normalized_postal):
        return "CA"
    return None


def _extract_city_region_postal_from_line(value: Any) -> dict[str, str] | None:
    if is_blank(value):
        return None

    text = re.sub(r"\s+", " ", _as_text(value).replace("\u00a0", " ")).strip(" ,")
    match = re.search(
        r"^(?P<city>.+?)(?:,\s*|\s+)(?P<region>[A-Za-z][A-Za-z .'-]*?)\s+(?P<postal>\d{4,5}(?:-\d{4})?|[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d)$",
        text,
    )
    if not match:
        return None

    city = match.group("city").strip(" ,")
    region_raw = match.group("region").strip(" ,")
    postal = _normalize_postal_code(match.group("postal"))
    country = _infer_country_from_region_or_postal(region_raw, postal)
    region = normalize_region_code(region_raw, country=country, preserve_unrecognized=False)

    if not city or region is None or postal is None:
        return None

    return {
        "city": city,
        "region": region,
        "postal": postal,
        "country": country or "US",
    }


def _repair_misaligned_address(record: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    city_field = str(options.get("city_field", "Address 1: City"))
    region_field = str(options.get("region_field", "Address 1: State/Province"))
    postal_field = str(options.get("postal_field", "Address 1: ZIP/Postal Code"))
    country_field = str(options.get("country_field", "Address 1: Country/Region"))
    phone_field = str(options.get("phone_field", "Main Phone"))
    street_line_field = str(options.get("street_line_field", "Address 1: Street 3"))

    city_value = record.get(city_field)
    region_value = record.get(region_field)
    postal_value = record.get(postal_field)
    country_value = record.get(country_field)
    phone_value = record.get(phone_field)
    street_line_value = record.get(street_line_field)

    normalized_country = normalize_country_code(country_value, preserve_unrecognized=False)
    fallback_country = normalize_country_code(phone_value, preserve_unrecognized=False)

    repaired = {
        city_field: None if is_blank(city_value) else _as_text(city_value).strip(),
        region_field: (
            normalize_region_code(
                region_value,
                country=normalized_country or fallback_country,
                preserve_unrecognized=True,
            )
            if not is_blank(region_value)
            else region_value
        ),
        postal_field: _normalize_postal_code(postal_value) if not is_blank(postal_value) else postal_value,
        country_field: (
            normalize_country_code(country_value, preserve_unrecognized=True)
            if not is_blank(country_value)
            else country_value
        ),
        phone_field: None if is_blank(phone_value) else _as_text(phone_value).strip(),
    }

    parsed_line = _extract_city_region_postal_from_line(street_line_value)
    if parsed_line:
        if is_blank(repaired[city_field]):
            repaired[city_field] = parsed_line["city"]
        if is_blank(repaired[region_field]):
            repaired[region_field] = parsed_line["region"]
        if is_blank(repaired[postal_field]):
            repaired[postal_field] = parsed_line["postal"]
        if is_blank(repaired[country_field]):
            repaired[country_field] = parsed_line["country"]

    inferred_country = (
        normalized_country
        or fallback_country
        or _infer_country_from_region_or_postal(repaired.get(region_field), repaired.get(postal_field))
    )
    if is_blank(repaired[country_field]) and inferred_country is not None:
        repaired[country_field] = inferred_country

    shifted_address = (
        not is_blank(region_value)
        and _looks_like_postal_candidate(country_value)
        and not _looks_like_phone(phone_value)
        and normalize_region_code(
            postal_value,
            country=fallback_country or inferred_country,
            preserve_unrecognized=False,
        )
        is not None
    )

    if shifted_address:
        shift_country = fallback_country or inferred_country or "US"
        postal_candidate = _normalize_postal_code(country_value)
        repaired[city_field] = _as_text(region_value).strip()
        repaired[region_field] = normalize_region_code(
            postal_value,
            country=shift_country,
            preserve_unrecognized=True,
        )
        repaired[postal_field] = (
            postal_candidate if postal_candidate and POSTAL_CODE_PATTERN.fullmatch(postal_candidate) else None
        )
        repaired[country_field] = shift_country
        repaired[phone_field] = None
    elif is_blank(country_value) and fallback_country is not None and not _looks_like_phone(phone_value):
        repaired[country_field] = fallback_country
        repaired[phone_field] = None
    elif (
        fallback_country is not None
        and normalize_country_code(repaired.get(country_field), preserve_unrecognized=False) is None
        and normalize_region_code(
            repaired.get(region_field),
            country=fallback_country,
            preserve_unrecognized=False,
        )
        is not None
    ):
        repaired[country_field] = fallback_country
        repaired[phone_field] = None
    elif fallback_country is not None and repaired.get(country_field) == fallback_country and not _looks_like_phone(phone_value):
        repaired[phone_field] = None

    return repaired

def apply_operation(
    value: Any,
    operation: Any,
    record: dict[str, Any] | None = None,
) -> Any:
    if isinstance(operation, str):
        name = operation
        options = {}
    elif isinstance(operation, dict):
        name = str(operation.get("name", "")).strip()
        options = operation
    else:
        raise ValueError(f"Unsupported transformation definition: {operation!r}")

    if not name:
        raise ValueError("Transformation must define a name.")

    if name == "trim":
        return value.strip() if isinstance(value, str) else value

    if name == "collapse_whitespace":
        if is_blank(value):
            return value
        text = _as_text(value).replace("_x000D_", " ").replace("\u00a0", " ")
        return re.sub(r"\s+", " ", text).strip()

    if name == "lowercase":
        return _as_text(value).lower() if not is_blank(value) else value

    if name == "uppercase":
        return _as_text(value).upper() if not is_blank(value) else value

    if name == "null_if_blank":
        return None if is_blank(value) else value

    if name == "default_if_blank":
        return options.get("value") if is_blank(value) else value

    if name == "null_if_in":
        tokens = {str(item).strip().casefold() for item in options.get("values", [])}
        text = _as_text(value).strip().casefold()
        return None if text in tokens else value

    if name == "map_values":
        if is_blank(value):
            return value

        raw_mapping = options.get("mapping", {})
        case_insensitive = bool(options.get("case_insensitive", True))
        preserve_unmapped = bool(options.get("preserve_unmapped", True))
        text = _as_text(value).strip()

        if case_insensitive:
            mapped_values = {
                str(key).strip().casefold(): mapped_value
                for key, mapped_value in raw_mapping.items()
            }
            lookup_value = text.casefold()
        else:
            mapped_values = {str(key): mapped_value for key, mapped_value in raw_mapping.items()}
            lookup_value = text

        if lookup_value in mapped_values:
            return mapped_values[lookup_value]

        return value if preserve_unmapped else options.get("default")

    if name == "normalize_country_code":
        normalized_country = normalize_country_code(value, preserve_unrecognized=True)
        return normalized_country if normalized_country is not None else value

    if name == "normalize_region_code":
        country_field = str(options.get("country_field", "")).strip()
        country_value = None if record is None or not country_field else record.get(country_field)
        normalized_region = normalize_region_code(
            value,
            country=country_value,
            preserve_unrecognized=True,
        )
        return normalized_region if normalized_region is not None else value

    if name == "repair_misaligned_address_component":
        if record is None:
            return value

        component = str(options.get("component", "")).strip().casefold()
        repaired = _repair_misaligned_address(record, options)
        field_by_component = {
            "city": str(options.get("city_field", "Address 1: City")),
            "region": str(options.get("region_field", "Address 1: State/Province")),
            "state": str(options.get("region_field", "Address 1: State/Province")),
            "postal": str(options.get("postal_field", "Address 1: ZIP/Postal Code")),
            "postal_code": str(options.get("postal_field", "Address 1: ZIP/Postal Code")),
            "zip": str(options.get("postal_field", "Address 1: ZIP/Postal Code")),
            "country": str(options.get("country_field", "Address 1: Country/Region")),
            "phone": str(options.get("phone_field", "Main Phone")),
        }
        target_field = field_by_component.get(component)
        if target_field is None:
            raise ValueError(f"Unsupported address component '{component}'.")
        return repaired.get(target_field)

    if name == "digits_only":
        return re.sub(r"\D+", "", _as_text(value)) if not is_blank(value) else value

    if name == "replace":
        if is_blank(value):
            return value
        return _as_text(value).replace(str(options.get("old", "")), str(options.get("new", "")))

    if name == "concat_fields":
        only_if_blank = options.get("only_if_blank", True)
        if only_if_blank and not is_blank(value):
            return value

        fields = options.get("fields", [])
        if not fields:
            raise ValueError("concat_fields requires a non-empty 'fields' list.")

        separator = str(options.get("separator", " "))
        parts = []
        for field_name in fields:
            source_value = None if record is None else record.get(field_name)
            if not is_blank(source_value):
                parts.append(str(source_value).strip())

        return separator.join(parts) if parts else value

    if name == "date_format":
        if is_blank(value):
            return value
        text = _as_text(value).strip()
        input_formats = options.get(
            "input_formats",
            ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"],
        )
        output_format = options.get("output_format", "%Y-%m-%d")
        for input_format in input_formats:
            try:
                parsed = datetime.strptime(text, input_format)
                return parsed.strftime(output_format)
            except ValueError:
                continue
        raise ValueError(f"Could not parse date value '{text}' using configured formats.")

    raise ValueError(f"Unknown transformation: {name}")


def apply_transformations(
    record: dict[str, Any], transformations: dict[str, list[Any]]
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    transformed = dict(record)
    issues: list[tuple[str, str]] = []

    for field_name, operations in transformations.items():
        for operation in operations or []:
            try:
                transformed[field_name] = apply_operation(
                    transformed.get(field_name),
                    operation,
                    transformed,
                )
            except Exception as exc:  # pragma: no cover - defensive reporting path
                issues.append((field_name, str(exc)))

    return transformed, issues


def apply_transformations_with_audit(
    record: dict[str, Any], transformations: dict[str, list[Any]]
) -> tuple[dict[str, Any], list[tuple[str, str]], dict[str, list[dict[str, Any]]]]:
    """
    Apply transformations to a record with audit trail tracking.
    
    Returns:
        Tuple of (transformed_record, issues_list, audit_trail_dict)
        where audit_trail_dict maps field names to lists of transformation steps
    """
    transformed = dict(record)
    issues: list[tuple[str, str]] = []
    audit_trail: dict[str, list[dict[str, Any]]] = {}

    for field_name, operations in transformations.items():
        audit_trail[field_name] = []
        current_value = transformed.get(field_name)
        
        for operation in operations or []:
            previous_value = current_value
            operation_name = operation if isinstance(operation, str) else operation.get("name", "unknown")
            
            try:
                current_value = apply_operation(current_value, operation, transformed)
                
                # Record transformation step
                audit_trail[field_name].append({
                    "operation": operation_name,
                    "input": previous_value,
                    "output": current_value,
                    "success": True
                })
                transformed[field_name] = current_value
                
            except Exception as exc:  # pragma: no cover - defensive reporting path
                audit_trail[field_name].append({
                    "operation": operation_name,
                    "input": previous_value,
                    "output": None,
                    "error": str(exc),
                    "success": False
                })
                issues.append((field_name, str(exc)))
                break  # Stop processing this field if transformation fails

    return transformed, issues, audit_trail
