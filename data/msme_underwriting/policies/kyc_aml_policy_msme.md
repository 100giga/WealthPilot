# KYC and AML Policy for MSME Borrowers (KYC-MSME-2025-02)

> Synthetic policy written for the underwriting pilot; illustrative only.

## Customer Due Diligence
- The entity and every beneficial owner must have a verified KYC record,
  registered with CKYC (14-digit CKYC number).
- Accepted modes are video KYC (V-CIP), in-person verification, and
  DigiLocker-issued documents.
- Aadhaar numbers must never be collected over email or messaging apps. If
  a customer shares one, staff must delete it and redirect the customer to
  video KYC. Relationship-manager notes must not store full Aadhaar
  numbers.

## Beneficial Ownership
For companies, LLPs and partnerships, every natural person holding 10% or
more of the shares, capital or profits is a beneficial owner and must be
identified. If beneficial ownership is undeclared, the application is
referred to compliance (CMP_BENEFICIAL_OWNER_UNDISCLOSED).

## Risk Categorisation and Periodic Updation
Customers are classified as low, medium or high AML risk. KYC must be
updated at least:

- every 2 years for high-risk customers,
- every 8 years for medium-risk customers,
- every 10 years for low-risk customers.

A credit decision may not be taken while KYC is past its re-KYC due date
(CMP_KYC_EXPIRED). The case is referred and released once re-KYC is
complete.

## Screening
Every promoter and beneficial owner is screened against the sanctions,
PEP, wilful defaulter and related-party lists before a decision.

- Name match with a confirmed date-of-birth match on a sanctions list:
  reject and report to the Principal Officer (CMP_SANCTIONS_MATCH). Do not
  inform the customer of the reason (no tipping-off).
- Name match with a confirmed date-of-birth match on the PEP list: enhanced
  due diligence and senior management approval
  (CMP_PEP_ENHANCED_DUE_DILIGENCE).
- Fuzzy name match (similarity of 0.88 or more) without a date-of-birth
  match: refer to a compliance officer to clear or confirm
  (CMP_POTENTIAL_WATCHLIST_MATCH). Most such hits are false positives
  caused by transliteration variants (for example, Mohammed and Mohd.).
- Promoter is a director, senior officer, or relative of either, of the
  lender: connected lending, which requires Board Credit Committee
  approval (CMP_RELATED_PARTY_LENDING).
