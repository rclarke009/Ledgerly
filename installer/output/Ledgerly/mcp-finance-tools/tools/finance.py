"""Compound interest and related financial calculations for MCP tools."""

from decimal import Decimal, getcontext

from pydantic import BaseModel, Field

getcontext().prec = 10  # good precision for money


class CompoundInput(BaseModel):
    """Input schema for compound interest calculation."""

    principal: float = Field(
        ..., description="Initial investment amount (e.g. 10000)"
    )
    rate: float = Field(
        ...,
        description="Annual interest rate as decimal (e.g. 0.05 for 5%)",
    )
    years: int = Field(..., description="Number of years (integer)")


class CompoundOutput(BaseModel):
    """Output schema for compound interest calculation."""

    final_amount: float
    total_interest: float


def calculate_compound_interest(
    principal: float, rate: float, years: int
) -> dict:
    """
    Calculate compound interest.

    Formula: A = P(1 + r)^t
    Returns final amount and total interest earned.
    """
    if years < 0 or rate < 0 or principal <= 0:
        raise ValueError(
            "Invalid inputs: principal > 0, rate >= 0, years >= 0"
        )

    p = Decimal(str(principal))
    r = Decimal(str(rate))
    t = years

    amount = p * (Decimal(1) + r) ** t
    interest = amount - p

    return {
        "final_amount": float(amount.quantize(Decimal("0.01"))),
        "total_interest": float(interest.quantize(Decimal("0.01"))),
    }
