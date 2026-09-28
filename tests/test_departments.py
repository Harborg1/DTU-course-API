from app.services.department_service import department_name, resolve_department_codes


def test_dtu_compute_aliases_resolve_to_imported_xml_code():
    for value in (
        "DTU Compute",
        "Compute",
        "Computer Science",
        "Department of Applied Mathematics and Computer Science",
        "01",
    ):
        assert resolve_department_codes(value) == {"1"}


def test_other_department_names_and_unknown_values_are_handled():
    assert resolve_department_codes("DTU Physics") == {"10"}
    assert resolve_department_codes("Department of Physics") == {"10"}
    assert resolve_department_codes("Unlisted research centre") == set()
    assert department_name("1") == (
        "Department of Applied Mathematics and Computer Science"
    )
