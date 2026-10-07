# Import contract

Use the downloadable workbook or ZIP of CSVs from the Data room. A ZIP must contain exactly `Assets.csv`, `Leases.csv`, and `Operating.csv`; nested paths and extra files are rejected. An XLSX must contain exactly the equivalent three sheets. Column order and header spelling are part of the contract.

Uploads are limited to 2 MB compressed, 8 MB expanded, and 6,000 data rows per sheet. A snapshot contains 1–100 assets. Formula cells are rejected; export values first. Amounts are nonnegative USD amounts with at most two decimal places. The parser accepts dollar signs and thousands separators but does not infer currencies. Negative adjustments must be reconciled upstream in this version.

| Sheet | Required columns |
|---|---|
| Assets | `asset_id`, `aliases`, `name`, `sector`, `market`, `area_sf`, `annual_debt_service`, `replacement_reserve`, `cap_rate` |
| Leases | `lease_id`, `asset_ref`, `tenant_name`, `area_sf`, `rent`, `rent_frequency`, `start_date`, `end_date` |
| Operating | `asset_ref`, `month`, `account`, `amount` |

Asset IDs are unique and use letters, digits, hyphens or underscores. `aliases` contains pipe-separated operator identifiers. Matching is case-insensitive; ambiguous aliases reject publication. Property area is positive whole square feet. Debt service and replacement reserves are annual USD amounts. Cap rates accept fractions (`0.06`) or explicit percentages (`6%`), between 0.5% and 30%.

Lease IDs are unique across the snapshot. `rent_frequency` is `monthly` or `annual`. ISO dates describe the current contract; end dates are inclusive. Active leases satisfy `start_date <= as_of <= end_date`. The active area total cannot exceed property area. The parser does not infer leased suites or de-duplicate overlapping subleases; feed owners must reconcile those records.

Operating months use `YYYY-MM`. The snapshot date must be the last day of a completed reporting month. For each property, all twelve months must explicitly contain `rent`, `other_income`, `tax`, `insurance`, `utilities`, `repairs`, and `management`. Enter zero rather than omitting an account. `capex`, `debt_service`, and `depreciation` are optional, retained in lineage, and excluded from NOI. Duplicate property/month/account combinations reject publication rather than silently summing.

An import is a full portfolio snapshot, not a partial upsert. Removed properties disappear from the active portfolio; history remains. Byte-identical files with the same tenant and reporting date reuse their staged import. Publication and restoration require an independent reviewer and the expected active dataset ID.

## Source documents

Reviewer uploads accept PDF, UTF-8 TXT, or Markdown. Limits: 2 MB, 40 PDF pages, and 120,000 extracted characters. A repeated exact title under the same property creates a new revision. Reviewer-only sources are excluded from analysts' retrieval. Current authorization always takes precedence over an old brief or a previously valid citation.
