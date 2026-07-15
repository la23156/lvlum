"""Tiny stdlib HTTP helpers (GET bytes / GET json / POST json) with retry + gzip."""
import gzip
import io
import json
import time
import urllib.request
import urllib.error

import config


def _open(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout)


def _decode(resp) -> bytes:
    data = resp.read()
    if resp.headers.get("Content-Encoding") == "gzip":
        data = gzip.decompress(data)
    return data


def get_bytes(url, headers=None, timeout=None, retries=4) -> bytes:
    timeout = timeout or config.HTTP_TIMEOUT
    h = {"User-Agent": config.UA, "Accept-Encoding": "gzip"}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=h)
            with _open(req, timeout) as resp:
                return _decode(resp)
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (404, 403, 410):
                raise
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def get_text(url, **kw) -> str:
    return get_bytes(url, **kw).decode("utf-8", errors="replace")


def get_json(url, **kw):
    return json.loads(get_text(url, **kw))


def post_json(url, payload, headers=None, timeout=None, retries=5):
    """POST JSON, return (status_code, parsed_json_or_text). Retries transient errors."""
    timeout = timeout or config.HTTP_TIMEOUT
    body = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": config.UA}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=h, method="POST")
            with _open(req, timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return resp.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except Exception:  # noqa: BLE001
                parsed = {"raw": raw}
            # 429 / 5xx are retryable; 4xx (param errors) bubble up to caller
            if e.code == 429 or e.code >= 500:
                last = (e.code, parsed)
                # honor Retry-After when present
                wait = e.headers.get("Retry-After")
                time.sleep(float(wait) if wait and wait.isdigit() else 2 * (attempt + 1))
                continue
            return e.code, parsed
        except Exception as e:  # noqa: BLE001
            last = (None, {"error": str(e)})
            time.sleep(2 * (attempt + 1))
    return last if last else (None, {"error": "unknown"})
