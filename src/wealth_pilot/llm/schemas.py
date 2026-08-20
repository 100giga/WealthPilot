"""Structured-output schemas for the intake pipeline (Milestone 1).

JSON-mode / function-calling only guarantees the *shape* of a response.
These models are the second validation layer that checks types, ranges
and business rules a schema alone can never enforce — e.g. a currency
code that isn't a real currency, or a negative savings balance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

RiskTolerance = Literal["conservative", "moderate", "aggressive"]
SupportedCurrency = Literal["INR", "USD", "EUR", "GBP"]


class FinancialProfile(BaseModel):
    """The validated result of a client intake conversation."""

    full_name: str = Field(min_length=1)
    annual_income: float = Field(ge=0)
    monthly_expenses: float = Field(ge=0)
    current_savings: float = Field(ge=0)
    risk_tolerance: RiskTolerance
    investment_horizon_years: int = Field(ge=1, le=50)
    primary_goal: str = Field(min_length=1)
    currency: SupportedCurrency = "INR"

    @field_validator("annual_income")
    @classmethod
    def income_must_exceed_expenses_times_zero(cls, v: float) -> float:
        # Shape-valid JSON can still smuggle a nonsensical value through —
        # e.g. {"annual_income": -450.0} parses fine as a float.
        if v < 0:
            raise ValueError("annual_income cannot be negative")
        return v


class RiskAssessment(BaseModel):
    score: int = Field(ge=0, le=100)
    tolerance: RiskTolerance
    rationale: str
    recommended_equity_allocation_pct: int = Field(ge=0, le=100)


class InvestmentPlan(BaseModel):
    summary: str
    monthly_contribution: float = Field(ge=0)
    allocation: dict[str, int]  # asset class -> percent
    requires_human_approval: bool = True

    @field_validator("allocation")
    @classmethod
    def allocation_sums_to_100(cls, v: dict[str, int]) -> dict[str, int]:
        total = sum(v.values())
        if total != 100:
            raise ValueError(f"allocation must sum to 100, got {total}")
        return v
