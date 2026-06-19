"""Local-only financial calculations for Ask tools (no external calls)."""

from __future__ import annotations

from decimal import Decimal, getcontext
from typing import Any

getcontext().prec = 10


def calculate_compound_interest(
    principal: float,
    rate: float,
    years: int,
) -> dict[str, Any]:
    """A = P(1 + r)^t. Rate is annual decimal (e.g. 0.05 for 5%)."""
    if years < 0 or rate < 0 or principal <= 0:
        raise ValueError("principal > 0, rate >= 0, years >= 0 required")
    p = Decimal(str(principal))
    r = Decimal(str(rate))
    amount = p * (Decimal(1) + r) ** years
    interest = amount - p
    return {
        "final_amount": float(amount.quantize(Decimal("0.01"))),
        "total_interest": float(interest.quantize(Decimal("0.01"))),
        "principal": principal,
        "rate_decimal": rate,
        "years": years,
    }


def calculate_simple_interest(
    principal: float,
    rate: float,
    years: float,
) -> dict[str, Any]:
    """Simple interest: I = P * r * t. Rate is annual decimal."""
    if years < 0 or rate < 0 or principal <= 0:
        raise ValueError("principal > 0, rate >= 0, years >= 0 required")
    p = Decimal(str(principal))
    r = Decimal(str(rate))
    t = Decimal(str(years))
    interest = p * r * t
    final_amount = p + interest
    return {
        "final_amount": float(final_amount.quantize(Decimal("0.01"))),
        "total_interest": float(interest.quantize(Decimal("0.01"))),
        "principal": principal,
        "rate_decimal": rate,
        "years": years,
    }


def calculate_cd_maturity_value(
    principal: float,
    rate_apr: float,
    term_months: int,
    *,
    compounding: str = "simple",
) -> dict[str, Any]:
    """Estimate value at maturity for a CD. rate_apr is percent (e.g. 4.5 for 4.5%)."""
    if principal <= 0 or term_months <= 0 or rate_apr < 0:
        raise ValueError("principal > 0, term_months > 0, rate_apr >= 0 required")
    rate_decimal = rate_apr / 100.0
    years = term_months / 12.0
    if compounding == "compound":
        result = calculate_compound_interest(principal, rate_decimal, max(1, int(round(years))))
        if years < 1:
            # Scale compound result for fractional year via simple for short terms
            result = calculate_simple_interest(principal, rate_decimal, years)
    else:
        result = calculate_simple_interest(principal, rate_decimal, years)
    return {
        **result,
        "rate_apr_percent": rate_apr,
        "term_months": term_months,
        "compounding": compounding,
        "note": "Estimate only; institution day-count rules may differ.",
    }


def compare_after_tax_yield(
    principal: float,
    rate_apr: float,
    years: float,
    federal_marginal_rate: float,
    *,
    state_rate: float = 0.0,
) -> dict[str, Any]:
    """
    Approximate after-tax interest. Rates are decimals (0.22 = 22%).
    Awareness only — not tax advice.
    """
    if principal <= 0 or years < 0 or rate_apr < 0:
        raise ValueError("principal > 0, years >= 0, rate_apr >= 0 required")
    gross = calculate_simple_interest(principal, rate_apr / 100.0, years)
    combined_tax = min(1.0, max(0.0, federal_marginal_rate) + max(0.0, state_rate))
    tax_on_interest = gross["total_interest"] * combined_tax
    after_tax_interest = gross["total_interest"] - tax_on_interest
    return {
        "principal": principal,
        "rate_apr_percent": rate_apr,
        "years": years,
        "gross_interest": gross["total_interest"],
        "estimated_tax": round(tax_on_interest, 2),
        "after_tax_interest": round(after_tax_interest, 2),
        "federal_marginal_rate": federal_marginal_rate,
        "state_rate": state_rate,
        "assumptions": [
            "Ordinary income tax on interest",
            "No deductions or credits modeled",
            "Not tax advice",
        ],
    }
