"""
Per-run backup of segment criteria to local filesystem.
Creates a timestamped folder with a manifest and individual segment JSON files.
"""

import json
import os
from datetime import datetime


BACKUP_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")


def create_backup(segments: list[dict], umbrella_name: str) -> str:
    """
    Back up the current IncludeCriteria and ExcludeCriteria for each segment.

    segments: list of dicts with keys id, name, includeCriteria, excludeCriteria
    umbrella_name: developer name of the umbrella segment (for manifest metadata)

    Returns the path to the created backup folder.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    folder = os.path.join(BACKUP_ROOT, f"run_{timestamp}")
    os.makedirs(folder, exist_ok=True)

    manifest = {
        "timestamp": timestamp,
        "umbrella_segment": umbrella_name,
        "target_count": len(segments),
        "segment_ids": [s["id"] for s in segments],
    }
    with open(os.path.join(folder, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    for seg in segments:
        filename = f"segment_{seg['id']}.json"
        payload = {
            "id": seg["id"],
            "name": seg.get("name", ""),
            "includeCriteria": seg.get("includeCriteria"),
            "excludeCriteria": seg.get("excludeCriteria"),
        }
        with open(os.path.join(folder, filename), "w") as f:
            json.dump(payload, f, indent=2)

    return folder
