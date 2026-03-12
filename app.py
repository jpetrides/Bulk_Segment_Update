"""
Bulk Segment Nesting Tool — Streamlit UI
Adds an umbrella segment reference to the IncludeCriteria of many target segments.
"""

import json
import streamlit as st

import sf_client
import segment_service
import backup as backup_mod
from criteria import build_nested_segment

st.set_page_config(page_title="Bulk Segment Nesting Tool", layout="wide")

# ── Session state defaults ────────────────────────────────────────────────────

DEFAULTS = {
    "session": None,
    "step": 1,
    "segments": [],
    "umbrella": None,
    "eligible": [],
    "excluded": [],
    "selected_ids": set(),
    "previews": [],
    "backup_path": None,
    "results": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("Segment Nesting Tool")
    st.markdown("---")
    step = st.session_state.step
    labels = ["Authenticate", "Configure", "Preview & Backup", "Execute"]
    for i, label in enumerate(labels, 1):
        if i < step:
            st.markdown(f"~~Step {i}: {label}~~")
        elif i == step:
            st.markdown(f"**Step {i}: {label}**")
        else:
            st.markdown(f"Step {i}: {label}")

    st.markdown("---")
    if st.session_state.session:
        st.success("Connected")
        st.caption(st.session_state.session["instance_url"])
    else:
        st.info("Not connected")

    st.markdown("---")
    batch_delay = st.slider(
        "Delay between batches (sec)", 0.0, 5.0, 1.0, 0.5,
        help="Pause between Composite API batches of 25",
    )

    if st.button("Reset All", type="secondary"):
        for k, v in DEFAULTS.items():
            st.session_state[k] = v
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — AUTHENTICATE
# ═══════════════════════════════════════════════════════════════════════════════

if st.session_state.step == 1:
    st.header("Step 1 — Authenticate to Salesforce")
    st.markdown(
        "Enter your Salesforce org credentials. You can provide either an existing "
        "access token or connected-app credentials for the username-password OAuth flow."
    )

    auth_method = st.radio(
        "Authentication method",
        ["Access Token", "Username-Password Flow"],
        horizontal=True,
    )

    if auth_method == "Access Token":
        col1, col2 = st.columns(2)
        with col1:
            instance_url = st.text_input("Instance URL", placeholder="https://myorg.my.salesforce.com")
        with col2:
            access_token = st.text_input("Access Token", type="password")

        if st.button("Connect", type="primary"):
            if not instance_url or not access_token:
                st.error("Both fields are required.")
            else:
                with st.spinner("Validating token..."):
                    try:
                        session = sf_client.authenticate(instance_url, access_token)
                        st.session_state.session = session
                        st.session_state.step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Authentication failed: {e}")

    else:
        col1, col2 = st.columns(2)
        with col1:
            login_url = st.text_input("Login URL", value="https://login.salesforce.com")
            client_id = st.text_input("Client ID (Consumer Key)")
            username = st.text_input("Username")
        with col2:
            st.text_input("", disabled=True, label_visibility="hidden")
            client_secret = st.text_input("Client Secret", type="password")
            password = st.text_input("Password + Security Token", type="password")

        if st.button("Connect", type="primary"):
            if not all([login_url, client_id, client_secret, username, password]):
                st.error("All fields are required.")
            else:
                with st.spinner("Authenticating..."):
                    try:
                        session = sf_client.authenticate_password(
                            login_url, client_id, client_secret, username, password
                        )
                        st.session_state.session = session
                        st.session_state.step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"Authentication failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — CONFIGURE
# ═══════════════════════════════════════════════════════════════════════════════

elif st.session_state.step == 2:
    st.header("Step 2 — Configure Umbrella and Target Segments")
    session = st.session_state.session

    nav_col1, nav_col2, _ = st.columns([1, 1, 4])
    with nav_col1:
        if st.button("Back to Auth", key="back_to_auth"):
            st.session_state.step = 1
            st.session_state.segments = []
            st.session_state.umbrella = None
            st.session_state.eligible = []
            st.session_state.excluded = []
            st.session_state.selected_ids = set()
            st.rerun()
    with nav_col2:
        if st.button("Refresh Segments", key="refresh_segments"):
            st.session_state.segments = []
            st.session_state.umbrella = None
            st.session_state.eligible = []
            st.session_state.excluded = []
            st.session_state.selected_ids = set()
            st.rerun()

    if not st.session_state.segments:
        with st.spinner("Fetching segments from MarketSegment sObject..."):
            try:
                segments = segment_service.fetch_all_segments(session)
                st.session_state.segments = segments
            except Exception as e:
                st.error(f"Failed to fetch segments: {e}")
                st.stop()

        with st.spinner("Enriching with DMO data from Connect API..."):
            try:
                st.session_state.segments = segment_service.enrich_with_dmo(
                    session, st.session_state.segments
                )
            except Exception as e:
                st.warning(
                    f"Could not fetch DMO data from Connect API: {e}\n\n"
                    "All segments will be shown as eligible (no DMO filtering)."
                )

    segments = st.session_state.segments
    st.info(f"Loaded **{len(segments)}** segments from the org.")

    # ── Pick umbrella ─────────────────────────────────────────────────────────

    st.subheader("Select Umbrella Segment")
    umbrella_options = {
        f"{s['name']} ({s['developerName']})  —  {s['marketSegmentType']}": s
        for s in segments
    }
    umbrella_label = st.selectbox(
        "Umbrella segment",
        options=[""] + list(umbrella_options.keys()),
        help="This segment will be nested into the IncludeCriteria of all target segments.",
    )

    if umbrella_label and umbrella_label in umbrella_options:
        umbrella = umbrella_options[umbrella_label]
        st.session_state.umbrella = umbrella

        st.markdown(f"""
        | Property | Value |
        |---|---|
        | Developer Name | `{umbrella['developerName']}` |
        | Type | {umbrella['marketSegmentType']} |
        | DMO | `{umbrella.get('segmentOnApiName', 'N/A')}` |
        | Publish Schedule | {umbrella['publishScheduleInterval']} |
        | Member Count | {umbrella.get('memberCount', 'N/A')} |
        """)

        # ── Filter eligible targets ──────────────────────────────────────────

        eligible, excluded = segment_service.filter_eligible(segments, umbrella)
        st.session_state.eligible = eligible
        st.session_state.excluded = excluded

        dmo_name = umbrella.get("segmentOnApiName", "unknown")
        already_nested = sum(
            1 for s in excluded
            if s["id"] != umbrella.get("id")
            and s.get("segmentOnApiName") == dmo_name
        )

        st.markdown("---")
        st.subheader("Target Segments")

        col1, col2, col3 = st.columns(3)
        col1.metric("Eligible", len(eligible))
        col2.metric("Different DMO / Umbrella", len(excluded) - already_nested)
        col3.metric("Already Nested", already_nested)

        if not eligible:
            st.warning("No eligible segments found for this umbrella.")
            st.stop()

        st.caption(
            f"Showing segments on **{dmo_name}** that do not already reference "
            f"**{umbrella['developerName']}**."
        )

        # ── Selection controls ────────────────────────────────────────────────

        if not st.session_state.selected_ids:
            st.session_state.selected_ids = {s["id"] for s in eligible}

        sel_col1, sel_col2, sel_col3 = st.columns([2, 1, 1])
        with sel_col1:
            st.markdown(
                f"**{len(st.session_state.selected_ids)} of {len(eligible)} "
                f"eligible segments selected**"
            )
        with sel_col2:
            if st.button("Select All"):
                st.session_state.selected_ids = {s["id"] for s in eligible}
                st.rerun()
        with sel_col3:
            if st.button("Deselect All"):
                st.session_state.selected_ids = set()
                st.rerun()

        search = st.text_input("Search segments by name", placeholder="Type to filter...")

        display_segments = eligible
        if search:
            search_lower = search.lower()
            display_segments = [
                s for s in eligible if search_lower in s["name"].lower()
            ]

        with st.expander(f"Edit Selection ({len(display_segments)} segments)", expanded=False):
            for seg in display_segments:
                checked = seg["id"] in st.session_state.selected_ids
                new_val = st.checkbox(
                    f"{seg['name']}  ({seg.get('memberCount', '?')} members, "
                    f"{seg['segmentStatus']})",
                    value=checked,
                    key=f"chk_{seg['id']}",
                )
                if new_val and seg["id"] not in st.session_state.selected_ids:
                    st.session_state.selected_ids.add(seg["id"])
                elif not new_val and seg["id"] in st.session_state.selected_ids:
                    st.session_state.selected_ids.discard(seg["id"])

        st.markdown("---")
        if st.button("Proceed to Preview", type="primary", disabled=not st.session_state.selected_ids):
            st.session_state.step = 3
            st.rerun()

    elif st.session_state.umbrella:
        st.session_state.umbrella = None
        st.session_state.eligible = []
        st.session_state.excluded = []
        st.session_state.selected_ids = set()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3 — PREVIEW & BACKUP
# ═══════════════════════════════════════════════════════════════════════════════

elif st.session_state.step == 3:
    st.header("Step 3 — Preview Changes and Create Backup")

    umbrella = st.session_state.umbrella
    selected = [
        s for s in st.session_state.eligible
        if s["id"] in st.session_state.selected_ids
    ]

    st.warning(
        f"This operation will modify the **IncludeCriteria** of **{len(selected)}** segments.\n\n"
        "Before proceeding, the tool will create a local backup of every affected segment. "
        "Consider also exporting the MarketSegment object via Data Loader or Workbench "
        "as an additional safety net."
    )

    st.markdown(f"**Umbrella:** {umbrella['name']} (`{umbrella['developerName']}`)")
    st.markdown(f"**Targets:** {len(selected)} segments")

    nav_col1, nav_col2, _ = st.columns([1, 2, 3])
    with nav_col1:
        if st.button("Back to Configure", key="back_to_configure"):
            st.session_state.step = 2
            st.session_state.previews = []
            st.session_state.backup_path = None
            st.rerun()

    # ── Backup + Preview ──────────────────────────────────────────────────────

    if not st.session_state.backup_path:
        with nav_col2:
            if st.button("Create Backup & Generate Preview", type="primary"):
                with st.spinner("Creating backup..."):
                    try:
                        path = backup_mod.create_backup(selected, umbrella["developerName"])
                        st.session_state.backup_path = path
                    except Exception as e:
                        st.error(f"Backup failed: {e}")
                        st.stop()

                with st.spinner("Building preview..."):
                    previews = segment_service.preview_changes(selected, umbrella)
                    st.session_state.previews = previews

                st.rerun()
    else:
        st.success(f"Backup saved to: `{st.session_state.backup_path}`")

    # ── Show previews ─────────────────────────────────────────────────────────

    if st.session_state.previews:
        st.subheader("Before / After Preview")
        st.caption("Showing the IncludeCriteria before and after injecting the NestedSegment reference.")

        previews = st.session_state.previews
        for i, p in enumerate(previews):
            expanded = i < 5
            with st.expander(f"{p['name']} ({p['id']})", expanded=expanded):
                bcol, acol = st.columns(2)
                with bcol:
                    st.markdown("**Before**")
                    st.code(
                        json.dumps(p["before"], indent=2) if p["before"] else "null",
                        language="json",
                    )
                with acol:
                    st.markdown("**After**")
                    st.code(json.dumps(p["after"], indent=2), language="json")

        st.markdown("---")
        if st.button("Proceed to Execute", type="primary"):
            st.session_state.step = 4
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4 — EXECUTE
# ═══════════════════════════════════════════════════════════════════════════════

elif st.session_state.step == 4:
    st.header("Step 4 — Execute Bulk Update")

    umbrella = st.session_state.umbrella
    selected = [
        s for s in st.session_state.eligible
        if s["id"] in st.session_state.selected_ids
    ]

    st.markdown(
        f"**Umbrella:** {umbrella['name']} (`{umbrella['developerName']}`)\n\n"
        f"**Targets:** {len(selected)} segments\n\n"
        f"**Backup:** `{st.session_state.backup_path}`"
    )

    if st.session_state.results is not None:
        results = st.session_state.results
    else:
        results = None

    nav_col1, nav_col2, _ = st.columns([1, 1, 4])
    with nav_col1:
        if st.button("Back to Preview", key="back_to_preview"):
            st.session_state.step = 3
            st.session_state.results = None
            st.rerun()

    if results is None:
        with nav_col2:
            if st.button("Execute Bulk Update", type="primary"):
                progress_bar = st.progress(0, text="Starting...")
                status_text = st.empty()

                def on_progress(done, total):
                    pct = done / total if total else 1.0
                    progress_bar.progress(pct, text=f"{done} / {total} segments processed")

                try:
                    results = segment_service.execute_bulk_update(
                        st.session_state.session,
                        selected,
                        umbrella,
                        on_progress=on_progress,
                        batch_delay=batch_delay,
                    )
                    st.session_state.results = results
                    progress_bar.progress(1.0, text="Complete!")
                except Exception as e:
                    st.error(f"Bulk update failed: {e}")
                    st.stop()

                st.rerun()

    if results is not None:
        succeeded = [r for r in results if r["status"] in (200, 204)]
        failed = [r for r in results if r["status"] not in (200, 204)]

        st.markdown("---")
        col1, col2, col3 = st.columns(3)
        col1.metric("Succeeded", len(succeeded))
        col2.metric("Failed", len(failed))
        col3.metric("Total", len(results))

        if failed:
            st.error("Some segments failed to update:")
            for f in failed:
                st.markdown(f"- **{f['name']}** ({f['id']}): `{f['error']}`")

        with st.expander("Full Results", expanded=False):
            for r in results:
                icon = "+" if r["status"] in (200, 204) else "x"
                err = f" — {r['error']}" if r.get("error") else ""
                st.text(f"[{icon}] {r['name']} ({r['id']}): HTTP {r['status']}{err}")

        st.success(
            f"Bulk update complete. {len(succeeded)} succeeded, {len(failed)} failed.\n\n"
            f"Backup folder: `{st.session_state.backup_path}`"
        )
