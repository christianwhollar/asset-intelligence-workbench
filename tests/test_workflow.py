import asyncio
import io
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

from brickline.auth import Identity, authenticate, credentials
from brickline.db import Problem, connect
from brickline.evidence import pages_from
from brickline.workflow import context, generate_narrative, market


def make_brief(client, live=False):
    r = client.post(
        "/api/briefs", json={"asset": "HAR", "question": "renewal notice roof capital works", "live": live}
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_authentication_and_tenant_boundaries(clients):
    assert clients["anonymous"].get("/api/portfolio").status_code == 401
    b = make_brief(clients["analyst"])
    assert clients["other"].get(f"/api/briefs/{b['id']}").status_code == 404
    assert clients["other"].get("/api/briefs").json() == []
    assert clients["other"].get(f"/api/briefs/{b['id']}/memo").status_code == 404
    assert clients["analyst"].get("/api/assets/UNKNOWN").status_code == 404
    assert all("VAULT" not in e["text"] for e in b["body"]["evidence"])
    assert clients["analyst"].get("/api/assets/HAR/search", params={"q": "VAULT"}).json() == []
    assert clients["reviewer"].get("/api/assets/HAR/search", params={"q": "VAULT"}).json()


def test_production_credentials_fail_closed(monkeypatch):
    monkeypatch.delenv("BRICKLINE_KEYS_JSON", raising=False)
    with pytest.raises(RuntimeError):
        credentials(False)
    monkeypatch.setenv(
        "BRICKLINE_KEYS_JSON", json.dumps({"short": {"tenant": "x", "user": "a", "role": "reviewer"}})
    )
    with pytest.raises(RuntimeError):
        credentials(False)
    key = "not-a-real-key-for-test-1234567890"
    monkeypatch.setenv(
        "BRICKLINE_KEYS_JSON", json.dumps({key: {"tenant": "x", "user": "a", "role": "analyst"}})
    )
    assert authenticate(credentials(False), key).user == "a"
    with pytest.raises(Problem):
        authenticate(credentials(False), "demo-analyst")


def test_document_access_is_filtered_before_retrieval(clients):
    a, r = clients["analyst"], clients["reviewer"]
    assert len(a.get("/api/assets/HAR/documents").json()) == 3
    docs = r.get("/api/assets/HAR/documents").json()
    private = next(d for d in docs if d["restricted"])
    assert len(docs) == 4
    assert a.delete("/api/documents/" + private["id"]).status_code == 403
    assert clients["other"].delete("/api/documents/" + private["id"]).status_code == 403


def test_document_revocation_redacts_old_brief_and_blocks_review_and_export(clients):
    a, r = clients["analyst"], clients["reviewer"]
    b = make_brief(a)
    ident = b["id"]
    doc = b["body"]["evidence"][0]["document"]
    assert r.delete("/api/documents/" + doc).status_code == 200
    read = a.get("/api/briefs/" + ident).json()
    assert read["stale"] and read["body"] is None
    assert a.get(f"/api/briefs/{ident}/memo").status_code == 409
    assert (
        r.post(
            f"/api/briefs/{ident}/review",
            json={"version": 1, "decision": "approved", "note": "Checked the evidence."},
        ).status_code
        == 409
    )
    assert doc not in str(a.get("/api/assets/HAR/search", params={"q": "renewal roof"}).json())


def test_revision_retires_previous_passages(clients):
    a, r = clients["analyst"], clients["reviewer"]
    b = make_brief(a)
    title = b["body"]["evidence"][0]["title"]
    uploaded = r.post(
        "/api/assets/HAR/documents",
        files={"file": ("update.txt", b"Updated renewal notice: deadline moved to October 31, 2025.")},
        data={"title": title},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["version"] == 2
    assert a.get("/api/briefs/" + b["id"]).json()["stale"]
    docs = a.get("/api/assets/HAR/documents").json()
    assert len([d for d in docs if d["title"] == title]) == 1


def test_reviewer_scoped_briefs_never_leak_to_analysts(clients):
    b = make_brief(clients["reviewer"])
    assert clients["analyst"].get("/api/briefs/" + b["id"]).status_code == 403
    assert clients["analyst"].get("/api/briefs").json() == []
    assert clients["analyst"].get("/api/briefs/" + b["id"] + "/memo").status_code == 403


def test_independent_review_and_racing_updates(clients):
    a, r = clients["analyst"], clients["reviewer"]
    b = make_brief(a)
    url = "/api/briefs/" + b["id"] + "/review"
    decision = {"version": 1, "decision": "approved", "note": "Verified the records and passages."}
    assert a.post(url, json=decision).status_code == 403
    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = list(pool.map(lambda _: r.post(url, json=decision).status_code, range(2)))
    assert sorted(codes) == [200, 409]
    memo = a.get("/api/briefs/" + b["id"] + "/memo")
    assert "APPROVED" in memo.text and "Human" not in memo.text[:20]
    own = make_brief(r)
    assert r.post("/api/briefs/" + own["id"] + "/review", json=decision).status_code == 403


def test_actions_use_optimistic_versions_and_tenant_scope(clients):
    a = clients["analyst"]
    item = a.post(
        "/api/actions", json={"asset": "HAR", "title": "Confirm renewal receipt", "owner": "Asset manager"}
    ).json()
    url = "/api/actions/" + item["id"]
    data = {"version": 1, "status": "in_progress", "owner": "Asset manager"}
    assert clients["other"].patch(url, json=data).status_code == 404
    assert a.patch(url, json=data).status_code == 200
    assert a.patch(url, json=data).status_code == 409
    assert a.get("/api/actions").json()[0]["version"] == 2


def test_feedback_is_idempotent_and_reports_only_observed_usage(clients):
    a = clients["analyst"]
    b = make_brief(a)
    url = "/api/briefs/" + b["id"] + "/feedback"
    assert a.post(url, json={"helpful": True, "comment": "Source rows helped."}).status_code == 200
    assert a.post(url, json={"helpful": False, "comment": "Need more documents."}).status_code == 200
    activity = a.get("/api/activity").json()
    assert activity["feedback"] == {"n": 1, "helpful": 0}
    assert activity["brief_counts"]["draft"] == 1
    assert clients["other"].get("/api/activity").json()["feedback"]["n"] == 0


def test_text_pdf_extraction_and_scan_rejection():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 50 700 Td (Renewal notice is due November 30, 2025.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    data = io.BytesIO()
    writer.write(data)
    assert "November 30" in pages_from(data.getvalue(), "lease.pdf")[0]
    blank = PdfWriter()
    blank.add_blank_page(width=612, height=792)
    data = io.BytesIO()
    blank.write(data)
    with pytest.raises(Problem, match="OCR"):
        pages_from(data.getvalue(), "scan.pdf")


def test_market_snapshot_prevents_future_context():
    assert market("2025-08-31")["observation"] is None
    assert market("2025-09-15")["observation"]["date"] <= "2025-09-15"
    assert market("2025-09-30")["observation"] == {"date": "2025-09-30", "value": 4.16}


@pytest.mark.parametrize("bad", ["unknown_id", "fake_quote", "extra_key"])
def test_live_output_rejects_invalid_citations_and_schema(clients, monkeypatch, bad):
    with connect(clients["path"]) as conn:
        body = context(conn, Identity("northline", "alex", "analyst"), "HAR", "renewal notice")
    hit = body["evidence"][0]
    reply = {
        "summary": "Review renewal notice.",
        "observations": [
            {"text": "Confirm the deadline.", "evidence_id": hit["id"], "quote": hit["text"][:50]}
        ],
    }
    if bad == "unknown_id":
        reply["observations"][0]["evidence_id"] = "invented"
    if bad == "fake_quote":
        reply["observations"][0]["quote"] = "a made-up quote that does not exist"
    if bad == "extra_key":
        reply["execute_trade"] = True

    async def fake_post(self, url, **kwargs):
        return httpx.Response(
            200, json={"message": {"content": json.dumps(reply)}}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(ValueError):
        asyncio.run(generate_narrative(body, "http://localhost:11434", "test-model"))


def test_valid_local_model_contract(clients, monkeypatch):
    with connect(clients["path"]) as conn:
        body = context(conn, Identity("northline", "alex", "analyst"), "HAR", "renewal notice")
    hit = body["evidence"][0]
    reply = {
        "summary": "Review renewal notice.",
        "observations": [
            {"text": "Confirm the deadline.", "evidence_id": hit["id"], "quote": hit["text"][:50]}
        ],
    }

    async def fake_post(self, url, **kwargs):
        assert "untrusted" in kwargs["json"]["messages"][0]["content"]
        assert "tools" not in kwargs["json"]  # Generation has no side-effect tools.
        return httpx.Response(
            200,
            json={"message": {"content": json.dumps(reply)}, "eval_count": 42},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    result = asyncio.run(generate_narrative(body, "http://localhost:11434", "test-model"))
    assert result["status"] == "draft" and result["tokens"]["output"] == 42


def test_api_contract_rejects_unknown_fields_and_oversized_requests(clients):
    a = clients["analyst"]
    assert (
        a.post(
            "/api/briefs", json={"asset": "HAR", "question": "renewal notice", "tenant": "other"}
        ).status_code
        == 422
    )
    assert a.post("/api/assets/HAR/scenario", json={"income_change_pct": 51}).status_code == 422
    assert a.post("/api/actions", content=b"x" * 3_000_001).status_code == 413
    assert a.get("/api/portfolio").headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in a.get("/").headers["content-security-policy"]


def test_sources_changed_during_generation_cannot_publish_a_stale_brief(clients, monkeypatch):
    from brickline import workflow
    from brickline.db import audit

    identity = Identity("northline", "alex", "analyst")

    async def change_sources(body, endpoint, model):
        with connect(clients["path"], write=True) as conn:
            conn.execute("UPDATE documents SET revoked=1 WHERE id=?", (body["evidence"][0]["document"],))
            audit(conn, Identity("northline", "jordan", "reviewer"), "document.revoked", {})
        return {"status": "draft", "response": {"summary": "Too late", "observations": []}}

    monkeypatch.setattr(workflow, "generate_narrative", change_sources)
    with pytest.raises(Problem, match="Sources changed"):
        asyncio.run(
            workflow.build_brief(
                clients["path"], identity, "HAR", "renewal notice", True, "http://localhost", "test"
            )
        )
    assert clients["analyst"].get("/api/briefs").json() == []


def test_provider_failure_preserves_evidence_without_model_claims(clients, monkeypatch):
    from brickline import workflow

    async def fail_provider(*args):
        raise httpx.ReadTimeout("provider timed out")

    monkeypatch.setattr(workflow, "generate_narrative", fail_provider)
    result = asyncio.run(
        workflow.build_brief(
            clients["path"],
            Identity("northline", "alex", "analyst"),
            "HAR",
            "renewal notice",
            True,
            "http://localhost",
            "test",
        )
    )
    assert result["body"]["narrative"]["status"] == "rejected"
    assert "response" not in result["body"]["narrative"]
    assert result["body"]["metrics"]["noi_cents"] > 0
    assert result["body"]["evidence"]


def test_snapshot_replacement_invalidates_existing_briefs(clients):
    from brickline.seed import tables, workbook
    from test_pipeline import upload

    a, r = clients["analyst"], clients["reviewer"]
    brief = make_brief(a)
    old = a.get("/api/portfolio").json()["snapshot"]["id"]
    data = tables()
    data["Operating"][0][3] += 100
    staged = upload(a, workbook(data)).json()
    assert (
        r.post("/api/imports/" + staged["id"] + "/publish", json={"expected_current": old}).status_code == 200
    )
    assert a.get("/api/briefs/" + brief["id"]).json()["body"] is None
    assert a.get("/api/briefs/" + brief["id"] + "/memo").status_code == 409


def test_hosted_mode_bootstraps_only_the_authenticated_tenant(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from brickline.api import create_app
    from brickline.seed import AS_OF, RESOURCES

    analyst_key = "test-only-analyst-0000000000000"
    reviewer_key = "test-only-reviewer-000000000000"
    monkeypatch.setenv(
        "BRICKLINE_KEYS_JSON",
        json.dumps(
            {
                analyst_key: {"tenant": "customer", "user": "importer", "role": "analyst"},
                reviewer_key: {"tenant": "customer", "user": "reviewer", "role": "reviewer"},
            }
        ),
    )
    app = create_app(tmp_path / "hosted.db")
    a = TestClient(app, headers={"X-API-Key": analyst_key})
    r = TestClient(app, headers={"X-API-Key": reviewer_key})
    assert a.get("/api/portfolio").status_code == 409
    assert a.get("/api/imports").json() == {"current": None, "imports": []}
    staged = a.post(
        "/api/imports",
        files={"file": ("portfolio.xlsx", (RESOURCES / "portfolio.xlsx").read_bytes())},
        data={"as_of": AS_OF},
    ).json()
    assert (
        r.post("/api/imports/" + staged["id"] + "/publish", json={"expected_current": None}).status_code
        == 200
    )
    assert len(a.get("/api/portfolio").json()["assets"]) == 6
    assert a.get("/api/assets/HAR/documents").json() == []
    assert TestClient(app, headers={"X-API-Key": "demo-analyst"}).get("/api/portfolio").status_code == 401
