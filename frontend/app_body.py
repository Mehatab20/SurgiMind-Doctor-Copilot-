# =============================================================================
# app_with_db_body.py  –  DB-integrated dashboard body
# Concatenated with app_with_db_header.py by build_app_with_db.py
# =============================================================================

import streamlit as st
import time
import json
import base64
import os

st.set_page_config(
    page_title="SurgiMind",
    layout="wide",
    initial_sidebar_state="expanded" 
)

if "auth_page" not in st.session_state:
    st.session_state["auth_page"] = "login"

# ── Import DB helpers ─────────────────────────────────────────────────────────
from backend.database_manager import (
    db,
    st_login, st_signup, st_logout, st_restore_session,
    st_save_report_after_assessment,
    st_export_report_json,
)

# =============================================================================
# CSS  (same palette as before, extended for auth pages and history panel)
# =============================================================================
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
:root {
    --navy:        #0D2B5E;
    --navy-mid:    #1A4080;
    --teal:        #1CB5A3;
    --teal-light:  #2DD4BF;
    --teal-dark:   #0E8A7C;
    --cyan:        #17C3CE;
    --bg:          #F4F7FB;
    --card-bg:     #FFFFFF;
    --border:      #E2EAF4;
    --text-dark:   #0D2B5E;
    --text-mid:    #3A5278;
    --text-light:  #6B84A8;
    --red:         #E53935;
    --red-soft:    #FFEBEE;
    --amber:       #F57C00;
    --amber-soft:  #FFF3E0;
    --green:       #2E7D32;
    --green-soft:  #E8F5E9;
    --shadow-sm:   0 2px 8px rgba(13,43,94,.07);
    --shadow-md:   0 4px 20px rgba(13,43,94,.12);
    --radius:      16px;
    --radius-sm:   10px;
}
html, body, [data-testid="stAppViewContainer"] {
    font-family: 'Inter', sans-serif !important;
    background: var(--bg) !important;
    color: var(--text-dark) !important;
}
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stAppViewContainer"] > .main > .block-container {
    padding: 0 2rem 2rem 2rem !important;
    max-width: 1400px !important;
}
[data-testid="stSidebar"] {
    background: linear-gradient(175deg, var(--navy) 0%, var(--navy-mid) 60%, #0F3460 100%) !important;
    border-right: none !important;
    box-shadow: 4px 0 24px rgba(13,43,94,.25) !important;
}
[data-testid="stSidebar"] * { color: #E8F0FA !important; }
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stSelectbox select,
[data-testid="stSidebar"] .stNumberInput input,
[data-testid="stSidebar"] .stTextArea textarea {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.20) !important;
    border-radius: var(--radius-sm) !important;
    color: #FFFFFF !important; font-size: 0.88rem !important;
}
[data-testid="stSidebar"] label {
    color: #B8D0F0 !important; font-size: 0.78rem !important;
    font-weight: 600 !important; letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
}
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.20) !important;
    border-radius: var(--radius-sm) !important;
}
.stButton > button {
    background: linear-gradient(135deg, var(--teal) 0%, var(--cyan) 100%) !important;
    color: #FFFFFF !important; border: none !important;
    border-radius: 50px !important; font-weight: 700 !important;
    font-size: 0.95rem !important; width: 100% !important;
    padding: 0.65rem 1.8rem !important; transition: all 0.25s ease !important;
    box-shadow: 0 4px 16px rgba(28,181,163,.40) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 28px rgba(28,181,163,.55) !important;
}
/* ── Auth pages ──────────────────────────────────────────────────────────── */
.auth-wrapper {
    min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, var(--navy) 0%, #0F3460 60%, var(--teal-dark) 100%);
}
.auth-card {
    background: #fff; border-radius: 24px;
    padding: 2.5rem 3rem; width: 100%; max-width: 480px;
    box-shadow: 0 24px 80px rgba(13,43,94,.30);
}
.auth-logo-row { text-align: center; margin-bottom: 1.5rem; }
.auth-title {
    font-size: 1.6rem; font-weight: 800; color: var(--navy);
    letter-spacing: -0.03em; margin: 0.5rem 0 0.2rem;
}
.auth-title span { color: var(--teal); }
.auth-subtitle { font-size: 0.8rem; color: var(--text-light); letter-spacing: 0.06em; }
.auth-tab-row { display: flex; gap: 0; border-bottom: 2px solid var(--border); margin-bottom: 1.75rem; }
.auth-tab {
    flex: 1; text-align: center; padding: 0.65rem;
    font-size: 0.85rem; font-weight: 700; cursor: pointer;
    color: var(--text-light); border-bottom: 2px solid transparent;
    margin-bottom: -2px; transition: all 0.2s;
}
.auth-tab.active { color: var(--navy); border-color: var(--teal); }

/* ── Cards ───────────────────────────────────────────────────────────────── */
.sm-card {
    background: var(--card-bg); border-radius: var(--radius);
    border: 1px solid var(--border); box-shadow: var(--shadow-sm);
    padding: 1.5rem 1.75rem; margin-bottom: 1.25rem;
    transition: box-shadow 0.2s ease;
}
.sm-card:hover { box-shadow: var(--shadow-md); }
.sm-card-title {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--text-light); margin: 0 0 0.75rem 0;
}

/* ── Top nav ─────────────────────────────────────────────────────────────── */
.sm-topbar {
    background: linear-gradient(90deg, var(--navy) 0%, var(--navy-mid) 100%);
    border-radius: 0 0 var(--radius) var(--radius);
    padding: 0.9rem 2rem; display: flex; align-items: center;
    justify-content: space-between; margin: 0 -2rem 1.75rem -2rem;
    box-shadow: var(--shadow-md);
}
.sm-topbar-brand { display: flex; align-items: center; gap: 0.75rem; }
.sm-topbar-title { font-size: 1.35rem; font-weight: 800; color: #fff; letter-spacing: -0.02em; }
.sm-topbar-title span { color: var(--teal-light); }
.sm-topbar-sub { font-size: 0.72rem; color: #7EC8E3; letter-spacing: 0.12em; text-transform: uppercase; }
.sm-topbar-right { display: flex; align-items: center; gap: 1rem; }
.sm-topbar-user { font-size: 0.8rem; color: #B8D8F8; font-weight: 500; }
.sm-topbar-badge {
    background: rgba(44,212,191,.18); border: 1px solid rgba(44,212,191,.35);
    color: var(--teal-light); border-radius: 50px; padding: 0.3rem 1rem;
    font-size: 0.72rem; font-weight: 600;
}

/* ── Risk gauge ──────────────────────────────────────────────────────────── */
.risk-gauge-card {
    background: var(--card-bg); border-radius: var(--radius);
    border: 1px solid var(--border); box-shadow: var(--shadow-md);
    padding: 1.75rem 2rem; margin-bottom: 1.25rem;
    text-align: center; position: relative; overflow: hidden;
}
.risk-gauge-card::before {
    content: ""; position: absolute; top: 0; left: 0; right: 0;
    height: 4px; border-radius: var(--radius) var(--radius) 0 0;
}
.risk-gauge-card.risk-high::before  { background: linear-gradient(90deg,#E53935,#FF5252); }
.risk-gauge-card.risk-med::before   { background: linear-gradient(90deg,#F57C00,#FFB300); }
.risk-gauge-card.risk-low::before   { background: linear-gradient(90deg,#2E7D32,#43A047); }
.risk-level-badge {
    display: inline-flex; align-items: center; gap: 0.5rem;
    padding: 0.45rem 1.4rem; border-radius: 50px;
    font-size: 0.8rem; font-weight: 700; letter-spacing: 0.1em;
    text-transform: uppercase; margin-bottom: 0.6rem;
}
.badge-high   { background: var(--red-soft);   color: var(--red);   border: 1.5px solid #FFCDD2; }
.badge-medium { background: var(--amber-soft); color: var(--amber); border: 1.5px solid #FFE0B2; }
.badge-low    { background: var(--green-soft); color: var(--green); border: 1.5px solid #C8E6C9; }
.risk-big-number { font-size: 4rem; font-weight: 800; line-height: 1; letter-spacing: -0.04em; margin: 0.4rem 0; }
.risk-big-high   { color: var(--red); }
.risk-big-medium { color: var(--amber); }
.risk-big-low    { color: var(--green); }
.confidence-row  { display: flex; align-items: center; justify-content: center; gap: 0.6rem; margin-top: 0.75rem; }
.conf-label  { font-size: 0.75rem; font-weight: 600; color: var(--text-light); text-transform: uppercase; }
.conf-bar-wrap { flex: 1; max-width: 160px; height: 8px; background: var(--border); border-radius: 50px; overflow: hidden; }
.conf-bar-fill { height: 100%; border-radius: 50px; }
.conf-bar-high   { background: linear-gradient(90deg,#E53935,#FF5252); }
.conf-bar-medium { background: linear-gradient(90deg,#F57C00,#FFB300); }
.conf-bar-low    { background: linear-gradient(90deg,#2E7D32,#43A047); }
.conf-pct { font-size: 0.9rem; font-weight: 700; color: var(--text-dark); }

/* ── History panel ───────────────────────────────────────────────────────── */
.hist-item {
    display: flex; align-items: center; gap: 0.75rem;
    padding: 0.7rem 0.9rem; border-radius: var(--radius-sm);
    border: 1px solid var(--border); margin-bottom: 0.4rem;
    cursor: pointer; transition: all 0.15s; background: #FAFCFF;
}
.hist-item:hover { background: #EEF5FF; border-color: #C5D8F7; box-shadow: var(--shadow-sm); }
.hist-item.active { background: #EEF5FF; border-color: var(--navy-mid); }
.hist-risk-dot {
    width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
}
.dot-high   { background: var(--red); }
.dot-medium { background: var(--amber); }
.dot-low    { background: var(--green); }
.hist-patient { font-size: 0.82rem; font-weight: 700; color: var(--text-dark); }
.hist-meta    { font-size: 0.70rem; color: var(--text-light); margin-top: 0.1rem; }
.hist-badge   {
    margin-left: auto; font-size: 0.65rem; font-weight: 700;
    padding: 0.15rem 0.55rem; border-radius: 4px; flex-shrink: 0;
}

/* ── Red flags ───────────────────────────────────────────────────────────── */
.red-flag-item {
    display: flex; align-items: flex-start; gap: 0.75rem;
    padding: 0.75rem 0.9rem; border-radius: var(--radius-sm);
    margin-bottom: 0.5rem; border-left: 3px solid;
}
.rf-critical { background:#FFF5F5; border-color:#E53935; }
.rf-high     { background:#FFF8F0; border-color:#F57C00; }
.rf-moderate { background:#FFFDE7; border-color:#F9A825; }
.rf-severity { font-size: 0.65rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; padding: 0.15rem 0.5rem; border-radius: 4px; white-space: nowrap; flex-shrink: 0; }
.sev-critical { background:#FFCDD2; color:#B71C1C; }
.sev-high     { background:#FFE0B2; color:#BF360C; }
.sev-moderate { background:#FFF9C4; color:#F57F17; }
.rf-lab  { font-weight: 700; font-size: 0.82rem; color: var(--text-dark); margin-bottom: 0.15rem; }
.rf-reason { font-size: 0.78rem; color: var(--text-mid); line-height: 1.45; }

/* ── AI Summary ──────────────────────────────────────────────────────────── */
.ai-summary-box {
    background: linear-gradient(135deg, var(--navy) 0%, #1A4D9C 50%, #0F3460 100%);
    border-radius: var(--radius); padding: 1.5rem 1.75rem; color: #E8F4FD;
    line-height: 1.7; font-size: 0.88rem; position: relative;
    box-shadow: var(--shadow-md); margin-bottom: 1.25rem;
}
.ai-summary-box::before {
    content: "AI"; position: absolute; top: 1rem; right: 1.25rem;
    background: rgba(44,212,191,.25); color: var(--teal-light);
    font-size: 0.6rem; font-weight: 800; letter-spacing: 0.12em;
    padding: 0.2rem 0.55rem; border-radius: 4px; border: 1px solid rgba(44,212,191,.3);
}
.ai-summary-title { font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; color: var(--teal-light); margin-bottom: 0.75rem; }

/* ── Misc ────────────────────────────────────────────────────────────────── */
.dx-box {
    background: #FAFCFF; border: 1px solid #D0E4F7;
    border-left: 4px solid var(--navy-mid); border-radius: var(--radius-sm);
    padding: 1rem 1.25rem; font-size: 0.88rem; color: var(--text-mid); line-height: 1.65;
}
.rec-item { display: flex; align-items: flex-start; gap: 0.75rem; padding: 0.8rem 1rem; border-radius: var(--radius-sm); background: linear-gradient(135deg,#F0F9FF,#E8F4FD); border: 1px solid #C5E5F8; margin-bottom: 0.5rem; }
.rec-num  { background: linear-gradient(135deg, var(--navy), var(--navy-mid)); color: #fff; font-weight: 700; font-size: 0.75rem; border-radius: 50%; min-width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.rec-text { font-size: 0.84rem; color: var(--text-mid); line-height: 1.5; }
.stat-chip { background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.85rem 1.2rem; box-shadow: var(--shadow-sm); text-align: center; }
.stat-chip-icon { font-size: 1.4rem; margin-bottom: 0.25rem; }
.stat-chip-val  { font-size: 1.2rem; font-weight: 800; color: var(--navy); }
.stat-chip-lbl  { font-size: 0.68rem; font-weight: 600; color: var(--text-light); text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.1rem; }
.sb-logo-area   { text-align: center; padding: 1.5rem 0 1.25rem 0; border-bottom: 1px solid rgba(255,255,255,0.12); margin-bottom: 1.25rem; }
.sb-brand-name  { font-size: 1.3rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.02em; margin-top: 0.4rem; }
.sb-brand-name span { color: var(--teal-light); }
.sb-tagline     { font-size: 0.62rem; color: #7EC8E3; letter-spacing: 0.12em; text-transform: uppercase; margin-top: 0.2rem; }
.sb-section-title { font-size: 0.65rem; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; color: var(--teal); padding: 0.5rem 0 0.25rem 0; margin-bottom: 0.25rem; border-bottom: 1px solid rgba(255,255,255,0.08); }
.sb-divider { border: none; border-top: 1px solid rgba(255,255,255,0.10); margin: 1rem 0; }
.empty-state { text-align: center; padding: 3.5rem 2rem; color: var(--text-light); }
.empty-state-icon { font-size: 3.5rem; margin-bottom: 0.75rem; opacity: 0.4; }
.empty-state-title { font-size: 1.05rem; font-weight: 700; color: var(--text-mid); margin-bottom: 0.4rem; }
.empty-state-sub { font-size: 0.82rem; line-height: 1.6; max-width: 320px; margin: 0 auto; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #C5D5EA; border-radius: 3px; }

/* ==========================================================
   SURGIMIND AUTH SCREEN
   ========================================================== */

.auth-page {
    min-height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
    background:
        linear-gradient(
            135deg,
            #0D2B5E 0%,
            #123D73 40%,
            #1CB5A3 100%
        );
}

.auth-container {
    width: 1200px;
    height: 760px;

    display: flex;

    background: white;

    border-radius: 32px;

    overflow: hidden;

    box-shadow:
        0 30px 80px rgba(0,0,0,.25);
}

.auth-image-panel {
    width: 48%;
    position: relative;

    background-size: cover;
    background-position: center;
}

.auth-image-overlay {
    position: absolute;
    inset: 0;

    background:
        linear-gradient(
            180deg,
            rgba(13,43,94,.15),
            rgba(13,43,94,.55)
        );
}

.auth-logo-watermark {
    position: absolute;

    top: 40px;
    left: 50%;

    transform: translateX(-50%);

    width: 130px;

    opacity: .18;

    filter: brightness(1.2);
}

.auth-tagline {
    position: absolute;

    bottom: 60px;
    left: 50px;
    right: 50px;

    color: white;
}

.auth-tagline h2 {
    font-size: 2rem;
    font-weight: 800;
    line-height: 1.2;
}

.auth-tagline p {
    margin-top: 12px;
    color: rgba(255,255,255,.8);
}

.auth-form-panel {
    width: 52%;

    display: flex;
    align-items: center;
    justify-content: center;

    padding: 60px;
}

.auth-form {
    width: 100%;
    max-width: 420px;
}

.auth-heading {
    font-size: 2.4rem;
    font-weight: 800;
    color: #0D2B5E;
}

.auth-heading span {
    color: #1CB5A3;
}

.auth-sub {
    color: #7A8AA5;
    margin-bottom: 30px;
}

</style>
"""


def logo_img_tag(size=72):
    """
    Reads logo.png from the frontend folder and returns 
    an HTML img tag with the base64 encoded image.
    """
    # Looks for logo.png in the same folder as this script
    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{data}" width="{size}" style="margin-bottom:10px;">'
    
    # Fallback if image is missing
    return "🧠" 

def get_base64_image(filename):
    path = os.path.join(
        os.path.dirname(__file__),
        filename
    )

    if os.path.exists(path):
        with open(path, "rb") as img:
            return base64.b64encode(
                img.read()
            ).decode()

    return ""

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_risk_colors(level):
    level = level.upper()
    if level == "HIGH":
        return {"card":"risk-high","badge":"badge-high","big":"risk-big-high","bar":"conf-bar-high","emoji":"🔴","dot":"dot-high","hist":"badge-high"}
    elif level == "MEDIUM":
        return {"card":"risk-med","badge":"badge-medium","big":"risk-big-medium","bar":"conf-bar-medium","emoji":"🟡","dot":"dot-medium","hist":"badge-medium"}
    else:
        return {"card":"risk-low","badge":"badge-low","big":"risk-big-low","bar":"conf-bar-low","emoji":"🟢","dot":"dot-low","hist":"badge-low"}


def severity_css(severity):
    s = severity.upper()
    if "CRITICAL" in s: return "rf-critical","sev-critical"
    if "HIGH"     in s: return "rf-high","sev-high"
    return "rf-moderate","sev-moderate"


def confidence_to_float(conf_str):
    try: return float(str(conf_str).strip().replace("%",""))/100
    except: return 0.75


def call_ml_model(diagnosis, admission_type, gender, age, lab_summary):
    try:
        from services.prediction_service import predict_risk
        return predict_risk(diagnosis=diagnosis, admission_type=admission_type.lower(),
                            gender=gender.lower(), age=float(age),
                            abnormal_lab_summary=lab_summary)
    except Exception as e:
        return {"risk_level":"MEDIUM","confidence":"75.0%",
                "possible_concerns":[str(e)],"clinical_text":f"{diagnosis} {admission_type}"}


def call_rag_llm(ml_output, patient_data):
    try:
        from rag_module.llm_reasoning import generate_report
        return generate_report(ml_output, patient_data)
    except Exception as e:
        from rag_module.llm_reasoning import detect_red_flags,_rule_based_report,_extract_abnormal_labs
        labs  = _extract_abnormal_labs(ml_output, patient_data)
        flags = detect_red_flags(labs)
        return _rule_based_report(ml_output, patient_data, flags, [])


# =============================================================================
# SESSION STATE INIT
# =============================================================================
defaults = {"report":None,"ml_result":None,"checks":{},"n_preds":0,
            "view_mode":"assess","loaded_report_id":None}
for k,v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =============================================================================
# RESTORE SESSION ON REFRESH
# =============================================================================
st_restore_session()

# =============================================================================
# AUTH PAGES  (shown when not logged in)
# =============================================================================

def render_login_page():
    """Two-panel Auth Page using background.jpg and Main image.jpg."""
    
    # 1. Image Base64 Encoding Helpers
    def get_base64(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    # Paths to your specific project assets
    bg_img = get_base64("background.jpg")
    main_img = get_base64("Main image.jpg")

    # 2. Custom CSS for the Two-Panel Layout
    st.markdown(f"""
    <style>
    /* Full page background */
    [data-testid="stAppViewContainer"] {{
        background: url("data:image/jpg;base64,{bg_img}");
        background-size: cover;
        background-position: center;
    }}
    
    .auth-wrapper {{
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 90vh;
        padding: 2rem;
    }}
    
    .auth-card {{
        background: white;
        border-radius: 32px;
        box-shadow: 0 40px 100px rgba(13, 43, 94, 0.25);
        display: flex;
        overflow: hidden;
        width: 100%;
        max-width: 1100px;
        min-height: 650px;
    }}
    
    /* Left side image panel */
    .image-panel {{
        flex: 1;
        background: url("data:image/jpg;base64,{main_img}");
        background-size: cover;
        background-position: center;
        display: flex;
        flex-direction: column;
        justify-content: flex-end;
        padding: 3rem;
        color: white;
    }}
    
    /* Right side form panel */
    .form-panel {{
        flex: 1.1;
        padding: 4rem;
        background: white;
    }}
    
    .brand-title {{ font-size: 2.2rem; font-weight: 800; color: #0D2B5E; margin-bottom: 0.5rem; }}
    .brand-title span {{ color: #1CB5A3; }}
    .sub-heading {{ color: #7A8AA5; font-size: 0.95rem; margin-bottom: 2.5rem; }}
    </style>
    """, unsafe_allow_html=True)

    # 3. Structural Container
    st.markdown('<div class="auth-wrapper"><div class="auth-card">', unsafe_allow_html=True)

    # ── LEFT PANEL (Image & Tagline) ──────────────────────────────────────────
    st.markdown(f"""
    <div class="image-panel">
        <div style="background: rgba(13, 43, 94, 0.6); padding: 1.5rem; border-radius: 16px; backdrop-filter: blur(10px);">
            <h2 style="margin:0;">Clinical Precision</h2>
            <p style="margin:0.5rem 0 0; opacity: 0.9;">AI-Powered Surgical Decision Support Grounded in Clinical Guidelines.</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── RIGHT PANEL (Auth Forms) ──────────────────────────────────────────────
    st.markdown('<div class="form-panel">', unsafe_allow_html=True)
    
    # Logo and Branding
    st.markdown(f"""
        <div style="text-align:left; margin-bottom: 2rem;">
            {logo_img_tag(72)}
            <div class="brand-title">Surgi<span>Mind</span></div>
        </div>
    """, unsafe_allow_html=True)

    if st.session_state["auth_page"] == "login":
        st.markdown('<div class="sub-heading">Welcome back, Doctor. Please sign in.</div>', unsafe_allow_html=True)
        user_in = st.text_input("Username", placeholder="dr.smith", key="li_user")
        pass_in = st.text_input("Password", type="password", placeholder="••••••••", key="li_pass")
        
        if st.button("Sign In →", use_container_width=True, type="primary"):
            result = st_login(user_in, pass_in) # logic from database_manager [1]
            if result["ok"]:
                st.rerun()
            else:
                st.error(f"❌ {result.get('error', 'Login failed')}")
        
        st.markdown('<p style="margin-top:2rem; color:#7A8AA5;">New to the platform?</p>', unsafe_allow_html=True)
        if st.button("Create Staff Account", key="go_to_reg"):
            st.session_state["auth_page"] = "signup"
            st.rerun()

    else:
        st.markdown('<div class="sub-heading">Register to access surgical intelligence.</div>', unsafe_allow_html=True)
        name_in = st.text_input("Full Name", placeholder="Dr. Sarah Smith")
        user_in = st.text_input("Username", placeholder="dr.sarah")
        spec_in = st.selectbox("Speciality", ["General Surgery", "Cardiology", "Neurology", "Orthopaedics"])
        hosp_in = st.text_input("Hospital", placeholder="City General")
        pass_in = st.text_input("Set Password", type="password")

        if st.button("Complete Registration", use_container_width=True, type="primary"):
            if len(pass_in) < 6:
                st.warning("⚠️ Password too short.")
            else:
                result = st_signup(user_in, name_in, pass_in, spec_in, hosp_in) # logic from database_manager [1]
                if result["ok"]:
                    st.rerun()
                else:
                    st.error(f"❌ {result.get('error')}")

        if st.button("Back to Sign In", key="back_to_li"):
            st.session_state["auth_page"] = "login"
            st.rerun()

    # Close panels
    st.markdown("</div></div></div>", unsafe_allow_html=True)


# =============================================================================
# HISTORY PANEL (sidebar section when logged in)
# =============================================================================

def render_history_sidebar(user_id):
    """Shows recent assessments in the sidebar with click-to-load."""
    st.markdown('<div class="sb-section-title">📋 Recent Assessments</div>', unsafe_allow_html=True)

    hist = db.get_history(user_id, limit=15)
    if not hist["ok"] or not hist["records"]:
        st.markdown('<div style="font-size:0.75rem;color:rgba(255,255,255,0.4);padding:0.5rem 0;">No assessments yet.</div>', unsafe_allow_html=True)
        return

    risk_emoji = {"HIGH":"🔴","MEDIUM":"🟡","LOW":"🟢"}
    for rec in hist["records"]:
        risk   = rec.get("risk_level","?")
        pname  = rec.get("patient_name","Unknown")[:22]
        diag   = str(rec.get("diagnosis",""))[:28]
        date   = rec.get("formatted_date","")
        rid    = rec.get("id")

        is_active = st.session_state.get("loaded_report_id") == rid
        btn_label = f"{risk_emoji.get(risk,'⚪')} {pname} | {risk}"

        if st.button(btn_label, key=f"hist_{rid}", use_container_width=True):
            # Load this report back into the dashboard
            r = db.get_report_by_id(rid, user_id)
            if r["ok"]:
                report = r["full_report"]
                report["risk_level"]  = r["report"].get("risk_level", report.get("risk_level","MEDIUM"))
                report["confidence"]  = r["report"].get("confidence", report.get("confidence","N/A"))
                report["patient_name"]= r["report"].get("patient_name","Patient")
                st.session_state["report"]           = report
                st.session_state["ml_result"]        = r["ml_result"]
                st.session_state["loaded_report_id"] = rid
                st.session_state["last_report_id"]   = rid
                st.session_state["checks"]           = {
                    i: False for i in range(len(report.get("preop_checklist",[])))
                }
                st.rerun()

        st.markdown(
            f'<div style="font-size:0.67rem;color:rgba(255,255,255,0.4);'
            f'margin:-0.4rem 0 0.25rem 0.2rem;">{diag or "—"} · {date}</div>',
            unsafe_allow_html=True
        )


# =============================================================================
# MAIN RENDER DECISION
# =============================================================================

if not st.session_state.get("user"):
    render_login_page()
    st.stop()   # ← nothing below runs until logged in

# =============================================================================
# AUTHENTICATED LAYOUT
# =============================================================================
user    = st.session_state["user"]
user_id = st.session_state["user_id"]


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div class="sb-logo-area">
        {logo_img_tag(64)}
        <div class="sb-brand-name">Surgi<span>Mind</span></div>
        <div class="sb-tagline">AI Surgical Decision Support</div>
    </div>
    <div style="text-align:center;padding:0.5rem 0 0.75rem;border-bottom:1px solid rgba(255,255,255,0.10);margin-bottom:1rem;">
        <div style="font-size:0.75rem;font-weight:700;color:#FFFFFF;">{user.get('full_name','Doctor')}</div>
        <div style="font-size:0.65rem;color:#7EC8E3;">{user.get('speciality','Surgery')} · {user.get('hospital','') or 'SurgiMind'}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-section-title">👤 Patient Demographics</div>', unsafe_allow_html=True)
    patient_name = st.text_input("Patient Name", placeholder="e.g. John Smith")
    col_a, col_b = st.columns(2)
    with col_a: age    = st.number_input("Age", min_value=0, max_value=120, value=55, step=1)
    with col_b: gender = st.selectbox("Gender", ["Male","Female","Other"])

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="sb-section-title">🏥 Clinical Details</div>', unsafe_allow_html=True)
    diagnosis      = st.text_area("Diagnosis", placeholder="e.g. sepsis with acute renal dysfunction", height=80)
    admission_type = st.selectbox("Admission Type", ["Emergency","Urgent","Elective"])
    surgery_type   = st.text_input("Surgery Type",  placeholder="e.g. exploratory laparotomy")
    symptoms       = st.text_area("Symptoms",        placeholder="e.g. fever, hypotension, altered mental status", height=65)

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="sb-section-title">💓 Vitals</div>', unsafe_allow_html=True)
    cv1,cv2 = st.columns(2)
    with cv1: bp = st.text_input("Blood Pressure", placeholder="120/80")
    with cv2: hr = st.number_input("Heart Rate", min_value=0, max_value=300, value=0, step=1)

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="sb-section-title">🧪 Lab Values</div>', unsafe_allow_html=True)
    cl1,cl2 = st.columns(2)
    with cl1:
        glucose    = st.number_input("Glucose",    min_value=0.0, value=0.0, step=0.1,  format="%.1f")
        creatinine = st.number_input("Creatinine", min_value=0.0, value=0.0, step=0.1,  format="%.2f")
        wbc        = st.number_input("WBC",        min_value=0.0, value=0.0, step=0.1,  format="%.1f")
        lactate    = st.number_input("Lactate",    min_value=0.0, value=0.0, step=0.1,  format="%.2f")
    with cl2:
        sodium     = st.number_input("Sodium",     min_value=0.0, value=0.0, step=0.1,  format="%.1f")
        potassium  = st.number_input("Potassium",  min_value=0.0, value=0.0, step=0.1,  format="%.2f")
        troponin   = st.number_input("Troponin",   min_value=0.0, value=0.0, step=0.001,format="%.3f")
    lab_summary = st.text_input("Abnormal Lab Summary", placeholder="e.g. lactate creatinine troponin")

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    run_btn = st.button("⚡ Run AI Assessment")

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    render_history_sidebar(user_id)

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    if st.button("🚪 Sign Out", key="logout_btn"):
        st_logout()
        st.rerun()

# ── Top nav ───────────────────────────────────────────────────────────────────
stats_r = db.get_stats(user_id)
stats   = stats_r.get("stats", {})
st.markdown(f"""
<div class="sm-topbar">
    <div class="sm-topbar-brand">
        {logo_img_tag(38)}
        <div>
            <div class="sm-topbar-title">Surgi<span>Mind</span></div>
            <div class="sm-topbar-sub">Clinical Decision Support · AI-Powered</div>
        </div>
    </div>
    <div class="sm-topbar-right">
        <span class="sm-topbar-user">
            👨‍⚕️ {user.get('full_name','Doctor')} &nbsp;·&nbsp;
            {stats.get('total_reports',0)} assessments saved
        </span>
        <span class="sm-topbar-badge">HIPAA Ready · v1.0</span>
    </div>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# PROCESSING
# =============================================================================
if run_btn:
    if not diagnosis.strip():
        st.error("⚠️ Please enter a diagnosis before running the assessment.")
    else:
        patient_data = {
            "patient_name":patient_name or "Unknown","age":age,"gender":gender,
            "admission_type":admission_type,"diagnosis":diagnosis,"symptoms":symptoms,
            "surgery_type":surgery_type,"blood_pressure":bp,
            "heart_rate":hr if hr else None,"glucose":glucose if glucose else None,
            "creatinine":creatinine if creatinine else None,"wbc":wbc if wbc else None,
            "lactate":lactate if lactate else None,"sodium":sodium if sodium else None,
            "potassium":potassium if potassium else None,"troponin":troponin if troponin else None,
        }
        with st.spinner("🔬 Running ML risk prediction…"):
            ml = call_ml_model(diagnosis, admission_type, gender, age, lab_summary)
            st.session_state["ml_result"] = ml
        with st.spinner("📚 Retrieving clinical guidelines…"):
            time.sleep(0.3)
        with st.spinner("🧠 Generating AI clinical reasoning…"):
            report = call_rag_llm(ml, patient_data)
            report["risk_level"]   = ml.get("risk_level",  report.get("risk_level","MEDIUM"))
            report["confidence"]   = ml.get("confidence",  report.get("confidence","N/A"))
            report["patient_name"] = patient_name or "Patient"
            st.session_state["report"] = report
            st.session_state["n_preds"] = st.session_state.get("n_preds",0) + 1
            st.session_state["checks"] = {i:False for i in range(len(report.get("preop_checklist",[])))}
            st.session_state["loaded_report_id"] = None  # new report, not from history

        # ── SAVE TO DATABASE ──────────────────────────────────────────────────
        with st.spinner("💾 Saving to database…"):
            rid = st_save_report_after_assessment(patient_data, ml, report)

        if rid:
            st.success(f"✅ Assessment complete and saved (Report #{rid})")
        else:
            st.warning("✅ Assessment complete (could not save to database – check logs)")

# =============================================================================
# DASHBOARD RENDER
# =============================================================================
report    = st.session_state.get("report")
ml_result = st.session_state.get("ml_result")

if report is None:
    # ── Stats chips from DB ───────────────────────────────────────────────────
    chip_data = [
        ("📊", stats.get("total_reports",0), "Total Reports"),
        ("🔴", stats.get("high_count",0),    "HIGH Risk"),
        ("🟡", stats.get("medium_count",0),  "MEDIUM Risk"),
        ("🟢", stats.get("low_count",0),      "LOW Risk"),
    ]
    cols = st.columns(4)
    for col,(icon,val,lbl) in zip(cols,chip_data):
        with col:
            st.markdown(f"""
            <div class="stat-chip">
                <div class="stat-chip-icon">{icon}</div>
                <div class="stat-chip-val">{val}</div>
                <div class="stat-chip-lbl">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="sm-card">
        <div class="empty-state">
            <div class="empty-state-icon">{logo_img_tag(80)}</div>
            <div class="empty-state-title">Ready for Assessment</div>
            <div class="empty-state-sub">
                Fill in patient details and click <strong>Run AI Assessment</strong>,
                or click a past assessment in the sidebar to reload it.
                Every report is saved automatically.
            </div>
        </div>
    </div>""", unsafe_allow_html=True)
else:
    # ── Full report rendering ─────────────────────────────────────────────────
    risk     = report.get("risk_level","MEDIUM").upper()
    conf_str = report.get("confidence","N/A")
    conf_flt = confidence_to_float(conf_str)
    colors   = get_risk_colors(risk)
    pname    = report.get("patient_name","Patient")
    loaded_id= st.session_state.get("loaded_report_id")

    if loaded_id:
        st.info(f"📂 Viewing saved report #{loaded_id} — use the form to run a new assessment")

    col_gauge, col_stats = st.columns([1,2], gap="medium")
    with col_gauge:
        st.markdown(f"""
        <div class="risk-gauge-card {colors['card']}">
            <div class="sm-card-title">🎯 Surgical Risk Level</div>
            <div class="risk-level-badge {colors['badge']}">{colors['emoji']} &nbsp; {risk}</div>
            <div class="risk-big-number {colors['big']}">{risk[0]}</div>
            <div style="font-size:0.78rem;color:var(--text-light);margin-bottom:0.75rem;">
                {risk.capitalize()} Risk Classification
            </div>
            <div class="confidence-row">
                <span class="conf-label">Confidence</span>
                <div class="conf-bar-wrap">
                    <div class="conf-bar-fill {colors['bar']}" style="width:{conf_flt*100:.0f}%"></div>
                </div>
                <span class="conf-pct">{conf_str}</span>
            </div>
            <div style="margin-top:1rem;font-size:0.72rem;color:var(--text-light);">
                Patient: <strong style="color:var(--text-dark)">{pname}</strong>
                &nbsp;·&nbsp; Backend: <em>{report.get('llm_backend_used','N/A')}</em>
            </div>
        </div>""", unsafe_allow_html=True)

    with col_stats:
        concerns = (ml_result or {}).get("possible_concerns",[])
        chips = [
            ("⚠️", len(report.get("red_flags",[])),"Red Flags"),
            ("📋", len(report.get("preop_checklist",[])),"Pre-op Tasks"),
            ("💊", len(report.get("surgical_options",[])),"Recommendations"),
            ("💾", st.session_state.get("n_preds",0),"Saved This Session"),
        ]
        chip_cols = st.columns(4)
        for col,(icon,val,lbl) in zip(chip_cols,chips):
            with col:
                st.markdown(f"""
                <div class="stat-chip">
                    <div class="stat-chip-icon">{icon}</div>
                    <div class="stat-chip-val">{val}</div>
                    <div class="stat-chip-lbl">{lbl}</div>
                </div>""", unsafe_allow_html=True)
        if concerns:
            tags = " ".join(
                f'<span style="background:#EEF4FF;color:var(--navy-mid);border:1px solid #C5D8F7;'
                f'border-radius:50px;padding:0.2rem 0.75rem;font-size:0.72rem;font-weight:600;'
                f'display:inline-block;margin:0.2rem 0.15rem;">{c}</span>'
                for c in concerns[:6]
            )
            st.markdown(f"""
            <div class="sm-card" style="margin-top:0.5rem">
                <div class="sm-card-title">🏷️ AI-Detected Concerns</div>{tags}
            </div>""", unsafe_allow_html=True)

    summary = report.get("ai_summary","")
    if summary:
        st.markdown(f"""
        <div class="ai-summary-box">
            <div class="ai-summary-title">🤖 AI Clinical Summary</div>{summary}
        </div>""", unsafe_allow_html=True)

    col_left, col_right = st.columns([3,2], gap="medium")
    with col_left:
        dx = report.get("probable_diagnosis","")
        if dx:
            st.markdown(f"""
            <div class="sm-card">
                <div class="sm-card-title">🩺 Probable Diagnosis</div>
                <div class="dx-box">{dx}</div>
                <div style="font-size:0.70rem;color:var(--text-light);margin-top:0.5rem;">
                    ⚠️ AI-generated impression only — not a confirmed diagnosis.
                </div>
            </div>""", unsafe_allow_html=True)

        options = report.get("surgical_options",[])
        if options:
            recs = "".join(f'<div class="rec-item"><div class="rec-num">{i}</div><div class="rec-text">{o}</div></div>'
                           for i,o in enumerate(options,1))
            st.markdown(f'<div class="sm-card"><div class="sm-card-title">🔪 Surgical Recommendations</div>{recs}</div>', unsafe_allow_html=True)

        contra = report.get("contraindications",[])
        if contra:
            items = "".join(
                f'<div style="display:flex;gap:0.6rem;align-items:flex-start;margin-bottom:0.5rem;font-size:0.83rem;color:var(--text-mid);">'
                f'<span style="color:#E53935;font-size:1rem;flex-shrink:0;">✗</span> {c}</div>' for c in contra)
            st.markdown(f'<div class="sm-card" style="border-left:3px solid #E53935"><div class="sm-card-title" style="color:#C62828">🚫 Contraindications</div>{items}</div>', unsafe_allow_html=True)

        guidelines = report.get("retrieved_guidelines",[])
        if guidelines:
            gl = ""
            for g in guidelines[:3]:
                src,title,excerpt = g.get("source",""),g.get("title",""),str(g.get("excerpt",g.get("text","")))[:280]
                gl += f'<div style="border:1px solid var(--border);border-radius:var(--radius-sm);padding:0.75rem 1rem;margin-bottom:0.6rem;background:#FAFCFF;"><div style="font-size:0.72rem;font-weight:700;color:var(--navy);margin-bottom:0.3rem;">📄 {title or src}</div><div style="font-size:0.78rem;color:var(--text-mid);line-height:1.5;">{excerpt}…</div></div>'
            st.markdown(f'<div class="sm-card"><div class="sm-card-title">📚 Retrieved Clinical Guidelines</div>{gl}</div>', unsafe_allow_html=True)

    with col_right:
        red_flags = report.get("red_flags",[])
        if red_flags:
            fhtml = ""
            for rf in red_flags:
                lab,reason,severity = rf.get("lab","Unknown"),rf.get("reason",""),rf.get("severity","MODERATE")
                ic,bc = severity_css(severity)
                fhtml += f'<div class="red-flag-item {ic}"><div><span class="rf-severity {bc}">{severity}</span></div><div><div class="rf-lab">⚗️ {lab}</div><div class="rf-reason">{str(reason)[:180]}{"…" if len(str(reason))>180 else ""}</div></div></div>'
            st.markdown(f'<div class="sm-card" style="border-top:3px solid #E53935"><div class="sm-card-title" style="color:#B71C1C">🚨 Red Flag Alerts</div>{fhtml}</div>', unsafe_allow_html=True)

        checklist = report.get("preop_checklist",[])
        if checklist:
            for i in range(len(checklist)):
                if i not in st.session_state["checks"]:
                    st.session_state["checks"][i] = False
            done  = sum(st.session_state["checks"].values())
            total = len(checklist)
            pct   = int(done/total*100) if total else 0
            st.markdown(f"""
            <div class="sm-card">
                <div class="sm-card-title">✅ Pre-operative Checklist</div>
                <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:1rem;">
                    <div style="flex:1;height:6px;background:var(--border);border-radius:50px;overflow:hidden;">
                        <div style="width:{pct}%;height:100%;border-radius:50px;
                                    background:linear-gradient(90deg,var(--teal),var(--cyan));"></div>
                    </div>
                    <span style="font-size:0.78rem;font-weight:700;color:var(--teal-dark);">{done}/{total}</span>
                </div>
            """, unsafe_allow_html=True)
            for i,item in enumerate(checklist):
                checked = st.session_state["checks"].get(i,False)
                new_val = st.checkbox(item, value=checked, key=f"chk_{i}_{abs(hash(item))%99999}")
                st.session_state["checks"][i] = new_val
            st.markdown("</div>", unsafe_allow_html=True)

    # ── Export bar ────────────────────────────────────────────────────────────
    st.markdown("---")
    ec1,ec2,ec3,_ = st.columns([1.2,1.2,1.2,2])
    with ec1:
        json_data = st_export_report_json() or json.dumps(report, indent=2, default=str)
        st.download_button(
            label     = "⬇️ Export JSON (DB)",
            data      = json_data,
            file_name = f"surgimind_{pname.replace(' ','_')}.json",
            mime      = "application/json",
            help      = "Downloads the report directly from the database",
        )
    with ec2:
        csv_data = db.export_all_history_csv(user_id)
        st.download_button(
            label     = "📊 Export All History CSV",
            data      = csv_data,
            file_name = f"surgimind_history_{user.get('username','user')}.csv",
            mime      = "text/csv",
        )
    with ec3:
        if st.button("🔄 New Assessment"):
            st.session_state["report"]    = None
            st.session_state["ml_result"] = None
            st.session_state["checks"]    = {}
            st.session_state["loaded_report_id"] = None
            st.rerun()

# =============================================================================
# FOOTER
# =============================================================================
st.markdown(f"""
<div style="text-align:center;padding:2rem 0 1rem;font-size:0.70rem;color:var(--text-light);
            border-top:1px solid var(--border);margin-top:1rem;">
    {logo_img_tag(24)} &nbsp;&nbsp;
    <strong style="color:var(--navy)">SurgiMind</strong> &nbsp;·&nbsp;
    AI-Powered Surgical Decision Support &nbsp;·&nbsp;
    For clinical decision support only — not a substitute for professional medical judgement
</div>
""", unsafe_allow_html=True)