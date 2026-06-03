# Dashboard Evolutivo Financiero Kappo

V1 tecnica para leer un Estado de Resultados exportado desde Kame y convertirlo a una base interna normalizada.

## Alcance actual

- Adapter Kame: `src/adapters/kame_eerr.py`.
- App Streamlit minima: carga Excel, muestra `Base_normalizada`, diagnostics y resumen simple.
- Sin graficos avanzados, webhook, alertas, waterfall ni exportacion Excel.

## Base_normalizada

Columnas obligatorias:

```text
periodo | grupo | cuenta | monto | origen | nivel | orden | fuente
```

Columnas de auditoria incluidas:

```text
fila_origen | monto_origen | signo_normalizado
```

## Ejecutar

```bash
pip install -r requirements.txt
streamlit run app.py
```
