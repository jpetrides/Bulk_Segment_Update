"""
NestedSegment criteria builder and merger.
Handles construction of the NestedSegment JSON block and injection into
existing IncludeCriteria (null, single filter, or LogicalComparison).
"""

import json


def build_nested_segment(umbrella: dict) -> dict:
    """
    Build a NestedSegment criteria node from an umbrella segment's metadata.

    umbrella must contain:
      - developerName (apiName from Connect API)
      - displayName
      - publishScheduleInterval (e.g. "NO_REFRESH", "One", "Twelve", etc.)
      - marketSegmentType (e.g. "UI", "EinsteinGptSegmentsUI", "Dbt")
    """
    return {
        "type": "NestedSegment",
        "nestingType": "definition",
        "segmentId": umbrella["developerName"],
        "subject": {
            "fieldApiName": umbrella["displayName"],
            "segmentDevName": umbrella["developerName"],
            "publishSchedule": umbrella.get("publishScheduleInterval", "NO_REFRESH"),
            "includeCriteria": None,
            "excludeCriteria": None,
            "nestedPublishBehavior": "useSegmentCriteria",
            "marketSegmentType": umbrella.get("marketSegmentType", "UI"),
            "hasGrl": False,
        },
    }


def _contains_nested_ref(criteria: dict | None, umbrella_dev_name: str) -> bool:
    """Check if criteria already contains a NestedSegment referencing the given umbrella."""
    if criteria is None:
        return False

    if criteria.get("type") == "NestedSegment":
        return criteria.get("segmentId") == umbrella_dev_name

    if criteria.get("type") == "LogicalComparison":
        for f in criteria.get("filters", []):
            if _contains_nested_ref(f, umbrella_dev_name):
                return True

    return False


def inject_nested_segment(existing_criteria: dict | None, nested_segment: dict) -> dict:
    """
    Merge a NestedSegment node into an existing IncludeCriteria.

    Cases:
      - None → return the NestedSegment directly
      - Single filter → wrap both in LogicalComparison AND
      - LogicalComparison → prepend to its filters array
      - Already contains same umbrella → return existing unchanged (idempotent)
    """
    umbrella_dev_name = nested_segment["segmentId"]

    if _contains_nested_ref(existing_criteria, umbrella_dev_name):
        return existing_criteria

    if existing_criteria is None:
        return nested_segment

    if existing_criteria.get("type") == "LogicalComparison":
        new_criteria = dict(existing_criteria)
        new_criteria["filters"] = [nested_segment] + list(existing_criteria.get("filters", []))
        return new_criteria

    return {
        "type": "LogicalComparison",
        "operator": "and",
        "filters": [nested_segment, existing_criteria],
    }


def criteria_to_json_string(criteria: dict | None) -> str | None:
    """Serialize criteria dict to a JSON string for the MarketSegment PATCH body."""
    if criteria is None:
        return None
    return json.dumps(criteria)
