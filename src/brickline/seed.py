"""Deterministic, wholly fictional property/operator inputs; no employer information."""

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from .auth import Identity
from .db import connect, initialize
from .evidence import add_document
from .pipeline import HEADERS, months, publish, stage

RESOURCES = Path(__file__).with_name("resources")
AS_OF = "2025-09-30"
PROPERTIES = [
    ("HAR", "Harbor Logistics", "Industrial", "Northern New Jersey", 120000, 0.94, 19, 6.0, 1000000),
    ("CED", "Cedar Exchange", "Office", "Charlotte, NC", 186000, 0.77, 31, 7.5, 2700000),
    ("JUN", "Junction Works", "Industrial", "Columbus, OH", 84000, 0.91, 13, 6.5, 610000),
    ("BEA", "Beacon Distribution", "Industrial", "Dallas, TX", 205000, 0.97, 15, 5.8, 1600000),
    ("ELM", "Elm Commons", "Office", "Raleigh, NC", 92000, 0.82, 26, 7.0, 1200000),
    ("MER", "Meridian Park", "Industrial", "Atlanta, GA", 156000, 0.95, 14, 6.2, 1020000),
]


def tables():
    result = {name: [] for name in HEADERS}
    for ix, (aid, name, sector, location, area, occupancy, psf, cap, debt) in enumerate(PROPERTIES):
        result["Assets"].append(
            [aid, f"operator-{ix + 1}|{name}", name, sector, location, area, debt, area * 0.25, f"{cap}%"]
        )
        occupied = int(area * occupancy)
        areas = [occupied // 6] * 5 + [occupied - 5 * (occupied // 6)]
        for j, leased in enumerate(areas):
            # High concentration of near-term expirations at Cedar and Elm.
            end = "2026-03-31" if j < (3 if sector == "Office" else 1) else f"{2027 + j // 2}-09-30"
            rent = leased * psf
            frequency = "monthly" if j % 2 == 0 else "annual"
            amount = round(rent / 12, 2) if frequency == "monthly" else rent
            result["Leases"].append(
                [
                    f"{aid}-{j + 1:02}",
                    f"operator-{ix + 1}",
                    f"{name.split()[0]} Occupier {j + 1}",
                    leased,
                    amount,
                    frequency,
                    "2022-10-01",
                    end,
                ]
            )
        for k, month in enumerate(months(AS_OF)):
            gross = round(occupied * psf / 12 * (1 + (k - 5) * 0.001), 2)
            costs = {
                "rent": gross,
                "other_income": round(gross * 0.04, 2),
                "tax": round(gross * 0.12, 2),
                "insurance": round(gross * 0.035, 2),
                "utilities": round(gross * (0.07 if sector == "Office" else 0.025), 2),
                "repairs": round(gross * (0.11 if sector == "Office" else 0.045), 2),
                "management": round(gross * 0.04, 2),
                "capex": 210000 if k == 11 and aid == "HAR" else 0,
                "debt_service": round(debt / 12, 2),
                "depreciation": 15000,
            }
            for account, amount in costs.items():
                result["Operating"].append([aid, month, account, amount])
    return result


def workbook(data):
    book = Workbook()
    book.remove(book.active)
    for name, columns in HEADERS.items():
        sheet = book.create_sheet(name)
        sheet.append(columns)
        for row in data[name]:
            sheet.append(row)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="294E40")
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(
                36, max(16, len(str(column[0].value)) + 3)
            )
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def make_examples():
    RESOURCES.mkdir(exist_ok=True)
    data = tables()
    (RESOURCES / "portfolio.xlsx").write_bytes(workbook(data))
    bad = {k: [list(r) for r in rows] for k, rows in data.items()}
    bad["Leases"][0][1] = "UNMAPPED PROPERTY"
    bad["Operating"].pop(0)
    (RESOURCES / "needs-review.xlsx").write_bytes(workbook(bad))
    with zipfile.ZipFile(RESOURCES / "portfolio-csv.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for name in HEADERS:
            out = io.StringIO()
            writer = csv.writer(out)
            writer.writerow(HEADERS[name])
            writer.writerows(data[name])
            z.writestr(name + ".csv", out.getvalue())
    manifest = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in RESOURCES.iterdir()
        if p.suffix in {".xlsx", ".zip"}
    }
    (RESOURCES / "examples-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def seed(path):
    initialize(path)
    with connect(path, write=True) as conn:
        for tenant in ("northline", "other"):
            if conn.execute("SELECT 1 FROM portfolios WHERE tenant=?", (tenant,)).fetchone():
                continue
            author, reviewer = (
                Identity(tenant, "seed-importer", "analyst"),
                Identity(tenant, "seed-reviewer", "reviewer"),
            )
            batch = stage(conn, author, (RESOURCES / "portfolio.xlsx").read_bytes(), "portfolio.xlsx", AS_OF)
            publish(conn, reviewer, batch["id"], None)
            for aid, name, *_ in PROPERTIES:
                docs = {
                    "Renewal notice": (
                        f"{name}. Synthetic lease abstract for {aid}-01. "
                        "The current term ends March 31, 2026. A renewal option requires written notice "
                        "no later than November 30, 2025. The asset manager must confirm receipt with counsel. "
                        "The rent roll states contractual base rent; it is not collected cash. "
                        "This abstract is fictional and is not a binding lease."
                    ),
                    "Capital works": (
                        f"{name}. Synthetic September operating note. The roof replacement estimate is $210,000. "
                        "The proposed project is a capital expenditure and must be reviewed separately from recurring operating expenses. "
                        "An engineering inspection is required before scope approval. Work is provisionally planned for May 2026. "
                        "No vendor has been appointed and no purchase order has been approved."
                    ),
                    "Leasing update": (
                        f"{name}. Synthetic asset-management update dated September 30, 2025. "
                        "The leasing team will contact occupiers with expirations in the next twelve months. "
                        "Rent-free periods and tenant-improvement allowances require separate underwriting. "
                        "The current figures omit those prospective concessions. No assumed renewal is included in the current rent roll."
                    ),
                }
                for suffix, text in docs.items():
                    add_document(conn, reviewer, aid, f"{name} — {suffix}", text.encode(), "note.txt")
                private = f"{name} restricted credit discussion. Internal code VAULT-{aid}-ONLY. Available only to independent reviewers."
                add_document(
                    conn,
                    reviewer,
                    aid,
                    f"{name} — Restricted credit note",
                    private.encode(),
                    "credit.txt",
                    True,
                )
    return path


if __name__ == "__main__":
    make_examples()
