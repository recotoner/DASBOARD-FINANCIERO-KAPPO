from __future__ import annotations

import math
from typing import Any

import pandas as pd


BALANCE_KPI_KEYS = [
    "periodo",
    "activo_total",
    "activo_corriente",
    "disponible",
    "valores_negociables",
    "cuentas_por_cobrar",
    "inventarios",
    "activo_fijo",
    "pasivo_corriente",
    "obligaciones_bancarias_cp",
    "cuentas_por_pagar",
    "patrimonio",
    "patrimonio_contable",
    "resultado_ejercicio",
    "patrimonio_mas_resultado",
    "patrimonio_ajustado_por_resultado",
    "capital_trabajo",
    "razon_corriente",
    "prueba_acida",
    "disponible_sobre_pasivo_corriente",
    "deuda_corriente_sobre_patrimonio",
    "deuda_corriente_sobre_patrimonio_contable",
    "deuda_corriente_sobre_patrimonio_ajustado",
    "obligaciones_bancarias_cp_sobre_pasivo_corriente",
    "inventarios_sobre_activo_corriente",
    "cuentas_por_cobrar_sobre_activo_corriente",
]


def calculate_balance_kpis(base_balance: pd.DataFrame) -> dict[str, Any]:
    """Calculate reliable initial KPIs from Base_balance_normalizada."""
    if base_balance is None or base_balance.empty:
        return {key: None for key in BALANCE_KPI_KEYS}

    periodo = str(base_balance["periodo"].dropna().iloc[0])
    activo_total = _amount_by_code(base_balance, "1")
    activo_corriente = _amount_by_code(base_balance, "1.01")
    disponible = _amount_by_code(base_balance, "1.01.01")
    valores_negociables = _amount_by_code(base_balance, "1.01.03")
    cuentas_por_cobrar = _amount_by_code(base_balance, "1.01.05")
    inventarios = _amount_by_code(base_balance, "1.01.09")
    activo_fijo = _amount_by_code(base_balance, "1.02")
    pasivo_corriente = _amount_by_code(base_balance, "2.01")
    obligaciones_bancarias_cp = _amount_by_code(base_balance, "2.01.01")
    cuentas_por_pagar = _amount_by_code(base_balance, "2.01.07")
    patrimonio = _amount_by_code(base_balance, "2.03")
    patrimonio_contable = patrimonio
    resultado_ejercicio = _amount_by_level_group(base_balance, "resultado", "Resultado")
    patrimonio_mas_resultado = patrimonio_contable + resultado_ejercicio
    patrimonio_ajustado_por_resultado = patrimonio_mas_resultado

    return {
        "periodo": periodo,
        "activo_total": activo_total,
        "activo_corriente": activo_corriente,
        "disponible": disponible,
        "valores_negociables": valores_negociables,
        "cuentas_por_cobrar": cuentas_por_cobrar,
        "inventarios": inventarios,
        "activo_fijo": activo_fijo,
        "pasivo_corriente": pasivo_corriente,
        "obligaciones_bancarias_cp": obligaciones_bancarias_cp,
        "cuentas_por_pagar": cuentas_por_pagar,
        "patrimonio": patrimonio,
        "patrimonio_contable": patrimonio_contable,
        "resultado_ejercicio": resultado_ejercicio,
        "patrimonio_mas_resultado": patrimonio_mas_resultado,
        "patrimonio_ajustado_por_resultado": patrimonio_ajustado_por_resultado,
        "capital_trabajo": activo_corriente - pasivo_corriente,
        "razon_corriente": _safe_div(activo_corriente, pasivo_corriente),
        "prueba_acida": _safe_div(activo_corriente - inventarios, pasivo_corriente),
        "disponible_sobre_pasivo_corriente": _safe_div(disponible, pasivo_corriente),
        "deuda_corriente_sobre_patrimonio": _safe_div(pasivo_corriente, patrimonio),
        "deuda_corriente_sobre_patrimonio_contable": _safe_div(
            pasivo_corriente, patrimonio_contable
        ),
        "deuda_corriente_sobre_patrimonio_ajustado": _safe_div(
            pasivo_corriente, patrimonio_ajustado_por_resultado
        ),
        "obligaciones_bancarias_cp_sobre_pasivo_corriente": _safe_div(
            obligaciones_bancarias_cp, pasivo_corriente
        ),
        "inventarios_sobre_activo_corriente": _safe_div(inventarios, activo_corriente),
        "cuentas_por_cobrar_sobre_activo_corriente": _safe_div(
            cuentas_por_cobrar, activo_corriente
        ),
    }


def balance_kpis_to_dataframe(kpis: dict[str, Any]) -> pd.DataFrame:
    if not kpis:
        return pd.DataFrame(columns=["indicador", "valor"])
    return pd.DataFrame(
        [{"indicador": key, "valor": value} for key, value in kpis.items()]
    )


def _amount_by_code(base: pd.DataFrame, code: str) -> float:
    rows = base[(base["nivel"] == "total") & (base["codigo"].astype(str) == code)]
    if rows.empty:
        return 0.0
    return float(rows.iloc[0]["monto"])


def _amount_by_level_group(base: pd.DataFrame, level: str, group: str) -> float:
    rows = base[(base["nivel"] == level) & (base["grupo"] == group)]
    if rows.empty:
        return 0.0
    return float(rows["monto"].sum())


def _safe_div(num: float, den: float) -> float:
    if den in (0, 0.0) or den is None:
        return float("nan")
    try:
        return float(num) / float(den)
    except (TypeError, ValueError, ZeroDivisionError):
        return float("nan")


def is_missing(value: Any) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return value is None
