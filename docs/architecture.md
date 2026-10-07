# Architecture and decisions

The business workflow is an asset-management review: consolidate operator files, surface lease and operating exposure, assemble an evidence brief, and assign a next step. A potential deployment should measure review completion time, corrections per import, source coverage, reviewer acceptance, and repeat usage against an observed baseline. The demo records activity and explicit usefulness feedback; it does not invent adoption or time savings.

## Structured data and SQL

A workbook or three-file CSV archive becomes a normalized, immutable dataset. Explicit operator aliases map to canonical asset IDs. Annual rent is normalized from monthly or annual input. USD values are stored as integer cents. The complete payload and validation report are retained, including rejected rows' sheet and row positions.

Publication runs in a SQLite `BEGIN IMMEDIATE` transaction. The reviewer must differ from the importer, the expected active snapshot must still match, and every validation error must be corrected. Relational inserts and the active-snapshot pointer commit together. Reads join against exactly that pointer, so historical versions cannot double count an asset. Restoration selects a previously published version with the same optimistic concurrency rule.

`analytics.py` contains the purpose-built SQL: aggregate operating accounts and active leases separately, then join those aggregates to asset assumptions. This avoids multiplying statement rows by lease rows. Model output never becomes SQL. A read transaction gives each metric and its source lineage a consistent snapshot.

## Documents and RAG

PDF text extraction preserves page numbers; text documents have one page. Source bytes are hashed, extracted pages are retained, and bounded overlapping chunks receive document, version and page identifiers. Uploading the same exact title creates a new revision and retires the predecessor. Scans without extractable text are rejected with an OCR instruction.

The tenant, property and current role determine the corpus before BM25 statistics are calculated. A revoked document cannot contribute to scoring. Retrieval is intentionally lexical: it can miss synonyms and is not a semantic retrieval claim. The separate Evidence Workbench project explores embeddings and retrieval benchmarks.

## Review brief lifecycle

Read-only context assembly invokes three fixed tools: portfolio metrics with source rows, authorized document retrieval, and a historical public-market snapshot. The optional local model receives those results and the review question as untrusted context. It returns a constrained narrative with citation identifiers and verbatim quotes.

Server checks cover schema shape, citation membership, and quote membership. They do not prove semantic entailment. Model prose is displayed separately from computed figures and exact source passages. The generation step has no action tools and no ability to alter database state. Provider errors produce an evidence-only fallback rather than silently manufacturing commentary.

A fingerprint covers the dataset, authorized document chunks and checksums, and the public context. The application checks it again after generation, on read, on export, and before approval. A source change withholds the old body. Reviewer-scoped briefs cannot be read by analysts. A different reviewer must record a decision using the current version; concurrent decisions cannot both succeed.

## Scope of governance

Static API keys map to a tenant, named user, and role. A secret-backed hosted deployment should replace this adapter with organizational identity and lifecycle management. The local demo keys deliberately make role changes visible. They are not suitable for public hosting.

Actions use optimistic versions; feedback is unique per brief and user. The tenant-scoped activity ledger is useful operational history, but a privileged database administrator can alter it. It is not an immutable compliance log.

## Deliberate limits

- One host and one SQLite database. No distributed queue, autoscaling, high-availability database, or enterprise SSO is claimed.
- Uploads are bounded; encrypted/scanned PDFs, OCR, currency conversion, unit-level subleases, break clauses, and arbitrary operator schemas are outside this version.
- Documents are curated by a reviewer. A document's date is prose; there is no automated legal interpretation or contract extraction guarantee.
- Two model drafts can run concurrently per process, with a 60-second provider timeout. Run a single API worker for that admission limit. A terminated process does not resume in-flight generation.
- The fixed synthetic query set measures regression behavior on the shipped fixture, not general real-estate retrieval quality. Real documents and business stakeholders are required to evaluate that.
