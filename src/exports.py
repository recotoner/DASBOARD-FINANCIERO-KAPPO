from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pandas as pd


SHEET_COLUMNS = {
    "Base_normalizada": [
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
    ],
    "KPIs_mensuales": [
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
    ],
    "Lectura_ejecutiva": [
        "orden",
        "lectura",
    ],
    "Alertas": [
        "periodo",
        "severidad",
        "indicador",
        "alerta",
        "valor",
        "umbral",
        "detalle",
    ],
    "Control_cuadratura": [
        "periodo",
        "grupo",
        "suma_detalle",
        "total_kame_normalizado",
        "diferencia",
        "cuadra",
    ],
    "Ranking_aumentos": [
        "grupo",
        "cuenta",
        "periodo_inicial",
        "monto_inicial",
        "periodo_final",
        "monto_final",
        "variacion_abs",
        "variacion_pct",
    ],
    "Ranking_disminuciones": [
        "grupo",
        "cuenta",
        "periodo_inicial",
        "monto_inicial",
        "periodo_final",
        "monto_final",
        "variacion_abs",
        "variacion_pct",
    ],
}


def build_analysis_workbook(
    *,
    base_normalizada: pd.DataFrame,
    kpis_mensuales: pd.DataFrame,
    control_cuadratura: list[dict[str, Any]] | pd.DataFrame,
    ranking_aumentos: pd.DataFrame,
    ranking_disminuciones: pd.DataFrame,
    diagnostics: dict[str, Any],
    lectura_ejecutiva: list[str] | pd.DataFrame | None = None,
    alertas_financieras: pd.DataFrame | None = None,
) -> bytes:
    """Build the evolutive financial analysis workbook in memory."""
    output = BytesIO()
    sheets = {
        "Base_normalizada": _ensure_columns(base_normalizada, "Base_normalizada"),
        "KPIs_mensuales": _ensure_columns(kpis_mensuales, "KPIs_mensuales"),
        "Lectura_ejecutiva": _ensure_columns(
            _reading_to_dataframe(lectura_ejecutiva), "Lectura_ejecutiva"
        ),
        "Alertas": _ensure_columns(alertas_financieras, "Alertas"),
        "Control_cuadratura": _ensure_columns(
            _as_dataframe(control_cuadratura), "Control_cuadratura"
        ),
        "Ranking_aumentos": _ensure_columns(ranking_aumentos, "Ranking_aumentos"),
        "Ranking_disminuciones": _ensure_columns(
            ranking_disminuciones, "Ranking_disminuciones"
        ),
        "Diagnostics": _diagnostics_to_dataframe(diagnostics),
    }

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            _write_sheet(writer, sheet_name, df)
            _format_sheet(writer, sheet_name)

    output.seek(0)
    return output.getvalue()


def _reading_to_dataframe(value: list[str] | pd.DataFrame | None) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if not value:
        return pd.DataFrame(columns=SHEET_COLUMNS["Lectura_ejecutiva"])
    return pd.DataFrame(
        [{"orden": idx + 1, "lectura": text} for idx, text in enumerate(value)]
    )


def _as_dataframe(value: list[dict[str, Any]] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return pd.DataFrame(value)


def _ensure_columns(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    expected = SHEET_COLUMNS.get(sheet_name)
    if expected is None:
        return df.copy() if df is not None else pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame(columns=expected)

    out = df.copy()
    for column in expected:
        if column not in out.columns:
            out[column] = pd.NA
    extra = [column for column in out.columns if column not in expected]
    return out[expected + extra]


def _diagnostics_to_dataframe(diagnostics: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for key, value in (diagnostics or {}).items():
        if key in {
            "control_cuadratura",
            "diferencias_a_revisar",
            "detalle_montos_negativos_diferencias",
        }:
            value_repr = json.dumps(value, ensure_ascii=False, default=str)
        elif isinstance(value, (dict, list)):
            value_repr = json.dumps(value, ensure_ascii=False, default=str)
        else:
            value_repr = value
        rows.append({"campo": key, "valor": value_repr})
    if not rows:
        return pd.DataFrame([{"campo": "nota", "valor": "Sin diagnostics disponibles"}])
    return pd.DataFrame(rows, columns=["campo", "valor"])


def _write_sheet(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame) -> None:
    if df is None or df.empty:
        note = pd.DataFrame({"nota": ["Sin datos disponibles para esta hoja"]})
        if df is not None and len(df.columns) > 0:
            note = pd.concat([pd.DataFrame(columns=df.columns), note], ignore_index=True)
        note.to_excel(writer, sheet_name=sheet_name, index=False)
        return
    df.to_excel(writer, sheet_name=sheet_name, index=False)


def _format_sheet(writer: pd.ExcelWriter, sheet_name: str) -> None:
    worksheet = writer.sheets[sheet_name]
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions

    for cell in worksheet[1]:
        cell.font = cell.font.copy(bold=True)
        cell.fill = cell.fill.copy(fill_type="solid", fgColor="E8F4DC")

    for column_cells in worksheet.columns:
        max_len = max(len(str(cell.value or "")) for cell in column_cells)
        worksheet.column_dimensions[column_cells[0].column_letter].width = min(
            max(max_len + 2, 12), 48
        )
