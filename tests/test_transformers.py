from data_standardizer.transformers import apply_transformations, normalize_loose_text


def test_normalize_loose_text_handles_case_spacing_and_aliases():
    assert normalize_loose_text(" ACME Corporation 5 ") == "acmecorp5"
    assert normalize_loose_text("Building 3") == normalize_loose_text("bldg 3")


def test_apply_transformations_can_map_country_and_build_full_name():
    record = {
        "First Name": " Ann ",
        "Last Name*": " O'Neil ",
        "Full Name (Auto)": "",
        "Country": "usa",
    }

    transformed, issues = apply_transformations(
        record,
        {
            "Full Name (Auto)": [
                {
                    "name": "concat_fields",
                    "fields": ["First Name", "Last Name*"],
                    "separator": " ",
                    "only_if_blank": True,
                },
                "trim",
                "collapse_whitespace",
            ],
            "Country": [
                {
                    "name": "map_values",
                    "mapping": {"usa": "US", "canada": "CA"},
                }
            ],
        },
    )

    assert issues == []
    assert transformed["Full Name (Auto)"] == "Ann O'Neil"
    assert transformed["Country"] == "US"


def test_apply_transformations_can_realign_shifted_account_address_fields():
    record = {
        "Address 1: City": "",
        "Address 1: State/Province": "Phoenix",
        "Address 1: ZIP/Postal Code": "Arizona",
        "Address 1: Country/Region": "85004",
        "Main Phone": "US",
    }

    transformed, issues = apply_transformations(
        record,
        {
            "Address 1: City": [
                {
                    "name": "repair_misaligned_address_component",
                    "component": "city",
                }
            ],
            "Address 1: State/Province": [
                {
                    "name": "repair_misaligned_address_component",
                    "component": "region",
                    "country_field": "Address 1: Country/Region",
                }
            ],
            "Address 1: ZIP/Postal Code": [
                {
                    "name": "repair_misaligned_address_component",
                    "component": "postal_code",
                }
            ],
            "Address 1: Country/Region": [
                {
                    "name": "repair_misaligned_address_component",
                    "component": "country",
                }
            ],
            "Main Phone": [
                {
                    "name": "repair_misaligned_address_component",
                    "component": "phone",
                }
            ],
        },
    )

    assert issues == []
    assert transformed["Address 1: City"] == "Phoenix"
    assert transformed["Address 1: State/Province"] == "AZ"
    assert transformed["Address 1: ZIP/Postal Code"] == "85004"
    assert transformed["Address 1: Country/Region"] == "US"
    assert transformed["Main Phone"] is None


def test_apply_transformations_handles_partial_shifted_zip_without_crashing():
    record = {
        "Address 1: City": "",
        "Address 1: State/Province": "Green Valley",
        "Address 1: ZIP/Postal Code": "AZ",
        "Address 1: Country/Region": "8561",
        "Main Phone": "US",
    }

    transformed, issues = apply_transformations(
        record,
        {
            "Address 1: City": [{"name": "repair_misaligned_address_component", "component": "city"}],
            "Address 1: State/Province": [{"name": "repair_misaligned_address_component", "component": "region"}],
            "Address 1: ZIP/Postal Code": [{"name": "repair_misaligned_address_component", "component": "postal_code"}],
            "Address 1: Country/Region": [{"name": "repair_misaligned_address_component", "component": "country"}],
            "Main Phone": [{"name": "repair_misaligned_address_component", "component": "phone"}],
        },
    )

    assert issues == []
    assert transformed["Address 1: City"] == "Green Valley"
    assert transformed["Address 1: State/Province"] == "AZ"
    assert transformed["Address 1: Country/Region"] == "US"
    assert transformed["Main Phone"] is None


def test_apply_transformations_can_extract_city_state_zip_from_third_address_line():
    record = {
        "Address 1: Street 3": "Huachuca City, AZ 85616",
        "Address 1: City": "",
        "Address 1: State/Province": "",
        "Address 1: ZIP/Postal Code": "",
        "Address 1: Country/Region": "",
        "Main Phone": "",
    }

    transformed, issues = apply_transformations(
        record,
        {
            "Address 1: City": [{"name": "repair_misaligned_address_component", "component": "city"}],
            "Address 1: State/Province": [{"name": "repair_misaligned_address_component", "component": "region"}],
            "Address 1: ZIP/Postal Code": [{"name": "repair_misaligned_address_component", "component": "postal_code"}],
            "Address 1: Country/Region": [{"name": "repair_misaligned_address_component", "component": "country"}],
        },
    )

    assert issues == []
    assert transformed["Address 1: City"] == "Huachuca City"
    assert transformed["Address 1: State/Province"] == "AZ"
    assert transformed["Address 1: ZIP/Postal Code"] == "85616"
    assert transformed["Address 1: Country/Region"] == "US"
