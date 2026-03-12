"""
Salesforce REST client for MarketSegment operations.
Handles auth, SOQL queries, sObject PATCH, Composite API, and Connect API segment reads.
"""

import json
import time
import html as html_mod
from urllib.parse import quote

import requests


def authenticate(instance_url: str, access_token: str, api_version: str = "66.0") -> dict:
    """Validate an existing access token and return a session dict."""
    instance_url = instance_url.rstrip("/")
    resp = requests.get(
        f"{instance_url}/services/data/v{api_version}/",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    resp.raise_for_status()
    return {
        "instance_url": instance_url,
        "access_token": access_token,
        "api_version": api_version,
    }


def authenticate_password(
    login_url: str,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
    api_version: str = "66.0",
) -> dict:
    """Authenticate via OAuth 2.0 username-password flow."""
    login_url = login_url.rstrip("/")
    resp = requests.post(
        f"{login_url}/services/oauth2/token",
        data={
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": client_secret,
            "username": username,
            "password": password,
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "instance_url": data["instance_url"],
        "access_token": data["access_token"],
        "api_version": api_version,
    }


def _headers(session: dict) -> dict:
    return {
        "Authorization": f"Bearer {session['access_token']}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base_url(session: dict) -> str:
    return f"{session['instance_url']}/services/data/v{session['api_version']}"


# ── SOQL ──────────────────────────────────────────────────────────────────────


def soql(session: dict, query: str) -> list[dict]:
    """Run a SOQL query with automatic pagination. Returns all records."""
    url = f"{_base_url(session)}/query/?q={quote(query)}"
    all_records = []
    while url:
        resp = requests.get(url, headers=_headers(session), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_records.extend(data.get("records", []))
        next_url = data.get("nextRecordsUrl")
        url = f"{session['instance_url']}{next_url}" if next_url else None
    return all_records


# ── sObject PATCH ─────────────────────────────────────────────────────────────


def patch(session: dict, sobject: str, record_id: str, body: dict) -> int:
    """PATCH a single sObject record. Returns HTTP status code."""
    url = f"{_base_url(session)}/sobjects/{sobject}/{record_id}"
    resp = requests.patch(url, headers=_headers(session), json=body, timeout=15)
    resp.raise_for_status()
    return resp.status_code


# ── Composite API ─────────────────────────────────────────────────────────────


def composite_patch(
    session: dict,
    updates: list[dict],
    batch_size: int = 25,
    delay_seconds: float = 1.0,
    on_batch_complete=None,
) -> list[dict]:
    """
    Batch-update MarketSegment records via the Composite API.

    updates: list of {"id": "1sgXXX", "body": {"IncludeCriteria": "..."}}
    Returns: list of {"id", "status", "error"} per record.
    """
    results = []
    for i in range(0, len(updates), batch_size):
        batch = updates[i : i + batch_size]
        subrequests = []
        for j, u in enumerate(batch):
            subrequests.append(
                {
                    "method": "PATCH",
                    "url": f"/services/data/v{session['api_version']}/sobjects/MarketSegment/{u['id']}",
                    "referenceId": f"seg_{i + j}",
                    "body": u["body"],
                }
            )

        resp = requests.post(
            f"{_base_url(session)}/composite",
            headers=_headers(session),
            json={"compositeRequest": subrequests},
            timeout=60,
        )
        resp.raise_for_status()

        for cr in resp.json().get("compositeResponse", []):
            idx = int(cr["referenceId"].split("_")[1])
            rec_id = updates[idx]["id"]
            error = None
            if cr["httpStatusCode"] not in (200, 204):
                body_data = cr.get("body")
                if isinstance(body_data, list) and body_data:
                    error = body_data[0].get("message", str(body_data))
                elif body_data:
                    error = str(body_data)
            results.append(
                {"id": rec_id, "status": cr["httpStatusCode"], "error": error}
            )

        if on_batch_complete:
            on_batch_complete(min(i + batch_size, len(updates)), len(updates))

        if i + batch_size < len(updates):
            time.sleep(delay_seconds)

    return results


# ── Connect API — Segments ────────────────────────────────────────────────────


def get_connect_segments(session: dict) -> list[dict]:
    """
    Fetch all segments from the Connect API (paginated).
    Returns list with apiName, displayName, segmentOnApiName, segmentType, publishInterval.
    """
    all_segments = []
    offset = 0
    batch_size = 200
    while True:
        url = (
            f"{_base_url(session)}/ssot/segments"
            f"?batchSize={batch_size}&offset={offset}"
        )
        resp = requests.get(url, headers=_headers(session), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        segments = data.get("segments", [])
        all_segments.extend(segments)
        if len(segments) < batch_size:
            break
        offset += batch_size
    return all_segments


def get_connect_segment(session: dict, api_name: str) -> dict:
    """Fetch a single segment from the Connect API by apiName."""
    url = f"{_base_url(session)}/ssot/segments/{api_name}"
    resp = requests.get(url, headers=_headers(session), timeout=15)
    resp.raise_for_status()
    data = resp.json()
    segments = data.get("segments", [data])
    return segments[0] if segments else data
