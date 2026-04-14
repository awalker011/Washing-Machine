from pathlib import Path

import pytest

from data_standardizer.gui import build_output_paths, format_run_summary, validate_run_inputs


def test_build_output_paths_uses_default_folder_next_to_input(tmp_path):
    input_file = tmp_path / "sample.xlsx"
    input_file.write_text("placeholder", encoding="utf-8")

    output_dir, logs_dir = build_output_paths(input_file, None)

    assert output_dir == tmp_path / "sample_washed_output"
    assert logs_dir == output_dir / "logs"


def test_format_run_summary_includes_totals_and_entities():
    summary = format_run_summary(
        {
            "totals": {"rows_read": 10, "rows_accepted": 8, "rows_rejected": 2},
            "entities": [
                {
                    "entity": "Accounts",
                    "rows_accepted": 5,
                    "rows_rejected": 1,
                    "duplicate_rows_flagged": 2,
                }
            ],
            "duplicate_log_file": "logs/duplicate_log.csv",
        }
    )

    assert "Rows read: 10" in summary
    assert "Accounts: accepted 5, rejected 1, duplicates flagged 2" in summary
    assert "duplicate_log.csv" in summary


def test_validate_run_inputs_rejects_missing_input_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Input file was not found"):
        validate_run_inputs(str(tmp_path / "missing.xlsx"), str(tmp_path / "output"))
