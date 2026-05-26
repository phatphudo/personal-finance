import streamlit as st

st.set_page_config(
    page_title="Personal Finance Dashboard",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Login gate ────────────────────────────────────────────────────────────────
if not st.session_state.get("authenticated"):
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        st.markdown("## 💰 Finance Dashboard")
        st.caption("Sign in to continue")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", width="stretch")

        if submitted:
            if (
                username == st.secrets["auth"]["username"]
                and password == st.secrets["auth"]["password"]
            ):
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Invalid username or password.")

    st.stop()


st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        /* ── Sidebar ── */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
        }
        [data-testid="stSidebar"] * {
            color: #e0e0e0 !important;
        }

        /* ── Metric cards ── adaptive border/bg via CSS variable approach */
        [data-testid="metric-container"] {
            border-radius: 12px;
            padding: 16px 20px;
            border: 1px solid rgba(128, 128, 128, 0.25);
        }
        [data-testid="metric-container"] label {
            font-size: 0.78rem !important;
            font-weight: 600 !important;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            opacity: 0.65;
        }
        [data-testid="metric-container"] [data-testid="stMetricValue"] {
            font-size: 1.6rem !important;
            font-weight: 700 !important;
        }

        /* light mode overrides */
        @media (prefers-color-scheme: light) {
            [data-testid="metric-container"] {
                background: #f7f8fc;
                border-color: #e0e3ef;
            }
            [data-testid="stExpander"] {
                background: #f7f8fc;
                border: 1px solid #e0e3ef;
                border-radius: 8px;
            }
            h2 { color: #1a1a2e; }
            h3, h4 { color: #3a3f5c; }
            hr { border-color: #e0e3ef; }
            .logo-area { border-bottom-color: #2d3145; }
        }

        /* dark mode overrides */
        @media (prefers-color-scheme: dark) {
            [data-testid="metric-container"] {
                background: #1c1f2b;
                border-color: #2d3145;
            }
            [data-testid="stExpander"] {
                background: #1c1f2b;
                border: 1px solid #2d3145;
                border-radius: 8px;
            }
            h2 { color: #ffffff; }
            h3, h4 { color: #c0c8e0; }
            hr { border-color: #2d3145; }
        }

        /* ── DataFrame ── */
        [data-testid="stDataFrame"] {
            border-radius: 8px;
            overflow: hidden;
        }

        /* ── Primary buttons ── */
        .stButton button[kind="primary"] {
            background: linear-gradient(135deg, #6C63FF, #a855f7);
            border: none;
            color: white !important;
            border-radius: 8px;
            font-weight: 600;
            padding: 0.5rem 1.5rem;
            transition: opacity 0.2s;
        }
        .stButton button[kind="primary"]:hover {
            opacity: 0.85;
        }

        /* ── Headings ── */
        h2 { font-weight: 700; margin-bottom: 0.25rem; }
        h3, h4 { font-weight: 600; }

        /* ── Sidebar logo area ── */
        .logo-area {
            padding: 1rem 0.5rem 2rem;
            border-bottom: 1px solid #2d3145;
            margin-bottom: 1rem;
        }
        .logo-area h1 {
            font-size: 1.2rem;
            font-weight: 700;
            color: #ffffff;
            margin: 0;
        }
        .logo-area p {
            font-size: 0.75rem;
            color: #8899cc;
            margin: 0;
        }

        /* ── Selectbox labels ── */
        [data-testid="stSelectbox"] label,
        [data-testid="stMultiSelect"] label {
            font-size: 0.82rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            opacity: 0.7;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div class="logo-area">
            <h1>💰 Finance Dashboard</h1>
            <p>Personal tracking & insights</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tool = st.radio(
        "Tool",
        ["⏱️ Work Hours", "💳 Budget Tracker", "⚙️ Settings"],
        label_visibility="collapsed",
    )

    if tool == "⏱️ Work Hours":
        view = st.radio(
            "View",
            ["Current Pay Period", "Period Comparison"],
            key="wh_view",
        )
    elif tool == "💳 Budget Tracker":
        view = st.radio(
            "View",
            ["Current Month", "Monthly Comparison", "Deposit Tracker"],
            key="budget_view",
        )
    else:
        view = None

    st.markdown("---")
    st.caption("Data source: Google Sheets")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

# ── Route to component ────────────────────────────────────────────────────────
if tool == "⚙️ Settings":
    from components import settings as settings_page

    settings_page.render()
elif tool == "⏱️ Work Hours":
    if view == "Current Pay Period":
        from components.work_hours import current as wh_current

        wh_current.render()
    else:
        from components.work_hours import compare as wh_compare

        wh_compare.render()
else:
    if view == "Current Month":
        from components.budget import current as budget_current

        budget_current.render()
    elif view == "Deposit Tracker":
        from components.budget import deposit_tracker

        deposit_tracker.render()
    else:
        from components.budget import compare as budget_compare

        budget_compare.render()
