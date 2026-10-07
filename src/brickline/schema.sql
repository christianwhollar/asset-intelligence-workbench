PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS datasets (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, as_of TEXT NOT NULL,
 checksum TEXT NOT NULL, actor TEXT NOT NULL, created TEXT NOT NULL,
 status TEXT NOT NULL, report TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(tenant, checksum, as_of)
);
CREATE TABLE IF NOT EXISTS portfolios (
 tenant TEXT PRIMARY KEY, dataset TEXT REFERENCES datasets(id)
);
CREATE TABLE IF NOT EXISTS assets (
 dataset TEXT REFERENCES datasets(id), id TEXT, name TEXT, sector TEXT, market TEXT,
 area_sf INTEGER, debt_cents INTEGER, reserve_cents INTEGER, cap_rate REAL, source_row INTEGER,
 PRIMARY KEY(dataset,id)
);
CREATE TABLE IF NOT EXISTS leases (
 dataset TEXT, id TEXT, asset TEXT, tenant_name TEXT, area_sf INTEGER,
 rent_cents INTEGER, start_date TEXT, end_date TEXT, source_row INTEGER,
 PRIMARY KEY(dataset,id), FOREIGN KEY(dataset,asset) REFERENCES assets(dataset,id)
);
CREATE INDEX IF NOT EXISTS lease_asset ON leases(dataset,asset,end_date);
CREATE TABLE IF NOT EXISTS operating (
 dataset TEXT, asset TEXT, month TEXT, account TEXT, amount_cents INTEGER, source_row INTEGER,
 PRIMARY KEY(dataset,asset,month,account), FOREIGN KEY(dataset,asset) REFERENCES assets(dataset,id)
);
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, tenant TEXT, asset TEXT, title TEXT, version INTEGER,
 restricted INTEGER, revoked INTEGER DEFAULT 0, checksum TEXT, created TEXT, pages TEXT
);
CREATE INDEX IF NOT EXISTS doc_scope ON documents(tenant,asset,revoked);
CREATE TABLE IF NOT EXISTS chunks (
 id TEXT PRIMARY KEY, document TEXT REFERENCES documents(id), page INTEGER, text TEXT
);
CREATE TABLE IF NOT EXISTS briefs (
 id TEXT PRIMARY KEY, tenant TEXT, asset TEXT, actor TEXT, role TEXT, created TEXT,
 fingerprint TEXT, body TEXT, status TEXT DEFAULT 'draft', version INTEGER DEFAULT 1,
 reviewer TEXT, review_note TEXT
);
CREATE TABLE IF NOT EXISTS actions (
 id TEXT PRIMARY KEY, tenant TEXT, asset TEXT, title TEXT, owner TEXT,
 status TEXT DEFAULT 'open', version INTEGER DEFAULT 1, created TEXT, updated TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
 brief TEXT REFERENCES briefs(id), actor TEXT, tenant TEXT, helpful INTEGER, comment TEXT,
 PRIMARY KEY(brief,actor)
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT, actor TEXT, at TEXT, kind TEXT, details TEXT
);
