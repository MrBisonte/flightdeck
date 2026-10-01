"""The contract, the reference dimensions and the SQL must agree.

contracts/flight_log.yml is the source of truth. The enum members are also
committed as reference dimensions under fixtures/reference/, and the caps are
repeated as constants in pipeline/10_typed.sql. Three copies of the same fact
is two chances to drift, so these tests pin them together.
"""
import csv
import json
import pathlib
import re

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = yaml.safe_load((ROOT / "contracts" / "flight_log.yml").read_text(encoding="utf-8"))
TYPED_SQL = (ROOT / "pipeline" / "10_typed.sql").read_text(encoding="utf-8")


def read_reference(name: str, column: str) -> list[str]:
    """One value per member in force. A versioned file also lists closed rows,
    which carry a valid_to, and those are history rather than the domain."""
    path = ROOT / "fixtures" / "reference" / name
    with path.open(encoding="utf-8", newline="") as fh:
        return [row[column] for row in csv.DictReader(fh) if not row.get("valid_to")]


@pytest.mark.parametrize(
    "enum_key, csv_name, csv_column",
    [
        ("state", "app_states.csv", "state"),
        ("mode", "modes.csv", "mode"),
        ("char", "characters.csv", "char"),
        ("boss", "boss_kinds.csv", "boss"),
    ],
)
def test_reference_dimension_matches_contract_enum(enum_key, csv_name, csv_column):
    assert read_reference(csv_name, csv_column) == CONTRACT["enums"][enum_key]


def test_every_reference_origin_carries_a_contract_class():
    """origins.csv is keyed on the origin, so the enum pins the kind column."""
    kinds = set(read_reference("origins.csv", "kind"))
    assert kinds <= set(CONTRACT["enums"]["origin_kind"])


def test_unlisted_is_derived_and_never_a_reference_row():
    """`unlisted` is what the LEFT JOIN produces when no row matches. A row
    claiming it would mean an origin listed as not listed."""
    assert "unlisted" in CONTRACT["enums"]["origin_kind"]
    assert "unlisted" not in set(read_reference("origins.csv", "kind"))


def test_the_typed_layer_fails_closed_on_an_unknown_origin():
    """The deny answer has to be the default, not a case someone remembered."""
    assert "coalesce(o.kind, 'unlisted')" in TYPED_SQL
    assert "coalesce(o.may_publish, false)" in TYPED_SQL


def test_state_enum_has_the_documented_fifteen():
    """The playbook says fifteen app states. If that changes, this must too."""
    assert len(CONTRACT["enums"]["state"]) == 15


def test_span_enum_is_the_six_frame_sections_in_order():
    assert CONTRACT["enums"]["span"] == ["sim", "tiles", "fog", "bodies", "vignette", "hud"]


# Every cap the contract declares, not a list repeated here. A hardcoded list is
# how two caps reached the YAML and never reached the warehouse: the test only
# checked the three it already knew about.
@pytest.mark.parametrize("cap_key", sorted(CONTRACT["caps"]))
def test_sql_rows_match_contract_cap(cap_key):
    """The caps are a table in the warehouse. Every version must equal the YAML,
    dates included, and no version may exist in one place only."""
    in_sql = [
        (int(value), start.replace(" ", "T").replace("+00", "Z"),
         None if end == "NULL" else end.strip("'").replace(" ", "T").replace("+00", "Z"))
        for value, start, end in re.findall(
            rf"\('{cap_key}',\s*(\d+),\s*'([^']+)',\s*(NULL|'[^']+')\)", TYPED_SQL)
    ]
    in_yaml = [(v["value"], v["valid_from"], v.get("valid_to"))
               for v in CONTRACT["caps"][cap_key]]
    assert in_sql, f"{cap_key} is not inserted into contract_caps"
    assert in_sql == in_yaml


@pytest.mark.parametrize("cap_key", sorted(CONTRACT["caps"]))
def test_every_cap_has_one_value_in_force(cap_key):
    """cap() reads the open version. Two would make the check ambiguous, and
    none would make it read NULL, which passes every record."""
    versions = CONTRACT["caps"][cap_key]
    assert sum(1 for v in versions if v.get("valid_to") is None) == 1, versions
    assert versions[-1].get("valid_to") is None, "the open version comes last"


def test_caps_are_a_table_not_session_variables():
    """Session variables do not survive a new connection, so a later layer would
    read NULL and every cap check would silently pass."""
    assert "CREATE OR REPLACE TABLE contract_caps" in TYPED_SQL
    assert "SET variable cap_" not in TYPED_SQL


def numeric_wire_fields() -> set[str]:
    """Every numeric leaf in wire_schema.jsonl, as the units block names it.

    A list element is written `[]` and a frame section under trace.spans is
    written `*`. bool is a subclass of int in Python, so it is excluded first.
    """
    found: set[str] = set()

    def walk(value, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                section = path == "trace.spans"
                walk(child, f"{path}.{'*' if section else key}" if path else key)
        elif isinstance(value, list):
            for child in value:
                walk(child, f"{path}[]")
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            found.add(path)

    schema = ROOT / "contracts" / "wire_schema.jsonl"
    for line in schema.read_text(encoding="utf-8").splitlines():
        if line.strip():
            walk(json.loads(line), "")
    return found


def test_every_numeric_wire_field_has_a_unit():
    """The wire sends bare numbers. A field with no unit in the contract is a
    number nobody can read safely."""
    missing = numeric_wire_fields() - set(CONTRACT["units"])
    assert not missing, sorted(missing)


def test_every_unit_entry_names_a_real_field():
    """A unit for a field the wire never sends is a stale entry."""
    stale = set(CONTRACT["units"]) - numeric_wire_fields()
    assert not stale, sorted(stale)


def test_every_unit_is_defined():
    kinds = set(CONTRACT["unit_kinds"])
    for field, entry in CONTRACT["units"].items():
        assert entry["unit"] in kinds, field
        assert entry["source"].startswith("src/"), field


def test_alarm_classes_in_sql_match_the_contract():
    match = re.search(r"class NOT IN \(([^)]*)\)", TYPED_SQL)
    assert match, "the alarm class check is missing from the typed layer"
    in_sql = sorted(v.strip().strip("'") for v in match.group(1).split(","))
    assert in_sql == sorted(CONTRACT["enums"]["alarm_class"])


def test_every_declared_record_kind_has_required_fields():
    for kind in CONTRACT["record_kinds"]:
        assert kind in CONTRACT["required_fields"], f"{kind} has no required fields"
