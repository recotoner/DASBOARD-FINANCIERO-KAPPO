from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class InputSummary(BaseModel):
    eerr_filename: str
    balance_filename: str
    comparison_type: str
    balance_period: str | None = None
    include_agent: bool = False


class EerrValidation(BaseModel):
    status: Literal["OK", "REVISAR"]
    periods_detected: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    control_details: list[dict[str, Any]] = Field(default_factory=list)
    exceptions: list[dict[str, Any]] = Field(default_factory=list)


class BalanceValidation(BaseModel):
    status: Literal["OK", "REVISAR"]
    period: str | None = None
    control: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    integrated_ready: bool
    eerr: EerrValidation
    balance: BalanceValidation


class AgentResult(BaseModel):
    requested: bool
    status: Literal["not_requested", "not_configured"]


class AnalyzeResponse(BaseModel):
    request_id: str
    status: Literal["ok", "review_required"]
    input: InputSummary
    validation: ValidationResult
    monthly_kpis: list[dict[str, Any]]
    comparison_context: dict[str, Any]
    comparison: dict[str, Any]
    balance_kpis: dict[str, Any]
    credit_kpis: dict[str, Any]
    agent: AgentResult
