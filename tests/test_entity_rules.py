from data_standardizer.entity_rules import evaluate_entity_rules


def _row(data, row_number):
    return {
        "data": data,
        "source_file": "sample.xlsx",
        "row_number": row_number,
        "raw_row": data,
    }


def test_evaluate_entity_rules_detects_parent_cycles():
    staged_entities = {
        "Accounts": {
            "rows": [
                _row({"Account Name*": "Acme", "Parent Account": "HoldCo"}, 2),
                _row({"Account Name*": "HoldCo", "Parent Account": "Acme"}, 3),
            ],
            "schema": {
                "entity_rules": [
                    {
                        "type": "no_parent_cycles",
                        "id_field": "Account Name*",
                        "parent_field": "Parent Account",
                        "message": "Parent Account creates a circular relationship chain.",
                    }
                ]
            },
        }
    }

    issues = evaluate_entity_rules(staged_entities)

    assert ("Accounts", "sample.xlsx", 2) in issues
    assert any("circular relationship chain" in reason for _, reason in issues[("Accounts", "sample.xlsx", 2)])


def test_evaluate_entity_rules_detects_excess_device_count():
    staged_entities = {
        "Building Locations": {
            "rows": [
                _row({"Name*": "Tower A", "# Elevators": "2"}, 2),
            ],
            "schema": {
                "entity_rules": [
                    {
                        "type": "child_count_lte_reference",
                        "child_entity": "Devices",
                        "parent_lookup_field": "Name*",
                        "child_lookup_field": "Building Location",
                        "limit_field": "# Elevators",
                        "message": "Assigned device count exceeds # Elevators for this building.",
                    }
                ]
            },
        },
        "Devices": {
            "rows": [
                _row({"Building Location": "Tower A"}, 10),
                _row({"Building Location": "Tower A"}, 11),
                _row({"Building Location": "Tower A"}, 12),
            ],
            "schema": {},
        },
    }

    issues = evaluate_entity_rules(staged_entities)

    assert ("Building Locations", "sample.xlsx", 2) in issues
    assert any("Assigned device count exceeds # Elevators" in reason for _, reason in issues[("Building Locations", "sample.xlsx", 2)])
