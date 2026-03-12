"""
Segment orchestration layer.
Fetches segments, enriches with DMO data, filters eligibility,
previews changes, and executes the bulk update.
"""

import html as html_mod
import json

import sf_client
from criteria import build_nested_segment, inject_nested_segment, criteria_to_json_string


SOQL_FIELDS = (
    "Id, Name, MarketSegmentType, SegmentStatus, "
    "LastSegmentMemberCount, IncludeCriteria, ExcludeCriteria, "
    "PublishScheduleInterval"
)


def _decode_criteria(raw: str | None) -> dict | None:
    """Decode an HTML-entity-encoded JSON criteria string."""
    if not raw:
        return None
    decoded = html_mod.unescape(raw)
    try:
        return json.loads(decoded)
    except json.JSONDecodeError:
        return None


def fetch_all_segments(session: dict) -> list[dict]:
    """
    Fetch all MarketSegment records via SOQL and decode criteria fields.
    Returns list of dicts with parsed includeCriteria / excludeCriteria.
    """
    query = f"SELECT {SOQL_FIELDS} FROM MarketSegment ORDER BY Name"
    records = sf_client.soql(session, query)

    segments = []
    for r in records:
        segments.append({
            "id": r["Id"],
            "name": r.get("Name", ""),
            "developerName": "",
            "marketSegmentType": r.get("MarketSegmentType", ""),
            "segmentStatus": r.get("SegmentStatus", ""),
            "memberCount": r.get("LastSegmentMemberCount"),
            "publishScheduleInterval": r.get("PublishScheduleInterval", ""),
            "includeCriteria": _decode_criteria(r.get("IncludeCriteria")),
            "excludeCriteria": _decode_criteria(r.get("ExcludeCriteria")),
            "includeCriteriaRaw": r.get("IncludeCriteria"),
            "excludeCriteriaRaw": r.get("ExcludeCriteria"),
        })
    return segments


def enrich_with_dmo(session: dict, segments: list[dict]) -> list[dict]:
    """
    Add segmentOnApiName (the DMO) and developerName to each segment by
    matching against Connect API data.  The SOQL MarketSegment object exposes
    neither the DMO nor the API/developer name, so we cross-reference using
    the Connect API's marketSegmentId (which equals the SOQL Id).
    """
    connect_segments = sf_client.get_connect_segments(session)

    id_to_connect = {}
    for cs in connect_segments:
        ms_id = cs.get("marketSegmentId", "")
        if ms_id:
            id_to_connect[ms_id] = cs

    for seg in segments:
        cs = id_to_connect.get(seg["id"])
        if cs:
            seg["developerName"] = cs.get("apiName", "")
            seg["segmentOnApiName"] = cs.get("segmentOnApiName", "")
            seg["displayName"] = cs.get("displayName", seg["name"])
        else:
            seg["segmentOnApiName"] = ""

    return segments


def filter_eligible(
    segments: list[dict], umbrella: dict
) -> tuple[list[dict], list[dict]]:
    """
    Filter segments to only those on the same DMO as the umbrella, excluding
    the umbrella itself and segments that already reference the umbrella.

    Returns (eligible, excluded).
    """
    umbrella_dmo = umbrella.get("segmentOnApiName", "")
    umbrella_dev = umbrella["developerName"]

    eligible = []
    excluded = []

    for seg in segments:
        if seg["id"] == umbrella.get("id"):
            excluded.append(seg)
            continue

        if seg.get("segmentOnApiName") != umbrella_dmo:
            excluded.append(seg)
            continue

        inc = seg.get("includeCriteria")
        if _already_has_nested_ref(inc, umbrella_dev):
            excluded.append(seg)
            continue

        eligible.append(seg)

    return eligible, excluded


def _already_has_nested_ref(criteria: dict | None, umbrella_dev_name: str) -> bool:
    if criteria is None:
        return False
    if criteria.get("type") == "NestedSegment":
        return criteria.get("segmentId") == umbrella_dev_name
    if criteria.get("type") == "LogicalComparison":
        for f in criteria.get("filters", []):
            if _already_has_nested_ref(f, umbrella_dev_name):
                return True
    return False


def preview_changes(
    segments: list[dict], umbrella: dict
) -> list[dict]:
    """
    Build before/after previews for each segment.
    Returns list of {"id", "name", "before", "after"}.
    """
    nested_seg = build_nested_segment(umbrella)
    results = []
    for seg in segments:
        before = seg.get("includeCriteria")
        after = inject_nested_segment(before, nested_seg)
        results.append({
            "id": seg["id"],
            "name": seg["name"],
            "before": before,
            "after": after,
        })
    return results


def execute_bulk_update(
    session: dict,
    segments: list[dict],
    umbrella: dict,
    on_progress=None,
    batch_delay: float = 1.0,
) -> list[dict]:
    """
    Execute the bulk update: inject NestedSegment into each segment's IncludeCriteria
    and PATCH via the Composite API.

    Returns list of {"id", "name", "status", "error"}.
    """
    nested_seg = build_nested_segment(umbrella)

    updates = []
    for seg in segments:
        new_criteria = inject_nested_segment(seg.get("includeCriteria"), nested_seg)
        body = {"IncludeCriteria": criteria_to_json_string(new_criteria)}
        updates.append({"id": seg["id"], "body": body, "name": seg["name"]})

    raw_results = sf_client.composite_patch(
        session,
        updates,
        batch_size=25,
        delay_seconds=batch_delay,
        on_batch_complete=on_progress,
    )

    name_map = {u["id"]: u["name"] for u in updates}
    for r in raw_results:
        r["name"] = name_map.get(r["id"], "")

    return raw_results
