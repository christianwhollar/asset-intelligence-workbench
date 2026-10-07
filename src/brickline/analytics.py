"""SQL-derived operating metrics. Monetary sums remain integer USD cents."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from .db import Problem, current

# Purpose-built SQL: the model and caller never supply SQL fragments.
PORTFOLIO_SQL = """
WITH cash AS (
 SELECT asset,
 SUM(CASE WHEN account IN ('rent','other_income') THEN amount_cents ELSE 0 END) income_cents,
 SUM(CASE WHEN account IN ('tax','insurance','utilities','repairs','management') THEN amount_cents ELSE 0 END) expense_cents,
 SUM(CASE WHEN account='capex' THEN amount_cents ELSE 0 END) capex_cents
 FROM operating WHERE dataset=:dataset GROUP BY asset
), roll AS (
 SELECT asset, SUM(area_sf) leased_sf, SUM(rent_cents) rent_cents,
 SUM(CASE WHEN end_date<=:horizon THEN rent_cents ELSE 0 END) expiry_rent_cents,
 SUM(rent_cents * (julianday(end_date)-julianday(:as_of))/365.25) weighted_term
 FROM leases WHERE dataset=:dataset AND start_date<=:as_of AND end_date>=:as_of GROUP BY asset
)
SELECT a.*,c.income_cents,c.expense_cents,c.capex_cents,
 COALESCE(r.leased_sf,0) leased_sf,COALESCE(r.rent_cents,0) rent_cents,
 COALESCE(r.expiry_rent_cents,0) expiry_rent_cents,COALESCE(r.weighted_term,0) weighted_term
FROM assets a JOIN cash c ON a.id=c.asset LEFT JOIN roll r ON a.id=r.asset
WHERE a.dataset=:dataset ORDER BY a.name
"""


def horizon(as_of):
    d = date.fromisoformat(as_of)
    try:
        return d.replace(year=d.year + 1).isoformat()
    except ValueError:
        return (d.replace(day=28, year=d.year + 1)).isoformat()


def ratio(num, den):
    return round(num / den, 6) if den else None


def metrics(conn, who, asset=None):
    snapshot = current(conn, who.tenant)
    params = {"dataset": snapshot["id"], "as_of": snapshot["as_of"], "horizon": horizon(snapshot["as_of"])}
    rows = []
    for record in conn.execute(PORTFOLIO_SQL, params):
        r = dict(record)
        r["noi_cents"] = r["income_cents"] - r["expense_cents"]
        r["occupancy"] = ratio(r["leased_sf"], r["area_sf"])
        r["expiry_share"] = ratio(r["expiry_rent_cents"], r["rent_cents"])
        r["walt_years"] = ratio(r.pop("weighted_term"), r["rent_cents"])
        r["dscr"] = ratio(r["noi_cents"] - r["reserve_cents"], r["debt_cents"])
        r["capitalized_noi_cents"] = round(r["noi_cents"] / r["cap_rate"]) if r["noi_cents"] > 0 else None
        r["attention"] = []
        if r["occupancy"] < 0.85:
            r["attention"].append("Occupancy below 85%")
        if (r["expiry_share"] or 0) > 0.25:
            r["attention"].append("Over 25% of base rent expires within 12 months")
        if r["dscr"] is not None and r["dscr"] < 1.25:
            r["attention"].append("Illustrative reserve-adjusted DSCR below 1.25x")
        rows.append(r)
    totals = {
        key: sum(r[key] for r in rows)
        for key in (
            "area_sf",
            "leased_sf",
            "income_cents",
            "expense_cents",
            "noi_cents",
            "rent_cents",
            "expiry_rent_cents",
            "debt_cents",
            "reserve_cents",
        )
    }
    totals["occupancy"] = ratio(totals["leased_sf"], totals["area_sf"])
    totals["dscr"] = ratio(totals["noi_cents"] - totals["reserve_cents"], totals["debt_cents"])
    totals["expiry_share"] = ratio(totals["expiry_rent_cents"], totals["rent_cents"])
    totals["attention_count"] = sum(bool(r["attention"]) for r in rows)
    if asset:
        result = next((r for r in rows if r["id"] == asset), None)
        if result is None:
            raise Problem("Asset not found", 404)
        return dict(result, as_of=snapshot["as_of"])
    return {"snapshot": snapshot, "assets": rows, "totals": totals}


def detail(conn, who, asset):
    m = metrics(conn, who, asset)
    ds = m["dataset"]
    leases = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM leases WHERE dataset=? AND asset=? ORDER BY end_date,id", (ds, asset)
        )
    ]
    for lease in leases:
        lease["active"] = lease["start_date"] <= m["as_of"] <= lease["end_date"]
    operating = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM operating WHERE dataset=? AND asset=? ORDER BY month,account", (ds, asset)
        )
    ]
    monthly = [
        dict(r)
        for r in conn.execute(
            """
        SELECT month,SUM(CASE WHEN account IN ('rent','other_income') THEN amount_cents
        WHEN account IN ('tax','insurance','utilities','repairs','management') THEN -amount_cents ELSE 0 END) noi_cents
        FROM operating WHERE dataset=? AND asset=? GROUP BY month ORDER BY month""",
            (ds, asset),
        )
    ]
    return {"metrics": m, "leases": leases, "operating": operating, "monthly": monthly}


def scenario(base, income_change, expense_change, cap_shift_bps):
    values = [Decimal(str(x)) for x in (income_change, expense_change, cap_shift_bps)]
    if not all(x.is_finite() for x in values):
        raise Problem("Scenario inputs must be finite")
    income_delta, expense_delta, shift = values
    if not -50 <= income_delta <= 50 or not -50 <= expense_delta <= 100 or not -300 <= shift <= 500:
        raise Problem("Scenario exceeds supported ranges")
    cap = Decimal(str(base["cap_rate"])) + shift / 10000
    if cap <= Decimal(".005"):
        raise Problem("Scenario cap rate must exceed 0.5%")

    def scaled(amount, pct):
        return int((Decimal(amount) * (1 + pct / 100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    income = scaled(base["income_cents"], income_delta)
    expense = scaled(base["expense_cents"], expense_delta)
    noi = income - expense
    value = int((Decimal(noi) / cap).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if noi > 0 else None
    grid = []
    for offset in (-50, 0, 50):
        cr = cap + Decimal(offset) / 10000
        grid.append(
            {
                "cap_rate": float(cr),
                "capitalized_noi_cents": round(noi / float(cr)) if noi > 0 and cr > 0 else None,
            }
        )
    return {
        "income_cents": income,
        "expense_cents": expense,
        "noi_cents": noi,
        "delta_noi_cents": noi - base["noi_cents"],
        "cap_rate": float(cap),
        "dscr": ratio(noi - base["reserve_cents"], base["debt_cents"]),
        "capitalized_noi_cents": value,
        "sensitivity": grid,
        "assumptions": {
            "income_change_pct": float(income_delta),
            "expense_change_pct": float(expense_delta),
            "cap_shift_bps": float(shift),
        },
        "method": "Uniform changes to trailing operating income and expenses; fixed reserve and debt service. "
        "Capitalized NOI is an illustrative sensitivity, not a stabilized forecast or appraisal.",
    }
