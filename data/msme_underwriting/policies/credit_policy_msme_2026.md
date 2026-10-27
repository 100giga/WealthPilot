# MSME Credit Policy CP-MSME-2026-03 (Effective 1 April 2026)

> Synthetic policy written for the underwriting pilot. It is illustrative and is
> not the policy of any real lender. Supersedes CP-MSME-2024-01.

## Scope
Applies to all credit facilities for Micro, Small and Medium Enterprises
(MSMEs) registered on the Udyam portal: Cash Credit, Term Loan, Equipment
Finance, PMMY Mudra loans and TReDS invoice discounting. Applications are
assessed under the policy in force on the application date.

## Knock-Out Criteria
An application is rejected without further assessment if any of the
following apply:

- KO_PROMOTER_SCORE_BELOW_MIN: key promoter bureau score below 650.
  New-to-credit promoters (no score) are not knocked out; see Conditions.
- KO_VINTAGE_BELOW_MIN: business vintage below 2 years. Waived for PMMY
  Mudra loans up to Rs 5 lakh (Shishu and Kishore).
- KO_NPA_HISTORY_90DPD: any account 90 or more days past due in the last
  12 months.
- KO_WRITTEN_OFF_OR_SETTLED: any written-off or settled account in the last
  24 months.
- KO_SUIT_FILED or KO_WILFUL_DEFAULTER: suit filed against the entity, or a
  promoter appears on the wilful defaulter list.
- KO_NEGATIVE_NET_WORTH: net worth zero or negative in the latest year.
- KO_NEGATIVE_LIST_SECTOR: sector on the negative list in the Sector Risk
  Appetite note.
- CMP_SANCTIONS_MATCH: confirmed sanctions match (name and date of birth).
  The case must also be reported to the Principal Officer.

## Financial Assessment

### Term products (Term Loan, Equipment Finance, PMMY Mudra)
Debt Service Coverage Ratio (DSCR) = (PAT + depreciation + interest) /
(interest + current maturities of long-term debt + proposed annual debt
service). The proposed debt service is computed at an indicative rate of
benchmark + 3.50%.

- DSCR of 1.25 or more is required for approval (1.35 for high-risk-tier
  sectors).
- DSCR between 1.10 and the approval level: approve with a reduced amount
  sized to meet the approval DSCR (CND_AMOUNT_REDUCED_FOR_DSCR), provided
  the reduced amount is at least 50% of the request.
- DSCR below 1.10, or a reduced amount below 50% of the request:
  FIN_DSCR_BELOW_FLOOR.

### Working-capital products (Cash Credit, TReDS)
Working-capital limits are self-liquidating, so they are not tested on DSCR.
Interest Service Coverage Ratio (ISCR) = EBITDA / (existing interest +
interest on the proposed limit).

- ISCR below 1.50: FIN_ISCR_BELOW_FLOOR. ISCR 1.50 to 2.00: CND_ISCR_MARGINAL.
- Current ratio below 1.00: FIN_LIQUIDITY_INADEQUATE. Current ratio 1.00 to
  1.25: CND_LIQUIDITY_MONITORING.
- For limits up to Rs 5 crore, the limit is capped at 20% of annual
  turnover (Nayak Committee turnover method): CND_WC_CAPPED_AT_20PCT_TURNOVER.

### Leverage
TOL/TNW (total outside liabilities / tangible net worth) above 4.0
(manufacturing and services) or 5.0 (trading) requires promoter equity
infusion (CND_PROMOTER_EQUITY_INFUSION). Above 6.0: FIN_LEVERAGE_EXCESSIVE.

## Banking and Bureau Conduct
- Inward cheque or NACH bounces in the last 12 months: more than 3 is
  CND_BOUNCE_MONITORING; more than 6 is BNK_EXCESSIVE_BOUNCES (reject).
- More than 6 credit enquiries in 6 months: CND_HIGH_RECENT_ENQUIRIES.
- CIBIL MSME Rank (CMR) 7 or 8: CND_CMR_ELEVATED. CMR 9 or 10:
  BUR_CMR_HIGH_RISK (reject).
- Delinquency of 1 to 89 days in the last 12 months:
  CND_RECENT_DELINQUENCY_EXPLANATION.
- New-to-credit key promoter on a non-Mudra product:
  CND_NEW_TO_CREDIT_GUARANTOR (a third-party guarantee is required).

## Data Consistency and Fraud Checks
New in this version. Bank data received through the Account Aggregator
framework and GST data through the GSTN API are treated as primary
evidence; uploaded PDFs are secondary.

- FRD_GST_BANK_MISMATCH: annualised GSTR-3B taxable turnover differs from
  net bank credits (credits / 1.12) by more than 30%.
- FRD_FINANCIALS_GST_MISMATCH: latest-year revenue in financial statements
  differs from annualised GST turnover by more than 30%.
- FRD_RELATED_PARTY_CIRCULAR_CREDITS: more than 50% of bank credits come
  from related or group entities.
- Fewer than 9 of 12 GST returns filed: CND_GST_RETURNS_INCOMPLETE.
- Udyam category inconsistent with the category derived from turnover and
  investment: CND_UDYAM_CATEGORY_UPDATE.

Any FRD_ flag refers the case to the Fraud Risk Unit. The engine must not
auto-decline on a fraud flag alone.

## Risk Grading
A 100-point scorecard combines promoter score (25), DSCR or ISCR (25),
leverage (15), vintage (10), banking conduct (10), GST filing discipline
(10) and CMR (5). Grades: WP1 at 80 or more, WP2 at 72, WP3 at 64, WP4 at
56, WP5 at 48, WP6 at 40, WP7 at 32, and WP8 below 32. WP8 is rejected
(RSK_SCORE_BELOW_CUTOFF); WP7 is approved only with conditions
(CND_HIGH_RISK_GRADE).

## Human Review and Delegation
- Any CMP_ or FRD_ flag requires human review before a decision.
- Any recommended amount above Rs 2 crore requires Credit Committee
  approval (HITL_ABOVE_CREDIT_COMMITTEE_THRESHOLD).
- A credit officer may override the engine only with a recorded reason. The
  override is logged against the officer's ID and reviewed monthly.

## Protected Attributes
Gender, religion, caste and the women-led flag must never be used as
inputs to the decision. The women-led flag is used only to determine
eligibility for scheme benefits (for example, the CGTMSE concession) and
for fairness audits.
