#!/usr/bin/env python
"""Generate the synthetic MSME loan-underwriting dataset.

    python scripts/generate_msme_data.py                 # 500 applicants, seed 2026
    python scripts/generate_msme_data.py --n 2000 --seed 7

Writes to data/msme_underwriting/generated/. Standard library only and fully
deterministic for a given seed + size. Every identifier (PAN, GSTIN, Udyam,
CIN, CKYC) is format-valid but randomly generated - none refer to a real
business or person.

The underwriting rules below mirror the two policy documents in
data/msme_underwriting/policies/ (CP-MSME-2024-01 and CP-MSME-2026-03).
Change a threshold in one place and you must change it in the other.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "msme_underwriting" / "generated"

LAKH = 100_000
CRORE = 10_000_000
AS_OF = date(2026, 10, 1)
FIRST_APPLICATION = date(2024, 7, 1)
LAST_APPLICATION = date(2026, 9, 30)
GST_GROSS_UP = 1.12  # bank credits include GST collected; rough blended rate


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Sector:
    key: str
    label: str
    nic_2digit: str
    kind: str  # manufacturing | trading | services
    weight: int
    ebitda_margin: float
    fixed_asset_ratio: float  # fixed assets / revenue
    debtor_days: int
    inventory_days: int
    creditor_days: int
    risk_tier: str  # low | medium | high | negative
    seasonality: float
    name_words: tuple[str, ...]


SECTORS = [
    Sector("textiles", "Textiles & apparel", "13", "manufacturing", 10, 0.10, 0.30, 75, 70, 55, "medium", 0.20, ("Textiles", "Fabrics", "Garments", "Weaves")),
    Sector("food_processing", "Food processing", "10", "manufacturing", 9, 0.09, 0.35, 30, 45, 30, "low", 0.15, ("Foods", "Agro Products", "Dairy", "Spices")),
    Sector("auto_components", "Auto components", "29", "manufacturing", 8, 0.12, 0.45, 70, 40, 60, "medium", 0.05, ("Auto Components", "Auto Parts", "Forgings")),
    Sector("pharma_chemicals", "Pharma & chemicals", "21", "manufacturing", 6, 0.15, 0.50, 80, 60, 70, "low", 0.05, ("Pharma", "Chemicals", "Life Sciences")),
    Sector("engineering", "Fabricated metal & engineering", "25", "manufacturing", 8, 0.11, 0.40, 85, 50, 60, "medium", 0.05, ("Engineering", "Fabricators", "Precision Works", "Industries")),
    Sector("plastics_packaging", "Plastics & packaging", "22", "manufacturing", 6, 0.10, 0.45, 60, 40, 50, "medium", 0.05, ("Polymers", "Packaging", "Plast")),
    Sector("wholesale_trade", "Wholesale trade", "46", "trading", 12, 0.04, 0.05, 45, 40, 40, "medium", 0.10, ("Traders", "Distributors", "Agencies", "Trading Co")),
    Sector("retail_trade", "Retail trade", "47", "trading", 9, 0.06, 0.08, 5, 50, 30, "high", 0.25, ("Stores", "Mart", "Retail", "Emporium")),
    Sector("it_services", "IT & software services", "62", "services", 7, 0.18, 0.10, 75, 0, 20, "low", 0.00, ("Infotech", "Technologies", "Software Solutions", "Digital")),
    Sector("logistics", "Logistics & transport", "49", "services", 7, 0.13, 0.60, 60, 0, 30, "medium", 0.05, ("Logistics", "Roadways", "Transport Co", "Carriers")),
    Sector("restaurants", "Restaurants & catering", "56", "services", 5, 0.12, 0.35, 5, 8, 20, "high", 0.15, ("Caterers", "Hospitality", "Kitchens")),
    Sector("construction", "Construction contractors", "43", "services", 6, 0.10, 0.25, 110, 30, 80, "high", 0.10, ("Constructions", "Infra", "Builders & Contractors")),
    Sector("healthcare", "Clinics & diagnostics", "86", "services", 5, 0.20, 0.55, 30, 5, 25, "low", 0.00, ("Diagnostics", "Healthcare", "Clinic")),
    Sector("tobacco", "Tobacco products", "12", "manufacturing", 1, 0.14, 0.30, 30, 60, 30, "negative", 0.05, ("Tobacco", "Beedi Works")),
    Sector("real_estate", "Real estate development", "41", "services", 1, 0.20, 0.10, 30, 300, 60, "negative", 0.00, ("Realty", "Developers", "Estates")),
]

# state -> (GST state code, Udyam state abbreviation, cities)
STATES = {
    "Maharashtra": ("27", "MH", ("Pune", "Mumbai", "Nashik", "Aurangabad")),
    "Gujarat": ("24", "GJ", ("Ahmedabad", "Surat", "Rajkot", "Vadodara")),
    "Tamil Nadu": ("33", "TN", ("Coimbatore", "Chennai", "Tiruppur", "Madurai")),
    "Karnataka": ("29", "KA", ("Bengaluru", "Mysuru", "Hubballi", "Belagavi")),
    "Uttar Pradesh": ("09", "UP", ("Kanpur", "Noida", "Lucknow", "Agra")),
    "Delhi": ("07", "DL", ("New Delhi",)),
    "Telangana": ("36", "TS", ("Hyderabad", "Warangal")),
    "Rajasthan": ("08", "RJ", ("Jaipur", "Jodhpur", "Bhilwara")),
    "West Bengal": ("19", "WB", ("Kolkata", "Howrah", "Siliguri")),
    "Punjab": ("03", "PB", ("Ludhiana", "Jalandhar", "Amritsar")),
    "Kerala": ("32", "KL", ("Kochi", "Thrissur")),
    "Haryana": ("06", "HR", ("Gurugram", "Faridabad", "Panipat")),
}
STATE_WEIGHTS = {"Maharashtra": 16, "Gujarat": 13, "Tamil Nadu": 12, "Karnataka": 9, "Uttar Pradesh": 10, "Delhi": 6,
                 "Telangana": 6, "Rajasthan": 6, "West Bengal": 7, "Punjab": 5, "Kerala": 4, "Haryana": 6}

BUSINESS_PREFIXES = ("Shree", "Sai", "Balaji", "Om", "Sri", "Ganesh", "Laxmi", "Kaveri", "Narmada", "Himalaya",
                     "Sahyadri", "Vindhya", "Coromandel", "Deccan", "Ganga", "Indus", "Aravali", "Malabar", "Konark",
                     "Navkar", "Annapurna", "Tapti", "Nilgiri", "Godavari", "Saraswati", "Surya", "Chandra", "Mahalaxmi")
FIRST_NAMES_F = ("Asha", "Priya", "Lakshmi", "Fatima", "Meena", "Kavita", "Anjali", "Deepa", "Sunita", "Nandini",
                 "Shabana", "Harpreet", "Radhika", "Swati", "Pooja", "Revathi", "Gulshan", "Neha", "Ishita", "Mary")
FIRST_NAMES_M = ("Rajesh", "Suresh", "Arjun", "Imran", "Vikram", "Ramesh", "Anil", "Sanjay", "Karthik", "Mohammed",
                 "Harish", "Gurpreet", "Venkatesh", "Rahul", "Amit", "Joseph", "Prakash", "Dinesh", "Sameer", "Naveen")
SURNAMES = ("Sharma", "Patel", "Reddy", "Iyer", "Shaikh", "Gupta", "Nair", "Singh", "Mehta", "Kulkarni", "Das",
            "Agarwal", "Menon", "Joshi", "Khan", "Rao", "Banerjee", "Chauhan", "Pillai", "Jain", "Desai", "Bhat",
            "Gill", "Mukherjee", "Naidu", "Thomas", "Venkataraman", "Saxena", "Pandey", "Fernandes")
MIDDLE_NAMES = ("Kumar", "Prasad", "Devi", "Lal", "Chandra", "Mohan", "Rani", "Nath", "Shankar", "Bai", "Kishore",
                "Ram", "Kant", "Singh", "Narayan", "Gopal", "Ali", "Jyoti", "Raj", "Kaur")
BUYERS = ("a Tier-1 auto OEM", "a national FMCG distributor", "a UAE importer", "a state PSU", "a large e-commerce marketplace",
          "a German machinery buyer", "a hospital chain", "a pharma major", "a modern-trade retail chain")


# --------------------------------------------------------------------------
# Credit policy parameters (see data/msme_underwriting/policies/)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Policy:
    policy_id: str
    effective_from: date
    min_promoter_score: int
    min_vintage_years: float
    dscr_approve: float
    dscr_approve_high_risk: float
    dscr_floor: float
    gst_bank_variance_refer: float
    financials_gst_variance_refer: float | None
    related_party_credit_refer: float | None
    credit_committee_threshold: int


POLICIES = [
    Policy("CP-MSME-2024-01", date(2024, 4, 1), 680, 3, 1.20, 1.30, 1.05, 0.40, None, None, 1 * CRORE),
    Policy("CP-MSME-2026-03", date(2026, 4, 1), 650, 2, 1.25, 1.35, 1.10, 0.30, 0.30, 0.50, 2 * CRORE),
]
MAX_TOL_TNW = {"manufacturing": 4.0, "services": 4.0, "trading": 5.0}
TOL_TNW_REJECT = 6.0
ISCR_CONDITION = 2.00  # working-capital products are tested on interest service coverage, not DSCR
ISCR_FLOOR = 1.50
CURRENT_RATIO_CONDITION = 1.25
CURRENT_RATIO_REJECT = 1.00
BOUNCES_CONDITION = 3
BOUNCES_REJECT = 6
ENQUIRIES_6M_CONDITION = 6
CMR_CONDITION = 7
CMR_REJECT = 9
WC_TURNOVER_CAP = 0.20  # Nayak Committee norm for working-capital limits up to Rs 5 crore
MUDRA_MAX = 20 * LAKH
CGTMSE_MAX = 10 * CRORE
BENCHMARK_RATE = 8.85  # illustrative external-benchmark lending rate, % p.a.
GRADE_SPREADS = {"WP1": 1.50, "WP2": 2.00, "WP3": 2.50, "WP4": 3.25, "WP5": 4.00, "WP6": 5.00, "WP7": 6.25}
GRADE_CUTOFFS = [(80, "WP1"), (72, "WP2"), (64, "WP3"), (56, "WP4"), (48, "WP5"), (40, "WP6"), (32, "WP7")]
HIGH_RISK_SECTOR_PREMIUM = 0.50
PROPERTY_COLLATERAL_DISCOUNT = 0.25
NAME_MATCH_THRESHOLD = 0.88

# MSME classification, revised thresholds effective 1 April 2025 (investment, turnover)
MSME_THRESHOLDS = [("micro", 2.5 * CRORE, 10 * CRORE), ("small", 25 * CRORE, 100 * CRORE), ("medium", 125 * CRORE, 500 * CRORE)]


def policy_for(application_date: date) -> Policy:
    return [p for p in POLICIES if p.effective_from <= application_date][-1]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def log_uniform(rng: random.Random, lo: float, hi: float) -> float:
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


def weighted(rng: random.Random, options: dict):
    return rng.choices(list(options), weights=list(options.values()))[0]


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, min(d.day, 28))


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def fy_label(end_year: int) -> str:
    return f"FY{end_year - 1}-{str(end_year)[2:]}"


def classify_msme(investment: float, turnover: float) -> str:
    for name, inv_cap, turnover_cap in MSME_THRESHOLDS:
        if investment <= inv_cap and turnover <= turnover_cap:
            return name
    return "not_msme"


def annuity(principal: float, rate_pct: float, months: int) -> float:
    r = rate_pct / 1200
    return principal * r / (1 - (1 + r) ** -months)


ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = ALNUM.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return ALNUM[(36 - total % 36) % 36]


def make_pan(rng: random.Random, holder_type: str, name_initial: str) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return ("".join(rng.choice(letters) for _ in range(3)) + holder_type + name_initial.upper()
            + f"{rng.randint(1, 9999):04d}" + rng.choice(letters))


def make_gstin(rng: random.Random, state_code: str, pan: str) -> str:
    first14 = f"{state_code}{pan}{rng.choice('123')}Z"
    return first14 + gstin_checksum(first14)


def normalize_name(name: str) -> str:
    return " ".join(name.lower().replace(".", " ").split())


def name_variant(rng: random.Random, name: str) -> str:
    """A transliteration-style spelling variant, the kind exact matching misses."""
    swaps = [("Mohammed", "Mohd."), ("Venkataraman", "Venkatraman"), ("ee", "i"), ("Shaikh", "Sheikh"),
             ("Gurpreet", "Gurprit"), ("Lakshmi", "Laxmi"), ("Joseph", "Josef"), ("Kulkarni", "Kulkarny")]
    rng.shuffle(swaps)
    for old, new in swaps:
        if old in name:
            return name.replace(old, new, 1)
    first, _, rest = name.partition(" ")
    return f"{first[:-1]} {rest}" if len(first) > 4 else f"{first}h {rest}"


# --------------------------------------------------------------------------
# Generator
# --------------------------------------------------------------------------

class Generator:
    def __init__(self, n: int, seed: int):
        self.n = n
        self.rng = random.Random(seed)
        self.seed = seed
        self.tables: dict[str, list[dict]] = {k: [] for k in (
            "applicants", "promoters", "loan_applications", "financial_statements", "bank_statement_monthly",
            "gst_returns_monthly", "bureau_reports", "kyc_records", "watchlist", "related_parties",
            "underwriting_decisions", "loan_performance", "ground_truth")}
        self.rm_notes: list[dict] = []
        self.used_names: set[str] = set()

    # ---- people & names ------------------------------------------------

    def person_name(self, female: bool) -> str:
        first, last = self.rng.choice(FIRST_NAMES_F if female else FIRST_NAMES_M), self.rng.choice(SURNAMES)
        if self.rng.random() < 0.6:
            return f"{first} {self.rng.choice(MIDDLE_NAMES)} {last}"
        return f"{first} {last}"

    def business_name(self, sector: Sector, constitution: str, city: str) -> str:
        suffix = {"proprietorship": "Enterprises", "partnership": "& Co", "llp": "LLP", "private_limited": "Pvt Ltd"}[constitution]
        base = f"{self.rng.choice(BUSINESS_PREFIXES)} {self.rng.choice(sector.name_words)}"
        name = f"{base} {suffix}"
        if name in self.used_names:
            name = f"{base} ({city}) {suffix}"
        self.used_names.add(name)
        return name

    def dob(self) -> date:
        return AS_OF - timedelta(days=self.rng.randint(25 * 365, 68 * 365))

    # ---- compliance reference lists ------------------------------------

    def build_watchlists(self) -> None:
        rng = self.rng
        lists = {"SANCTIONS": 30, "PEP": 20, "WILFUL_DEFAULTER": 15}
        n = 0
        for list_type, count in lists.items():
            for _ in range(count):
                n += 1
                name = self.person_name(rng.random() < 0.3)
                self.tables["watchlist"].append({
                    "entry_id": f"WL-{n:04d}", "list_type": list_type, "name": name,
                    "aliases": name_variant(rng, name) if rng.random() < 0.5 else "",
                    "date_of_birth": self.dob().isoformat(),
                    "designation": rng.choice(("Member, Municipal Corporation", "Former MLA", "Senior civil servant",
                                               "Director, state PSU")) if list_type == "PEP" else "",
                    "source": "synthetic", "listed_on": (AS_OF - timedelta(days=rng.randint(30, 2000))).isoformat(),
                })
        for i in range(25):
            self.tables["related_parties"].append({
                "related_party_id": f"RP-{i + 1:03d}", "name": self.person_name(rng.random() < 0.4),
                "date_of_birth": self.dob().isoformat(),
                "relationship": rng.choice(("Director of lender", "Relative of director", "Senior officer of lender",
                                            "Relative of senior officer")),
                "source": "synthetic",
            })

    def plant_compliance_cases(self, promoter: dict) -> str | None:
        """Occasionally make a promoter collide with a watchlist / related-party entry.
        Returns the planted case type for ground truth, or None."""
        r = self.rng.random()
        wl = self.tables["watchlist"]
        if r < 0.012:
            entry = self.rng.choice([w for w in wl if w["list_type"] == "SANCTIONS"])
            promoter["name"], promoter["date_of_birth"] = entry["name"], entry["date_of_birth"]
            return "sanctions_true_match"
        if r < 0.030:
            entry = self.rng.choice([w for w in wl if w["list_type"] in ("SANCTIONS", "PEP")])
            promoter["name"] = name_variant(self.rng, entry["name"])  # similar name, different person (DOB differs)
            return "watchlist_false_positive"
        if r < 0.045:
            entry = self.rng.choice([w for w in wl if w["list_type"] == "PEP"])
            promoter["name"], promoter["date_of_birth"] = entry["name"], entry["date_of_birth"]
            return "pep_true_match"
        if r < 0.055:
            entry = self.rng.choice([w for w in wl if w["list_type"] == "WILFUL_DEFAULTER"])
            promoter["name"], promoter["date_of_birth"] = entry["name"], entry["date_of_birth"]
            return "wilful_defaulter"
        if r < 0.065:
            entry = self.rng.choice(self.tables["related_parties"])
            promoter["name"], promoter["date_of_birth"] = entry["name"], entry["date_of_birth"]
            return "related_party"
        return None

    def screen(self, promoter: dict) -> list[dict]:
        hits = []
        pname = normalize_name(promoter["name"])
        for entry in self.tables["watchlist"]:
            names = [entry["name"]] + ([entry["aliases"]] if entry["aliases"] else [])
            score = max(difflib.SequenceMatcher(None, pname, normalize_name(x)).ratio() for x in names)
            if score >= NAME_MATCH_THRESHOLD:
                hits.append({"list_type": entry["list_type"], "entry_id": entry["entry_id"], "name_score": round(score, 3),
                             "dob_match": entry["date_of_birth"] == promoter["date_of_birth"]})
        for entry in self.tables["related_parties"]:
            if normalize_name(entry["name"]) == pname and entry["date_of_birth"] == promoter["date_of_birth"]:
                hits.append({"list_type": "RELATED_PARTY", "entry_id": entry["related_party_id"], "name_score": 1.0, "dob_match": True})
        return hits

    # ---- one applicant end to end --------------------------------------

    def generate(self) -> None:
        self.build_watchlists()
        for i in range(1, self.n + 1):
            self.one_applicant(i)
        self.build_eval_sets()

    def one_applicant(self, i: int) -> None:
        rng = self.rng
        applicant_id, application_id = f"MSME-{i:05d}", f"LA-{i:05d}"
        z = rng.gauss(0, 1)  # latent credit quality - ground truth only
        sector = rng.choices(SECTORS, weights=[s.weight for s in SECTORS])[0]
        state = weighted(rng, STATE_WEIGHTS)
        state_code, state_abbr, cities = STATES[state]
        city = rng.choice(cities)

        target = weighted(rng, {"micro": 60, "small": 30, "medium": 10})
        turnover_range = {"micro": (15 * LAKH, 9.5 * CRORE), "small": (10.5 * CRORE, 95 * CRORE), "medium": (105 * CRORE, 450 * CRORE)}[target]
        true_revenue = log_uniform(rng, *turnover_range)
        constitution = weighted(rng, {
            "micro": {"proprietorship": 55, "partnership": 20, "llp": 10, "private_limited": 15},
            "small": {"proprietorship": 15, "partnership": 20, "llp": 15, "private_limited": 50},
            "medium": {"proprietorship": 0, "partnership": 5, "llp": 10, "private_limited": 85},
        }[target])
        vintage_years = round(clip(log_uniform(rng, 1.2, 30) + (2 if target != "micro" else 0), 0.5, 40), 1)

        # Application timing and the data windows it implies
        app_date = FIRST_APPLICATION + timedelta(days=rng.randint(0, (LAST_APPLICATION - FIRST_APPLICATION).days))
        policy = policy_for(app_date)
        latest_fy_end = app_date.year if app_date.month >= 7 else app_date.year - 1
        audit_status = "audited" if app_date >= date(latest_fy_end, 10, 1) else "provisional"
        statement_months = [add_months(date(app_date.year, app_date.month, 1), -k) for k in range(12, 0, -1)]

        fraud_type = None
        if rng.random() < 0.05:
            fraud_type = rng.choice(("gst_invoice_inflation", "circular_trading", "financials_inflated"))

        # ---- entity ----
        women_led = rng.random() < 0.22
        holder = {"proprietorship": "P", "partnership": "F", "llp": "F", "private_limited": "C"}[constitution]
        n_promoters = 1 if constitution == "proprietorship" else rng.randint(2, 3)
        promoters = []
        planted = None
        for p in range(n_promoters):
            female = women_led if p == 0 else rng.random() < 0.3
            promoter = {"promoter_id": f"{applicant_id}-P{p + 1}", "applicant_id": applicant_id,
                        "name": self.person_name(female), "date_of_birth": self.dob().isoformat(),
                        "role": "Proprietor" if constitution == "proprietorship" else ("Managing Partner" if constitution != "private_limited" else "Managing Director") if p == 0 else ("Partner" if constitution != "private_limited" else "Director"),
                        "gender": "female" if female else "male"}
            if p == 0:
                planted = self.plant_compliance_cases(promoter)
            promoter["pan"] = make_pan(rng, "P", promoter["name"].split()[-1][0])
            promoters.append(promoter)
        shares = [rng.uniform(0.3, 1.0) for _ in promoters]
        for promoter, s in zip(promoters, shares):
            promoter["shareholding_pct"] = round(100 * s / sum(shares), 1)

        first_promoter = promoters[0]
        entity_name = first_promoter["name"] + " " + rng.choice(sector.name_words) if constitution == "proprietorship" and rng.random() < 0.3 else None
        legal_name = entity_name or self.business_name(sector, constitution, city)
        entity_pan = first_promoter["pan"] if constitution == "proprietorship" else make_pan(rng, holder, legal_name[0])
        gst_registered = true_revenue >= (20 * LAKH if sector.kind == "services" else 40 * LAKH) or rng.random() < 0.3
        gstin = make_gstin(rng, state_code, entity_pan) if gst_registered else ""

        # ---- financial statements (3 FYs, fewer for young businesses) ----
        fixed_assets_latest = true_revenue * sector.fixed_asset_ratio * rng.uniform(0.7, 1.3)
        inv_cap = dict((name, cap) for name, cap, _ in MSME_THRESHOLDS)[target]
        fixed_assets_latest = min(fixed_assets_latest, inv_cap / 0.7 * 0.95)
        investment_pm = fixed_assets_latest * 0.7 if sector.kind == "manufacturing" else fixed_assets_latest * 0.5
        growth = 0.08 + 0.10 * z + rng.gauss(0, 0.08)
        debt_share = clip(0.30 - 0.09 * z + rng.gauss(0, 0.08), 0.05, 0.92)
        margin = clip(sector.ebitda_margin + 0.03 * z + rng.gauss(0, 0.02), -0.05, 0.40)
        reported_multiplier = rng.uniform(1.4, 1.7) if fraud_type == "financials_inflated" else 1.0
        years_available = min(3, max(1, int(vintage_years)))

        fin_rows = []
        for k in range(years_available):
            fy_end = latest_fy_end - k
            scale = (1 + growth) ** -k
            revenue = true_revenue * scale * reported_multiplier
            fa = fixed_assets_latest * (1 - 0.05 * k)
            ebitda = revenue * (margin + rng.gauss(0, 0.01))
            receivables = revenue * sector.debtor_days * rng.uniform(0.8, 1.3) / 365
            inventory = revenue * sector.inventory_days * rng.uniform(0.8, 1.3) / 365
            cash = revenue * rng.uniform(0.01, 0.04)
            current_assets = receivables + inventory + cash
            total_assets = fa + current_assets
            total_debt = total_assets * debt_share
            st_borrowings = total_debt * (0.5 if sector.kind == "trading" else 0.3)
            lt_debt = total_debt - st_borrowings
            payables = revenue * sector.creditor_days * rng.uniform(0.8, 1.2) / 365
            other_cl = total_assets * 0.04
            net_worth = total_assets - total_debt - payables - other_cl
            depreciation = fa * 0.08
            interest = total_debt * rng.uniform(0.095, 0.12)
            pbt = ebitda - depreciation - interest
            tax = max(0.0, pbt * 0.25)
            fin_rows.append({
                "applicant_id": applicant_id, "fiscal_year": fy_label(fy_end),
                "audit_status": audit_status if k == 0 else "audited",
                "revenue": round(revenue), "ebitda": round(ebitda), "depreciation": round(depreciation),
                "interest_expense": round(interest), "profit_before_tax": round(pbt), "tax": round(tax),
                "profit_after_tax": round(pbt - tax), "fixed_assets": round(fa), "inventory": round(inventory),
                "receivables": round(receivables), "cash_and_bank": round(cash), "current_assets": round(current_assets),
                "total_assets": round(total_assets), "short_term_borrowings": round(st_borrowings),
                "long_term_debt": round(lt_debt), "current_maturities_ltd": round(lt_debt / 5),
                "trade_payables": round(payables), "other_current_liabilities": round(other_cl),
                "current_liabilities": round(payables + st_borrowings + other_cl + lt_debt / 5),
                "total_debt": round(total_debt), "net_worth": round(net_worth),
            })
        self.tables["financial_statements"].extend(fin_rows)
        latest = fin_rows[0]

        reg_category = classify_msme(investment_pm, latest["revenue"] / reported_multiplier)
        udyam_category = reg_category if rng.random() > 0.06 else rng.choice([c for c in ("micro", "small", "medium") if c != reg_category])

        # ---- bank statements & GST (12 months before application) ----
        related_share_base = clip(rng.gauss(0.08, 0.05), 0.0, 0.3)
        bank_credit_mult = rng.uniform(1.4, 1.8) if fraud_type == "circular_trading" else 1.0
        gst_mult = rng.uniform(1.6, 2.4) if fraud_type == "gst_invoice_inflation" else 1.0
        aa_sourced = rng.random() < (0.75 if app_date >= date(2026, 1, 1) else 0.5)
        late_filings = 0
        bank_rows, gst_rows = [], []
        for m in statement_months:
            season = 1 + sector.seasonality * math.cos(2 * math.pi * (m.month - 10.5) / 12)
            monthly_true = true_revenue / 12 * season
            credits = monthly_true * GST_GROSS_UP * bank_credit_mult * rng.gauss(1, 0.06)
            related = related_share_base if fraud_type != "circular_trading" else rng.uniform(0.55, 0.8)
            bank_rows.append({
                "applicant_id": applicant_id, "month": m.strftime("%Y-%m"),
                "data_source": "account_aggregator" if aa_sourced else "uploaded_pdf",
                "total_credits": round(credits), "total_debits": round(credits * rng.gauss(0.98, 0.03)),
                "credit_count": max(3, int(credits / rng.uniform(25_000, 250_000))),
                "avg_eod_balance": round(max(2_000, credits * clip(0.06 + 0.04 * z + rng.gauss(0, 0.02), 0.005, 0.3))),
                "cash_deposit_pct": round(clip(rng.gauss(0.35 if sector.key in ("retail_trade", "restaurants") else 0.06, 0.04), 0, 0.9), 3),
                "related_party_credit_pct": round(clip(related + rng.gauss(0, 0.02), 0, 0.95), 3),
                "emi_debits": round(latest["long_term_debt"] / 48 + latest["long_term_debt"] * 0.105 / 12),
                "inward_cheque_bounces": poisson(rng, math.exp(-2.2 - 1.1 * z) / 1.0),
                "od_utilisation_pct": round(clip(0.65 - 0.12 * z + rng.gauss(0, 0.08), 0.05, 1.0), 3),
            })
            if gst_registered:
                due = add_months(m, 1).replace(day=20)
                days_late = 0 if rng.random() < clip(0.85 + 0.08 * z, 0.3, 0.99) else rng.randint(1, 60)
                filed = rng.random() < clip(0.97 + 0.03 * z, 0.75, 1.0)
                late_filings += 1 if (days_late or not filed) else 0
                taxable = monthly_true * gst_mult * rng.gauss(1, 0.05)
                gst_rows.append({
                    "applicant_id": applicant_id, "gstin": gstin, "return_type": "GSTR-3B", "tax_period": m.strftime("%Y-%m"),
                    "data_source": "gstn_api" if aa_sourced else "uploaded",
                    "filing_status": "filed" if filed else "not_filed",
                    "filed_on": (due + timedelta(days=days_late)).isoformat() if filed else "",
                    "days_late": days_late if filed else "",
                    "taxable_turnover": round(taxable) if filed else "",
                    "tax_paid": round(taxable * rng.uniform(0.05, 0.18)) if filed else "",
                })
        self.tables["bank_statement_monthly"].extend(bank_rows)
        self.tables["gst_returns_monthly"].extend(gst_rows)

        # ---- bureau ----
        bureau_rows = []
        for promoter in promoters:
            ntc = rng.random() < (0.12 if target == "micro" else 0.03)
            score = None if ntc else int(clip(752 + 55 * z + rng.gauss(0, 30), 300, 900))
            dpd_draw = z + rng.gauss(0, 0.5)
            max_dpd = 0 if ntc or dpd_draw > -1.0 else (30 if dpd_draw > -1.5 else (60 if dpd_draw > -1.9 else (90 if dpd_draw > -2.3 else 120)))
            promoter.update({"bureau_score": score if score is not None else "", "new_to_credit": ntc})
            bureau_rows.append({
                "subject_id": promoter["promoter_id"], "applicant_id": applicant_id, "subject_type": "individual",
                "bureau_score": score if score is not None else "", "cmr_rank": "", "new_to_credit": ntc,
                "active_accounts": 0 if ntc else poisson(rng, 2.5), "max_dpd_12m": max_dpd,
                "enquiries_6m": poisson(rng, max(0.2, 1.8 - 0.8 * z)),
                "written_off_or_settled_24m": (not ntc) and rng.random() < (0.25 if z < -1.6 else 0.004),
                "suit_filed": False, "wilful_defaulter": planted == "wilful_defaulter" and promoter is first_promoter,
                "report_date": (app_date - timedelta(days=rng.randint(0, 5))).isoformat(),
            })
        has_commercial = constitution != "proprietorship" and rng.random() < 0.8
        cmr = int(clip(round(5 - 2 * z + rng.gauss(0, 1)), 1, 10)) if has_commercial else ""
        bureau_rows.append({
            "subject_id": applicant_id, "applicant_id": applicant_id, "subject_type": "commercial",
            "bureau_score": "", "cmr_rank": cmr, "new_to_credit": not has_commercial,
            "active_accounts": poisson(rng, 3) if has_commercial else 0,
            "max_dpd_12m": bureau_rows[0]["max_dpd_12m"] if has_commercial else 0,
            "enquiries_6m": poisson(rng, max(0.2, 1.5 - 0.6 * z)), "written_off_or_settled_24m": False,
            "suit_filed": has_commercial and z < -1.8 and rng.random() < 0.3, "wilful_defaulter": False,
            "report_date": app_date.isoformat(),
        })
        self.tables["bureau_reports"].extend(bureau_rows)

        # ---- KYC ----
        aml_risk = weighted(rng, {"low": 65, "medium": 28, "high": 7})
        if planted == "pep_true_match":
            aml_risk = "high"
        kyc_date = app_date - timedelta(days=rng.randint(30, 2400))
        periodicity_years = {"low": 10, "medium": 8, "high": 2}[aml_risk]
        re_kyc_due = kyc_date + timedelta(days=365 * periodicity_years)
        bo_declared = constitution == "proprietorship" or rng.random() > 0.04
        self.tables["kyc_records"].append({
            "applicant_id": applicant_id, "ckyc_number": f"{rng.randint(10**13, 10**14 - 1)}",
            "kyc_mode": weighted(rng, {"video_kyc": 45, "in_person": 35, "digilocker": 20}),
            "kyc_verified_on": kyc_date.isoformat(), "aml_risk_category": aml_risk,
            "re_kyc_due_on": re_kyc_due.isoformat(),
            "kyc_status": "valid" if re_kyc_due >= app_date else "expired",
            "beneficial_owners_declared": bo_declared,
            "beneficial_owner_ids": "|".join(p["promoter_id"] for p in promoters if p["shareholding_pct"] >= 10),
            "address_verified": rng.random() > 0.02,
        })

        # ---- loan application ----
        purpose = weighted(rng, {"working_capital": 50, "capex_machinery": 25, "capex_expansion": 15, "vehicle_purchase": 5 if sector.key == "logistics" else 1, "refinance": 5})
        appetite = 1 + clip(-0.3 * z, -0.2, 0.8)
        if purpose == "working_capital":
            requested = true_revenue * rng.uniform(0.08, 0.20) * appetite
        else:  # term borrowing is sized off cash generation, a few years of EBITDA
            requested = max(true_revenue * margin, true_revenue * 0.02) * rng.uniform(0.5, 1.8) * appetite
        requested = max(50_000, round(requested / 10_000) * 10_000)
        if target == "micro" and requested <= MUDRA_MAX and rng.random() < 0.6:
            product = "PMMY Mudra"
            mudra_category = "Shishu" if requested <= 50_000 else "Kishore" if requested <= 5 * LAKH else "Tarun" if requested <= 10 * LAKH else "Tarun Plus"
            tenure = rng.choice((36, 48, 60))
        elif purpose == "working_capital":
            product = "TReDS Invoice Discounting" if sector.kind != "trading" and rng.random() < 0.15 else "Cash Credit"
            mudra_category = ""
            tenure = 3 if product.startswith("TReDS") else 12
        elif purpose in ("capex_machinery", "vehicle_purchase"):
            product, mudra_category, tenure = "Equipment Finance", "", rng.choice((36, 48, 60))
        else:
            product, mudra_category, tenure = "Term Loan", "", rng.choice((48, 60, 72, 84))
        collateral_type = weighted(rng, {"none_cgtmse": 35, "residential_property": 20, "commercial_property": 15,
                                         "hypothecation_stock_debtors": 15, "hypothecation_machinery": 10, "fd_lien": 5})
        if product == "PMMY Mudra":
            collateral_type = "none_cgtmse"
        collateral_value = 0 if collateral_type == "none_cgtmse" else round(requested * rng.uniform(0.6, 2.2), -4)
        self.tables["loan_applications"].append({
            "application_id": application_id, "applicant_id": applicant_id, "application_date": app_date.isoformat(),
            "product": product, "mudra_category": mudra_category, "purpose": purpose, "requested_amount": int(requested),
            "requested_tenure_months": tenure, "collateral_type": collateral_type, "collateral_value": int(collateral_value),
            "cgtmse_requested": collateral_type == "none_cgtmse" and requested <= CGTMSE_MAX,
            "channel": weighted(rng, {"branch": 35, "digital_aa": 40 if aa_sourced else 10, "dsa": 20, "ocen_marketplace": 5}),
            "account_aggregator_consent_id": f"AA-{rng.getrandbits(48):012x}" if aa_sourced else "",
            "relationship_manager": f"RM-{rng.randint(1, 40):03d}",
        })

        applicant = {
            "applicant_id": applicant_id, "legal_name": legal_name, "constitution": constitution,
            "pan": entity_pan, "gstin": gstin, "gst_registered": gst_registered,
            "udyam_number": f"UDYAM-{state_abbr}-{rng.randint(1, 40):02d}-{rng.randint(1, 9_999_999):07d}",
            "udyam_category": udyam_category, "derived_msme_category": reg_category,
            "cin_or_llpin": (f"U{sector.nic_2digit}{rng.randint(100, 999)}{state_abbr}{app_date.year - int(vintage_years)}PTC{rng.randint(100000, 999999)}"
                             if constitution == "private_limited" else (f"AA{rng.choice('ABCDEFGH')}-{rng.randint(1000, 9999)}" if constitution == "llp" else "")),
            "sector": sector.key, "sector_label": sector.label, "nic_2digit": sector.nic_2digit, "business_type": sector.kind,
            "sector_risk_tier": sector.risk_tier, "state": state, "city": city,
            "date_of_incorporation": (app_date - timedelta(days=int(vintage_years * 365))).isoformat(),
            "vintage_years": vintage_years, "employees": max(1, int(true_revenue / rng.uniform(8 * LAKH, 40 * LAKH))),
            "investment_plant_machinery": round(investment_pm), "women_led": women_led, "export_oriented": rng.random() < 0.12,
            "key_promoter_id": first_promoter["promoter_id"], "is_synthetic": True,
        }
        self.tables["applicants"].append(applicant)
        self.tables["promoters"].extend(promoters)

        # ---- underwrite, decide, perform ----
        loan = self.tables["loan_applications"][-1]
        kyc = self.tables["kyc_records"][-1]
        decision = self.underwrite(applicant, loan, fin_rows, bank_rows, gst_rows, bureau_rows, promoters, kyc, sector, policy)
        true_pd = 1 / (1 + math.exp(-(-3.4 - 1.25 * z + {"low": -0.3, "medium": 0, "high": 0.4, "negative": 0.6}[sector.risk_tier]
                                       + (2.0 if fraud_type else 0) + (0.5 if decision["dscr"] is not None and decision["dscr"] < 1.25 else 0))))
        self.finalize(decision, loan, true_pd, fraud_type, planted, rng)
        self.tables["underwriting_decisions"].append(decision)
        self.tables["ground_truth"].append({
            "applicant_id": applicant_id, "application_id": application_id, "latent_quality_z": round(z, 4),
            "true_pd_12m": round(true_pd, 4), "fraud_type": fraud_type or "", "planted_compliance_case": planted or "",
        })
        self.write_rm_notes(applicant, loan, promoters, z, fraud_type, sector, app_date)

    # ---- rules engine --------------------------------------------------

    def underwrite(self, applicant, loan, fin_rows, bank_rows, gst_rows, bureau_rows, promoters, kyc, sector, policy) -> dict:
        latest = fin_rows[0]
        reasons, conditions, refer = [], [], []
        knockouts = []
        is_mudra = loan["product"] == "PMMY Mudra"
        is_wc = loan["product"] in ("Cash Credit", "TReDS Invoice Discounting")
        amount = loan["requested_amount"]

        # Compliance screening
        hits = self.screen(promoters[0])
        for hit in hits:
            if hit["list_type"] == "SANCTIONS" and hit["dob_match"]:
                knockouts.append("CMP_SANCTIONS_MATCH")
            elif hit["list_type"] == "WILFUL_DEFAULTER" and hit["dob_match"]:
                knockouts.append("KO_WILFUL_DEFAULTER")
            elif hit["list_type"] == "PEP" and hit["dob_match"]:
                refer.append("CMP_PEP_ENHANCED_DUE_DILIGENCE")
            elif hit["list_type"] == "RELATED_PARTY":
                refer.append("CMP_RELATED_PARTY_LENDING")
            else:
                refer.append("CMP_POTENTIAL_WATCHLIST_MATCH")
        if kyc["kyc_status"] == "expired":
            refer.append("CMP_KYC_EXPIRED")
        if not kyc["beneficial_owners_declared"]:
            refer.append("CMP_BENEFICIAL_OWNER_UNDISCLOSED")

        # Knock-outs
        if sector.risk_tier == "negative":
            knockouts.append("KO_NEGATIVE_LIST_SECTOR")
        individual = [b for b in bureau_rows if b["subject_type"] == "individual"]
        commercial = next(b for b in bureau_rows if b["subject_type"] == "commercial")
        key_bureau = individual[0]
        score = key_bureau["bureau_score"]
        if score == "":
            if not is_mudra:
                conditions.append("CND_NEW_TO_CREDIT_GUARANTOR")
        elif score < policy.min_promoter_score:
            knockouts.append("KO_PROMOTER_SCORE_BELOW_MIN")
        if any(b["wilful_defaulter"] for b in bureau_rows) and "KO_WILFUL_DEFAULTER" not in knockouts:
            knockouts.append("KO_WILFUL_DEFAULTER")
        if any(b["written_off_or_settled_24m"] for b in bureau_rows):
            knockouts.append("KO_WRITTEN_OFF_OR_SETTLED")
        if any(b["suit_filed"] for b in bureau_rows):
            knockouts.append("KO_SUIT_FILED")
        if max(b["max_dpd_12m"] for b in bureau_rows) >= 90:
            knockouts.append("KO_NPA_HISTORY_90DPD")
        if applicant["vintage_years"] < policy.min_vintage_years and not (is_mudra and amount <= 5 * LAKH):
            knockouts.append("KO_VINTAGE_BELOW_MIN")
        if latest["net_worth"] <= 0:
            knockouts.append("KO_NEGATIVE_NET_WORTH")

        # Fraud / data-consistency checks
        bank_credits = sum(r["total_credits"] for r in bank_rows)
        gst_turnover = sum(r["taxable_turnover"] for r in gst_rows if r["taxable_turnover"] != "")
        filed_months = sum(1 for r in gst_rows if r["filing_status"] == "filed")
        gst_bank_var = fin_gst_var = None
        if filed_months >= 9:
            gst_annual = gst_turnover * 12 / filed_months
            bank_net = bank_credits / GST_GROSS_UP
            gst_bank_var = abs(gst_annual - bank_net) / max(gst_annual, bank_net)
            fin_gst_var = abs(latest["revenue"] - gst_annual) / max(latest["revenue"], gst_annual)
            if gst_bank_var > policy.gst_bank_variance_refer:
                refer.append("FRD_GST_BANK_MISMATCH")
            if policy.financials_gst_variance_refer is not None and fin_gst_var > policy.financials_gst_variance_refer:
                refer.append("FRD_FINANCIALS_GST_MISMATCH")
        elif applicant["gst_registered"]:
            conditions.append("CND_GST_RETURNS_INCOMPLETE")
        related_pct = sum(r["related_party_credit_pct"] * r["total_credits"] for r in bank_rows) / bank_credits
        if policy.related_party_credit_refer is not None and related_pct > policy.related_party_credit_refer:
            refer.append("FRD_RELATED_PARTY_CIRCULAR_CREDITS")
        if applicant["udyam_category"] != applicant["derived_msme_category"]:
            conditions.append("CND_UDYAM_CATEGORY_UPDATE")

        # Financial assessment
        indicative_rate = BENCHMARK_RATE + 3.5
        service_per_rupee = (12 * annuity(1, indicative_rate, loan["requested_tenure_months"])
                             if not is_wc else indicative_rate / 100)
        existing_service = latest["interest_expense"] + latest["current_maturities_ltd"]
        cash_accrual = latest["profit_after_tax"] + latest["depreciation"] + latest["interest_expense"]
        dscr = cash_accrual / (existing_service + amount * service_per_rupee)
        target_dscr = policy.dscr_approve_high_risk if sector.risk_tier == "high" else policy.dscr_approve
        recommended_amount = amount
        iscr = latest["ebitda"] / (latest["interest_expense"] + amount * indicative_rate / 100)
        if is_wc:
            if iscr < ISCR_FLOOR:
                reasons.append("FIN_ISCR_BELOW_FLOOR")
            elif iscr < ISCR_CONDITION:
                conditions.append("CND_ISCR_MARGINAL")
        elif dscr < policy.dscr_floor:
            reasons.append("FIN_DSCR_BELOW_FLOOR")
        elif dscr < target_dscr:
            affordable = (cash_accrual / target_dscr - existing_service) / service_per_rupee
            if affordable < 0.5 * amount:
                reasons.append("FIN_DSCR_BELOW_FLOOR")
            else:
                recommended_amount = round(affordable, -4)
                conditions.append("CND_AMOUNT_REDUCED_FOR_DSCR")

        tol = latest["total_debt"] + latest["trade_payables"] + latest["other_current_liabilities"]
        tol_tnw = tol / latest["net_worth"] if latest["net_worth"] > 0 else None
        if tol_tnw is not None:
            if tol_tnw > TOL_TNW_REJECT:
                reasons.append("FIN_LEVERAGE_EXCESSIVE")
            elif tol_tnw > MAX_TOL_TNW[sector.kind]:
                conditions.append("CND_PROMOTER_EQUITY_INFUSION")
        current_ratio = latest["current_assets"] / latest["current_liabilities"]
        if is_wc:
            if current_ratio < CURRENT_RATIO_REJECT:
                reasons.append("FIN_LIQUIDITY_INADEQUATE")
            elif current_ratio < CURRENT_RATIO_CONDITION:
                conditions.append("CND_LIQUIDITY_MONITORING")
            if loan["requested_amount"] <= 5 * CRORE:
                cap = WC_TURNOVER_CAP * latest["revenue"]
                if recommended_amount > cap:
                    recommended_amount = round(cap, -4)
                    conditions.append("CND_WC_CAPPED_AT_20PCT_TURNOVER")

        bounces = sum(r["inward_cheque_bounces"] for r in bank_rows)
        if bounces > BOUNCES_REJECT:
            reasons.append("BNK_EXCESSIVE_BOUNCES")
        elif bounces > BOUNCES_CONDITION:
            conditions.append("CND_BOUNCE_MONITORING")
        enquiries = max(b["enquiries_6m"] for b in bureau_rows)
        if enquiries > ENQUIRIES_6M_CONDITION:
            conditions.append("CND_HIGH_RECENT_ENQUIRIES")
        cmr = commercial["cmr_rank"]
        if cmr != "":
            if cmr >= CMR_REJECT:
                reasons.append("BUR_CMR_HIGH_RISK")
            elif cmr >= CMR_CONDITION:
                conditions.append("CND_CMR_ELEVATED")
        if 0 < key_bureau["max_dpd_12m"] < 90:
            conditions.append("CND_RECENT_DELINQUENCY_EXPLANATION")

        # Scorecard -> grade -> price
        late_share = (sum(1 for r in gst_rows if r["filing_status"] != "filed" or (r["days_late"] or 0) > 0) / len(gst_rows)) if gst_rows else 0.5
        points = (
            (10 if score == "" else clip((score - 600) / 300, 0, 1) * 25)
            + (clip((iscr - 1) / 2, 0, 1) if is_wc else clip(dscr - 1, 0, 1)) * 25
            + (clip((6 - tol_tnw) / 6, 0, 1) * 15 if tol_tnw is not None else 0)
            + min(applicant["vintage_years"] / 10, 1) * 10
            + max(0, 10 - 2 * bounces)
            + 10 * (1 - late_share)
            + ((10 - cmr) / 9 * 5 if cmr != "" else 2.5)
        )
        grade = next((g for cutoff, g in GRADE_CUTOFFS if points >= cutoff), "WP8")
        if grade == "WP8":
            reasons.append("RSK_SCORE_BELOW_CUTOFF")
        elif grade == "WP7":
            conditions.append("CND_HIGH_RISK_GRADE")

        if knockouts:
            recommendation = "REJECT"
        elif refer:
            recommendation = "REFER"
        elif reasons:
            recommendation = "REJECT"
        elif conditions:
            recommendation = "APPROVE_WITH_CONDITIONS"
        else:
            recommendation = "APPROVE"

        rate = ""
        if grade in GRADE_SPREADS and recommendation != "REJECT":
            rate = BENCHMARK_RATE + GRADE_SPREADS[grade] + (HIGH_RISK_SECTOR_PREMIUM if sector.risk_tier == "high" else 0)
            if loan["collateral_type"] in ("residential_property", "commercial_property"):
                rate -= PROPERTY_COLLATERAL_DISCOUNT
            rate = round(rate, 2)
        human_reasons = list(refer)
        if recommendation in ("APPROVE", "APPROVE_WITH_CONDITIONS") and recommended_amount > policy.credit_committee_threshold:
            human_reasons.append("HITL_ABOVE_CREDIT_COMMITTEE_THRESHOLD")

        return {
            "application_id": loan["application_id"], "applicant_id": applicant["applicant_id"],
            "policy_id": policy.policy_id, "engine_version": "uw-rules-1.0",
            "dscr": round(dscr, 3), "iscr": round(iscr, 3), "current_ratio": round(current_ratio, 3),
            "tol_tnw": round(tol_tnw, 3) if tol_tnw is not None else "",
            "gst_bank_variance": round(gst_bank_var, 3) if gst_bank_var is not None else "",
            "financials_gst_variance": round(fin_gst_var, 3) if fin_gst_var is not None else "",
            "related_party_credit_pct": round(related_pct, 3), "inward_bounces_12m": bounces,
            "promoter_bureau_score": score, "cmr_rank": cmr, "scorecard_points": round(points, 1), "risk_grade": grade,
            "recommendation": recommendation,
            "reason_codes": "|".join(knockouts + refer + reasons),
            "conditions": "|".join(conditions) if recommendation != "REJECT" else "",
            "human_review_required": bool(human_reasons), "human_review_reasons": "|".join(human_reasons),
            "requested_amount": amount,
            "recommended_amount": int(recommended_amount) if recommendation != "REJECT" else 0,
            "interest_rate_pct": rate,
            "cgtmse_cover": loan["cgtmse_requested"] and recommendation != "REJECT" and recommended_amount <= CGTMSE_MAX,
            "watchlist_hits": json.dumps(hits) if hits else "",
        }

    # ---- human-in-the-loop resolution and loan performance ------------

    def finalize(self, d: dict, loan: dict, true_pd: float, fraud_type, planted, rng) -> None:
        app_date = date.fromisoformat(loan["application_date"])
        decision_date = app_date + timedelta(days=rng.randint(2, 21))
        rec = d["recommendation"]
        final, decided_by, override = None, "engine", ""
        reasons = set(d["reason_codes"].split("|")) if d["reason_codes"] else set()

        if d["human_review_required"] and app_date >= AS_OF - timedelta(days=35):  # the live HITL queue
            final, decided_by = "PENDING_HUMAN_REVIEW", ""
        elif rec == "REFER":
            fraud_flags = {r for r in reasons if r.startswith("FRD_")}
            if fraud_flags:
                decided_by = "fraud_risk_unit"
                final = "DECLINED" if (fraud_type or rng.random() < 0.3) else None
            elif "CMP_POTENTIAL_WATCHLIST_MATCH" in reasons:
                decided_by = "compliance_officer"
                final = None if planted == "watchlist_false_positive" or rng.random() < 0.8 else "DECLINED"
            elif "CMP_RELATED_PARTY_LENDING" in reasons:
                decided_by = "board_credit_committee"
                final = None if rng.random() < 0.5 else "DECLINED"
            else:
                decided_by = "compliance_officer"
                final = None if rng.random() < 0.85 else "DECLINED"
            if final is None:  # cleared - fall back to the financial view, with conditions
                final = "DECLINED" if any(r.startswith(("FIN_", "BNK_", "BUR_", "RSK_")) for r in reasons) else "APPROVED_WITH_CONDITIONS"
                override = "Cleared on review; " + ("financial criteria not met" if final == "DECLINED" else "standard conditions applied")
        elif rec == "REJECT":
            final = "DECLINED"
            borderline = d["reason_codes"] in ("FIN_DSCR_BELOW_FLOOR", "FIN_ISCR_BELOW_FLOOR", "RSK_SCORE_BELOW_CUTOFF") and d["dscr"] >= 0.95
            if borderline and rng.random() < 0.25:
                final, decided_by = "APPROVED_WITH_CONDITIONS", "credit_officer"
                override = rng.choice(("Confirmed export order book covers debt service", "Promoter offered additional collateral",
                                       "Seasonal dip in FY; current-year provisional numbers stronger"))
        else:
            final = "APPROVED" if rec == "APPROVE" else "APPROVED_WITH_CONDITIONS"
            if d["human_review_required"]:
                decided_by = "credit_committee"
                if rng.random() < 0.1:
                    final, override = "DECLINED", "Committee concern on concentration risk"
            elif rng.random() < 0.03:
                final, decided_by, override = "DECLINED", "credit_officer", "Site visit found unit partially idle"
            if final.startswith("APPROVED") and rng.random() < 0.04:
                final = "WITHDRAWN_BY_APPLICANT"

        d.update({"final_decision": final, "decided_by": decided_by, "override_reason": override,
                  "decision_date": decision_date.isoformat() if final != "PENDING_HUMAN_REVIEW" else ""})

        if not final.startswith("APPROVED"):
            return
        disbursed = decision_date + timedelta(days=rng.randint(3, 15))
        if disbursed > AS_OF:
            return
        mob = min(12, months_between(disbursed, AS_OF))
        default_month = rng.randint(1, 12) if rng.random() < true_pd else None
        if default_month is not None and default_month <= mob:
            status, dpd = "NPA", 90 + 30 * (mob - default_month)
        elif default_month is not None and default_month - mob <= 2:
            status, dpd = ("SMA-2", 75) if default_month - mob == 1 else ("SMA-1", 45)
        else:
            status, dpd = ("SMA-0", 15) if rng.random() < 0.04 else ("STANDARD", 0)
        self.tables["loan_performance"].append({
            "application_id": d["application_id"], "disbursed_on": disbursed.isoformat(),
            "sanctioned_amount": d["recommended_amount"] or d["requested_amount"], "months_on_book": mob,
            "current_dpd": dpd, "asset_classification": status, "performance_window_complete": mob == 12,
            "default_90dpd_12m": (status == "NPA") if mob == 12 else "",
            "as_of": AS_OF.isoformat(),
        })

    # ---- relationship-manager notes (episodic memory) ------------------

    def write_rm_notes(self, applicant, loan, promoters, z, fraud_type, sector, app_date) -> None:
        rng = self.rng
        rm, who = loan["relationship_manager"], promoters[0]["name"]
        t = app_date - timedelta(days=rng.randint(20, 90))
        emp = applicant["employees"]

        def note(channel, text, facts=()):
            nonlocal t
            t += timedelta(days=rng.randint(3, 20))
            self.rm_notes.append({"applicant_id": applicant["applicant_id"], "timestamp": f"{t.isoformat()}T{rng.randint(9, 18):02d}:{rng.choice(('00', '15', '30', '45'))}:00+05:30",
                                  "author": rm, "channel": channel, "note": text, "facts": [{"key": k, "value": v} for k, v in facts]})

        util = int(clip(70 + 12 * z + rng.gauss(0, 8), 20, 98))
        note("site_visit", f"Visited the {applicant['city']} unit. Capacity utilisation looks around {util}%, roughly {emp} people on rolls. Premises {'well maintained' if z > -0.5 else 'partly idle, some machines covered'}.",
             [("capacity_utilisation_pct", util), ("employees", emp)])
        if rng.random() < 0.6:
            order = int(clip(rng.gauss(0.08, 0.04), 0.01, 0.3) * applicant["investment_plant_machinery"] / LAKH + rng.randint(5, 60))
            note("call", f"{who} says a new order from {rng.choice(BUYERS)} worth about Rs {order} lakh is expected next quarter.",
                 [("expected_order_lakh", order)])
        conc = int(clip(rng.gauss(35, 15), 8, 85))
        note("branch_visit", f"Top customer is about {conc}% of sales per the promoter. Requested {loan['product']} of Rs {loan['requested_amount'] / LAKH:.1f} lakh for {loan['purpose'].replace('_', ' ')}.",
             [("top_customer_concentration_pct", conc)])
        if rng.random() < 0.35:
            new_emp = max(1, emp + rng.randint(-5, 15))
            note("call", f"Follow-up: headcount is now {new_emp} after {'hiring for the new line' if new_emp >= emp else 'some attrition'}.", [("employees", new_emp)])
        if z < -0.8 and rng.random() < 0.5:
            demand = rng.randint(3, 40)
            note("branch_visit", f"Promoter mentioned a pending GST demand notice of about Rs {demand} lakh, currently under appeal. Not visible in bureau.",
                 [("pending_tax_demand_lakh", demand)])
        if fraud_type == "circular_trading" and rng.random() < 0.6:
            note("site_visit", "Large inflows from two group concerns at the same address; promoter was vague about the underlying trade.")
        if rng.random() < 0.05:
            note("whatsapp", f"{who} shared Aadhaar ending {rng.randint(1000, 9999)} over WhatsApp for re-KYC. Advised to use video KYC instead; message deleted.")
        if rng.random() < 0.15:
            note("call", f"{who}'s family member is expected to join the business next year; succession planning discussed.")

    # ---- evaluation sets ------------------------------------------------

    def build_eval_sets(self) -> None:
        rng = self.rng
        by_rec: dict[str, list[dict]] = {}
        for d in self.tables["underwriting_decisions"]:
            by_rec.setdefault(d["recommendation"], []).append(d)
        self.agent_eval = []
        for rec, rows in sorted(by_rec.items()):
            for d in rng.sample(rows, min(12, len(rows))):
                self.agent_eval.append({
                    "application_id": d["application_id"], "policy_id": d["policy_id"],
                    "expected_recommendation": d["recommendation"],
                    "expected_reason_codes": [r for r in d["reason_codes"].split("|") if r],
                    "expected_conditions": [c for c in d["conditions"].split("|") if c],
                    "expected_human_review": d["human_review_required"],
                    "expected_risk_grade": d["risk_grade"],
                })
        truth = {g["application_id"]: g for g in self.tables["ground_truth"]}
        self.compliance_eval = []
        for d in self.tables["underwriting_decisions"]:
            flags = [r for r in d["reason_codes"].split("|") if r.startswith(("CMP_", "FRD_")) or r == "KO_WILFUL_DEFAULTER"]
            g = truth[d["application_id"]]
            if flags or g["planted_compliance_case"] or g["fraud_type"]:
                self.compliance_eval.append({
                    "application_id": d["application_id"], "expected_flags": flags,
                    "ground_truth_case": g["planted_compliance_case"] or g["fraud_type"],
                    "expected_action": "reject_and_report" if "CMP_SANCTIONS_MATCH" in flags
                    else "reject" if "KO_WILFUL_DEFAULTER" in flags else "refer_to_human" if flags else "not_detected_by_rules",
                })
        clean = [d for d in self.tables["underwriting_decisions"] if not d["reason_codes"] and not truth[d["application_id"]]["fraud_type"]]
        for d in rng.sample(clean, min(15, len(clean))):
            self.compliance_eval.append({"application_id": d["application_id"], "expected_flags": [], "ground_truth_case": "clean",
                                         "expected_action": "pass"})

    # ---- output ---------------------------------------------------------

    def write(self, out: Path) -> dict:
        out.mkdir(parents=True, exist_ok=True)
        counts = {}
        for name, rows in self.tables.items():
            with (out / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            counts[f"{name}.csv"] = len(rows)
        with (out / "rm_interactions.jsonl").open("w", encoding="utf-8") as f:
            for n in self.rm_notes:
                f.write(json.dumps(n, ensure_ascii=False) + "\n")
        counts["rm_interactions.jsonl"] = len(self.rm_notes)
        (out / "agent_eval_cases.json").write_text(json.dumps(self.agent_eval, indent=2), encoding="utf-8")
        (out / "compliance_eval_cases.json").write_text(json.dumps(self.compliance_eval, indent=2), encoding="utf-8")
        counts["agent_eval_cases.json"] = len(self.agent_eval)
        counts["compliance_eval_cases.json"] = len(self.compliance_eval)
        recs: dict[str, int] = {}
        finals: dict[str, int] = {}
        for d in self.tables["underwriting_decisions"]:
            recs[d["recommendation"]] = recs.get(d["recommendation"], 0) + 1
            finals[d["final_decision"]] = finals.get(d["final_decision"], 0) + 1
        manifest = {"seed": self.seed, "applicants": self.n, "as_of": AS_OF.isoformat(), "files": counts,
                    "recommendations": recs, "final_decisions": finals,
                    "policies": [{"policy_id": p.policy_id, "effective_from": p.effective_from.isoformat()} for p in POLICIES],
                    "note": "Synthetic data. Identifiers are random and format-valid only; no real persons or businesses."}
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=500, help="number of MSME applicants")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    gen = Generator(args.n, args.seed)
    gen.generate()
    manifest = gen.write(args.out)
    print(json.dumps({k: manifest[k] for k in ("files", "recommendations", "final_decisions")}, indent=2))


if __name__ == "__main__":
    main()
