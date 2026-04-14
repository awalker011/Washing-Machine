import csv
import json

import pytest
from openpyxl import Workbook

from data_standardizer.pipeline import process_all


def test_duplicate_log_includes_rows_that_are_invalid_for_other_reasons(tmp_path):
    input_dir = tmp_path / "input"
    schema_dir = tmp_path / "schemas"
    mapping_dir = tmp_path / "mappings"
    output_dir = tmp_path / "output"
    logs_dir = tmp_path / "logs"

    input_dir.mkdir()
    schema_dir.mkdir()
    mapping_dir.mkdir()

    (input_dir / "accounts.csv").write_text(
        "Account Name*,Account Type\n"
        "Acme Corp,???\n"
        "Acme Corp,???\n",
        encoding="utf-8",
    )

    (schema_dir / "accounts.json").write_text(
        json.dumps(
            {
                "entity_name": "Accounts",
                "output_columns": ["Account Name*", "Account Type"],
                "fields": {
                    "Account Name*": {"type": "string", "required": True},
                    "Account Type": {"type": "string", "disallow_values": ["???"]},
                },
                "duplicate_rules": [
                    {
                        "name": "account_name_exact",
                        "type": "exact",
                        "fields": ["Account Name*"],
                        "exclude": True,
                        "message": "Duplicate Account Name* values were found.",
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (mapping_dir / "accounts.json").write_text(
        json.dumps(
            {
                "entity_name": "Accounts",
                "schema": "Accounts",
                "source_patterns": ["accounts.csv"],
                "target_file": "Accounts.csv",
                "error_file": "Accounts_errors.csv",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    process_all(
        input_path=str(input_dir),
        schema_path=str(schema_dir),
        mapping_path=str(mapping_dir),
        output_dir=str(output_dir),
        logs_dir=str(logs_dir),
    )

    duplicate_log_path = logs_dir / "duplicate_log.csv"
    with duplicate_log_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert {row["row_number"] for row in rows} == {"2", "3"}


def test_process_all_raises_when_no_input_files_match(tmp_path):
    input_dir = tmp_path / "input"
    schema_dir = tmp_path / "schemas"
    mapping_dir = tmp_path / "mappings"

    input_dir.mkdir()
    schema_dir.mkdir()
    mapping_dir.mkdir()

    (schema_dir / "accounts.json").write_text(
        json.dumps(
            {
                "entity_name": "Accounts",
                "output_columns": ["Account Name*"],
                "fields": {"Account Name*": {"type": "string", "required": True}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (mapping_dir / "accounts.json").write_text(
        json.dumps(
            {
                "entity_name": "Accounts",
                "schema": "Accounts",
                "source_patterns": ["missing.csv"],
                "target_file": "Accounts.csv",
                "error_file": "Accounts_errors.csv",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="No input files matched"):
        process_all(
            input_path=str(input_dir),
            schema_path=str(schema_dir),
            mapping_path=str(mapping_dir),
            output_dir=str(tmp_path / "output"),
            logs_dir=str(tmp_path / "logs"),
        )


def test_process_all_raises_when_configured_sheet_is_missing(tmp_path):
    input_dir = tmp_path / "input"
    schema_dir = tmp_path / "schemas"
    mapping_dir = tmp_path / "mappings"

    input_dir.mkdir()
    schema_dir.mkdir()
    mapping_dir.mkdir()

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Wrong Sheet"
    worksheet.append(["Account Name*"])
    worksheet.append(["Acme Corp"])
    workbook.save(input_dir / "accounts.xlsx")

    (schema_dir / "accounts.json").write_text(
        json.dumps(
            {
                "entity_name": "Accounts",
                "output_columns": ["Account Name*"],
                "fields": {"Account Name*": {"type": "string", "required": True}},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    (mapping_dir / "accounts.json").write_text(
        json.dumps(
            {
                "entity_name": "Accounts",
                "schema": "Accounts",
                "source_patterns": ["accounts.xlsx"],
                "sheet_name": "Accounts",
                "target_file": "Accounts.csv",
                "error_file": "Accounts_errors.csv",
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Worksheet 'Accounts' was not found"):
        process_all(
            input_path=str(input_dir),
            schema_path=str(schema_dir),
            mapping_path=str(mapping_dir),
            output_dir=str(tmp_path / "output"),
            logs_dir=str(tmp_path / "logs"),
        )
