from copy import deepcopy

import pytest

from brickline.analytics import horizon, scenario
from brickline.db import Problem
from brickline.pipeline import months
from brickline.seed import workbook
from test_pipeline import upload


def known_data():
    return {
        "Assets": [["ONE", "external", "Example One", "Industrial", "Fictional", 100, 24000, 1200, 0.06]],
        "Leases": [
            ["L1", "external", "Occupier A", 50, 10000, "annual", "2020-01-01", "2026-03-31"],
            ["L2", "ONE", "Occupier B", 25, 2500, "monthly", "2020-01-01", "2028-09-30"],
            ["OLD", "ONE", "Expired", 25, 50000, "annual", "2020-01-01", "2025-09-29"],
            ["FUTURE", "ONE", "Future", 25, 50000, "annual", "2026-10-01", "2030-09-30"],
        ],
        "Operating": [
            ["ONE", month, account, amount]
            for month in months("2025-09-30")
            for account, amount in {
                "rent": 10000,
                "other_income": 1000,
                "tax": 1000,
                "insurance": 1000,
                "utilities": 1000,
                "repairs": 1000,
                "management": 1000,
                "capex": 999999,
                "debt_service": 2000,
                "depreciation": 15000,
            }.items()
        ],
    }


def test_known_cash_flows_and_lease_boundary_dates(clients):
    a, r = clients["analyst"], clients["reviewer"]
    row = upload(a, workbook(known_data())).json()
    assert row["report"]["valid"]
    active = a.get("/api/portfolio").json()["snapshot"]["id"]
    assert r.post(f"/api/imports/{row['id']}/publish", json={"expected_current": active}).status_code == 200
    m = a.get("/api/assets/ONE").json()["metrics"]
    assert m["noi_cents"] == 7_200_000
    assert m["occupancy"] == 0.75
    assert m["rent_cents"] == 4_000_000
    assert m["expiry_share"] == 0.25
    assert m["dscr"] == 2.95  # (72,000 - 1,200) / 24,000
    assert m["capitalized_noi_cents"] == 120_000_000
    assert m["capex_cents"] == 999999 * 12 * 100  # Present in lineage, excluded from NOI.
    expected = (
        10000
        * (
            (__import__("datetime").date(2026, 3, 31) - __import__("datetime").date(2025, 9, 30)).days
            / 365.25
        )
        + 30000
        * (
            (__import__("datetime").date(2028, 9, 30) - __import__("datetime").date(2025, 9, 30)).days
            / 365.25
        )
    ) / 40000
    assert m["walt_years"] == pytest.approx(expected, abs=1e-6)
    assert horizon("2024-02-29") == "2025-02-28"


def test_scenario_math_and_zero_debt(clients):
    m = clients["analyst"].get("/api/assets/HAR").json()["metrics"]
    s = scenario(m, -10, 20, 100)
    expected = round(m["income_cents"] * 0.9) - round(m["expense_cents"] * 1.2)
    assert s["noi_cents"] == expected
    assert s["cap_rate"] == pytest.approx(m["cap_rate"] + 0.01)
    assert s["capitalized_noi_cents"] < m["capitalized_noi_cents"]
    assert s["dscr"] < m["dscr"]
    debt_free = deepcopy(m)
    debt_free["debt_cents"] = 0
    assert scenario(debt_free, 0, 0, 0)["dscr"] is None
    for arguments in [(float("nan"), 0, 0), (0, 0, -1000), (0, 101, 0)]:
        with pytest.raises(Problem):
            scenario(m, *arguments)


def test_portfolio_ratios_weight_amounts_not_asset_percentages(clients):
    p = clients["analyst"].get("/api/portfolio").json()
    assert p["totals"]["occupancy"] == round(
        sum(a["leased_sf"] for a in p["assets"]) / sum(a["area_sf"] for a in p["assets"]), 6
    )
    assert p["totals"]["dscr"] == round(
        sum(a["noi_cents"] - a["reserve_cents"] for a in p["assets"])
        / sum(a["debt_cents"] for a in p["assets"]),
        6,
    )
    assert p["totals"]["expiry_share"] == round(
        sum(a["expiry_rent_cents"] for a in p["assets"]) / sum(a["rent_cents"] for a in p["assets"]), 6
    )
