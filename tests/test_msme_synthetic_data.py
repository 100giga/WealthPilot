import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from wealth_pilot.config import PROJECT_ROOT
from wealth_pilot.rag.evaluate import GoldenExample, evaluate
from wealth_pilot.rag.index import HybridIndex
from wealth_pilot.rag.loader import load_documents
from wealth_pilot.rag.security import scan

MSME_DIR = PROJECT_ROOT / "data" / "msme_underwriting"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_msme_data", PROJECT_ROOT / "scripts" / "generate_msme_data.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


gen_module = _load_generator()


@pytest.fixture(scope="module")
def dataset(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("msme")
    gen = gen_module.Generator(n=150, seed=11)
    gen.generate()
    gen.write(out)
    return out


def _rows(out: Path, name: str) -> list[dict]:
    with (out / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_generation_is_deterministic_for_a_seed(dataset, tmp_path):
    again = gen_module.Generator(n=150, seed=11)
    again.generate()
    again.write(tmp_path)
    for name in ("applicants", "underwriting_decisions", "bank_statement_monthly"):
        assert (dataset / f"{name}.csv").read_bytes() == (tmp_path / f"{name}.csv").read_bytes()


def test_every_child_row_points_at_a_known_applicant(dataset):
    applicant_ids = {r["applicant_id"] for r in _rows(dataset, "applicants")}
    for table in ("promoters", "loan_applications", "financial_statements", "bank_statement_monthly",
                  "gst_returns_monthly", "bureau_reports", "kyc_records", "underwriting_decisions"):
        assert {r["applicant_id"] for r in _rows(dataset, table)} <= applicant_ids, table
    decided = {r["application_id"] for r in _rows(dataset, "underwriting_decisions")}
    assert {r["application_id"] for r in _rows(dataset, "loan_performance")} <= decided


def test_gstins_carry_a_valid_checksum(dataset):
    gstins = [r["gstin"] for r in _rows(dataset, "applicants") if r["gstin"]]
    assert gstins
    assert all(g[-1] == gen_module.gstin_checksum(g[:14]) for g in gstins)


def test_decisions_follow_policy_invariants(dataset):
    for d in _rows(dataset, "underwriting_decisions"):
        codes = set(filter(None, d["reason_codes"].split("|")))
        if any(c.startswith("KO_") or c == "CMP_SANCTIONS_MATCH" for c in codes):
            assert d["recommendation"] == "REJECT"
        if d["recommendation"] == "REFER":
            assert d["human_review_required"] == "True"
            assert any(c.startswith(("CMP_", "FRD_")) for c in codes)
        if d["recommendation"] == "REJECT":
            assert d["recommended_amount"] == "0" and d["interest_rate_pct"] == ""
        if d["final_decision"].startswith("APPROVED") and d["recommendation"] == "REJECT":
            assert d["override_reason"], "an override of the engine must record a reason"


def test_performance_labels_only_exist_for_disbursed_loans(dataset):
    finals = {d["application_id"]: d["final_decision"] for d in _rows(dataset, "underwriting_decisions")}
    for p in _rows(dataset, "loan_performance"):
        assert finals[p["application_id"]].startswith("APPROVED")
        assert (p["default_90dpd_12m"] != "") == (p["performance_window_complete"] == "True")


def test_policy_corpus_supports_retrieval_and_flags_the_planted_injection():
    docs = load_documents(MSME_DIR / "policies")
    golden = [GoldenExample(**g) for g in json.loads((MSME_DIR / "rag_golden_set.json").read_text())]
    report = evaluate(golden, HybridIndex(docs).search, k=5)
    assert report.recall_at_k >= 0.9
    flagged = (MSME_DIR / "policies" / "applicant_upload_ca_certificate_flagged.md").read_text()
    assert {"overt_command", "context_confusion"} <= {f.category for f in scan(flagged)}
