"""Validate the approved national backfill configuration and scope expansion."""

from pathlib import Path

from skill_compass.collection.search_scopes import (
    build_full_scope_actor_input,
    build_search_scopes,
    load_search_scope_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "profiles/data_analytics/search_scopes.yaml"

EXPECTED_LOCATIONS = {
    "NT": "Northern Territory NT",
    "NSW": "New South Wales NSW",
    "VIC": "Victoria VIC",
    "QLD": "Queensland QLD",
    "WA": "Western Australia WA",
    "SA": "South Australia SA",
    "ACT": "Australian Capital Territory ACT",
    "TAS": "Tasmania TAS",
}

EXPECTED_CLASSIFICATIONS = {
    "Accounting": "1200",
    "Administration & Office Support": "6251",
    "Advertising, Arts & Media": "6304",
    "Banking & Financial Services": "1203",
    "Call Centre & Customer Service": "1204",
    "CEO & General Management": "7019",
    "Community Services & Development": "6163",
    "Construction": "1206",
    "Consulting & Strategy": "6076",
    "Design & Architecture": "6263",
    "Education & Training": "6123",
    "Engineering": "1209",
    "Farming, Animals & Conservation": "6205",
    "Government & Defence": "1210",
    "Healthcare & Medical": "1211",
    "Hospitality & Tourism": "1212",
    "Human Resources & Recruitment": "6317",
    "Information & Communication Technology": "6281",
    "Insurance & Superannuation": "1214",
    "Legal": "1216",
    "Manufacturing, Transport & Logistics": "6092",
    "Marketing & Communications": "6008",
    "Mining, Resources & Energy": "6058",
    "Real Estate & Property": "1220",
    "Retail & Consumer Products": "6043",
    "Sales": "6362",
    "Science & Technology": "1223",
    "Self Employment": "6261",
    "Sport & Recreation": "6246",
    "Trades & Services": "1225",
}


def test_exact_locations_and_partition_strategy() -> None:
    config = load_search_scope_config(CONFIG_PATH)

    assert config.locations == EXPECTED_LOCATIONS
    assert config.simple_state_scopes == ("NT", "QLD", "WA", "SA", "ACT", "TAS")
    assert "NSW" not in config.simple_state_scopes
    assert "VIC" not in config.simple_state_scopes
    assert config.partitioned_states == ("NSW", "VIC")


def test_exact_classification_baseline() -> None:
    config = load_search_scope_config(CONFIG_PATH)

    configured = {
        item.classification_name: item.classification_id
        for item in config.classifications
    }
    assert len(config.classifications) == 30
    assert configured == EXPECTED_CLASSIFICATIONS


def test_scope_count_is_derived_as_six_plus_two_times_thirty() -> None:
    config = load_search_scope_config(CONFIG_PATH)
    scopes = build_search_scopes(config)

    nsw_scopes = [scope for scope in scopes if scope.state_code == "NSW"]
    vic_scopes = [scope for scope in scopes if scope.state_code == "VIC"]
    state_scopes = [scope for scope in scopes if scope.classification_id is None]
    assert len(state_scopes) == 6
    assert len(nsw_scopes) == 30
    assert len(vic_scopes) == 30
    assert config.expected_scope_count == 6 + (30 * 2)
    assert len(scopes) == config.expected_scope_count == 66


def test_scope_ids_are_stable_unique_and_filename_safe() -> None:
    config = load_search_scope_config(CONFIG_PATH)
    scopes = build_search_scopes(config)
    by_classification = {
        (scope.state_code, scope.classification_name): scope.scope_id
        for scope in scopes
        if scope.classification_name is not None
    }

    assert [scope.scope_id for scope in scopes[:6]] == [
        "nt_state",
        "qld_state",
        "wa_state",
        "sa_state",
        "act_state",
        "tas_state",
    ]
    assert by_classification[("NSW", "Accounting")] == "nsw_accounting"
    assert (
        by_classification[("NSW", "Information & Communication Technology")]
        == "nsw_information_communication_technology"
    )
    assert (
        by_classification[("VIC", "Science & Technology")] == "vic_science_technology"
    )
    assert len({scope.scope_id for scope in scopes}) == 66


def test_full_actor_inputs_use_verified_fields_and_no_500_item_limit() -> None:
    config = load_search_scope_config(CONFIG_PATH)
    scopes = build_search_scopes(config)
    state_input = build_full_scope_actor_input(config=config, scope=scopes[0])
    classification_input = build_full_scope_actor_input(config=config, scope=scopes[6])

    assert state_input == {
        "alertOnNewJob": False,
        "country": "AU",
        "diagnose": False,
        "fetchDescriptions": True,
        "keywords": "Data Analyst",
        "location": "Northern Territory NT",
        "maxItems": 0,
        "monitorMode": False,
    }
    assert classification_input["location"] == "New South Wales NSW"
    assert classification_input["classification"] == "1200"
    assert classification_input["maxItems"] == 0
