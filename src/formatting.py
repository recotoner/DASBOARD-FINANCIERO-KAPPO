from __future__ import annotations

import math

import pandas as pd


COLUMN_LABELS = {
    "periodo": "Período",
    "grupo": "Grupo",
    "cuenta": "Cuenta",
    "nivel": "Nivel",
    "monto": "Monto",
    "filas": "Filas",
    "ingresos_explotacion": "Ingresos explotación",
    "costos_explotacion": "Costos explotación",
    "margen_explotacion": "Margen explotación",
    "margen_pct": "Margen %",
    "gastos_administracion_ventas": "Gastos adm. y ventas",
    "gastos_financieros": "Gastos financieros / bancarios",
    "resultado_operacional": "Resultado operacional",
    "utilidad_perdida_ejercicio": "Resultado final",
    "var_mom_ingresos": "Var. ingresos mes",
    "var_mom_gastos_administracion_ventas": "Var. gastos mes",
    "var_mom_resultado_final": "Var. resultado mes",
    "periodo_inicial": "Período inicial",
    "monto_inicial": "Valor inicial",
    "periodo_final": "Período final",
    "monto_final": "Valor final",
    "variacion_abs": "Variación",
    "variacion_pct": "Variación %",
    "severidad": "Severidad",
    "indicador": "Indicador",
    "alerta": "Alerta",
    "valor": "Valor",
    "umbral": "Umbral",
    "detalle": "Detalle",
    "suma_detalle": "Suma detalle",
    "total_kame_normalizado": "Total Kame normalizado",
    "diferencia": "Diferencia",
    "cuadra": "Cuadra",
}

KPI_MONEY_COLUMNS = [
    "ingresos_explotacion",
    "costos_explotacion",
    "margen_explotacion",
    "gastos_administracion_ventas",
    "gastos_financieros",
    "resultado_operacional",
    "utilidad_perdida_ejercicio",
    "var_mom_ingresos",
    "var_mom_gastos_administracion_ventas",
    "var_mom_resultado_final",
]

RANKING_COLUMNS = [
    "grupo",
    "cuenta",
    "periodo_inicial",
    "monto_inicial",
    "periodo_final",
    "monto_final",
    "variacion_abs",
]


def format_clp(value: object) -> str:
    number = _to_float(value)
    if _is_missing(number):
        return "N/D"
    sign = "-" if number < 0 else ""
    return f"{sign}${abs(number):,.0f}"


def format_signed_clp(value: object) -> str:
    number = _to_float(value)
    if _is_missing(number):
        return "N/D"
    if number > 0:
        return f"+{format_clp(number)}"
    return format_clp(number)


def format_pct(value: object) -> str:
    number = _to_float(value)
    if _is_missing(number):
        return "N/D"
    return f"{number * 100:,.1f}%"


def format_signed_pct(value: object) -> str:
    number = _to_float(value)
    if _is_missing(number):
        return "N/D"
    sign = "+" if number > 0 else ""
    return f"{sign}{number * 100:,.1f}%"


def rename_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    return df.rename(columns={col: COLUMN_LABELS.get(col, col) for col in df.columns})


def format_kpis_table(kpis: pd.DataFrame) -> pd.DataFrame:
    if kpis is None or kpis.empty:
        return pd.DataFrame()
    out = kpis.copy()
    for column in KPI_MONEY_COLUMNS:
        if column in out.columns:
            out[column] = out[column].map(format_clp)
    if "margen_pct" in out.columns:
        out["margen_pct"] = out["margen_pct"].map(format_pct)
    return rename_for_display(out)


def format_ranking_table(ranking: pd.DataFrame) -> pd.DataFrame:
    if ranking is None or ranking.empty:
        return pd.DataFrame()
    columns = [column for column in RANKING_COLUMNS if column in ranking.columns]
    out = ranking[columns].copy()
    for column in ["monto_inicial", "monto_final", "variacion_abs"]:
        if column in out.columns:
            out[column] = out[column].map(format_clp)
    return rename_for_display(out)


def format_alerts_table(alerts: pd.DataFrame) -> pd.DataFrame:
    if alerts is None or alerts.empty:
        return pd.DataFrame()
    columns = [
        "periodo",
        "severidad",
        "indicador",
        "alerta",
        "valor",
        "umbral",
        "detalle",
    ]
    out = alerts[[column for column in columns if column in alerts.columns]].copy()
    return rename_for_display(out)


def format_control_table(control_rows: list[dict] | pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(control_rows)
    if out.empty:
        return out
    for column in ["suma_detalle", "total_kame_normalizado", "diferencia"]:
        if column in out.columns:
            out[column] = out[column].map(format_clp)
    return rename_for_display(out)


def format_group_summary_table(summary: pd.DataFrame) -> pd.DataFrame:
    if summary is None or summary.empty:
        return pd.DataFrame()
    out = summary.copy()
    if "monto" in out.columns:
        out["monto"] = out["monto"].map(format_clp)
    return rename_for_display(out)


def _to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _is_missing(value: float) -> bool:
    try:
        return math.isnan(float(value))
    except (TypeError, ValueError):
        return True

