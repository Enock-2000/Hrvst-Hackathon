"""Shared HTTP POST helper for alert integrations."""

from __future__ import annotations

import json
import sys
from typing import Any
from urllib import error as url_error
from urllib import request as url_request


def post_json(
    *,
    base_url: str,
    path: str,
    bearer_token: str,
    payload: dict[str, Any],
    timeout_sec: float,
    log_label: str,
) -> bool:
    req = url_request.Request(
        url=f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        },
        method="POST",
    )
    try:
        with url_request.urlopen(req, timeout=timeout_sec) as resp:
            status = resp.getcode()
        print(f"  {log_label} sent (status={status}).")
        return True
    except url_error.HTTPError as e:
        print(f"  {log_label} failed: HTTP {e.code} {e.reason}", file=sys.stderr)
    except url_error.URLError as e:
        print(f"  {log_label} failed: {e.reason}", file=sys.stderr)
    return False
