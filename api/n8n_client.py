from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any


N8N_TIMEOUT_SECONDS = 120


def post_analysis_to_n8n(payload: dict[str, Any]) -> dict[str, Any]:
    webhook_url = os.getenv("N8N_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {
            "requested": True,
            "status": "not_configured",
            "status_code": None,
            "error": "N8N_WEBHOOK_URL no está configurada.",
        }

    request = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=N8N_TIMEOUT_SECONDS,
        ) as response:
            body = response.read().decode("utf-8", errors="replace")
            parsed = _parse_response(body)
            return {
                "requested": True,
                "status": "ok",
                "status_code": response.status,
                "error": None,
                "salud_financiera": parsed.get("salud_financiera"),
                "diagnostico": parsed.get("diagnostico", []),
                "recomendaciones": parsed.get("recomendaciones", []),
                "informe": parsed.get("informe"),
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "requested": True,
            "status": "http_error",
            "status_code": exc.code,
            "error": body or str(exc),
        }
    except (TimeoutError, socket.timeout):
        return {
            "requested": True,
            "status": "timeout",
            "status_code": None,
            "error": f"n8n no respondió dentro de {N8N_TIMEOUT_SECONDS} segundos.",
        }
    except urllib.error.URLError as exc:
        is_timeout = isinstance(exc.reason, (TimeoutError, socket.timeout))
        return {
            "requested": True,
            "status": "timeout" if is_timeout else "connection_error",
            "status_code": None,
            "error": str(exc.reason),
        }
    except Exception as exc:
        return {
            "requested": True,
            "status": "error",
            "status_code": None,
            "error": str(exc),
        }


def _parse_response(body: str) -> dict[str, Any]:
    if not body:
        return {}
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {"informe": body}
    if isinstance(parsed, list) and parsed:
        parsed = parsed[0]
    return parsed if isinstance(parsed, dict) else {"informe": str(parsed)}
