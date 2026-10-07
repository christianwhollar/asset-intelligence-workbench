# Financial methods and public data

These conventions define the application; they do not replace a property's accounting policy, loan agreement, or appraisal.

| Metric | Calculation |
|---|---|
| T12 operating income | Sum of `rent` and `other_income` over twelve complete reporting months |
| T12 operating expenses | Sum of `tax`, `insurance`, `utilities`, `repairs`, and `management` over the same months |
| NOI | Operating income minus operating expenses; excludes capital expenditure, depreciation, and debt service |
| Area occupancy | Active leased square feet / gross leasable square feet at the snapshot date |
| 12-month lease exposure | Annual base rent of currently active leases ending by the corresponding date next year / annual base rent of all active leases |
| Weighted lease term | Remaining days / 365.25, weighted by each active lease's annual base rent |
| Reserve-adjusted DSCR | (T12 NOI − declared annual replacement reserve) / annual scheduled principal and interest |
| Capitalized NOI sensitivity | Scenario NOI / explicitly supplied scenario cap rate; suppressed if NOI is not positive |

Portfolio occupancy, exposure and debt coverage are ratios of summed quantities, not averages of asset percentages. Zero debt produces an undefined coverage ratio. The leap-day exposure horizon uses February 28 in the following non-leap year. Currency inputs retain integer-cent precision; scenario changes use decimal arithmetic and round to the nearest cent with half-up rounding.

The scenario applies uniform percentage changes to operating income and expenses while holding debt service and reserves fixed. This intentionally makes the arithmetic inspectable. It does not produce a stabilized NOI forecast, model lease-by-lease renewals, or estimate a property's market value.

The [Federal Reserve's definitions for qualifying CRE loans](https://www.federalreserve.gov/frrs/regulations/section-24414-definitions-applicable-to-qualifying-commercial-loans-commercial-real-estate-loans-and-automobile-loans.htm) describe NOI and reserve-adjusted debt coverage. Our account mapping is narrower and explicit. The [interagency policy statement's valuation discussion](https://www.federalreserve.gov/frrs/guidance/policy-statement-on-prudent-commercial-real-estate-loan-accommodations-and-workouts.htm) distinguishes stabilized income capitalization from troubled or unstabilized property valuation; the UI labels the calculation as a sensitivity.

## Historical market snapshot

`resources/treasury-2025-09.csv` contains September 2025 observations for [DGS10](https://fred.stlouisfed.org/series/DGS10), Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity, Quoted on an Investment Basis. Source: Board of Governors of the Federal Reserve System, distributed through FRED, Federal Reserve Bank of St. Louis. Units are percent, daily, not seasonally adjusted.

`market.json` records the download URL, retrieval time and SHA-256 checksum of the original CSV. The most recent observation at or before the portfolio snapshot is selected; later observations are never inserted into an earlier brief. The shipped September 30, 2025 observation is 4.16%. It is historical context, not current pricing, a property cap rate, or an estimate of borrowing cost. No paid or authenticated API is required.
