# MSME Credit Policy CP-MSME-2024-01 (Superseded)

> Synthetic policy written for the underwriting pilot; illustrative only.
> Effective 1 April 2024 to 31 March 2026. Superseded by CP-MSME-2026-03.
> Use this document only for applications dated before 1 April 2026.

## Scope
Applies to MSME credit facilities with an application date between 1 April
2024 and 31 March 2026.

## Knock-Out Criteria
- KO_PROMOTER_SCORE_BELOW_MIN: key promoter bureau score below 680.
- KO_VINTAGE_BELOW_MIN: business vintage below 3 years. Waived for PMMY
  Mudra loans up to Rs 5 lakh.
- KO_NPA_HISTORY_90DPD, KO_WRITTEN_OFF_OR_SETTLED, KO_SUIT_FILED,
  KO_WILFUL_DEFAULTER, KO_NEGATIVE_NET_WORTH and KO_NEGATIVE_LIST_SECTOR
  apply as in later versions.

## Financial Assessment
- Term products: DSCR of 1.20 or more for approval (1.30 for high-risk
  sectors). DSCR below 1.05 is rejected. Between the two, the amount is
  reduced to meet the approval DSCR.
- Working-capital products: ISCR floor of 1.50, current ratio floor of 1.00,
  and the 20% turnover cap for limits up to Rs 5 crore.
- TOL/TNW limits of 4.0 (manufacturing and services) and 5.0 (trading),
  with rejection above 6.0.

## Data Consistency Checks
- FRD_GST_BANK_MISMATCH: GST turnover and net bank credits differ by more
  than 40%.
- This version has no financial-statements-vs-GST check and no
  related-party credit check. Both were added in CP-MSME-2026-03 after a
  fraud review found inflated audited financials and circular trading going
  undetected.

## Human Review and Delegation
- Any recommended amount above Rs 1 crore requires Credit Committee
  approval.
- CMP_ and FRD_ flags require human review.
