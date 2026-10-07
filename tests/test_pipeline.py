import io
import zipfile
from copy import deepcopy

import pytest
from openpyxl import load_workbook

from brickline.db import Problem
from brickline.pipeline import read_tables, validate
from brickline.seed import AS_OF, RESOURCES, tables, workbook


def parsed():
    return read_tables((RESOURCES / "portfolio.xlsx").read_bytes(), "portfolio.xlsx")


def upload(client, data=None, name="snapshot.xlsx"):
    data = data or (RESOURCES / "portfolio.xlsx").read_bytes()
    return client.post("/api/imports", files={"file": (name, data)}, data={"as_of": AS_OF})


def test_xlsx_and_csv_have_identical_normalized_records():
    x = validate(parsed(), AS_OF)
    z = validate(read_tables((RESOURCES / "portfolio-csv.zip").read_bytes(), "portfolio.zip"), AS_OF)
    assert x == z
    assert x[1]["valid"]
    assert x[1]["counts"] == {"assets": 6, "leases": 36, "operating": 720}
    raw = parsed()["Leases"][0]
    assert x[0]["leases"][0]["rent_cents"] == round(raw["rent"] * 100) * 12
    assert x[0]["leases"][0]["asset"] == "HAR"


@pytest.mark.parametrize(
    "sheet,index,key,value,message",
    [
        ("Assets", 1, "aliases", "HAR", "ambiguous"),
        ("Assets", 0, "cap_rate", "NaN", "cap rate"),
        ("Assets", 0, "area_sf", "Infinity", "range"),
        ("Leases", 0, "asset_ref", "not-a-property", "Unknown asset"),
        ("Leases", 1, "lease_id", "HAR-01", "Duplicate lease"),
        ("Leases", 0, "rent_frequency", "weekly", "rent_frequency"),
        ("Leases", 0, "rent", "99.999", "whole cents"),
        ("Leases", 0, "rent", "-1", "range"),
        ("Leases", 0, "area_sf", 999999, "exceeds property"),
        ("Leases", 0, "end_date", "2020-01-01", "precedes"),
        ("Operating", 0, "month", "2026-01", "outside"),
        ("Operating", 0, "account", "undocumented-netting", "Unknown account"),
    ],
)
def test_bad_business_data_is_reported_at_a_source_row(sheet, index, key, value, message):
    data = parsed()
    data[sheet][index][key] = value
    _, report = validate(data, AS_OF)
    assert not report["valid"]
    assert any(message in error["message"] for error in report["errors"])
    assert all("sheet" in e and "row" in e for e in report["errors"])


def test_missing_account_and_duplicate_account_do_not_silently_net():
    data = parsed()
    data["Operating"].pop(0)
    data["Operating"].append(deepcopy(data["Operating"][0]))
    report = validate(data, AS_OF)[1]
    assert any("Duplicate" in e["message"] for e in report["errors"])
    assert any("missing accounts rent" in e["message"] for e in report["errors"])


@pytest.mark.parametrize("as_of", ["2025-09-15", "not-a-date", "2099-09-30"])
def test_only_completed_month_ends(as_of):
    with pytest.raises(Problem):
        validate(parsed(), as_of)


def test_formula_cells_are_never_evaluated_or_treated_as_cached_values():
    book = load_workbook(io.BytesIO((RESOURCES / "portfolio.xlsx").read_bytes()))
    book["Assets"]["F2"] = "=100+100"
    stream = io.BytesIO()
    book.save(stream)
    with pytest.raises(Problem, match="Formula"):
        read_tables(stream.getvalue(), "formula.xlsx")


def test_archive_is_bounded_and_unexpected_paths_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("../outside.csv", "hello")
    with pytest.raises(Problem):
        read_tables(stream.getvalue(), "wrong.zip")
    with pytest.raises(Problem):
        read_tables(b"x" * 2_000_001, "big.xlsx")
    with pytest.raises(Problem):
        read_tables(b"broken", "bad.xlsx")


def test_invalid_import_is_staged_without_touching_live_data(clients):
    c = clients["analyst"]
    before = c.get("/api/portfolio").json()
    bad = upload(c, (RESOURCES / "needs-review.xlsx").read_bytes()).json()
    assert not bad["report"]["valid"]
    result = clients["reviewer"].post(
        f"/api/imports/{bad['id']}/publish", json={"expected_current": before["snapshot"]["id"]}
    )
    assert result.status_code == 422
    assert c.get("/api/portfolio").json() == before


def test_publish_requires_an_independent_reviewer_and_expected_snapshot(clients):
    a, r = clients["analyst"], clients["reviewer"]
    before = a.get("/api/portfolio").json()
    data = tables()
    data["Operating"][0][3] += 100
    blob = workbook(data)
    staged = upload(a, blob).json()
    url = f"/api/imports/{staged['id']}/publish"
    assert a.post(url, json={"expected_current": before["snapshot"]["id"]}).status_code == 403
    assert r.post(url, json={"expected_current": "stale"}).status_code == 409
    assert clients["other"].post(url, json={"expected_current": None}).status_code == 403
    assert r.post(url, json={"expected_current": before["snapshot"]["id"]}).status_code == 200
    after = a.get("/api/portfolio").json()
    assert after["totals"]["noi_cents"] == before["totals"]["noi_cents"] + 10000
    assert len(after["assets"]) == 6  # New versions never double count historical records.
    assert upload(a, blob).json()["reused"]  # Byte-identical input is idempotent.
    old = before["snapshot"]["id"]
    assert r.post(f"/api/imports/{old}/publish", json={"expected_current": staged["id"]}).status_code == 200
    assert a.get("/api/portfolio").json()["totals"] == before["totals"]


def test_reviewer_cannot_publish_own_import(clients):
    data = tables()
    data["Assets"][0][2] = "Renamed synthetic property"
    row = upload(clients["reviewer"], workbook(data)).json()
    active = clients["reviewer"].get("/api/portfolio").json()["snapshot"]["id"]
    result = clients["reviewer"].post(f"/api/imports/{row['id']}/publish", json={"expected_current": active})
    assert result.status_code == 403
