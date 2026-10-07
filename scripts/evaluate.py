"""Reproduce the local data, retrieval, concurrency and optional live-model checks."""

import argparse
import asyncio
import json
import sqlite3
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from brickline.api import create_app
from brickline.auth import Identity
from brickline.db import connect
from brickline.evidence import search
from brickline.pipeline import read_tables, validate
from brickline.seed import AS_OF, PROPERTIES, RESOURCES
from brickline.workflow import build_brief

QUESTIONS = [
    ("When must the renewal notice be delivered?", "Renewal notice"),
    ("What is the proposed roof replacement estimate?", "Capital works"),
    ("Has a vendor been appointed for the capital works?", "Capital works"),
    ("How are rent-free periods and tenant-improvement allowances treated?", "Leasing update"),
    ("Which occupiers should the leasing team contact?", "Leasing update"),
]


def evaluate(output, model):
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "evaluation.db"
        app = create_app(path, demo=True)
        a = TestClient(app, headers={"X-API-Key": "demo-analyst"})
        analyst = Identity("northline", "alex", "analyst")
        times, results = [], []
        with connect(path) as conn:
            for aid, name, *_ in PROPERTIES:
                for question, expected in QUESTIONS:
                    start = time.perf_counter()
                    hits = search(conn, analyst, aid, question)
                    elapsed = (time.perf_counter() - start) * 1000
                    times.append(elapsed)
                    titles = [h["title"] for h in hits]
                    results.append(
                        {
                            "asset": aid,
                            "question": question,
                            "expected_title": f"{name} — {expected}",
                            "returned_titles": titles,
                            "milliseconds": elapsed,
                            "hit_at_1": bool(titles and titles[0] == f"{name} — {expected}"),
                            "hit_at_3": f"{name} — {expected}" in titles[:3],
                        }
                    )
        raw = (RESOURCES / "portfolio.xlsx").read_bytes()
        faults = []
        mutations = [
            ("unknown property", lambda d: d["Leases"][0].update(asset_ref="NOT_MAPPED")),
            ("duplicate lease", lambda d: d["Leases"][1].update(lease_id=d["Leases"][0]["lease_id"])),
            ("overallocated area", lambda d: d["Leases"][0].update(area_sf=9999999)),
            ("fractional cents", lambda d: d["Leases"][0].update(rent="12.345")),
            ("missing monthly rent", lambda d: d["Operating"].pop(0)),
            ("unknown account", lambda d: d["Operating"][0].update(account="UNMAPPED")),
            ("ambiguous alias", lambda d: d["Assets"][1].update(aliases="HAR")),
            ("invalid date interval", lambda d: d["Leases"][0].update(end_date="1900-01-01")),
        ]
        for name, change in mutations:
            data = read_tables(raw, "portfolio.xlsx")
            change(data)
            report = validate(data, AS_OF)[1]
            faults.append({"fault": name, "rejected": not report["valid"], "errors": report["error_count"]})
        action = a.post(
            "/api/actions", json={"asset": "HAR", "title": "Verify renewal receipt", "owner": "Asset manager"}
        ).json()

        def update(_):
            return a.patch(
                "/api/actions/" + action["id"],
                json={"version": 1, "status": "in_progress", "owner": "Asset manager"},
            ).status_code

        with ThreadPoolExecutor(max_workers=12) as pool:
            statuses = list(pool.map(update, range(24)))
        with sqlite3.connect(path) as src, sqlite3.connect(Path(directory) / "restored.db") as dest:
            src.backup(dest)
        restored = TestClient(
            create_app(Path(directory) / "restored.db", demo=True), headers={"X-API-Key": "demo-analyst"}
        )
        restoration = restored.get("/api/portfolio").json() == a.get("/api/portfolio").json()
        assert restoration and statuses.count(200) == 1 and all(f["rejected"] for f in faults)
        live = []
        if model:

            async def run():
                for aid, *_ in PROPERTIES:
                    brief = await build_brief(
                        path,
                        analyst,
                        aid,
                        "What renewal notice and capital works need attention?",
                        True,
                        "http://127.0.0.1:11434",
                        model,
                    )
                    live.append(
                        {
                            "asset": aid,
                            "narrative": brief["body"]["narrative"],
                            "citations": [
                                {k: h[k] for k in ("id", "title", "text")} for h in brief["body"]["evidence"]
                            ],
                        }
                    )
                    print(aid, brief["body"]["narrative"]["status"], flush=True)

            asyncio.run(run())
        record = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "protocol": "Fixed synthetic corpus: six properties, five developer-authored question templates per property. "
            "This measures fixture retrieval and application behavior, not independent real-world quality or adoption.",
            "data": {"assets": 6, "leases": 36, "statement_rows": 720, "authorized_documents_per_asset": 3},
            "retrieval": {
                "queries": len(results),
                "hit_at_1": sum(r["hit_at_1"] for r in results) / len(results),
                "hit_at_3": sum(r["hit_at_3"] for r in results) / len(results),
                "p50_ms": statistics.median(times),
            },
            "ingestion_faults": faults,
            "concurrent_updates": {
                "attempts": 24,
                "accepted": statuses.count(200),
                "conflicts": statuses.count(409),
            },
            "backup_restore_equal": restoration,
            "live_model": {
                "model": model or None,
                "calls": len(live),
                "contract_valid": sum(r["narrative"]["status"] == "draft" for r in live),
                "meaning": "Schema, citation membership and exact-quote checks only; not factual-entailment evaluation.",
            },
        }
        (output / "report.json").write_text(json.dumps(record, indent=2) + "\n")
        (output / "retrieval.jsonl").write_text("".join(json.dumps(r) + "\n" for r in results))
        (output / "live-drafts.json").write_text(json.dumps(live, indent=2) + "\n")
        print(json.dumps(record, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("reports/local-study"))
    parser.add_argument("--model", default="")
    args = parser.parse_args()
    evaluate(args.output, args.model)
