from __future__ import annotations

import math

import pandas as pd


KPI_COLUMNS = [
    "periodo",
    "ingresos_explotacion",
    "costos_explotacion",
    "margen_explotacion",
    "margen_pct",
    "gastos_administracion_ventas",
    "gastos_financieros",
    "resultado_operacional",
    "utilidad_perdida_ejercicio",
    "var_mom_ingresos",
    "var_mom_gastos_administracion_ventas",
    "var_mom_resultado_final",
]

COMPARISON_TYPES = {
    "ultimo_vs_anterior": "Último mes vs mes anterior",
    "ultimo_vs_inicio": "Último mes vs inicio del año actual",
    "ultimo_vs_primer_cargado": "Último mes vs primer período cargado",
    "mismo_mes_anio_anterior": "Mismo mes año anterior vs mes actual",
    "acumulado_anual": "Acumulado año actual vs acumulado año anterior",
}

RANKING_COLUMNS = [
    "grupo",
    "cuenta",
    "periodo_inicial",
    "monto_inicial",
    "periodo_final",
    "monto_final",
    "variacion_abs",
    "variacion_pct",
]


def calculate_financial_kpis(base: pd.DataFrame) -> pd.DataFrame:
    """Calculate executive monthly KPIs from Base_normalizada."""
    if base is None or base.empty:
        return pd.DataFrame(columns=KPI_COLUMNS)

    periods = sorted(base["periodo"].dropna().astype(str).unique())
    rows = []
    for period in periods:
        period_df = base.loc[base["periodo"].astype(str) == period].copy()
        ingresos = _amount_by_group(period_df, "Ingresos de explotacion", "total")
        costos = _amount_by_group(period_df, "Costos de explotacion", "total")
        margen = _result_by_account(period_df, "MARGEN DE EXPLOTACION")
        if _is_missing(margen):
            margen = ingresos + costos

        gastos_admin = _amount_by_group(period_df, "Gastos administracion y ventas", "total")
        gastos_fin = _amount_by_group_with_detail_fallback(period_df, "Gastos financieros")
        resultado_operacional = _result_by_account(period_df, "RESULTADO OPERACIONAL")
        utilidad_final = _result_by_account(period_df, "UTILIDAD")

        rows.append(
            {
                "periodo": period,
                "ingresos_explotacion": ingresos,
                "costos_explotacion": costos,
                "margen_explotacion": margen,
                "margen_pct": _safe_div(margen, ingresos),
                "gastos_administracion_ventas": gastos_admin,
                "gastos_financieros": gastos_fin,
                "resultado_operacional": resultado_operacional,
                "utilidad_perdida_ejercicio": utilidad_final,
            }
        )

    kpis = pd.DataFrame(rows)
    if kpis.empty:
        return pd.DataFrame(columns=KPI_COLUMNS)

    kpis["var_mom_ingresos"] = kpis["ingresos_explotacion"].diff()
    kpis["var_mom_gastos_administracion_ventas"] = kpis[
        "gastos_administracion_ventas"
    ].diff()
    kpis["var_mom_resultado_final"] = kpis["utilidad_perdida_ejercicio"].diff()
    return kpis[KPI_COLUMNS]


def latest_period_kpis(kpis: pd.DataFrame) -> dict[str, float | str | None]:
    if kpis is None or kpis.empty:
        return {}
    row = kpis.sort_values("periodo").iloc[-1]
    return row.to_dict()


def rank_account_movements(base: pd.DataFrame, top_n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank detail accounts by movement between first and last detected period."""
    return _rank_account_movements_by_period_positions(base, first_pos=0, last_pos=-1, top_n=top_n)


def rank_latest_month_movements(base: pd.DataFrame, top_n: int = 10) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank detail accounts by movement between previous and latest detected period."""
    return _rank_account_movements_by_period_positions(base, first_pos=-2, last_pos=-1, top_n=top_n)


def build_comparison_context(kpis: pd.DataFrame, comparison_type: str) -> dict:
    periods = _sorted_periods(kpis)
    label = COMPARISON_TYPES.get(comparison_type, comparison_type)
    unavailable = {
        "key": comparison_type,
        "label": label,
        "available": False,
        "message": "No hay datos suficientes para esta comparación.",
    }
    if len(periods) < 2:
        return unavailable

    latest = periods[-1]
    latest_year, latest_month = _split_period(latest)

    if comparison_type == "ultimo_vs_anterior":
        return _period_context(comparison_type, label, periods[-2], latest)

    if comparison_type == "ultimo_vs_inicio":
        current_year_periods = [p for p in periods if _split_period(p)[0] == latest_year]
        if not current_year_periods:
            return {
                **unavailable,
                "message": f"No hay períodos disponibles para el año {latest_year}.",
            }
        return _period_context(comparison_type, label, current_year_periods[0], latest)

    if comparison_type == "ultimo_vs_primer_cargado":
        return _period_context(comparison_type, label, periods[0], latest)

    if comparison_type == "mismo_mes_anio_anterior":
        previous_year_period = f"{latest_year - 1}-{latest_month:02d}"
        if previous_year_period not in periods:
            return {
                **unavailable,
                "message": (
                    f"No existe el mismo mes del año anterior ({previous_year_period}) "
                    f"para compararlo con {latest}."
                ),
            }
        return _period_context(comparison_type, label, previous_year_period, latest)

    if comparison_type == "acumulado_anual":
        current_periods = [p for p in periods if _split_period(p)[0] == latest_year]
        previous_periods_all = [p for p in periods if _split_period(p)[0] == latest_year - 1]
        current_months = {_split_period(p)[1] for p in current_periods}
        previous_periods = [
            p for p in previous_periods_all if _split_period(p)[1] in current_months
        ]
        if not current_periods or not previous_periods:
            return {
                **unavailable,
                "message": (
                    f"No hay períodos acumulados comparables para {latest_year - 1} "
                    f"y {latest_year}."
                ),
            }
        return {
            "key": comparison_type,
            "label": label,
            "available": True,
            "mode": "accumulated",
            "periodo_inicial": f"Acumulado {latest_year - 1}",
            "periodo_final": f"Acumulado {latest_year}",
            "initial_periods": previous_periods,
            "final_periods": current_periods,
            "message": "",
        }

    return unavailable


def compare_kpis(kpis: pd.DataFrame, context: dict) -> dict:
    if kpis is None or kpis.empty or not context.get("available"):
        return {}

    if context.get("mode") == "period":
        initial = _kpi_values_for_period(kpis, context["periodo_inicial"])
        final = _kpi_values_for_period(kpis, context["periodo_final"])
    else:
        initial = _kpi_values_for_periods(kpis, context["initial_periods"])
        final = _kpi_values_for_periods(kpis, context["final_periods"])

    return {
        "label": context["label"],
        "periodo_inicial": context["periodo_inicial"],
        "periodo_final": context["periodo_final"],
        "initial": initial,
        "final": final,
        "delta": {
            key: final.get(key, float("nan")) - initial.get(key, float("nan"))
            for key in [
                "ingresos_explotacion",
                "margen_explotacion",
                "gastos_administracion_ventas",
                "utilidad_perdida_ejercicio",
            ]
        },
        "margin_delta_pp": (
            final.get("margen_pct", float("nan")) - initial.get("margen_pct", float("nan"))
        )
        * 100,
    }


def rank_account_movements_for_context(
    base: pd.DataFrame, context: dict, top_n: int = 10
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not context.get("available"):
        empty = pd.DataFrame(columns=RANKING_COLUMNS)
        return empty, empty
    if context.get("mode") == "period":
        return _rank_account_movements_by_period_values(
            base,
            initial_periods=[context["periodo_inicial"]],
            final_periods=[context["periodo_final"]],
            initial_label=context["periodo_inicial"],
            final_label=context["periodo_final"],
            top_n=top_n,
        )
    return _rank_account_movements_by_period_values(
        base,
        initial_periods=context["initial_periods"],
        final_periods=context["final_periods"],
        initial_label=context["periodo_inicial"],
        final_label=context["periodo_final"],
        top_n=top_n,
    )


def _rank_account_movements_by_period_positions(
    base: pd.DataFrame, *, first_pos: int, last_pos: int, top_n: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if base is None or base.empty:
        empty = pd.DataFrame(columns=RANKING_COLUMNS)
        return empty, empty

    detail = base.loc[base["nivel"] == "detalle"].copy()
    if detail.empty:
        empty = pd.DataFrame(columns=RANKING_COLUMNS)
        return empty, empty

    periods = sorted(detail["periodo"].dropna().astype(str).unique())
    if len(periods) < 2:
        empty = pd.DataFrame(columns=RANKING_COLUMNS)
        return empty, empty

    first_period = periods[first_pos]
    last_period = periods[last_pos]
    return _rank_account_movements_by_period_values(
        base,
        initial_periods=[first_period],
        final_periods=[last_period],
        initial_label=first_period,
        final_label=last_period,
        top_n=top_n,
    )


def _rank_account_movements_by_period_values(
    base: pd.DataFrame,
    *,
    initial_periods: list[str],
    final_periods: list[str],
    initial_label: str,
    final_label: str,
    top_n: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if base is None or base.empty:
        empty = pd.DataFrame(columns=RANKING_COLUMNS)
        return empty, empty
    detail = base.loc[base["nivel"] == "detalle"].copy()
    if detail.empty:
        empty = pd.DataFrame(columns=RANKING_COLUMNS)
        return empty, empty

    initial = (
        detail.loc[detail["periodo"].isin(initial_periods)]
        .groupby(["grupo", "cuenta"], as_index=False)["monto"]
        .sum()
        .rename(columns={"monto": "monto_inicial"})
    )
    final = (
        detail.loc[detail["periodo"].isin(final_periods)]
        .groupby(["grupo", "cuenta"], as_index=False)["monto"]
        .sum()
        .rename(columns={"monto": "monto_final"})
    )
    pivot = initial.merge(final, on=["grupo", "cuenta"], how="outer").fillna(0.0)
    pivot["periodo_inicial"] = initial_label
    pivot["periodo_final"] = final_label
    pivot["variacion_abs"] = pivot["monto_final"] - pivot["monto_inicial"]
    pivot["variacion_pct"] = pivot.apply(
        lambda row: _safe_div(row["variacion_abs"], abs(row["monto_inicial"])),
        axis=1,
    )
    ranked = pivot[RANKING_COLUMNS].sort_values("variacion_abs", ascending=False)
    mayores_aumentos = ranked.head(top_n).reset_index(drop=True)
    mayores_disminuciones = ranked.sort_values("variacion_abs").head(top_n).reset_index(drop=True)
    return mayores_aumentos, mayores_disminuciones


def _period_context(comparison_type: str, label: str, initial: str, final: str) -> dict:
    return {
        "key": comparison_type,
        "label": label,
        "available": True,
        "mode": "period",
        "periodo_inicial": initial,
        "periodo_final": final,
        "initial_periods": [initial],
        "final_periods": [final],
        "message": "",
    }


def _kpi_values_for_period(kpis: pd.DataFrame, period: str) -> dict:
    row = kpis.loc[kpis["periodo"].astype(str) == period]
    if row.empty:
        return {}
    return row.iloc[0].to_dict()


def _kpi_values_for_periods(kpis: pd.DataFrame, periods: list[str]) -> dict:
    scoped = kpis.loc[kpis["periodo"].isin(periods)].copy()
    if scoped.empty:
        return {}
    ingresos = float(scoped["ingresos_explotacion"].sum())
    margen = float(scoped["margen_explotacion"].sum())
    return {
        "periodo": ", ".join(periods),
        "ingresos_explotacion": ingresos,
        "costos_explotacion": float(scoped["costos_explotacion"].sum()),
        "margen_explotacion": margen,
        "margen_pct": _safe_div(margen, ingresos),
        "gastos_administracion_ventas": float(scoped["gastos_administracion_ventas"].sum()),
        "gastos_financieros": float(scoped["gastos_financieros"].sum()),
        "resultado_operacional": float(scoped["resultado_operacional"].sum()),
        "utilidad_perdida_ejercicio": float(scoped["utilidad_perdida_ejercicio"].sum()),
    }


def _sorted_periods(df: pd.DataFrame) -> list[str]:
    if df is None or df.empty or "periodo" not in df.columns:
        return []
    return sorted(df["periodo"].dropna().astype(str).unique())


def _split_period(period: str) -> tuple[int, int]:
    year, month = str(period).split("-", 1)
    return int(year), int(month)


def format_currency(value: float | int | None) -> str:
    if value is None or _is_missing(value):
        return "N/D"
    return f"${value:,.0f}"


def format_percent(value: float | int | None) -> str:
    if value is None or _is_missing(value):
        return "N/D"
    return f"{value * 100:,.1f}%"


def _amount_by_group(period_df: pd.DataFrame, group: str, level: str) -> float:
    mask = (period_df["grupo"] == group) & (period_df["nivel"] == level)
    if not mask.any():
        return 0.0
    return float(pd.to_numeric(period_df.loc[mask, "monto"], errors="coerce").fillna(0).sum())


def _amount_by_group_with_detail_fallback(period_df: pd.DataFrame, group: str) -> float:
    total_mask = (period_df["grupo"] == group) & (period_df["nivel"] == "total")
    if total_mask.any():
        return float(pd.to_numeric(period_df.loc[total_mask, "monto"], errors="coerce").fillna(0).sum())
    detail_mask = (period_df["grupo"] == group) & (period_df["nivel"] == "detalle")
    if not detail_mask.any():
        return 0.0
    return float(pd.to_numeric(period_df.loc[detail_mask, "monto"], errors="coerce").fillna(0).sum())


def _result_by_account(period_df: pd.DataFrame, account_token: str) -> float:
    result = period_df.loc[period_df["nivel"] == "resultado"].copy()
    if result.empty:
        return float("nan")
    token = _fold(account_token)
    mask = result["cuenta"].map(_fold).str.contains(token, na=False)
    if not mask.any():
        return float("nan")
    return float(pd.to_numeric(result.loc[mask, "monto"], errors="coerce").fillna(0).sum())


def _safe_div(num: float, den: float) -> float:
    if den in (0, 0.0) or _is_missing(num) or _is_missing(den):
        return float("nan")
    return float(num) / float(den)


def _is_missing(value: float | int | None) -> bool:
    if value is None:
        return True
    try:
        return bool(math.isnan(float(value)))
    except (TypeError, ValueError):
        return False


def _fold(value: object) -> str:
    import unicodedata

    text = "" if value is None else str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))

