
from datetime import datetime
from html import escape
import re

import streamlit as st

from components.admin_dashboard import show_admin_dashboard
from components.admin_login import show_admin_login

from services.public_results_service import (
    get_public_lottery_results,
    get_published_draws_page,
    get_published_prize_numbers_page
)
from services.number_search_service import (
    search_winning_number,
    search_winning_number_page,
    get_number_search_statistics,
    get_number_search_breakdown
)
from services.frequency_analysis_service import (
    get_winning_number_frequency_page
)
from services.probability_analysis_service import (
    get_winning_number_probability_page
)
from services.historical_trends_service import (
    get_historical_draws_page,
    get_historical_draw_numbers_page
)


# ==========================================
# PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="NumberDuniya",
    page_icon="🎯",
    layout="wide"
)


# Public presentation only; no changes to authentication or data access.
st.markdown("""
<style>
/* Comfortable touch targets and compact mobile-first spacing */
.block-container {max-width: 1180px; padding-top: 1.2rem; padding-bottom: 2rem;}
.stButton button, .stFormSubmitButton button {min-height: 2.9rem; border-radius: 0.75rem; font-weight: 650;}
.stTextInput input {min-height: 2.9rem; border-radius: 0.7rem; font-size: 1.05rem;}
.nd-hero {padding: 1.1rem 1.2rem; border-radius: 1.15rem;
 background: linear-gradient(120deg,#fff2f3,#f3f7ff); margin-bottom: .9rem;}
.nd-hero h1 {font-size: clamp(1.55rem, 4.8vw, 2.45rem); line-height: 1.2;
 margin: 0 0 .35rem; color: #242b40;}
.nd-hero p {margin: 0; color: #596478; font-size: .96rem;}
.nd-number-grid {display:grid; grid-template-columns:repeat(auto-fill,minmax(88px,1fr)); gap:8px; margin:.5rem 0 1.3rem;}
.nd-number {text-align:center; border:1px solid #dbe3ee; border-radius:10px;
 background:#f8faff; padding:10px 4px; font-weight:750; font-size:1.05rem;
 letter-spacing:.035em; color:#24314b; overflow-wrap:anywhere;}
@media(max-width:640px) {
 .block-container {padding: .55rem .85rem 1.5rem;}
 .nd-hero {padding: .85rem .9rem; margin-bottom: .3rem;}
 .nd-hero h1 {font-size: 1.6rem;}
 h2 {font-size:1.45rem !important;}
 h3 {font-size:1.2rem !important;}
 .nd-number-grid {grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;}
 .stButton button, .stFormSubmitButton button {min-height:3.1rem;}
}
@media(prefers-color-scheme:dark) {
 .nd-hero {background:linear-gradient(120deg,#292237,#202d3c);}
 .nd-hero h1,.nd-number {color:#f5f7ff;}
 .nd-hero p {color:#d0d6e4;}
 .nd-number {background:#253246;border-color:#45536a;}
}

/* Compact, accessible mobile search result summaries. */
.nd-summary-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:.65rem 0 .55rem;}
.nd-summary-card {padding:12px 13px;background:#f7f9fc;border:1px solid #e3e8f0;border-radius:12px;min-width:0;}
.nd-summary-label {font-size:.81rem;color:#566176;line-height:1.3;margin-bottom:4px;}
.nd-summary-value {font-size:1.65rem;font-weight:750;line-height:1.15;color:#1d2b44;font-variant-numeric:tabular-nums;}
.nd-search-analytics {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:.7rem 0 1rem;}
.nd-analysis-panel {border:1px solid #e3e8f0;border-radius:12px;padding:12px 13px;min-width:0;}
.nd-analysis-title {font-size:1rem;font-weight:750;color:#25334b;margin:0 0 8px;}
.nd-analysis-entry {margin:0 0 8px;}
.nd-analysis-entry:last-child {margin-bottom:0;}
.nd-analysis-label {font-size:.87rem;color:#27364d;margin-bottom:4px;overflow-wrap:anywhere;}
.nd-analysis-track {height:6px;background:#e7eef8;border-radius:6px;overflow:hidden;}
.nd-analysis-fill {height:100%;background:#2487df;border-radius:6px;}
.nd-history-heading {margin: .6rem 0 .3rem;font-size:1.1rem;font-weight:750;color:#25334b;}
@media(max-width:640px) {
 .nd-summary-grid {grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;}
 .nd-summary-card {padding:10px 11px;}
 .nd-summary-value {font-size:1.4rem;}
 .nd-search-analytics {grid-template-columns:1fr;gap:8px;}
 .nd-analysis-panel {padding:10px 12px;}
}
@media(prefers-color-scheme:dark) {
 .nd-summary-card,.nd-analysis-panel {background:#202a39;border-color:#45536a;}
 .nd-summary-label,.nd-analysis-label {color:#d1d9e5;}
 .nd-summary-value,.nd-analysis-title,.nd-history-heading {color:#f5f7ff;}
 .nd-analysis-track {background:#3a4a60;}
}

/* Historical Trends: grouped draw metadata and paginated number tiles. */
.nd-history-group {display:flex;justify-content:space-between;flex-wrap:wrap;
 gap:4px 10px;align-items:center;margin:12px 0 5px;padding:8px 10px;
 background:#f1f6fc;border:1px solid #dce6f3;border-radius:10px;
 color:#24314b;font-size:.9rem;}
.nd-history-group span {font-size:.82rem;color:#5a6a82;}
.nd-history-numbers {margin:5px 0 8px !important;}
.nd-history-numbers .nd-number {padding:9px 4px;}
@media(prefers-color-scheme:dark) {
 .nd-history-group {background:#253246;border-color:#45536a;color:#f5f7ff;}
 .nd-history-group span {color:#c5cfe0;}
}

/* Dense analytics tiles: 12 results per page, no tall progress bars. */
.nd-stat-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:6px 0 10px;}
.nd-stat-tile {min-width:0;display:flex;justify-content:space-between;align-items:center;
 gap:7px;padding:11px 12px;border:1px solid #dfe5ed;border-radius:10px;
 background:#f8faff;color:#24314b;}
.nd-stat-tile strong {font-size:1rem;overflow-wrap:anywhere;}
.nd-stat-tile span {font-size:.86rem;font-weight:700;color:#276aa0;white-space:nowrap;}
@media(max-width:640px) {
 .nd-stat-grid {grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;}
 .nd-stat-tile {padding:9px 10px;}
}
@media(prefers-color-scheme:dark) {
 .nd-stat-tile {background:#253246;border-color:#45536a;color:#f5f7ff;}
 .nd-stat-tile span {color:#a5d5ff;}
}

/* Paginated prize viewer: one category and nine numbers per page. */
.nd-draw-summary {padding:9px 11px;border:1px solid #dfe5ed;border-radius:11px;
 margin:4px 0 9px;color:#27364d;background:#f8faff;font-size:.94rem;}
.nd-draw-summary div {font-size:.83rem;color:#607089;margin-top:3px;}
.nd-prize-info {display:flex;justify-content:space-between;align-items:center;
 gap:8px;margin:9px 0 4px;font-size:.96rem;color:#25334b;}
.nd-prize-info span {font-size:.8rem;color:#65748a;}
.nd-paged-numbers {margin:5px 0 6px !important;}
@media(max-width:640px) {
 .nd-paged-numbers .nd-number {padding:9px 3px;font-size:1rem;}
 .nd-draw-summary {padding:8px 10px;}
}
@media(prefers-color-scheme:dark) {
 .nd-draw-summary {background:#202a39;border-color:#45536a;color:#f4f6fc;}
 .nd-draw-summary div,.nd-prize-info span {color:#c5cfe0;}
 .nd-prize-info {color:#f4f6fc;}
}

/* Dense, readable result cards: minimal scrolling without tiny touch targets. */
.nd-result-card {border:1px solid #dfe5ed;border-radius:12px;padding:11px 12px;margin:5px 0 8px;background:#fff;color:#263347;}
.nd-result-title {font-weight:750;font-size:1rem;line-height:1.3;margin-bottom:6px;overflow-wrap:anywhere;}
.nd-result-meta {display:flex;flex-wrap:wrap;gap:5px 12px;font-size:.86rem;line-height:1.5;color:#465369;}
.nd-result-meta span {display:inline-block;}
.nd-result-number {font-size:1.08rem;font-weight:800;color:#154c85;letter-spacing:.025em;}
.nd-status {display:inline-block;padding:2px 8px;border-radius:30px;background:#e8f7ef;color:#146b46;font-weight:700;font-size:.78rem;}
.nd-list-heading {font-weight:750;font-size:1.08rem;margin:.45rem 0 .25rem;}
.nd-small-note {color:#647084;font-size:.8rem;margin:.2rem 0 .5rem;}
@media(max-width:640px) {
 .nd-result-card {padding:10px 11px;margin:4px 0 7px;}
 .nd-result-title {font-size:.98rem;margin-bottom:4px;}
 .nd-result-meta {gap:3px 9px;font-size:.84rem;}
 .nd-search-analytics {grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:.45rem 0 .55rem;}
 .nd-analysis-panel {padding:8px 9px;}
 .nd-analysis-title {font-size:.83rem;margin-bottom:5px;}
 .nd-analysis-label {font-size:.79rem;margin-bottom:3px;}
 .nd-analysis-entry {margin-bottom:5px;}
 .nd-history-heading {margin:.45rem 0 .2rem;}
}
@media(prefers-color-scheme:dark) {
 .nd-result-card {background:#202a39;border-color:#45536a;color:#f4f6fc;}
 .nd-result-meta,.nd-small-note {color:#c5cfe0;}
 .nd-result-number {color:#a5d5ff;}
}
</style>
""", unsafe_allow_html=True)


# ==========================================
# DISPLAY HELPERS
# ==========================================

def display_lottery_name(result):
    """Public-facing title: state lottery/operator name only."""
    return str(result.get("lottery_name") or "Unknown State Lottery").strip()


def show_simple_records(rows, title_field=None, value_field=None, *, viewer_key="records"):
    """Compact, paginated records without pandas/PyArrow."""
    if not rows:
        st.info("No records available.")
        return

    if title_field and value_field:
        page_size = 12
        total_pages = max(1, (len(rows) + page_size - 1) // page_size)
        st.caption(f"{len(rows)} unique numbers · {page_size} per page")
        if total_pages > 1:
            page = st.selectbox(
                "Select results page",
                options=list(range(1, total_pages + 1)),
                format_func=lambda number: f"Page {number} of {total_pages}",
                key=f"nd_analytics_page_{viewer_key}_{len(rows)}",
            )
        else:
            page = 1

        first = (page - 1) * page_size
        visible = rows[first:first + page_size]
        cards = []
        for row in visible:
            number = escape(str(row.get(title_field) or ""))
            value = escape(str(row.get(value_field, 0)))
            cards.append(
                '<div class="nd-stat-tile">'
                f'<strong>{number}</strong>'
                f'<span>{value}</span>'
                '</div>'
            )
        st.markdown(
            '<div class="nd-stat-grid">' + ''.join(cards) + '</div>',
            unsafe_allow_html=True,
        )
        if total_pages > 1:
            st.caption(
                f"Showing {first + 1}–{first + len(visible)} of {len(rows)}"
            )
    else:
        for index, row in enumerate(rows, start=1):
            with st.expander(f"Record #{index}"):
                if isinstance(row, dict):
                    for field, value in row.items():
                        st.write(f"**{field}:** {value}")
                else:
                    st.write(row)


def render_compact_analysis(title, rows, label_key, count_key):
    """Small responsive bars for search breakdown; no dataframe/PyArrow."""
    values = [max(0, int(row.get(count_key) or 0)) for row in rows]
    highest = max(values, default=0)
    entries = []
    for row, count in zip(rows, values):
        label = escape(str(row.get(label_key) or "N/A"))
        percent = (count / highest * 100) if highest else 0
        entries.append(
            '<div class="nd-analysis-entry">'
            f'<div class="nd-analysis-label">{label} — <strong>{count}</strong></div>'
            '<div class="nd-analysis-track">'
            f'<div class="nd-analysis-fill" style="width:{percent:.1f}%"></div>'
            '</div></div>'
        )
    return (
        '<section class="nd-analysis-panel">'
        f'<div class="nd-analysis-title">{escape(title)}</div>'
        + ''.join(entries)
        + '</section>'
    )


def render_result_card(result, *, matching=False):
    """Compact public card; all dynamic text is HTML escaped."""
    title = escape(display_lottery_name(result))
    meta = []
    state = result.get("state_name")
    if state:
        meta.append(f"<span>📍 {escape(str(state))}</span>")
    date = result.get("result_date")
    if date:
        meta.append(f"<span>📅 {escape(str(date))}</span>")
    draw_time = result.get("draw_time")
    if draw_time:
        meta.append(f"<span>🕒 {escape(format_draw_time(draw_time))}</span>")
    if matching:
        category = result.get("category_name")
        if category:
            meta.append(f"<span>🏅 {escape(str(category))}</span>")
        amount = result.get("prize_amount")
        if amount is not None:
            meta.append(f"<span>💰 {escape(format_amount(amount))}</span>")
        number = escape(str(result.get("winning_number") or ""))
        meta.append(f'<span>🔢 <strong class="nd-result-number">{number}</strong></span>')
    else:
        meta.append('<span class="nd-status">✓ Published</span>')
    return (
        '<article class="nd-result-card">'
        f'<div class="nd-result-title">🎯 {title}</div>'
        '<div class="nd-result-meta">' + ''.join(meta) + '</div></article>'
    )


def format_draw_time(value):
    """
    Convert 18:00:00 into 06:00 PM.
    """
    if not value:
        return "N/A"

    value = str(value).strip()

    for pattern in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(
                value, pattern
            ).strftime("%I:%M %p")
        except ValueError:
            pass

    return value


def format_amount(amount):
    if amount is None:
        return "N/A"

    try:
        return f"₹{float(amount):,.0f}"
    except (ValueError, TypeError):
        return str(amount)


def show_result_information(result):
    """
    Common result details for cards and search.
    """
    st.write(
        "🏷️ **State:**",
        result.get("state_name") or "N/A"
    )
    st.write(
        "📅 **Result Date:**",
        result.get("result_date") or "N/A"
    )
    st.write(
        "🕒 **Draw Time:**",
        format_draw_time(result.get("draw_time"))
    )
    if result.get("draw_number"):
        st.write(
            "🎟️ **Draw Number:**",
            result["draw_number"]
        )


# ==========================================
# PUBLIC NUMBER SEARCH
# ==========================================

def show_number_search():

    st.subheader("🔎 Search Your Lucky Number")

    st.caption(
        "Enter any 4-digit or 5-digit number. "
        "Search across all published lottery results."
    )

    with st.form("winning_number_search_form"):

        ticket_number = st.text_input(
            "🎟️ Enter Lottery Number",
            placeholder="Example: 1256 or 91256",
            max_chars=5
        )

        search_clicked = st.form_submit_button(
            "🔍 Search Number",
            use_container_width=True,
            type="primary"
        )

    if not search_clicked:
        cached = st.session_state.get("nd_last_search")
        if not cached:
            return
        ticket_number = cached["ticket_number"]
        statistics = cached["statistics"]
        breakdown = cached["breakdown"]
    else:
        ticket_number = ticket_number.strip()

    if search_clicked:
        if not re.fullmatch(r"[0-9]{4,5}", ticket_number):
            st.session_state.pop("nd_last_search", None)
            st.warning(
                "Please enter exactly 4 or 5 digits. "
                "Example: 0210 or 91256."
            )
            return
        try:
            with st.spinner("Searching published results..."):
                statistics = get_number_search_statistics(ticket_number)
                breakdown = get_number_search_breakdown(ticket_number)
            st.session_state["nd_last_search"] = {
                "ticket_number": ticket_number,
                "statistics": statistics,
                "breakdown": breakdown,
            }
        except Exception:
            st.session_state.pop("nd_last_search", None)
            st.error("Unable to search lottery results right now. Please try again later.")
            return

    # ======================================
    # SEARCH SUMMARY
    # ======================================

    st.markdown(
        f"### 🎯 Search Results for {ticket_number}"
    )

    total_occurrences = statistics.get(
        "total_occurrences", 0
    )
    matching_draws = statistics.get(
        "matching_draws", 0
    )
    total_draws = statistics.get(
        "total_published_draws", 0
    )
    historical_rate = statistics.get(
        "historical_rate", 0.0
    )

    summary_metrics = [
        ("🏆 Total Occurrences", str(total_occurrences)),
        ("🎟️ Matching Draws", str(matching_draws)),
        ("📅 Published Draws", str(total_draws)),
        ("📊 Historical Rate", f"{historical_rate:.2f}%"),
    ]
    summary_html = ''.join(
        '<div class="nd-summary-card">'
        f'<div class="nd-summary-label">{escape(label)}</div>'
        f'<div class="nd-summary-value">{escape(value)}</div>'
        '</div>'
        for label, value in summary_metrics
    )
    st.markdown(
        '<div class="nd-summary-grid">' + summary_html + '</div>',
        unsafe_allow_html=True
    )

    st.caption(
        "Historical Rate = Matching Published Draws "
        "÷ Total Published Draws × 100. "
        "This is NOT the probability of winning "
        "a future lottery."
    )

    if total_occurrences == 0:

        st.info(
            f"No published winning results found "
            f"for number {ticket_number}."
        )
        return

    st.success(
        f"🎉 Number {ticket_number} appeared "
        f"{total_occurrences} time(s) across "
        f"{matching_draws} published draw(s)."
    )

    # Compact, mobile-friendly prize and draw-time breakdown.
    # The aggregation is unchanged; only its presentation differs.
    if breakdown:
        prize_counts = {}
        time_counts = {}
        for item in breakdown:
            category = item["category_name"]
            count = item["occurrences"]
            prize_counts[category] = prize_counts.get(category, 0) + count
            session = item["draw_session"]
            time_counts[session] = time_counts.get(session, 0) + count

        prize_rows = [
            {"Prize Category": category, "Occurrences": count}
            for category, count in prize_counts.items()
        ]
        time_rows = [
            {"Draw Time": session, "Occurrences": count}
            for session, count in time_counts.items()
        ]
        st.markdown(
            '<div class="nd-search-analytics">'
            + render_compact_analysis(
                "🏆 Prize-wise Analysis", prize_rows, "Prize Category", "Occurrences"
            )
            + render_compact_analysis(
                "🕒 Draw Time Analysis", time_rows, "Draw Time", "Occurrences"
            )
            + '</div>',
            unsafe_allow_html=True
        )

    # ======================================
    # MATCHING RESULT HISTORY
    # ======================================
    st.markdown(
        '<div class="nd-history-heading">📜 Matching Result History</div>',
        unsafe_allow_html=True
    )
    st.caption(
        "Browse all matching prize records, eight per page. "
        "Statistics are calculated from all published results."
    )

    page_size = 8
    total_matches = max(0, int(total_occurrences))
    page_count = max(1, (total_matches + page_size - 1) // page_size)
    page_key = f"nd_match_page_{ticket_number}"
    if search_clicked:
        st.session_state[page_key] = 1

    if page_count > 1:
        # A numeric selector avoids creating an enormous options list.
        current_page = int(st.number_input(
            "Matching results page",
            min_value=1,
            max_value=page_count,
            step=1,
            key=page_key,
        ))
    else:
        current_page = 1

    # Fetch the selected page from Supabase, not from a full local result set.
    try:
        with st.spinner("Loading matching result history..."):
            page_data = search_winning_number_page(
                ticket_number, page=current_page, page_size=page_size
            )
        shown = page_data["records"]
        # The RPC count is authoritative when a nonempty page is returned.
        if shown:
            total_matches = page_data["total_count"]
    except Exception:
        st.error("Unable to load matching history right now. Please try again later.")
        return

    begin = (current_page - 1) * page_size
    if shown:
        st.markdown(
            f'<div class="nd-small-note">Showing {begin + 1}–{begin + len(shown)} '
            f'of {total_matches} matching records</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No matching records on this page. Please refresh your search.")
    for match in shown:
        st.markdown(render_result_card(match, matching=True), unsafe_allow_html=True)


# ==========================================
# PUBLIC RESULTS DASHBOARD
# ==========================================

def show_public_dashboard():

    # Search is available even when there
    # are no results in the latest-10 list.
    show_number_search()

    st.divider()
    st.subheader("🏆 Latest Lottery Results")

    try:
        with st.spinner("Loading published lottery results..."):
            # The lightweight metadata listing is paginated by PostgreSQL.
            first_page = get_published_draws_page(page=1, page_size=4)
            published_total = first_page["total_count"]
            page_count = max(1, (published_total + 3) // 4)
            selected_page = st.selectbox(
                "Published results page",
                options=list(range(1, page_count + 1)),
                format_func=lambda n: f"Page {n} of {page_count}",
                key="nd_published_results_page",
            ) if page_count > 1 else 1
            listing = (first_page if selected_page == 1 else
                       get_published_draws_page(page=selected_page, page_size=4))
            # Existing prize viewer and analytics remain on their tested RPC.
            # The detailed viewer now pages via its own RPC; the legacy nested
            # fetch remains for prize metadata and analytics until later steps.
            results = get_public_lottery_results(limit=10)
    except Exception:
        st.error("Unable to load lottery results right now. Please try again later.")
        return

    if published_total == 0:
        st.info("📭 No published lottery results are available yet.")
    else:
        st.markdown('<div class="nd-list-heading">🎟️ Published Results</div>', unsafe_allow_html=True)
        page_rows = listing["records"]
        first_number = (selected_page - 1) * 4 + 1
        last_number = first_number + len(page_rows) - 1
        st.caption(f"Showing published draws {first_number}–{last_number} of {published_total}")
        for start in range(0, len(page_rows), 2):
            columns = st.columns(2)
            for column, result in zip(columns, page_rows[start:start + 2]):
                with column:
                    st.markdown(render_result_card(result), unsafe_allow_html=True)

        # ==================================
        # DETAILED WINNING NUMBERS
        # ==================================

        st.divider()

        with st.expander(
            "🔢 Detailed Winning Numbers — Show / Hide",
            expanded=False
        ):

            draw_options = {
                str(result["draw_id"]): result
                for result in results
            }

            selected_draw_id = st.selectbox(
                "Select a lottery result",
                options=list(draw_options.keys()),
                format_func=lambda draw_id: (
                    f"{display_lottery_name(draw_options[draw_id])} "
                    f"| {draw_options[draw_id].get('result_date', 'N/A')} "
                    f"| {format_draw_time(draw_options[draw_id].get('draw_time'))}"
                ),
                key="public_selected_draw"
            )

            selected_draw = draw_options[
                selected_draw_id
            ]

            # Compact draw summary, avoiding repeated multi-line metadata.
            draw_summary = (
                f'<div class="nd-draw-summary">'
                f'<strong>🎯 {escape(display_lottery_name(selected_draw))}</strong>'
                f'<div>{escape(str(selected_draw.get("state_name") or ""))}'
                f' · {escape(str(selected_draw.get("result_date") or ""))}'
                f' · {escape(format_draw_time(selected_draw.get("draw_time")))}</div>'
                f'</div>'
            )
            st.markdown(draw_summary, unsafe_allow_html=True)

            prizes = selected_draw.get("prizes") or []
            if not prizes:
                st.info("No prize details are available for this result.")
            else:
                # The category selector is scoped to the selected draw.
                category_labels = [
                    f"{prize.get('category_name') or 'Prize Category'} "
                    f"({len(prize.get('winning_numbers') or [])})"
                    for prize in prizes
                ]
                category_index = st.selectbox(
                    "🏅 Select Prize Category",
                    options=list(range(len(prizes))),
                    format_func=lambda index: category_labels[index],
                    key=f"nd_prize_category_{selected_draw_id}",
                )
                prize = prizes[category_index]
                category_name = prize.get("category_name") or "Prize Category"
                prize_amount = prize.get("prize_amount")
                # Filter and paginate in PostgreSQL, not in Python.
                viewer_key = f"{selected_draw_id}_{category_index}"
                number_query = st.text_input(
                    "🔎 Find a number in this prize",
                    placeholder="Type a full number or part of it",
                    key=f"nd_prize_find_{viewer_key}",
                ).strip()
                if len(number_query) > 100:
                    st.warning("Search is limited to 100 characters.")
                else:
                    page_size = 9
                    try:
                        first_page = get_published_prize_numbers_page(
                            selected_draw_id, category_name, page=1,
                            page_size=page_size, search=number_query,
                        )
                        total_matches = first_page["total_count"]
                        total_pages = max(1, first_page["total_pages"])
                        st.markdown(
                            '<div class="nd-prize-info">'
                            f'<strong>{escape(str(category_name))}</strong>'
                            f'<span>{total_matches} of '
                            f'{len(prize.get("winning_numbers") or [])} numbers</span></div>',
                            unsafe_allow_html=True,
                        )
                        if prize_amount is not None:
                            st.caption(f"Prize Amount: {format_amount(prize_amount)}")

                        if not total_matches:
                            st.info("No matching number found in this prize.")
                        else:
                            page_number = st.selectbox(
                                "Page",
                                options=list(range(1, total_pages + 1)),
                                format_func=lambda n: f"Page {n} of {total_pages}",
                                key=f"nd_prize_page_{viewer_key}_{number_query}_{total_pages}",
                                label_visibility="collapsed",
                            ) if total_pages > 1 else 1
                            page_data = (first_page if page_number == 1 else
                                         get_published_prize_numbers_page(
                                             selected_draw_id, category_name,
                                             page=page_number, page_size=page_size,
                                             search=number_query,
                                         ))
                            visible_numbers = page_data["winning_numbers"]
                            tiles = "".join(
                                f'<div class="nd-number">{escape(number)}</div>'
                                for number in visible_numbers
                            )
                            st.markdown(
                                f'<div class="nd-number-grid nd-paged-numbers">{tiles}</div>',
                                unsafe_allow_html=True,
                            )
                            if total_pages > 1:
                                first = (page_number - 1) * page_size
                                st.caption(
                                    f"Showing {first + 1}–"
                                    f"{first + len(visible_numbers)} of "
                                    f"{total_matches} numbers"
                                )
                    except Exception:
                        st.error("Unable to load prize numbers. Please try again.")

    # Compact navigation: keep each analytics feature and its original logic.
    st.divider()
    st.subheader("📈 Lottery Analytics")
    frequency_tab, distribution_tab, history_tab = st.tabs(
        ["📊 Frequency", "📈 Distribution", "📅 History"]
    )

    with frequency_tab:
        # ======================================
        # FREQUENCY ANALYSIS
        # ======================================

        st.markdown("### 📊 Frequency Analysis")

        st.caption(
            "Analyze how often winning numbers "
            "have appeared in published results."
        )

        if not results:
            st.info(
                "Frequency Analysis will be available "
                "once lottery results are published."
            )

        else:
            lottery_options = sorted({
                result.get("lottery_name")
                for result in results
                if result.get("lottery_name")
            })

            if not lottery_options:
                st.info(
                    "No state lotteries available "
                    "for analysis."
                )

            else:
                selected_lottery = st.selectbox(
                    "Select State Lottery",
                    options=lottery_options,
                    key="frequency_lottery_name"
                )

                category_options = sorted({
                    prize.get("category_name")
                    for result in results
                    if result.get("lottery_name") == selected_lottery
                    for prize in (result.get("prizes") or [])
                    if prize.get("category_name")
                })

                if not category_options:
                    st.info(
                        "No prize categories available "
                        "for this state lottery."
                    )

                else:
                    selected_category = st.selectbox(
                        "Select Prize Category",
                        options=category_options,
                        key="frequency_category"
                    )

                    selection = (selected_lottery, selected_category)
                    state_key = "nd_frequency_result"
                    page_key = "nd_frequency_server_page"
                    if st.button(
                        "📊 Analyze Frequency",
                        use_container_width=True
                    ):
                        # Store only the selection, not the entire frequency dataset.
                        st.session_state[state_key] = selection
                        st.session_state[page_key] = 1

                    if st.session_state.get(state_key) == selection:
                        page_size = 12
                        try:
                            # First request supplies the global count and first page.
                            with st.spinner("Analyzing published winning numbers..."):
                                first_page = get_winning_number_frequency_page(
                                    selected_lottery, selected_category,
                                    page=1, page_size=page_size,
                                )
                            total_count = first_page["total_count"]
                            total_occurrences = first_page["total_occurrences"]
                            total_pages = max(1, first_page["total_pages"])

                            if total_count == 0:
                                st.info("No frequency data available for this selection.")
                            else:
                                st.success(
                                    f"Found {total_count} unique winning number(s)."
                                )
                                st.caption(
                                    f"{total_occurrences} historical occurrence(s) "
                                    f"· {page_size} unique numbers per page"
                                )
                                # A number input avoids building an enormous page list.
                                # Reset an out-of-range page when published data changes.
                                if st.session_state.get(page_key, 1) > total_pages:
                                    st.session_state[page_key] = 1
                                if total_pages > 1:
                                    page = int(st.number_input(
                                        "Frequency results page",
                                        min_value=1,
                                        max_value=total_pages,
                                        step=1,
                                        key=page_key,
                                    ))
                                else:
                                    page = 1

                                data = (first_page if page == 1 else
                                        get_winning_number_frequency_page(
                                            selected_lottery, selected_category,
                                            page=page, page_size=page_size,
                                        ))
                                rows = data["frequencies"]
                                if not rows:
                                    st.info("No frequency records on this page.")
                                else:
                                    tiles = []
                                    for item in rows:
                                        number = escape(str(item.get("winning_number") or ""))
                                        frequency = escape(str(item.get("frequency", 0)))
                                        tiles.append(
                                            '<div class="nd-stat-tile">'
                                            f'<strong>{number}</strong>'
                                            f'<span>{frequency}</span>'
                                            '</div>'
                                        )
                                    st.markdown(
                                        '<div class="nd-stat-grid">' + ''.join(tiles) + '</div>',
                                        unsafe_allow_html=True,
                                    )
                                    first = (page - 1) * page_size + 1
                                    st.caption(
                                        f"Showing {first}–{first + len(rows) - 1} "
                                        f"of {total_count} unique numbers "
                                        f"· Page {page} of {total_pages}"
                                    )
                        except Exception:
                            st.error(
                                "Unable to analyze frequency right now. "
                                "Please try again later."
                            )

    with distribution_tab:
        # ======================================
        # PROBABILITY DISTRIBUTION
        # ======================================

        st.markdown("### 📊 Probability Distribution")

        st.caption(
            "Historical percentage distribution of "
            "winning numbers. This does not predict "
            "future lottery outcomes."
        )

        if not results:
            st.info(
                "Probability Distribution will be available "
                "once lottery results are published."
            )

        else:
            probability_lotteries = sorted({
                result.get("lottery_name")
                for result in results
                if result.get("lottery_name")
            })

            if not probability_lotteries:
                st.info(
                    "No state lotteries available "
                    "for analysis."
                )

            else:
                probability_lottery = st.selectbox(
                    "Select State Lottery",
                    options=probability_lotteries,
                    key="probability_lottery"
                )

                probability_categories = sorted({
                    prize.get("category_name")
                    for result in results
                    if result.get("lottery_name") == probability_lottery
                    for prize in (result.get("prizes") or [])
                    if prize.get("category_name")
                })

                if not probability_categories:
                    st.info(
                        "No prize categories available "
                        "for this state lottery."
                    )

                else:
                    probability_category = st.selectbox(
                        "Select Prize Category",
                        options=probability_categories,
                        key="probability_category"
                    )

                    selection = (probability_lottery, probability_category)
                    state_key = "nd_distribution_result"
                    page_key = "nd_distribution_server_page"
                    if st.button(
                        "📊 Analyze Distribution",
                        use_container_width=True
                    ):
                        # Save only the selected filters, not the entire dataset.
                        st.session_state[state_key] = selection
                        st.session_state[page_key] = 1

                    if st.session_state.get(state_key) == selection:
                        page_size = 12
                        try:
                            with st.spinner("Calculating historical distribution..."):
                                first_page = get_winning_number_probability_page(
                                    probability_lottery, probability_category,
                                    page=1, page_size=page_size,
                                )
                            total_count = first_page["total_count"]
                            total_occurrences = first_page["total_occurrences"]
                            total_pages = max(1, first_page["total_pages"])

                            if total_count == 0:
                                st.info("No historical distribution data available.")
                            else:
                                st.success(f"Analyzed {total_count} unique winning numbers.")
                                st.caption(
                                    f"{total_occurrences} historical occurrence(s) "
                                    f"· {page_size} unique numbers per page · "
                                    "Historical share (%) — not a prediction of future results."
                                )
                                if not 1 <= st.session_state.get(page_key, 1) <= total_pages:
                                    st.session_state[page_key] = 1
                                if total_pages > 1:
                                    page = int(st.number_input(
                                        "Distribution results page",
                                        min_value=1,
                                        max_value=total_pages,
                                        step=1,
                                        key=page_key,
                                    ))
                                else:
                                    page = 1

                                data = (first_page if page == 1 else
                                        get_winning_number_probability_page(
                                            probability_lottery, probability_category,
                                            page=page, page_size=page_size,
                                        ))
                                rows = data["distribution"]
                                if not rows:
                                    st.info("No distribution records on this page.")
                                else:
                                    tiles = []
                                    for item in rows:
                                        number = escape(str(item.get("winning_number") or ""))
                                        percentage = float(item.get("percentage") or 0)
                                        tiles.append(
                                            '<div class="nd-stat-tile">'
                                            f'<strong>{number}</strong>'
                                            f'<span>{percentage:.2f}%</span>'
                                            '</div>'
                                        )
                                    st.markdown(
                                        '<div class="nd-stat-grid">' + ''.join(tiles) + '</div>',
                                        unsafe_allow_html=True,
                                    )
                                    first = (page - 1) * page_size + 1
                                    st.caption(
                                        f"Showing {first}–{first + len(rows) - 1} "
                                        f"of {total_count} unique numbers "
                                        f"· Page {page} of {total_pages}"
                                    )
                        except Exception:
                            st.error(
                                "Unable to calculate historical distribution right now. "
                                "Please try again later."
                            )

    with history_tab:
        # ======================================
        # HISTORICAL TRENDS
        # ======================================

        st.markdown("### 📉 Historical Trends")

        st.caption(
            "Explore date-wise historical winning "
            "numbers from published lottery results."
        )

        if not results:
            st.info(
                "Historical Trends will be available "
                "once lottery results are published."
            )

        else:
            historical_lotteries = sorted({
                result.get("lottery_name")
                for result in results
                if result.get("lottery_name")
            })

            if not historical_lotteries:
                st.info(
                    "No state lotteries available."
                )

            else:
                historical_lottery = st.selectbox(
                    "Select State Lottery",
                    options=historical_lotteries,
                    key="historical_lottery"
                )

                historical_categories = sorted({
                    prize.get("category_name")
                    for result in results
                    if result.get("lottery_name") == historical_lottery
                    for prize in (result.get("prizes") or [])
                    if prize.get("category_name")
                })

                if not historical_categories:
                    st.info(
                        "No prize categories available."
                    )

                else:
                    historical_category = st.selectbox(
                        "Select Prize Category",
                        options=historical_categories,
                        key="historical_category"
                    )

                    selection = (historical_lottery, historical_category)
                    state_key = "nd_historical_result"
                    draw_page_key = "nd_history_server_draw_page"
                    if st.button(
                        "📉 Analyze Historical Trends",
                        use_container_width=True
                    ):
                        # Store only the filters. The server returns paged data.
                        st.session_state[state_key] = selection
                        st.session_state[draw_page_key] = 1

                    if st.session_state.get(state_key) == selection:
                        draws_per_page = 5
                        numbers_per_page = 9
                        try:
                            with st.spinner("Loading historical draw summaries..."):
                                first_draw_page = get_historical_draws_page(
                                    historical_lottery, historical_category,
                                    page=1, page_size=draws_per_page,
                                )
                            total_draws = int(first_draw_page["total_draws"])
                            total_numbers = int(first_draw_page["total_numbers"])
                            draw_pages = max(1, int(first_draw_page["total_pages"]))

                            if total_draws == 0:
                                st.info("No historical data available.")
                            else:
                                st.success(
                                    f"Found {total_numbers} historical winning-number "
                                    f"records across {total_draws} draw(s)."
                                )
                                st.caption(
                                    f"{draws_per_page} draws per page · "
                                    f"{numbers_per_page} numbers per draw page"
                                )

                                if not 1 <= st.session_state.get(draw_page_key, 1) <= draw_pages:
                                    st.session_state[draw_page_key] = 1
                                if draw_pages > 1:
                                    draw_page = int(st.number_input(
                                        "Historical draws page",
                                        min_value=1,
                                        max_value=draw_pages,
                                        step=1,
                                        key=draw_page_key,
                                    ))
                                else:
                                    draw_page = 1

                                draw_data = (
                                    first_draw_page if draw_page == 1 else
                                    get_historical_draws_page(
                                        historical_lottery, historical_category,
                                        page=draw_page, page_size=draws_per_page,
                                    )
                                )
                                visible_draws = draw_data["draws"]
                                st.caption(
                                    f"Draws page {draw_page} of {draw_pages} · "
                                    f"Showing {len(visible_draws)} draw(s)"
                                )

                                date_counts = {}
                                for draw in visible_draws:
                                    draw_id = str(draw["draw_id"])
                                    result_date = str(draw.get("result_date") or "")
                                    draw_time = format_draw_time(draw.get("draw_time"))
                                    number_count = int(draw.get("number_count") or 0)
                                    date_counts[result_date] = (
                                        date_counts.get(result_date, 0) + number_count
                                    )
                                    st.markdown(
                                        '<div class="nd-history-group">'
                                        f'<strong>📅 {escape(result_date)}</strong>'
                                        f'<span>🕒 {escape(draw_time)}'
                                        f' · {number_count} numbers</span>'
                                        '</div>',
                                        unsafe_allow_html=True,
                                    )

                                    number_pages = max(
                                        1, (number_count + numbers_per_page - 1)
                                        // numbers_per_page
                                    )
                                    number_page_key = (
                                        f"nd_history_server_numbers_"
                                        f"{historical_lottery}_{historical_category}_{draw_id}"
                                    )
                                    if not 1 <= st.session_state.get(number_page_key, 1) <= number_pages:
                                        st.session_state[number_page_key] = 1
                                    if number_pages > 1:
                                        number_page = int(st.number_input(
                                            f"Winning numbers page — {result_date} {draw_time}",
                                            min_value=1,
                                            max_value=number_pages,
                                            step=1,
                                            key=number_page_key,
                                        ))
                                    else:
                                        number_page = 1

                                    numbers_data = get_historical_draw_numbers_page(
                                        draw_id, historical_category,
                                        page=number_page, page_size=numbers_per_page,
                                    )
                                    visible_numbers = numbers_data["winning_numbers"]
                                    tiles = ''.join(
                                        '<div class="nd-number">'
                                        f'{escape(str(number))}</div>'
                                        for number in visible_numbers
                                    )
                                    st.markdown(
                                        '<div class="nd-number-grid nd-history-numbers">'
                                        + tiles + '</div>',
                                        unsafe_allow_html=True,
                                    )
                                    if number_count:
                                        first_number = (number_page - 1) * numbers_per_page + 1
                                        st.caption(
                                            f"Showing {first_number}–"
                                            f"{first_number + len(visible_numbers) - 1} "
                                            f"of {number_count} numbers · "
                                            f"Page {number_page} of {number_pages}"
                                        )

                                st.markdown("#### 📊 Winning Numbers by Result Date")
                                st.caption("Counts for the draws on this page only.")
                                chart_rows = [
                                    {"Result Date": date, "Winning Numbers": count}
                                    for date, count in sorted(date_counts.items())
                                ]
                                show_simple_records(
                                    chart_rows, "Result Date", "Winning Numbers",
                                    viewer_key=(
                                        f"historical_dates_{historical_lottery}_"
                                        f"{historical_category}_{draw_page}"
                                    ),
                                )
                        except Exception:
                            st.error(
                                "Unable to load historical trends right now. "
                                "Please try again later."
                            )

    st.caption(
        "Analytics are based on published lottery "
        "results. Historical statistics do not "
        "guarantee future outcomes."
    )


# ==========================================
# APPLICATION HEADER
# ==========================================



# ==========================================
# NAVIGATION
# ==========================================

page = st.sidebar.radio(
    "Navigation",
    ["🏠 Dashboard", "🔐 Admin Login"]
)

if page == "🏠 Dashboard":
    st.markdown(
        '<section class="nd-hero"><h1>🎯 NumberDuniya</h1>'
        '<p>Apna lucky number search karein · Lottery results & analytics</p>'
        '</section>',
        unsafe_allow_html=True
    )
    show_public_dashboard()

elif page == "🔐 Admin Login":

    if st.session_state.get("admin_authenticated"):

        show_admin_dashboard()

        if st.button("🚪 Logout"):

            client = st.session_state.get(
                "admin_client"
            )

            if client:
                try:
                    client.auth.sign_out()
                except Exception:
                    pass

            st.session_state.pop(
                "admin_authenticated",
                None
            )

            st.session_state.pop(
                "admin_client",
                None
            )

            st.rerun()

    else:
        show_admin_login()


# ==========================================
# NUMBERDUNIYA COPYRIGHT FOOTER
# ==========================================

st.divider()

st.markdown(
    f"""
    <div style="
        text-align: center;
        color: #888888;
        font-size: 13px;
        padding: 12px 0 20px 0;
        line-height: 1.8;
    ">
        © {datetime.now().year} NumberDuniya.
        All Rights Reserved.
        <br>
        Developed by <strong>Md Samim Ansari</strong>
    </div>
    """,
    unsafe_allow_html=True
)
