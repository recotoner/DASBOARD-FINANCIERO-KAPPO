from __future__ import annotations

import io
import math
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from api.schemas import AnalyzeResponse
from src.adapters.kame_balance import load_kame_balance
from src.adapters.kame_eerr import load_kame_eerr
from src.balance_metrics import calculate_balance_kpis
from src.credit_metrics import calculate_credit_kpis
from src.metrics import (
    COMPARISON_TYPES,
    build_comparison_context,
    calculate_financial_kpis,
    compare_kpis,
    latest_period_kpis,
)


MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = {".xlsx", ".xlsm"}
PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

app = FastAPI(
    title="Kappo Financial API",
    version="0.1.0",
    description="API paralela del Dashboard Financiero Kappo.",
)


class NamedBytesIO(io.BytesIO):
    def __init__(self, content: bytes, name: str):
        super().__init__(content)
        self.name = name


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kappo-financial-api"}


@app.post("/v1/analyze", response_model=AnalyzeResponse)
async def analyze(
    eerr_file: UploadFile = File(...),
    balance_file: UploadFile = File(...),
    comparison_type: str = Form("ultimo_vs_anterior"),
    balance_period: str | None = Form(None),
    include_agent: bool = Form(False),
) -> AnalyzeResponse:
    if comparison_type not in COMPARISON_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Tipo de comparación no válido.",
                "allowed": list(COMPARISON_TYPES),
            },
        )

    if balance_period and not PERIOD_PATTERN.match(balance_period):
        raise HTTPException(
            status_code=422,
            detail="balance_period debe tener formato YYYY-MM.",
        )

    eerr_stream = await _read_excel(eerr_file)
    balance_stream = await _read_excel(balance_file)

    try:
        base_eerr, eerr_diagnostics = load_kame_eerr(eerr_stream)
        base_balance, balance_diagnostics = load_kame_balance(
            balance_stream,
            periodo=balance_period,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No fue posible normalizar los archivos: {exc}",
        ) from exc

    if base_eerr.empty:
        raise HTTPException(status_code=422, detail="El EERR no generó registros.")
    if base_balance.empty:
        raise HTTPException(status_code=422, detail="El Balance no generó registros.")

    monthly_kpis = calculate_financial_kpis(base_eerr)
    comparison_context = build_comparison_context(
        monthly_kpis,
        comparison_type,
    )
    comparison = compare_kpis(monthly_kpis, comparison_context)
    balance_kpis = calculate_balance_kpis(base_balance)

    eerr_credit_basis = comparison.get("final") or latest_period_kpis(monthly_kpis)
    credit_kpis = calculate_credit_kpis(
        eerr_kpis=eerr_credit_basis,
        balance_kpis=balance_kpis,
        comparison_context=comparison_context,
    )

    eerr_summary = eerr_diagnostics.get("resumen_control_cuadratura", {})
    eerr_status = eerr_summary.get("estado_general", "REVISAR")

    balance_control = balance_diagnostics.get("control_balance", {})
    balance_status = "OK" if balance_control.get("cuadra_balance") else "REVISAR"
    integrated_ready = eerr_status == "OK" and balance_status == "OK"

    result = {
        "request_id": str(uuid.uuid4()),
        "status": "ok" if integrated_ready else "review_required",
        "input": {
            "eerr_filename": eerr_file.filename or "eerr.xlsx",
            "balance_filename": balance_file.filename or "balance.xlsx",
            "comparison_type": comparison_type,
            "balance_period": balance_period,
            "include_agent": include_agent,
        },
        "validation": {
            "integrated_ready": integrated_ready,
            "eerr": {
                "status": eerr_status,
                "periods_detected": eerr_diagnostics.get("periodos_detectados", []),
                "summary": eerr_summary,
                "control_details": eerr_diagnostics.get("control_cuadratura", []),
                "exceptions": eerr_diagnostics.get("exceptions", []),
            },
            "balance": {
                "status": balance_status,
                "period": balance_kpis.get("periodo"),
                "control": balance_control,
            },
        },
        "monthly_kpis": monthly_kpis,
        "comparison_context": comparison_context,
        "comparison": comparison,
        "balance_kpis": balance_kpis,
        "credit_kpis": credit_kpis,
        "agent": {
            "requested": include_agent,
            "status": "not_configured" if include_agent else "not_requested",
        },
    }
    return AnalyzeResponse.model_validate(_json_safe(result))


async def _read_excel(upload: UploadFile) -> NamedBytesIO:
    filename = upload.filename or ""
    suffix = Path(filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Solo se aceptan archivos .xlsx o .xlsm.",
        )

    content = await upload.read()
    if not content:
        raise HTTPException(status_code=422, detail=f"{filename} está vacío.")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"{filename} supera el límite de 20 MB.",
        )

    return NamedBytesIO(content, filename)


def _json_safe(value: Any) -> Any:
    if isinstance(value, pd.DataFrame):
        return _json_safe(value.to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return _json_safe(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
