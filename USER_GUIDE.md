# User Guide — Bulk Segment Nesting Tool

This guide walks you through using the Bulk Segment Nesting Tool to add an umbrella segment reference to the IncludeCriteria of many Data Cloud segments at once.

---

## Before You Start

### What You Need

- **Python 3.10 or later** installed on your machine
- **Salesforce credentials** — one of the following:
  - An instance URL (e.g., `https://myorg.my.salesforce.com`) and a valid access token
  - Connected-app credentials (Client ID, Client Secret, Username, Password + Security Token)
- **An umbrella segment already created** in your Data Cloud org. This is the segment that filters out the profiles you want to exclude. You should verify it works correctly in the Data Cloud UI before running this tool.

### Required Salesforce Permissions

The authenticated user must have:

- Read access to the `MarketSegment` sObject (for querying segment data)
- Write access to the `MarketSegment` sObject (for updating IncludeCriteria)
- Access to the Data Cloud Connect API (`/ssot/segments` endpoint)

### Important Notes

- This tool modifies the `IncludeCriteria` field on the `MarketSegment` Salesforce object. It does **not** use the Data Cloud Segment PATCH API (which blocks edits to UI-created segments).
- The tool is **additive only** — it adds the umbrella segment reference without removing or changing any existing filter criteria.
- **Exclude and Rank & Limit criteria are never touched.** The `MarketSegment` sObject stores Include, Exclude, and Rank & Limit in three separate fields (`IncludeCriteria`, `ExcludeCriteria`, `GroupSortLimitFilterCriteria`). This tool's PATCH payload only sends the `IncludeCriteria` field — Salesforce will not modify the other two fields.
- The operation is **idempotent** — running it twice with the same umbrella will not create duplicate references.
- A local backup is created before any changes are written. However, you should also consider creating an independent backup using Data Loader or Workbench as an extra precaution.

---

## Installation

Open a terminal and navigate to the tool's folder:

```bash
cd Bulk_Segment_Update
```

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

---

## Running the Tool

Start the app:

```bash
streamlit run app.py
```

Your browser will open to `http://localhost:8501`. If it doesn't, open that URL manually.

---

## Step-by-Step Walkthrough

### Step 1 — Authenticate

You have two authentication options:

**Option A: Access Token**

1. Enter your Salesforce **Instance URL** (e.g., `https://myorg.my.salesforce.com`).
2. Paste a valid **Access Token**.
   - You can get one from Workbench, the Salesforce CLI (`sf org display`), or your browser's developer console while logged in to Salesforce.
3. Click **Connect**.

**Option B: Username-Password Flow**

1. Enter the **Login URL** (`https://login.salesforce.com` for production, `https://test.salesforce.com` for sandboxes).
2. Enter your connected app's **Client ID** and **Client Secret**.
3. Enter your Salesforce **Username** and **Password** (a security token appended to the password is typically not required for Data Cloud orgs).
4. Click **Connect**.

If authentication succeeds, the sidebar will show "Connected" with your instance URL, and you'll advance to Step 2.

### Step 2 — Configure

This step has two parts: picking the umbrella segment and selecting target segments.

**Picking the Umbrella Segment**

1. Wait for the tool to load all segments from your org (this may take a moment for large orgs).
2. Use the dropdown to select the umbrella segment you previously created.
3. The tool displays the umbrella's properties (Developer Name, DMO, Type, etc.) for confirmation.

**Selecting Target Segments**

Once you select an umbrella, the tool automatically:

- Queries the Connect API to determine which DMO each segment is built on.
- Filters to only show segments on the **same DMO** as the umbrella.
- Removes the umbrella itself from the list.
- Removes segments that already contain a nested reference to this umbrella.

You'll see a summary showing:

- **Eligible** — segments that can receive the nested reference
- **Different DMO / Umbrella** — segments filtered out due to DMO mismatch or being the umbrella itself
- **Already Nested** — segments that already have this umbrella nested

By default, **all eligible segments are selected**. You can:

- Use **Deselect All** to clear the selection
- Use **Select All** to re-select everything
- Use the **search box** to find specific segments by name
- Open the **Edit Selection** expander to toggle individual segments

When you're satisfied with the selection, click **Proceed to Preview**.

**Navigation**

- **Back to Auth** — returns to Step 1 if you need to reconnect or switch orgs.
- **Refresh Segments** — re-fetches all segments from the org without requiring re-authentication. Use this if you've made changes to segments in the Data Cloud UI and want the tool to pick them up.

### Step 3 — Preview and Backup

This step ensures you understand what will change and creates a safety net.

1. Read the **warning banner** carefully.
2. Click **Create Backup & Generate Preview**.
3. The tool creates a backup folder under `backups/` containing:
   - `manifest.json` — metadata about this run (timestamp, umbrella name, target IDs)
   - One JSON file per segment — containing the original `IncludeCriteria` and `ExcludeCriteria`
4. The backup path is displayed (e.g., `backups/run_2026-03-12_143022/`).
5. Review the **Before / After** previews. Each segment has an expandable section showing:
   - **Before** — the current IncludeCriteria JSON
   - **After** — the new IncludeCriteria JSON with the NestedSegment reference added

The first 5 segments are expanded by default. You can expand or collapse any of them.

You can click **Back to Configure** at any time to change your umbrella or target selection.

When you're ready, click **Proceed to Execute**.

### Step 4 — Execute

1. Review the summary (umbrella, target count, backup path).
2. Click **Execute Bulk Update**. You can also click **Back to Preview** if you need to review the changes again.
3. A progress bar tracks the operation. The tool processes segments in batches of 25 via the Salesforce Composite API, with a configurable delay between batches (adjustable in the sidebar).
4. When complete, you'll see:
   - **Succeeded / Failed / Total** counts
   - Any errors listed individually with the segment name and error message
   - A link to the backup folder

---

## After the Update

### Verifying the Changes

1. Open a few segments in the Data Cloud UI and confirm the umbrella segment appears as a nested filter in the Include criteria.
2. Check that existing filter criteria are unchanged.
3. Monitor segment recalculation to ensure segments process correctly.

### If Something Goes Wrong

**Restoring from Backup**

Each backup file contains the original `IncludeCriteria` for the segment. To restore:

1. Open the backup file (e.g., `backups/run_2026-03-12_143022/segment_1sgWs000001MVhJ.json`).
2. Copy the `includeCriteria` value.
3. Use the Salesforce REST API, Workbench, or Data Loader to PATCH the `MarketSegment` record with the original value:

```
PATCH /services/data/v66.0/sobjects/MarketSegment/{segment_id}
Content-Type: application/json

{
  "IncludeCriteria": "<paste the original JSON string here>"
}
```

Alternatively, you could build a bulk restore script using the same approach this tool uses.

---

## Sidebar Controls

| Control | Description |
|---|---|
| **Delay between batches** | Pause (in seconds) between each batch of 25 API calls. Increase if you hit rate limits. |
| **Reset All** | Clears all state and returns to Step 1. Use this to start over with a different umbrella or org. |

Every step (except Step 1) has a **Back** button to return to the previous step. You can navigate backward freely without losing your auth session.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "Authentication failed" | Verify your access token is valid and hasn't expired. Tokens typically last 1-2 hours. |
| "Failed to fetch segments" | Check that the user has read access to the `MarketSegment` sObject. |
| "Could not fetch DMO data" | The Connect API may require specific Data Cloud permissions. All segments will still be shown, but without DMO filtering. |
| Segments fail during execution | Check the error message — common causes are expired tokens (re-authenticate) or field-level security blocking writes to `IncludeCriteria`. |
| Progress stalls | The Composite API has a 120-second timeout per batch. If your org is under heavy load, try increasing the batch delay. |

---

## Technical Details

### How the NestedSegment Reference Works

When you nest segment A inside segment B in the Data Cloud UI, Salesforce adds a JSON block to segment B's `IncludeCriteria` field on the `MarketSegment` sObject:

```json
{
  "type": "NestedSegment",
  "nestingType": "definition",
  "segmentId": "Umbrella_Segment_Dev_Name",
  "subject": {
    "fieldApiName": "Umbrella Segment Display Name",
    "segmentDevName": "Umbrella_Segment_Dev_Name",
    "publishSchedule": "NO_REFRESH",
    "includeCriteria": null,
    "excludeCriteria": null,
    "nestedPublishBehavior": "useSegmentCriteria",
    "marketSegmentType": "UI",
    "hasGrl": false
  }
}
```

This tool constructs exactly this JSON block and merges it into each target segment's existing IncludeCriteria:

- If the segment has **no existing criteria** (`null`) → the NestedSegment becomes the sole criteria.
- If the segment has a **single filter** (e.g., one `TextComparison`) → both are wrapped in a `LogicalComparison` with operator `and`.
- If the segment already has a **`LogicalComparison`** (multiple filters joined by AND/OR) → the NestedSegment is prepended to its `filters` array, preserving the existing logic.
- If the segment **already references this umbrella** → no change is made (idempotent).

### How Segment Criteria Are Stored

The `MarketSegment` sObject has three independent `textarea` fields for segment logic:

| Field | UI Section | What It Controls |
|---|---|---|
| `IncludeCriteria` | Include | Filters that define who is IN the segment |
| `ExcludeCriteria` | Exclude | Filters that remove people from the segment |
| `GroupSortLimitFilterCriteria` | Rank & Limit | Advanced sorting and capping logic |

Each field contains its own JSON blob (or `null` if unused). Because they are separate database columns, updating one field has absolutely no effect on the others. This tool only writes to `IncludeCriteria`.

### API Endpoints Used

| Endpoint | Purpose |
|---|---|
| `POST /services/oauth2/token` | Username-password authentication |
| `GET /services/data/vXX.0/` | Token validation |
| `GET /services/data/vXX.0/query/?q=...` | SOQL queries for MarketSegment data |
| `GET /services/data/vXX.0/ssot/segments` | Connect API — fetch segment DMO info |
| `POST /services/data/vXX.0/composite` | Batch PATCH operations (25 per request) |
