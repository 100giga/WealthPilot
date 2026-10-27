"""Browse the synthetic MSME underwriting dataset (data/msme_underwriting/).

Served by examples/web_demo.py under /msme. Reads the generated CSV/JSONL
files on every request, so re-running scripts/generate_msme_data.py shows
up on refresh.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from html import escape
from pathlib import Path
from urllib.parse import urlencode

MSME_DIR = Path(__file__).resolve().parents[1] / "data" / "msme_underwriting"
GEN = MSME_DIR / "generated"
PAGE_SIZE = 50

REC_CLASS = {"APPROVE": "ok", "APPROVE_WITH_CONDITIONS": "warn", "REFER": "info", "REJECT": "bad",
             "APPROVED": "ok", "APPROVED_WITH_CONDITIONS": "warn", "PENDING_HUMAN_REVIEW": "info",
             "DECLINED": "bad", "WITHDRAWN_BY_APPLICANT": "muted"}


def _csv(name: str) -> list[dict]:
    with (GEN / f"{name}.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out


def inr(value) -> str:
    if value in ("", None):
        return "—"
    v = float(value)
    sign, v = ("-" if v < 0 else ""), abs(v)
    if v >= 1e7:
        return f"{sign}₹{v / 1e7:.2f} Cr"
    if v >= 1e5:
        return f"{sign}₹{v / 1e5:.1f} L"
    return f"{sign}₹{v:,.0f}"


def pill(text: str) -> str:
    return f'<span class="pill {REC_CLASS.get(text, "")}">{escape(text.replace("_", " ").title())}</span>' if text else ""


def codes(text: str) -> str:
    return " ".join(f"<code>{escape(c)}</code>" for c in text.split("|") if c) or "—"


def table(headers: list[str], rows: list[list[str]], cls: str = "") -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tablewrap"><table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def nav(active: str) -> str:
    links = [("/", "Wealth Pilot demo"), ("/msme", "MSME applications"), ("/msme/queue", "Review queue"),
             ("/msme/policies", "Policies")]
    tabs = "".join(f'<a href="{h}" class="{"on" if h == active else ""}">{t}</a>' for h, t in links)
    return ('<header class="topbar"><div class="topbar-in"><a href="/msme" class="brand"><span class="logo">WP</span>'
            f'<span>Wealth Pilot <small>MSME Credit</small></span></a><nav>{tabs}</nav></div></header>')


def _missing() -> str:
    return ('<section class="card"><h2>No generated data yet</h2><p>Run '
            "<code>python scripts/generate_msme_data.py</code> and refresh.</p></section>")


# ---------------------------------------------------------------- overview

def overview(params: dict[str, str]) -> tuple[str, str]:
    if not (GEN / "manifest.json").exists():
        return "MSME applications", nav("/msme") + _missing()
    apps = {a["applicant_id"]: a for a in _csv("applicants")}
    loans = {l["application_id"]: l for l in _csv("loan_applications")}
    decisions = _csv("underwriting_decisions")
    perf = _csv("loan_performance")

    n = len(decisions)
    rec = Counter(d["recommendation"] for d in decisions)
    final = Counter(d["final_decision"] for d in decisions)
    complete = [p for p in perf if p["performance_window_complete"] == "True"]
    default_rate = sum(p["default_90dpd_12m"] == "True" for p in complete) / len(complete) if complete else 0
    approved = rec["APPROVE"] + rec["APPROVE_WITH_CONDITIONS"]
    disbursed = sum(float(p["sanctioned_amount"]) for p in perf)
    tiles = [
        ("Applications", f"{n}", ""),
        ("Engine approve rate", f"{approved / n:.0%}", f"{rec['APPROVE_WITH_CONDITIONS']} with conditions"),
        ("Referred to humans", f"{rec['REFER']}", f"{final['PENDING_HUMAN_REVIEW']} still pending"),
        ("Rejected", f"{rec['REJECT'] / n:.0%}", f"{rec['REJECT']} applications"),
        ("Disbursed", inr(disbursed), f"{len(perf)} loans"),
        ("12m default (90+ DPD)", f"{default_rate:.1%}", f"{len(complete)} loans with full window"),
    ]
    kpis = '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="k">{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>' for k, v, s in tiles) + "</div>"

    # reason-code frequency
    reason_counts = Counter(c for d in decisions for c in d["reason_codes"].split("|") if c).most_common(10)
    top = max((c for _, c in reason_counts), default=1)
    bars = "".join(f'<div class="bar"><span class="lbl"><code>{escape(code)}</code></span>'
                   f'<span class="track"><span class="fill" style="width:{c / top * 100:.0f}%"></span></span><span class="num">{c}</span></div>'
                   for code, c in reason_counts)

    # filters
    f_rec, f_prod, f_sector, q = (params.get(k, "") for k in ("rec", "product", "sector", "q"))
    page = max(1, int(params.get("page", "1") or 1))
    rows = []
    for d in decisions:
        a, l = apps[d["applicant_id"]], loans[d["application_id"]]
        if f_rec and d["recommendation"] != f_rec:
            continue
        if f_prod and l["product"] != f_prod:
            continue
        if f_sector and a["sector"] != f_sector:
            continue
        if q and q.lower() not in f'{a["legal_name"]} {d["application_id"]} {a["city"]} {d["reason_codes"]}'.lower():
            continue
        rows.append((d, a, l))
    rows.sort(key=lambda t: t[2]["application_date"], reverse=True)
    pages = max(1, -(-len(rows) // PAGE_SIZE))
    page = min(page, pages)
    shown = rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    def select(name, current, options):
        opts = '<option value="">All</option>' + "".join(
            f'<option value="{escape(v)}"{" selected" if v == current else ""}>{escape(t)}</option>' for v, t in options)
        return f'<label>{name}<select name="{name.lower()}">{opts}</select></label>'

    form = ('<form class="filters" method="get" action="/msme">'
            + select("Rec", f_rec, [(r, r.replace("_", " ").title()) for r in sorted(rec)])
            + select("Product", f_prod, [(p, p) for p in sorted({l["product"] for l in loans.values()})])
            + select("Sector", f_sector, sorted({(a["sector"], a["sector_label"]) for a in apps.values()}, key=lambda t: t[1]))
            + f'<label>Search<input name="q" value="{escape(q)}" placeholder="name, city, LA-00012, FRD_…"></label>'
            + '<button type="submit">Filter</button><a href="/msme">Reset</a></form>')

    trs = [[f'<a href="/msme/{d["application_id"]}">{d["application_id"]}</a>', l["application_date"],
            escape(a["legal_name"]) + f'<div class="sub2">{escape(a["sector_label"])} · {escape(a["city"])}</div>',
            escape(l["product"]), inr(l["requested_amount"]), d["risk_grade"], d["dscr"] if l["product"] not in ("Cash Credit", "TReDS Invoice Discounting") else f'{d["iscr"]} <span class="sub2">ISCR</span>',
            pill(d["recommendation"]), pill(d["final_decision"])] for d, a, l in shown]
    base = {k: v for k, v in (("rec", f_rec), ("product", f_prod), ("sector", f_sector), ("q", q)) if v}
    pager = f'<div class="pager">{len(rows)} matching · page {page} of {pages} '
    if page > 1:
        pager += f'<a href="/msme?{urlencode({**base, "page": page - 1})}">← Prev</a> '
    if page < pages:
        pager += f'<a href="/msme?{urlencode({**base, "page": page + 1})}">Next →</a>'
    pager += "</div>"

    body = (nav("/msme") + "<h1>MSME Loan Underwriting</h1>"
            + '<div class="sub">Synthetic dataset from <code>scripts/generate_msme_data.py</code> · all identifiers are fake</div>'
            + kpis
            + f'<section class="card"><h2>Most frequent reason codes</h2>{bars}</section>'
            + f'<section class="card"><h2>Applications</h2>{form}'
            + table(["Application", "Date", "Business", "Product", "Requested", "Grade", "DSCR", "Engine", "Final"], trs, "apps")
            + pager + "</section>")
    return "MSME applications", body


# ------------------------------------------------------------------ detail

def detail(application_id: str) -> tuple[str, str] | None:
    if not (GEN / "manifest.json").exists():
        return None
    decisions = {d["application_id"]: d for d in _csv("underwriting_decisions")}
    d = decisions.get(application_id)
    if d is None:
        return None
    aid = d["applicant_id"]
    a = next(x for x in _csv("applicants") if x["applicant_id"] == aid)
    l = next(x for x in _csv("loan_applications") if x["application_id"] == application_id)
    promoters = _by(_csv("promoters"), "applicant_id")[aid]
    fins = _by(_csv("financial_statements"), "applicant_id")[aid]
    bank = _by(_csv("bank_statement_monthly"), "applicant_id")[aid]
    gst = {g["tax_period"]: g for g in _by(_csv("gst_returns_monthly"), "applicant_id").get(aid, [])}
    bureau = _by(_csv("bureau_reports"), "applicant_id")[aid]
    kyc = next(x for x in _csv("kyc_records") if x["applicant_id"] == aid)
    perf = next((p for p in _csv("loan_performance") if p["application_id"] == application_id), None)
    truth = next(g for g in _csv("ground_truth") if g["application_id"] == application_id)
    notes = []
    with (GEN / "rm_interactions.jsonl").open(encoding="utf-8") as f:
        for line in f:
            n = json.loads(line)
            if n["applicant_id"] == aid:
                notes.append(n)

    def kv(pairs):
        return '<dl class="kv">' + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in pairs) + "</dl>"

    is_wc = l["product"] in ("Cash Credit", "TReDS Invoice Discounting")
    decision = (
        f'<section class="card decision"><h2>Decision</h2>'
        f'<div class="row">{pill(d["recommendation"])} <span class="arrow">→</span> {pill(d["final_decision"])}'
        f' <span class="sub2">by {escape(d["decided_by"] or "—")} · {d["policy_id"]}</span></div>'
        + kv([("Risk grade", f'<b>{d["risk_grade"]}</b> ({d["scorecard_points"]} pts)'),
              ("ISCR" if is_wc else "DSCR", d["iscr"] if is_wc else d["dscr"]),
              ("Current ratio", d["current_ratio"]), ("TOL/TNW", d["tol_tnw"] or "n/a (net worth ≤ 0)"),
              ("GST ↔ bank variance", d["gst_bank_variance"] or "—"), ("Financials ↔ GST variance", d["financials_gst_variance"] or "—"),
              ("Related-party credits", f'{float(d["related_party_credit_pct"]):.0%}'), ("Bounces (12m)", d["inward_bounces_12m"]),
              ("Requested → recommended", f'{inr(d["requested_amount"])} → {inr(d["recommended_amount"])}'),
              ("Rate", f'{d["interest_rate_pct"]}%' if d["interest_rate_pct"] else "—"), ("CGTMSE cover", d["cgtmse_cover"]),
              ("Reason codes", codes(d["reason_codes"])), ("Conditions", codes(d["conditions"])),
              ("Human review", codes(d["human_review_reasons"]) if d["human_review_required"] == "True" else "Not required"),
              ("Override reason", escape(d["override_reason"]) or "—")])
        + "</section>")

    profile = (f'<section class="card"><h2>Business</h2>' + kv([
        ("Legal name", escape(a["legal_name"])), ("Constitution", a["constitution"].replace("_", " ")),
        ("Sector", f'{escape(a["sector_label"])} (NIC {a["nic_2digit"]}, {a["sector_risk_tier"]} risk)'),
        ("Location", f'{a["city"]}, {a["state"]}'), ("Vintage", f'{a["vintage_years"]} years'),
        ("MSME category", f'Udyam: {a["udyam_category"]} · derived: {a["derived_msme_category"]}'),
        ("Employees", a["employees"]), ("PAN / GSTIN", f'<code>{a["pan"]}</code> / <code>{a["gstin"] or "not registered"}</code>'),
        ("Udyam", f'<code>{a["udyam_number"]}</code>'), ("Women-led", a["women_led"] + ' <span class="sub2">(scheme eligibility only)</span>'),
    ]) + "</section>")
    loan = (f'<section class="card"><h2>Loan request</h2>' + kv([
        ("Product", escape(l["product"]) + (f' ({l["mudra_category"]})' if l["mudra_category"] else "")),
        ("Purpose", l["purpose"].replace("_", " ")), ("Amount", inr(l["requested_amount"])),
        ("Tenure", f'{l["requested_tenure_months"]} months'),
        ("Collateral", f'{l["collateral_type"].replace("_", " ")} {inr(l["collateral_value"]) if l["collateral_value"] != "0" else ""}'),
        ("Channel", l["channel"].replace("_", " ")), ("Applied", l["application_date"]), ("RM", l["relationship_manager"]),
    ]) + "</section>")

    hits = json.loads(d["watchlist_hits"]) if d["watchlist_hits"] else []
    prom_rows = [[escape(p["name"]), p["role"], p["date_of_birth"], f'{p["shareholding_pct"]}%',
                  p["bureau_score"] or "NTC", f'<code>{p["pan"]}</code>'] for p in promoters]
    people = (f'<section class="card"><h2>Promoters & screening</h2>'
              + table(["Name", "Role", "DOB", "Share", "Bureau", "PAN"], prom_rows)
              + ("<p><b>Watchlist hits on key promoter:</b> " + ", ".join(
                  f'{h["list_type"]} {h["entry_id"]} (name {h["name_score"]}, DOB {"match" if h["dob_match"] else "differs"})' for h in hits) + "</p>"
                 if hits else "<p class='sub2'>No watchlist hits.</p>")
              + kv([("KYC", f'{kyc["kyc_status"]} · {kyc["kyc_mode"]} · verified {kyc["kyc_verified_on"]} · re-KYC due {kyc["re_kyc_due_on"]}'),
                    ("AML risk", kyc["aml_risk_category"]), ("Beneficial owners declared", kyc["beneficial_owners_declared"])])
              + "</section>")

    fin_keys = [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("profit_after_tax", "PAT"), ("depreciation", "Depreciation"),
                ("interest_expense", "Interest"), ("total_assets", "Total assets"), ("current_assets", "Current assets"),
                ("current_liabilities", "Current liabilities"), ("total_debt", "Total debt"), ("net_worth", "Net worth")]
    fins = sorted(fins, key=lambda r: r["fiscal_year"])
    fin_table = table(["₹"] + [f'{f["fiscal_year"]}<div class="sub2">{f["audit_status"]}</div>' for f in fins],
                      [[label] + [inr(f[k]) for f in fins] for k, label in fin_keys], "num")

    bank_rows = [[b["month"], inr(b["total_credits"]), inr(gst[b["month"]]["taxable_turnover"]) if b["month"] in gst else "—",
                  (gst[b["month"]]["filing_status"] + (f' +{gst[b["month"]]["days_late"]}d' if gst[b["month"]]["days_late"] not in ("", "0") else "")) if b["month"] in gst else "—",
                  inr(b["avg_eod_balance"]), f'{float(b["related_party_credit_pct"]):.0%}', b["inward_cheque_bounces"]] for b in bank]
    bank_table = table(["Month", "Bank credits", "GST turnover", "GSTR-3B", "Avg balance", "Related-party", "Bounces"], bank_rows, "num")
    src = bank[0]["data_source"].replace("_", " ") if bank else ""

    bureau_rows = [[b["subject_id"], b["subject_type"], b["bureau_score"] or ("CMR " + b["cmr_rank"] if b["cmr_rank"] else "NTC"),
                    b["max_dpd_12m"], b["enquiries_6m"], b["active_accounts"],
                    ", ".join(k for k in ("written_off_or_settled_24m", "suit_filed", "wilful_defaulter") if b[k] == "True") or "—"] for b in bureau]

    note_html = "".join(
        f'<li><div class="sub2">{n["timestamp"][:10]} · {n["channel"].replace("_", " ")} · {n["author"]}</div>{escape(n["note"])}'
        + (f'<div class="facts">{" ".join(f"<code>{escape(x["key"])}={escape(str(x["value"]))}</code>" for x in n["facts"])}</div>' if n["facts"] else "")
        + "</li>" for n in sorted(notes, key=lambda n: n["timestamp"]))

    perf_html = (kv([("Disbursed", f'{perf["disbursed_on"]} · {inr(perf["sanctioned_amount"])}'),
                     ("Months on book", perf["months_on_book"]), ("Status", f'{perf["asset_classification"]} (DPD {perf["current_dpd"]})'),
                     ("12m default", perf["default_90dpd_12m"] or "window not complete")])
                 if perf else "<p class='sub2'>Not disbursed.</p>")

    body = (nav("") + f'<a href="/msme" class="back">← All applications</a>'
            + f'<h1>{escape(a["legal_name"])}</h1><div class="sub">{application_id} · {aid}</div>'
            + decision + '<div class="grid2">' + profile + loan + "</div>" + people
            + f'<section class="card"><h2>Financial statements</h2>{fin_table}</section>'
            + f'<section class="card"><h2>Bank & GST, 12 months before application</h2><div class="sub2">Bank data via {src}</div>{bank_table}</section>'
            + f'<section class="card"><h2>Bureau</h2>{table(["Subject", "Type", "Score", "Max DPD 12m", "Enquiries 6m", "Active", "Flags"], bureau_rows)}</section>'
            + f'<section class="card"><h2>Relationship-manager notes (memory)</h2><ul class="notes">{note_html}</ul></section>'
            + f'<section class="card"><h2>Loan performance</h2>{perf_html}</section>'
            + '<section class="card"><details><summary>Ground truth (evaluation only — never shown to agents)</summary>'
            + kv([("Latent quality z", truth["latent_quality_z"]), ("True 12m PD", f'{float(truth["true_pd_12m"]):.1%}'),
                  ("Fraud type", truth["fraud_type"] or "none"), ("Planted compliance case", truth["planted_compliance_case"] or "none")])
            + "</details></section>")
    return application_id, body


# ------------------------------------------------------------------- queue

def queue() -> tuple[str, str]:
    if not (GEN / "manifest.json").exists():
        return "Review queue", nav("/msme/queue") + _missing()
    apps = {a["applicant_id"]: a for a in _csv("applicants")}
    decisions = [d for d in _csv("underwriting_decisions") if d["human_review_required"] == "True"]
    pending = [d for d in decisions if d["final_decision"] == "PENDING_HUMAN_REVIEW"]
    resolved = [d for d in decisions if d["final_decision"] != "PENDING_HUMAN_REVIEW"]

    def rows(ds):
        return [[f'<a href="/msme/{d["application_id"]}">{d["application_id"]}</a>', escape(apps[d["applicant_id"]]["legal_name"]),
                 inr(d["requested_amount"]), pill(d["recommendation"]), codes(d["human_review_reasons"]),
                 pill(d["final_decision"]), escape(d["decided_by"]), escape(d["override_reason"])] for d in ds]

    who = Counter(d["decided_by"] for d in resolved)
    body = (nav("/msme/queue") + "<h1>Human-in-the-loop review</h1>"
            + f'<div class="sub">{len(decisions)} applications needed a human; decided by: '
            + ", ".join(f"{k.replace('_', ' ')} ({v})" for k, v in who.most_common()) + "</div>"
            + f'<section class="card"><h2>Pending ({len(pending)})</h2>'
            + table(["Application", "Business", "Amount", "Engine", "Why review", "Status", "", ""], rows(pending)) + "</section>"
            + f'<section class="card"><h2>Resolved ({len(resolved)})</h2>'
            + table(["Application", "Business", "Amount", "Engine", "Why review", "Final", "Decided by", "Note"],
                    rows(sorted(resolved, key=lambda d: d["decision_date"], reverse=True))) + "</section>")
    return "Review queue", body


# ---------------------------------------------------------------- policies

def _md(text: str) -> str:
    """Just enough Markdown for the policy notes: headings, lists, tables, quotes."""
    out, in_list, table_rows = [], False, []

    def inline(s: str) -> str:
        s = escape(s)
        parts = s.split("`")
        s = "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))
        bold = s.split("**")
        return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(bold))

    def flush_table():
        if table_rows:
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in table_rows if not set(r) <= set("|-: ")]
            out.append(table([inline(c) for c in cells[0]], [[inline(c) for c in r] for r in cells[1:]]))
            table_rows.clear()

    for line in text.splitlines():
        if line.startswith("|"):
            table_rows.append(line)
            continue
        flush_table()
        if in_list and not line.startswith(("- ", "  ")):
            out.append("</ul>")
            in_list = False
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level + 1}>{inline(line.lstrip('# '))}</h{level + 1}>")
        elif line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(line[2:])}")
        elif line.startswith("  ") and in_list:
            out.append(" " + inline(line.strip()))
        elif line.startswith(">"):
            out.append(f'<blockquote>{inline(line.lstrip("> "))}</blockquote>')
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
    flush_table()
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def policies(name: str | None = None) -> tuple[str, str] | None:
    files = sorted((MSME_DIR / "policies").glob("*.md"))
    listing = "".join(
        f'<li><a href="/msme/policies/{p.stem}" class="{"on" if p.stem == name else ""}">{p.stem}</a>'
        + (' <span class="pill bad">injection fixture</span>' if "flagged" in p.stem else "")
        + (' <span class="pill muted">superseded</span>' if "superseded" in p.stem else "") + "</li>" for p in files)
    if name is None:
        golden = json.loads((MSME_DIR / "rag_golden_set.json").read_text(encoding="utf-8"))
        gs = table(["Question", "Expected document(s)"], [[escape(g["query"]), codes("|".join(g["expected_doc_ids"]))] for g in golden])
        return "Policies", (nav("/msme/policies") + "<h1>Policy corpus (RAG)</h1>"
                            + f'<section class="card"><h2>Documents</h2><ul class="doclist">{listing}</ul></section>'
                            + f'<section class="card"><h2>Golden retrieval set</h2>{gs}</section>')
    path = MSME_DIR / "policies" / f"{name}.md"
    if path not in files:
        return None
    return name, (nav("/msme/policies") + '<a href="/msme/policies" class="back">← All policies</a>'
                  + f'<section class="card doc">{_md(path.read_text(encoding="utf-8"))}</section>')
