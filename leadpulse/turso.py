import json
from typing import Any, Dict, List, Optional
import httpx
from .config import TURSO_AUTH_TOKEN, TURSO_DATABASE_URL


def is_turso_configured() -> bool:
    """Checks if Turso database credentials are provided."""
    return bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)


def get_turso_http_url() -> str:
    """Normalizes the Turso database URL to an HTTPS endpoint."""
    url = TURSO_DATABASE_URL.strip()
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    elif not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url.rstrip("/")


def execute_turso_query(sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    """
    Executes a SQL statement against Turso serverless SQLite via its HTTP v2 pipeline.
    Returns list of dict rows (like sqlite3.Row).
    """
    if not is_turso_configured():
        raise RuntimeError("Turso database credentials (TURSO_DATABASE_URL, TURSO_AUTH_TOKEN) not set.")

    http_url = f"{get_turso_http_url()}/v2/pipeline"
    headers = {
        "Authorization": f"Bearer {TURSO_AUTH_TOKEN}",
        "Content-Type": "application/json",
    }

    # Format args for Turso pipeline
    formatted_args = []
    if params:
        for p in params:
            if p is None:
                formatted_args.append({"type": "null"})
            elif isinstance(p, int):
                formatted_args.append({"type": "integer", "value": str(p)})
            elif isinstance(p, float):
                formatted_args.append({"type": "float", "value": p})
            elif isinstance(p, bytes):
                formatted_args.append({"type": "blob", "base64": p.hex()})
            else:
                formatted_args.append({"type": "text", "value": str(p)})

    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": sql,
                    "args": formatted_args
                }
            },
            {"type": "close"}
        ]
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(http_url, headers=headers, json=payload)
        if resp.status_code != 200:
            raise RuntimeError(f"Turso error ({resp.status_code}): {resp.text}")

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return []

        first_res = results[0]
        if first_res.get("type") == "error":
            raise RuntimeError(f"Turso query error: {first_res.get('error', {}).get('message')}")

        resp_data = first_res.get("response", {}).get("result", {})
        cols = [c["name"] for c in resp_data.get("cols", [])]
        rows = resp_data.get("rows", [])

        output_rows = []
        for r in rows:
            row_dict = {}
            for idx, val_obj in enumerate(r):
                col_name = cols[idx]
                if isinstance(val_obj, dict):
                    row_dict[col_name] = val_obj.get("value")
                else:
                    row_dict[col_name] = val_obj
            output_rows.append(row_dict)

        return output_rows
