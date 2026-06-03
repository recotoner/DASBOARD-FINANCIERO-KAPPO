from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


BASE_COLUMNS = [
    "periodo",
    "grupo",
    "cuenta",
    "monto",
    "origen",
    "nivel",
    "orden",
    "fuente",
    "fila_origen",
    "monto_origen",
    "signo_normalizado",
]

ADJUSTMENT_COLUMNS = [
    "ajuste_id",
    "fecha_creacion",
    "origen_ajuste",
    "adapter",
    "fuente",
    "periodo",
    "grupo",
    "cuenta",
    "monto",
    "motivo",
    "tipo_ajuste",
    "estado",
    "usuario",
    "exception_id",
    "impacta_kpis",
    "observacion",
]


def build_manual_adjustment(
    *,
    exception: dict[str, Any],
    source_name: str,
    motivo: str,
    usuario: str = "usuario_streamlit",
) -> dict[str, Any]:
    """Create a traceable manual adjustment that offsets a reconciliation difference."""
    periodo = str(exception.get("periodo", ""))
    grupo = str(exception.get("grupo", ""))
    exception_id = str(exception.get("exception_id", ""))
    diferencia = float(exception.get("diferencia", 0) or 0)
    monto_ajuste = -diferencia
    ajuste_id = _build_adjustment_id(periodo, grupo, exception_id)
    return {
        "ajuste_id": ajuste_id,
        "fecha_creacion": datetime.now().isoformat(timespec="seconds"),
        "origen_ajuste": "manual_usuario",
        "adapter": exception.get("adapter", "kame_eerr"),
        "fuente": source_name,
        "periodo": periodo,
        "grupo": grupo,
        "cuenta": "Ajuste manual de cuadratura",
        "monto": monto_ajuste,
        "motivo": motivo or "Ajuste manual para cuadrar suma detalle vs total Kame.",
        "tipo_ajuste": "cuadratura_manual",
        "estado": "aplicado",
        "usuario": usuario,
        "exception_id": exception_id,
        "impacta_kpis": True,
        "observacion": (
            "Generado desde diferencia de cuadratura. "
            "Base_normalizada original no se modifica."
        ),
    }


def apply_manual_adjustments(
    base_normalizada: pd.DataFrame, ajustes: list[dict[str, Any]]
) -> pd.DataFrame:
    """Return Base_ajustada = Base_normalizada + applied manual adjustment rows."""
    if base_normalizada is None:
        base_normalizada = pd.DataFrame(columns=BASE_COLUMNS)
    base = base_normalizada.copy()
    applied = [ajuste for ajuste in ajustes if ajuste.get("estado") == "aplicado"]
    if not applied:
        return base

    adjustment_rows = []
    next_order = _next_adjustment_order(base)
    for idx, ajuste in enumerate(applied):
        adjustment_rows.append(
            {
                "periodo": ajuste.get("periodo"),
                "grupo": ajuste.get("grupo"),
                "cuenta": ajuste.get("cuenta", "Ajuste manual de cuadratura"),
                "monto": float(ajuste.get("monto", 0) or 0),
                "origen": "ajuste_usuario",
                "nivel": "detalle",
                "orden": next_order + idx,
                "fuente": f"ajuste_manual::{ajuste.get('ajuste_id')}",
                "fila_origen": None,
                "monto_origen": float(ajuste.get("monto", 0) or 0),
                "signo_normalizado": False,
                "ajuste_id": ajuste.get("ajuste_id"),
                "tipo_ajuste": ajuste.get("tipo_ajuste"),
                "motivo_ajuste": ajuste.get("motivo"),
            }
        )

    adjustments_df = pd.DataFrame(adjustment_rows)
    return pd.concat([base, adjustments_df], ignore_index=True, sort=False)


def build_control_cuadratura(base: pd.DataFrame) -> list[dict[str, Any]]:
    """Build the same group total reconciliation control over any normalized base."""
    if base is None or base.empty:
        return []

    levels_by_group = base.groupby("grupo")["nivel"].agg(lambda values: set(values))
    groups_with_detail_and_total = [
        group
        for group, levels in levels_by_group.items()
        if {"detalle", "total"}.issubset(levels)
    ]
    if not groups_with_detail_and_total:
        return []

    eligible = base[
        base["grupo"].isin(groups_with_detail_and_total)
        & base["nivel"].isin(["detalle", "total"])
    ].copy()
    pivot = (
        eligible.groupby(["periodo", "grupo", "nivel"], as_index=False)["monto"]
        .sum()
        .pivot_table(
            index=["periodo", "grupo"],
            columns="nivel",
            values="monto",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
    )
    if "detalle" not in pivot.columns:
        pivot["detalle"] = 0.0
    if "total" not in pivot.columns:
        pivot["total"] = 0.0

    pivot = pivot.rename(
        columns={
            "detalle": "suma_detalle",
            "total": "total_kame_normalizado",
        }
    )
    pivot["diferencia"] = pivot["suma_detalle"] - pivot["total_kame_normalizado"]
    pivot["cuadra"] = pivot["diferencia"].abs() <= 1
    pivot = pivot.sort_values(["periodo", "grupo"])
    return pivot[
        ["periodo", "grupo", "suma_detalle", "total_kame_normalizado", "diferencia", "cuadra"]
    ].to_dict("records")


def build_control_summary(control_cuadratura: list[dict[str, Any]]) -> dict[str, Any]:
    grupos_periodo_auditados = len(control_cuadratura)
    controles_ok = sum(1 for row in control_cuadratura if row.get("cuadra"))
    controles_con_diferencia = grupos_periodo_auditados - controles_ok
    mayor_diferencia_abs = (
        max(abs(float(row.get("diferencia", 0) or 0)) for row in control_cuadratura)
        if control_cuadratura
        else 0.0
    )
    return {
        "grupos_periodo_auditados": grupos_periodo_auditados,
        "controles_ok": controles_ok,
        "controles_con_diferencia": controles_con_diferencia,
        "mayor_diferencia_abs": mayor_diferencia_abs,
        "estado_general": "OK" if controles_con_diferencia == 0 else "REVISAR",
    }


def ajustes_to_dataframe(ajustes: list[dict[str, Any]]) -> pd.DataFrame:
    if not ajustes:
        return pd.DataFrame(columns=ADJUSTMENT_COLUMNS)
    out = pd.DataFrame(ajustes)
    for column in ADJUSTMENT_COLUMNS:
        if column not in out.columns:
            out[column] = pd.NA
    return out[ADJUSTMENT_COLUMNS]


def _next_adjustment_order(base: pd.DataFrame) -> int:
    if base is None or base.empty or "orden" not in base.columns:
        return 900000
    try:
        return int(pd.to_numeric(base["orden"], errors="coerce").max()) + 1
    except (TypeError, ValueError):
        return 900000


def _build_adjustment_id(periodo: str, grupo: str, exception_id: str) -> str:
    suffix = abs(hash(f"{periodo}|{grupo}|{exception_id}")) % 1_000_000
    clean_group = "".join(ch if ch.isalnum() else "_" for ch in grupo).strip("_").lower()
    return f"AJ-{periodo}-{clean_group}-{suffix:06d}"
