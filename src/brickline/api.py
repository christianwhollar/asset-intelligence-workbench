import asyncio
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, Header, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from . import analytics, evidence, pipeline, workflow
from .auth import authenticate, credentials
from .db import Problem, audit, connect, initialize, now

ROOT = Path(__file__).parent


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Publish(Strict):
    expected_current: str | None = None


class Scenario(Strict):
    income_change_pct: float = Field(default=0, ge=-50, le=50)
    expense_change_pct: float = Field(default=0, ge=-50, le=100)
    cap_shift_bps: float = Field(default=0, ge=-300, le=500)


class BriefInput(Strict):
    asset: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=3, max_length=500)
    live: bool = False


class Review(Strict):
    version: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=5, max_length=1000)


class Action(Strict):
    asset: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=5, max_length=250)
    owner: str = Field(min_length=1, max_length=100)


class ActionUpdate(Strict):
    version: int = Field(ge=1)
    status: Literal["open", "in_progress", "closed"]
    owner: str = Field(min_length=1, max_length=100)


class Feedback(Strict):
    helpful: bool
    comment: str = Field(default="", max_length=500)


def create_app(path=None, demo=False, model=None):
    path = path or os.environ.get("BRICKLINE_DB", "runtime/brickline.db")
    keys = credentials(demo)
    model = model or os.environ.get("BRICKLINE_MODEL", "")
    endpoint = os.environ.get("BRICKLINE_OLLAMA_URL", "http://127.0.0.1:11434")
    initialize(path)
    if demo:
        from .seed import seed

        seed(path)
    semaphore = asyncio.Semaphore(2)

    @asynccontextmanager
    async def lifespan(app):
        yield

    app = FastAPI(
        title="Brickline Asset Intelligence",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.path = path

    @app.exception_handler(Problem)
    async def issue(request, exc):
        return JSONResponse({"detail": exc.message}, status_code=exc.status)

    @app.exception_handler(sqlite3.OperationalError)
    async def database_busy(request, exc):
        return JSONResponse(
            {"detail": "Database temporarily unavailable; retry the request."}, status_code=503
        )

    @app.middleware("http")
    async def security(request, call_next):
        start = time.perf_counter()
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > 3_000_000):
            return JSONResponse({"detail": "Request exceeds 3 MB"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["Server-Timing"] = f"app;dur={(time.perf_counter() - start) * 1000:.1f}"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def who(x_api_key: str | None = Header(default=None)):
        return authenticate(keys, x_api_key)

    async def bounded(file):
        data = await file.read(pipeline.LIMIT + 1)
        await file.close()
        if len(data) > pipeline.LIMIT:
            raise Problem("Upload exceeds 2 MB", 413)
        return data

    @app.get("/health")
    def health():
        with connect(path) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok"}

    @app.get("/api/session")
    def session(identity=Depends(who)):
        return {
            "tenant": identity.tenant,
            "user": identity.user,
            "role": identity.role,
            "demo": demo,
            "model": model or None,
        }

    @app.get("/api/portfolio")
    def portfolio(identity=Depends(who)):
        with connect(path) as conn:
            return analytics.metrics(conn, identity)

    @app.get("/api/assets/{asset}")
    def asset_detail(asset: str, identity=Depends(who)):
        with connect(path) as conn:
            return analytics.detail(conn, identity, asset)

    @app.post("/api/assets/{asset}/scenario")
    def scenario(asset: str, body: Scenario, identity=Depends(who)):
        with connect(path) as conn:
            base = analytics.metrics(conn, identity, asset)
        return analytics.scenario(base, body.income_change_pct, body.expense_change_pct, body.cap_shift_bps)

    @app.get("/api/imports")
    def imports(identity=Depends(who)):
        with connect(path) as conn:
            return pipeline.imports(conn, identity)

    @app.post("/api/imports")
    async def import_data(file: UploadFile = File(), as_of: str = Form(), identity=Depends(who)):
        data = await bounded(file)
        # Parsing is bounded and occurs before a write transaction to avoid holding a DB lock on workbook I/O.
        parsed = await run_in_threadpool(
            lambda: pipeline.validate(pipeline.read_tables(data, file.filename), as_of)
        )
        with connect(path, write=True) as conn:
            return pipeline.stage(conn, identity, data, file.filename, as_of, parsed=parsed)

    @app.post("/api/imports/{ident}/publish")
    def publish(ident: str, body: Publish, identity=Depends(who)):
        with connect(path, write=True) as conn:
            return pipeline.publish(conn, identity, ident, body.expected_current)

    @app.get("/api/examples/{filename}")
    def example(filename: str, identity=Depends(who)):
        if filename not in {"portfolio.xlsx", "needs-review.xlsx", "portfolio-csv.zip"}:
            raise Problem("Example not found", 404)
        return FileResponse(ROOT / "resources" / filename, filename=filename)

    @app.get("/api/assets/{asset}/documents")
    def documents(asset: str, identity=Depends(who)):
        with connect(path) as conn:
            return evidence.document_list(conn, identity, asset)

    @app.post("/api/assets/{asset}/documents")
    async def upload_doc(
        asset: str,
        file: UploadFile = File(),
        title: str = Form(min_length=3, max_length=150),
        restricted: bool = Form(default=False),
        identity=Depends(who),
    ):
        if identity.role != "reviewer":
            raise Problem("Reviewer required to curate source documents", 403)
        data = await bounded(file)
        with connect(path, write=True) as conn:
            return evidence.add_document(conn, identity, asset, title, data, file.filename, restricted)

    @app.delete("/api/documents/{ident}")
    def revoke(ident: str, identity=Depends(who)):
        with connect(path, write=True) as conn:
            evidence.revoke(conn, identity, ident)
        return {"revoked": True}

    @app.get("/api/assets/{asset}/search")
    def search(asset: str, q: str, identity=Depends(who)):
        if not 1 <= len(q) <= 500:
            raise Problem("Search must contain 1–500 characters")
        with connect(path) as conn:
            return evidence.search(conn, identity, asset, q)

    @app.post("/api/briefs")
    async def brief(body: BriefInput, identity=Depends(who)):
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=0.2)
        except TimeoutError as exc:
            raise Problem("Two briefs are already running; retry shortly.", 429) from exc
        try:
            return await workflow.build_brief(
                path, identity, body.asset, body.question, body.live, endpoint, model
            )
        finally:
            semaphore.release()

    @app.get("/api/briefs")
    def briefs(identity=Depends(who)):
        with connect(path) as conn:
            return [
                dict(r)
                for r in conn.execute(
                    """SELECT id,asset,actor,created,status,version FROM briefs
                WHERE tenant=? AND (role='analyst' OR ?='reviewer') ORDER BY created DESC LIMIT 50""",
                    (identity.tenant, identity.role),
                )
            ]

    @app.get("/api/briefs/{ident}")
    def read_brief(ident: str, identity=Depends(who)):
        with connect(path) as conn:
            return workflow.get_brief(conn, identity, ident)

    @app.post("/api/briefs/{ident}/review")
    def review(ident: str, body: Review, identity=Depends(who)):
        with connect(path, write=True) as conn:
            return workflow.review(conn, identity, ident, body.version, body.decision, body.note)

    @app.get("/api/briefs/{ident}/memo")
    def export_memo(ident: str, identity=Depends(who)):
        with connect(path) as conn:
            result = workflow.memo(workflow.get_brief(conn, identity, ident, require_fresh=True))
        return PlainTextResponse(
            result, headers={"Content-Disposition": f'attachment; filename="brief-{ident}.md"'}
        )

    @app.post("/api/briefs/{ident}/feedback")
    def feedback(ident: str, body: Feedback, identity=Depends(who)):
        with connect(path, write=True) as conn:
            workflow.get_brief(conn, identity, ident, require_fresh=True)
            conn.execute(
                "INSERT INTO feedback VALUES(?,?,?,?,?) ON CONFLICT(brief,actor) DO UPDATE SET helpful=excluded.helpful,comment=excluded.comment",
                (ident, identity.user, identity.tenant, int(body.helpful), body.comment),
            )
            audit(conn, identity, "feedback.recorded", {"brief": ident, "helpful": body.helpful})
        return {"saved": True}

    @app.get("/api/actions")
    def actions(identity=Depends(who)):
        with connect(path) as conn:
            return [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM actions WHERE tenant=? ORDER BY created DESC LIMIT 100", (identity.tenant,)
                )
            ]

    @app.post("/api/actions")
    def action(body: Action, identity=Depends(who)):
        with connect(path, write=True) as conn:
            analytics.metrics(conn, identity, body.asset)
            ident, stamp = uuid.uuid4().hex, now()
            conn.execute(
                "INSERT INTO actions VALUES(?,?,?,?,?,'open',1,?,?)",
                (ident, identity.tenant, body.asset, body.title, body.owner, stamp, stamp),
            )
            audit(conn, identity, "action.created", {"id": ident, "asset": body.asset})
        return {"id": ident}

    @app.patch("/api/actions/{ident}")
    def update_action(ident: str, body: ActionUpdate, identity=Depends(who)):
        with connect(path, write=True) as conn:
            r = conn.execute(
                "SELECT * FROM actions WHERE id=? AND tenant=?", (ident, identity.tenant)
            ).fetchone()
            if not r:
                raise Problem("Action not found", 404)
            if r["version"] != body.version:
                raise Problem("Action changed; refresh before updating", 409)
            conn.execute(
                "UPDATE actions SET status=?,owner=?,version=version+1,updated=? WHERE id=?",
                (body.status, body.owner, now(), ident),
            )
            audit(conn, identity, "action.updated", {"id": ident, "status": body.status})
        return {"updated": True}

    @app.get("/api/activity")
    def activity(identity=Depends(who)):
        with connect(path) as conn:
            counts = dict(
                conn.execute(
                    "SELECT status,COUNT(*) FROM briefs WHERE tenant=? GROUP BY status", (identity.tenant,)
                ).fetchall()
            )
            feedback = conn.execute(
                "SELECT COUNT(*) n,SUM(helpful) helpful FROM feedback WHERE tenant=?", (identity.tenant,)
            ).fetchone()
            events = [
                dict(r, details=json.loads(r["details"]))
                for r in conn.execute(
                    "SELECT * FROM events WHERE tenant=? ORDER BY id DESC LIMIT 60", (identity.tenant,)
                )
            ]
        return {"brief_counts": counts, "feedback": dict(feedback), "events": events}

    app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "web" / "index.html")

    return app
