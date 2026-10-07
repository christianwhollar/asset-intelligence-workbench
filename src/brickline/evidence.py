"""Authorization precedes corpus construction, scoring, and citation lookup."""

import hashlib
import io
import math
import re
import uuid
from collections import Counter

from pypdf import PdfReader

from .analytics import metrics
from .db import Problem, audit, now, packed


def pages_from(data, filename):
    if len(data) > 2_000_000:
        raise Problem("Document exceeds 2 MB")
    try:
        if filename.lower().endswith(".pdf"):
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or len(reader.pages) > 40:
                raise Problem("Use an unencrypted PDF with at most 40 pages")
            pages = [p.extract_text() or "" for p in reader.pages]
        elif filename.lower().endswith((".txt", ".md")):
            pages = [data.decode("utf-8")]
        else:
            raise Problem("Use PDF, TXT, or Markdown documents")
        if sum(map(len, pages)) > 120_000:
            raise Problem("Extracted text exceeds 120,000 characters")
        if len("".join(pages).strip()) < 20:
            raise Problem("No usable text. Scanned PDFs require OCR before upload.")
        return pages
    except Problem:
        raise
    except Exception as exc:
        raise Problem("Document text extraction failed") from exc


def add_document(conn, who, asset, title, data, filename, restricted=False):
    metrics(conn, who, asset)
    pages = pages_from(data, filename)
    checksum = hashlib.sha256(data).hexdigest()
    previous = (
        conn.execute(
            "SELECT MAX(version) FROM documents WHERE tenant=? AND asset=? AND title=?",
            (who.tenant, asset, title),
        ).fetchone()[0]
        or 0
    )
    ident = uuid.uuid4().hex
    # Revisions with the same exact title supersede their predecessors.
    conn.execute(
        "UPDATE documents SET revoked=1 WHERE tenant=? AND asset=? AND title=?", (who.tenant, asset, title)
    )
    conn.execute(
        "INSERT INTO documents VALUES(?,?,?,?,?,?,0,?,?,?)",
        (ident, who.tenant, asset, title, previous + 1, int(restricted), checksum, now(), packed(pages)),
    )
    chunks = 0
    for page_no, page in enumerate(pages, 1):
        clean = re.sub(r"\s+", " ", page).strip()
        for start in range(0, len(clean), 650):
            text = clean[start : start + 800]
            cid = f"{ident}:p{page_no}:c{chunks + 1}"
            conn.execute("INSERT INTO chunks VALUES(?,?,?,?)", (cid, ident, page_no, text))
            chunks += 1
    audit(
        conn,
        who,
        "document.added",
        {"id": ident, "asset": asset, "version": previous + 1, "checksum": checksum},
    )
    return {"id": ident, "version": previous + 1, "pages": len(pages), "chunks": chunks}


def corpus(conn, who, asset):
    metrics(conn, who, asset)
    rows = conn.execute(
        """SELECT c.id,c.document,c.page,c.text,d.title,d.version,d.checksum
       FROM chunks c JOIN documents d ON c.document=d.id
       WHERE d.tenant=? AND d.asset=? AND d.revoked=0 AND (d.restricted=0 OR ?='reviewer')
       ORDER BY d.title,d.version,c.page,c.id""",
        (who.tenant, asset, who.role),
    ).fetchall()
    return [dict(r) for r in rows]


def document_list(conn, who, asset):
    metrics(conn, who, asset)
    return [
        dict(r)
        for r in conn.execute(
            """SELECT id,title,version,restricted,checksum,created
        FROM documents WHERE tenant=? AND asset=? AND revoked=0 AND (restricted=0 OR ?='reviewer')
        ORDER BY title""",
            (who.tenant, asset, who.role),
        )
    ]


def revoke(conn, who, ident):
    if who.role != "reviewer":
        raise Problem("Reviewer required", 403)
    row = conn.execute("SELECT id FROM documents WHERE id=? AND tenant=?", (ident, who.tenant)).fetchone()
    if not row:
        raise Problem("Document not found", 404)
    conn.execute("UPDATE documents SET revoked=1 WHERE id=?", (ident,))
    audit(conn, who, "document.revoked", {"id": ident})


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def search(conn, who, asset, query, limit=5):
    documents = corpus(conn, who, asset)
    query_tokens = set(tokens(query))
    if not query_tokens or not documents:
        return []
    bags = [Counter(tokens(d["text"])) for d in documents]
    avg = sum(sum(b.values()) for b in bags) / len(bags)
    frequency = Counter(t for b in bags for t in b)
    result = []
    for d, bag in zip(documents, bags):
        size = sum(bag.values())
        score = 0.0
        for t in query_tokens:
            n = bag[t]
            if n:
                idf = math.log(1 + (len(bags) - frequency[t] + 0.5) / (frequency[t] + 0.5))
                score += idf * n * 2.2 / (n + 1.2 * (0.25 + 0.75 * size / max(avg, 1)))
        if score > 0:
            result.append(dict(d, score=round(score, 6)))
    return sorted(result, key=lambda r: (-r["score"], r["id"]))[:limit]
