import skill_compass


def test_package_import_exposes_version() -> None:
    assert skill_compass.__version__ == "0.1.0"
