from data_standardizer.validators import (
    validate_cross_field_rules,
    validate_field,
    validate_relationship_rules,
)


def test_validate_field_flags_bad_formats_and_placeholders():
    email_issues = validate_field("Email", "user@@example.com", {"type": "string", "format": "email"})
    phone_issues = validate_field("Business Phone", "(555)1234", {"type": "string", "format": "phone"})
    blank_placeholder_issues = validate_field("Fax", "--", {"type": "string", "format": "phone"})
    postal_issues = validate_field("Postal / Zip", "123", {"type": "string", "format": "postal_code_us_ca"})
    enum_issues = validate_field("Account Type", "???", {"type": "string", "disallow_values": ["???"]})

    assert any("valid email" in message for _, message in email_issues)
    assert any("valid phone number" in message for _, message in phone_issues)
    assert blank_placeholder_issues == []
    assert any("valid US ZIP or Canadian postal code" in message for _, message in postal_issues)
    assert any("disallowed placeholder" in message for _, message in enum_issues)


def test_cross_field_rules_require_complete_address_and_distinct_parent():
    record = {
        "Account Name*": "Acme Corp",
        "Parent Account": "Acme Corp",
        "Address 1: Street 1": "",
        "Address 1: City": "Boston",
        "Address 1: State/Province": "MA",
        "Address 1: ZIP/Postal Code": "02108",
    }
    rules = [
        {
            "type": "fields_not_equal",
            "fields": ["Account Name*", "Parent Account"],
            "message": "Parent Account cannot reference the same Account Name*.",
        },
        {
            "type": "required_if_any",
            "trigger_fields": [
                "Address 1: Street 1",
                "Address 1: City",
                "Address 1: State/Province",
                "Address 1: ZIP/Postal Code",
            ],
            "required_fields": [
                "Address 1: Street 1",
                "Address 1: City",
                "Address 1: State/Province",
                "Address 1: ZIP/Postal Code",
            ],
            "message": "Address is incomplete.",
        },
    ]

    issues = validate_cross_field_rules(record, rules)

    assert any("Parent Account cannot reference" in message for _, message in issues)
    assert ("Address 1: Street 1", "Address is incomplete.") in issues


def test_validate_field_accepts_full_state_name_for_region_code_by_country():
    issues = validate_field(
        "Address 1: State/Province",
        "Arizona",
        {
            "type": "string",
            "format": "region_code_by_country",
            "country_field": "Address 1: Country/Region",
        },
        {"Address 1: Country/Region": "US"},
    )

    assert issues == []


def test_relationship_rules_offer_similar_values_and_use_normalized_lookup():
    must_exist_rules = [
        {
            "type": "must_exist_in_entity",
            "field": "Account",
            "other_entity": "Accounts",
            "other_field": "Account Name*",
            "message": "Account must exist.",
        }
    ]
    must_exist_issues = validate_relationship_rules(
        {"Account": "sales two"},
        must_exist_rules,
        {("Accounts", "Account Name*"): {"Sales Two"}},
        {
            ("Accounts", "Account Name*"): {
                "Sales Two": [{"data": {"Account Name*": "Sales Two"}, "source_file": "a.xlsx", "row_number": 2}]
            }
        },
    )

    assert any("Similar existing value(s): Sales Two" in message for _, message in must_exist_issues)

    related_field_rules = [
        {
            "type": "related_field_equals",
            "field": "Account",
            "lookup_field": "Building Location",
            "other_entity": "Building Locations",
            "other_lookup_field": "Name*",
            "other_value_field": "Customer (Account - for Invoicing)",
            "message": "Device Account does not match the building account.",
        }
    ]
    related_rows_index = {
        ("Building Locations", "Name*"): {
            "Bldg 3": [
                {
                    "data": {
                        "Name*": "Bldg 3",
                        "Customer (Account - for Invoicing)": "Acme Corp",
                    },
                    "source_file": "b.xlsx",
                    "row_number": 2,
                }
            ]
        }
    }

    related_issues = validate_relationship_rules(
        {"Building Location": "Building 3", "Account": "Acme Corp"},
        related_field_rules,
        {},
        related_rows_index,
    )

    assert related_issues == []
