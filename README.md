# Bulk Segment Nesting Tool

A local Streamlit application that bulk-updates Salesforce Data Cloud segments by injecting a "nested segment" reference into their IncludeCriteria. This allows you to add an umbrella segment filter to hundreds or thousands of existing segments in a single operation.

## Use Case

When onboarding a large batch of new profiles into a Unified Profile, you may want to exclude those new profiles from all existing segments. The approach is:

1. Create a single "umbrella" segment that excludes the new profiles.
2. Use this tool to nest that umbrella segment into the IncludeCriteria of every target segment.

This is equivalent to manually opening each segment in the Data Cloud UI and adding a nested segment filter — but automated across your entire segment library.

## Prerequisites

- Python 3.10+
- A Salesforce org with Data Cloud enabled
- A valid access token or connected-app credentials with access to:
  - The Salesforce REST API (SOQL, sObject PATCH)
  - The Data Cloud Connect API (`/ssot/segments`)

## Setup

```bash
cd Bulk_Segment_Update
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

The app opens in your browser at `http://localhost:8501`.

## How It Works

1. **Authenticate** — Enter your Salesforce instance URL and access token (or connected-app credentials).
2. **Configure** — Select an umbrella segment and review the eligible target segments (automatically filtered by DMO compatibility).
3. **Preview & Backup** — Review before/after JSON diffs and create a local backup of all affected segments.
4. **Execute** — Run the bulk update via the Salesforce Composite API in batches of 25.

## File Structure

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — 4-step wizard |
| `sf_client.py` | Salesforce REST client (auth, SOQL, PATCH, Composite API) |
| `segment_service.py` | Segment fetching, DMO enrichment, filtering, bulk update orchestration |
| `criteria.py` | NestedSegment JSON builder and criteria merger |
| `backup.py` | Per-run backup to local filesystem |
| `backups/` | Backup folder (auto-created at runtime) |

## Safety Features

- **Mandatory backup** before any writes — the Execute button is disabled until a backup exists.
- **Idempotent** — segments that already reference the umbrella are automatically skipped.
- **DMO filtering** — only segments built on the same Data Model Object as the umbrella are eligible.
- **Rate limiting** — configurable delay between Composite API batches (default: 1 second).
- **No destructive writes** — the tool only adds to IncludeCriteria; it does not delete or overwrite existing filters.

## Restoring from Backup

Each run creates a timestamped folder under `backups/` containing a `manifest.json` and individual segment files. To restore a segment, use the Salesforce REST API or Workbench to PATCH the `MarketSegment` sObject with the original `IncludeCriteria` from the backup file.
