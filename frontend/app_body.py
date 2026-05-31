# =============================================================================
# app_body.py  -  SurgiMind CSS + Dashboard Logic
# This file is concatenated with app_start.py by build_app.py
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
    color: #FFFFFF !important;
    font-size: 0.88rem !important;
}
[data-testid="stSidebar"] .stTextInput input:focus,
[data-testid="stSidebar"] .stTextArea textarea:focus {
    border-color: var(--teal-light) !important;
    box-shadow: 0 0 0 3px rgba(44,212,191,.20) !important;
}
[data-testid="stSidebar"] label {
    color: #B8D0F0 !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    text-transform: uppercase !important;
}
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.20) !important;
    border-radius: var(--radius-sm) !important;
}

.stButton > button {
    background: linear-gradient(135deg, var(--teal) 0%, var(--cyan) 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 50px !important;
    font-weight: 700 !important;
    font-size: 0.95rem !important;
    letter-spacing: 0.03em !important;
    padding: 0.65rem 1.8rem !important;
    width: 100% !important;
    transition: all 0.25s ease !important;
    box-shadow: 0 4px 16px rgba(28,181,163,.40) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 28px rgba(28,181,163,.55) !important;
}

.sm-card {
    background: var(--card-bg);
    border-radius: var(--radius);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-sm);
    padding: 1.5rem 1.75rem;
    margin-bottom: 1.25rem;
    transition: box-shadow 0.2s ease;
}
.sm-card:hover { box-shadow: var(--shadow-md); }
.sm-card-title {
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-light);
    margin: 0 0 0.75rem 0;
}

.sm-topbar {
    background: linear-gradient(90deg, var(--navy) 0%, var(--navy-mid) 100%);
    border-radius: 0 0 var(--radius) var(--radius);
    padding: 0.9rem 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 0 -2rem 1.75rem -2rem;
    box-shadow: var(--shadow-md);
}
.sm-topbar-brand { display: flex; align-items: center; gap: 0.75rem; }
.sm-topbar-title { font-size: 1.35rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.02em; }
.sm-topbar-title span { color: var(--teal-light); }
.sm-topbar-sub { font-size: 0.72rem; color: #7EC8E3; letter-spacing: 0.12em; text-transform: uppercase; }
.sm-topbar-badge {
    background: rgba(44,212,191,.18);
    border: 1px solid rgba(44,212,191,.35);
    color: var(--teal-light);
    border-radius: 50px;
    padding: 0.3rem 1rem;
    font-size: 0.72rem;
    font-weight: 600;
}

.risk-gauge-card {
    background: var(--card-bg);
    border-radius: var(--radius);
    border: 1px solid var(--border);
    box-shadow: var(--shadow-md);
    padding: 1.75rem 2rem;
    margin-bottom: 1.25rem;
    text-align: center;
    position: relative;
    overflow: hidden;
}
.risk-gauge-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    border-radius: var(--radius) var(--radius) 0 0;
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

.risk-big-number {
    font-size: 4rem; font-weight: 800; line-height: 1;
    letter-spacing: -0.04em; margin: 0.4rem 0;
}
.risk-big-high   { color: var(--red); }
.risk-big-medium { color: var(--amber); }
.risk-big-low    { color: var(--green); }

.confidence-row {
    display: flex; align-items: center; justify-content: center;
    gap: 0.6rem; margin-top: 0.75rem;
}
.conf-label { font-size: 0.75rem; font-weight: 600; color: var(--text-light); text-transform: uppercase; }
.conf-bar-wrap { flex: 1; max-width: 160px; height: 8px; background: var(--border); border-radius: 50px; overflow: hidden; }
.conf-bar-fill { height: 100%; border-radius: 50px; }
.conf-bar-high   { background: linear-gradient(90deg,#E53935,#FF5252); }
.conf-bar-medium { background: linear-gradient(90deg,#F57C00,#FFB300); }
.conf-bar-low    { background: linear-gradient(90deg,#2E7D32,#43A047); }
.conf-pct { font-size: 0.9rem; font-weight: 700; color: var(--text-dark); }

.red-flag-item {
    display: flex; align-items: flex-start; gap: 0.75rem;
    padding: 0.75rem 0.9rem; border-radius: var(--radius-sm);
    margin-bottom: 0.5rem; border-left: 3px solid;
}
.rf-critical { background:#FFF5F5; border-color:#E53935; }
.rf-high     { background:#FFF8F0; border-color:#F57C00; }
.rf-moderate { background:#FFFDE7; border-color:#F9A825; }
.rf-severity {
    font-size: 0.65rem; font-weight: 800; letter-spacing: 0.08em;
    text-transform: uppercase; padding: 0.15rem 0.5rem;
    border-radius: 4px; white-space: nowrap; flex-shrink: 0;
}
.sev-critical { background:#FFCDD2; color:#B71C1C; }
.sev-high     { background:#FFE0B2; color:#BF360C; }
.sev-moderate { background:#FFF9C4; color:#F57F17; }
.rf-lab  { font-weight: 700; font-size: 0.82rem; color: var(--text-dark); margin-bottom: 0.15rem; }
.rf-reason { font-size: 0.78rem; color: var(--text-mid); line-height: 1.45; }

.ai-summary-box {
    background: linear-gradient(135deg, var(--navy) 0%, #1A4D9C 50%, #0F3460 100%);
    border-radius: var(--radius);
    padding: 1.5rem 1.75rem;
    color: #E8F4FD;
    line-height: 1.7;
    font-size: 0.88rem;
    position: relative;
    box-shadow: var(--shadow-md);
    margin-bottom: 1.25rem;
}
.ai-summary-box::before {
    content: "AI";
    position: absolute; top: 1rem; right: 1.25rem;
    background: rgba(44,212,191,.25);
    color: var(--teal-light);
    font-size: 0.6rem; font-weight: 800; letter-spacing: 0.12em;
    padding: 0.2rem 0.55rem; border-radius: 4px;
    border: 1px solid rgba(44,212,191,.3);
}
.ai-summary-title {
    font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--teal-light); margin-bottom: 0.75rem;
}

.dx-box {
    background: #FAFCFF;
    border: 1px solid #D0E4F7;
    border-left: 4px solid var(--navy-mid);
    border-radius: var(--radius-sm);
    padding: 1rem 1.25rem;
    font-size: 0.88rem;
    color: var(--text-mid);
    line-height: 1.65;
    margin-bottom: 0.75rem;
}

.stat-chip {
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.85rem 1.2rem;
    box-shadow: var(--shadow-sm);
    text-align: center;
}
.stat-chip-icon { font-size: 1.4rem; margin-bottom: 0.25rem; }
.stat-chip-val  { font-size: 1.2rem; font-weight: 800; color: var(--navy); }
.stat-chip-lbl  { font-size: 0.68rem; font-weight: 600; color: var(--text-light);
                  text-transform: uppercase; letter-spacing: 0.06em; margin-top: 0.1rem; }

.sb-logo-area {
    text-align: center; padding: 1.5rem 0 1.25rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.12);
    margin-bottom: 1.25rem;
}
.sb-brand-name { font-size: 1.3rem; font-weight: 800; color: #FFFFFF; letter-spacing: -0.02em; margin-top: 0.4rem; }
.sb-brand-name span { color: var(--teal-light); }
.sb-tagline { font-size: 0.62rem; color: #7EC8E3; letter-spacing: 0.12em; text-transform: uppercase; margin-top: 0.2rem; }
.sb-section-title {
    font-size: 0.65rem; font-weight: 800; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--teal);
    padding: 0.5rem 0 0.25rem 0; margin-bottom: 0.25rem;
    border-bottom: 1px solid rgba(255,255,255,0.08);
}
.sb-divider { border: none; border-top: 1px solid rgba(255,255,255,0.10); margin: 1rem 0; }

.rec-item {
    display: flex; align-items: flex-start; gap: 0.75rem;
    padding: 0.8rem 1rem; border-radius: var(--radius-sm);
    background: linear-gradient(135deg,#F0F9FF,#E8F4FD);
    border: 1px solid #C5E5F8; margin-bottom: 0.5rem;
}
.rec-num {
    background: linear-gradient(135deg, var(--navy), var(--navy-mid));
    color: #fff; font-weight: 700; font-size: 0.75rem;
    border-radius: 50%; min-width: 24px; height: 24px;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.rec-text { font-size: 0.84rem; color: var(--text-mid); line-height: 1.5; }

.empty-state { text-align: center; padding: 3.5rem 2rem; color: var(--text-light); }
.empty-state-icon { font-size: 3.5rem; margin-bottom: 0.75rem; opacity: 0.4; }
.empty-state-title { font-size: 1.05rem; font-weight: 700; color: var(--text-mid); margin-bottom: 0.4rem; }
.empty-state-sub { font-size: 0.82rem; line-height: 1.6; max-width: 320px; margin: 0 auto; }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #C5D5EA; border-radius: 3px; }
</style>
"""

import streamlit as st
import base64
import os
import time

def logo_img_tag(size=72):
    """
    Reads the logo.png file from the frontend folder and returns 
    an HTML img tag with the base64 encoded image.
    """
    # This assumes logo.png is in the same folder as app.py
    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        return f'<img src="data:image/png;base64,{data}" width="{size}" style="margin-bottom:10px;">'
    
    # Fallback icon if logo image is missing
    return "🧠" 


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_risk_colors(level):
    level = level.upper()
    if level == "HIGH":
        return {"card": "risk-high",  "badge": "badge-high",   "big": "risk-big-high",   "bar": "conf-bar-high",   "emoji": "🔴"}
    elif level == "MEDIUM":
        return {"card": "risk-med",   "badge": "badge-medium",  "big": "risk-big-medium", "bar": "conf-bar-medium", "emoji": "🟡"}
    else:
        return {"card": "risk-low",   "badge": "badge-low",     "big": "risk-big-low",    "bar": "conf-bar-low",    "emoji": "🟢"}


def severity_css(severity):
    s = severity.upper()
    if "CRITICAL" in s: return "rf-critical", "sev-critical"
    if "HIGH"     in s: return "rf-high",     "sev-high"
    return "rf-moderate", "sev-moderate"


def confidence_to_float(conf_str):
    try:
        return float(str(conf_str).strip().replace("%", "")) / 100
    except Exception:
        return 0.75


def call_ml_model(diagnosis, admission_type, gender, age, lab_summary):
    try:
        from services.prediction_service import predict_risk
        return predict_risk(
            diagnosis            = diagnosis,
            admission_type       = admission_type.lower(),
            gender               = gender.lower(),
            age                  = float(age),
            abnormal_lab_summary = lab_summary,
        )
    except Exception as e:
        return {
            "risk_level": "MEDIUM", "confidence": "75.0%",
            "possible_concerns": [str(e)],
            "clinical_text": f"{diagnosis} {admission_type}",
        }


def call_rag_llm(ml_output, patient_data):
    try:
        from rag_module.llm_reasoning import generate_report
        return generate_report(ml_output, patient_data)
    except Exception as e:
        from rag_module.llm_reasoning import detect_red_flags, _rule_based_report, _extract_abnormal_labs
        labs  = _extract_abnormal_labs(ml_output, patient_data)
        flags = detect_red_flags(labs)
        return _rule_based_report(ml_output, patient_data, flags, [])


# =============================================================================
# SESSION STATE
# =============================================================================
if "report"    not in st.session_state: st.session_state.report    = None
if "ml_result" not in st.session_state: st.session_state.ml_result = None
if "checks"    not in st.session_state: st.session_state.checks    = {}
if "n_preds"   not in st.session_state: st.session_state.n_preds   = 0

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.markdown(f"""
    <div class="sb-logo-area">
        {logo_img_tag(72)}
        <div class="sb-brand-name">Surgi<span>Mind</span></div>
        <div class="sb-tagline">AI-Powered Surgical Decision Support</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sb-section-title">👤 Patient Demographics</div>', unsafe_allow_html=True)
    patient_name = st.text_input("Patient Name", placeholder="e.g. John Smith")
    col_a, col_b = st.columns(2)
    with col_a: age    = st.number_input("Age", min_value=0, max_value=120, value=55, step=1)
    with col_b: gender = st.selectbox("Gender", ["Male", "Female", "Other"])

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="sb-section-title">🏥 Clinical Details</div>', unsafe_allow_html=True)
    diagnosis      = st.text_area("Diagnosis", placeholder="e.g. sepsis with acute renal dysfunction", height=90)
    admission_type = st.selectbox("Admission Type", ["Emergency", "Urgent", "Elective"])
    surgery_type   = st.text_input("Surgery Type", placeholder="e.g. exploratory laparotomy")
    symptoms       = st.text_area("Symptoms", placeholder="e.g. fever, hypotension, altered mental status", height=75)

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="sb-section-title">💓 Vitals</div>', unsafe_allow_html=True)
    col_v1, col_v2 = st.columns(2)
    with col_v1: bp = st.text_input("Blood Pressure", placeholder="120/80")
    with col_v2: hr = st.number_input("Heart Rate", min_value=0, max_value=300, value=0, step=1)

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    st.markdown('<div class="sb-section-title">🧪 Lab Values</div>', unsafe_allow_html=True)
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        glucose    = st.number_input("Glucose",    min_value=0.0, value=0.0, step=0.1, format="%.1f")
        creatinine = st.number_input("Creatinine", min_value=0.0, value=0.0, step=0.1, format="%.2f")
        wbc        = st.number_input("WBC",        min_value=0.0, value=0.0, step=0.1, format="%.1f")
        lactate    = st.number_input("Lactate",    min_value=0.0, value=0.0, step=0.1, format="%.2f")
    with col_l2:
        sodium     = st.number_input("Sodium",     min_value=0.0, value=0.0, step=0.1, format="%.1f")
        potassium  = st.number_input("Potassium",  min_value=0.0, value=0.0, step=0.1, format="%.2f")
        troponin   = st.number_input("Troponin",   min_value=0.0, value=0.0, step=0.001, format="%.3f")

    lab_summary = st.text_input("Abnormal Lab Summary", placeholder="e.g. lactate creatinine troponin",
                                help="Space-separated abnormal lab names")

    st.markdown('<hr class="sb-divider">', unsafe_allow_html=True)
    run_btn = st.button("⚡ Run AI Assessment")

# =============================================================================
# TOP NAV
# =============================================================================
st.markdown(f"""
<div class="sm-topbar">
    <div class="sm-topbar-brand">
        {logo_img_tag(38)}
        <div>
            <div class="sm-topbar-title">Surgi<span>Mind</span></div>
            <div class="sm-topbar-sub">Clinical Decision Support · AI-Powered</div>
        </div>
    </div>
    <div class="sm-topbar-badge">HIPAA Ready &nbsp;·&nbsp; v1.0</div>
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
            "patient_name": patient_name or "Unknown",
            "age": age, "gender": gender,
            "admission_type": admission_type, "diagnosis": diagnosis,
            "symptoms": symptoms, "surgery_type": surgery_type,
            "blood_pressure": bp, "heart_rate": hr if hr else None,
            "glucose": glucose if glucose else None, "creatinine": creatinine if creatinine else None,
            "wbc": wbc if wbc else None, "lactate": lactate if lactate else None,
            "sodium": sodium if sodium else None, "potassium": potassium if potassium else None,
            "troponin": troponin if troponin else None,
        }
        with st.spinner("🔬 Running ML risk prediction…"):
            ml = call_ml_model(diagnosis, admission_type, gender, age, lab_summary)
            st.session_state.ml_result = ml
        with st.spinner("📚 Retrieving clinical guidelines…"):
            time.sleep(0.3)
        with st.spinner("🧠 Generating AI clinical reasoning…"):
            report = call_rag_llm(ml, patient_data)
            report["risk_level"]   = ml.get("risk_level",  report.get("risk_level", "MEDIUM"))
            report["confidence"]   = ml.get("confidence",  report.get("confidence", "N/A"))
            report["patient_name"] = patient_name or "Patient"
            st.session_state.report = report
            st.session_state.n_preds += 1
            st.session_state.checks = {i: False for i in range(len(report.get("preop_checklist", [])))}
        st.success("✅ Assessment complete.")

# =============================================================================
# DASHBOARD
# =============================================================================
report    = st.session_state.report
ml_result = st.session_state.ml_result

if report is None:
    st.markdown(f"""
    <div class="sm-card">
        <div class="empty-state">
            <div class="empty-state-icon">{logo_img_tag(90)}</div>
            <div class="empty-state-title">No Assessment Generated Yet</div>
            <div class="empty-state-sub">
                Fill in patient details in the sidebar and click
                <strong>Run AI Assessment</strong> to generate a complete surgical risk report.
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    cols = st.columns(4)
    for col, (icon, title, sub) in zip(cols, [
        ("🧠","ML Risk Model","RandomForest + TF-IDF"),
        ("📚","RAG Retrieval","Clinical Guidelines"),
        ("💬","LLM Reasoning","Llama3 / Groq"),
        ("✅","Pre-op Checklist","Interactive"),
    ]):
        with col:
            st.markdown(f"""
            <div class="stat-chip">
                <div class="stat-chip-icon">{icon}</div>
                <div class="stat-chip-val" style="font-size:0.88rem">{title}</div>
                <div class="stat-chip-lbl">{sub}</div>
            </div>""", unsafe_allow_html=True)
else:
    risk     = report.get("risk_level", "MEDIUM").upper()
    conf_str = report.get("confidence", "N/A")
    conf_flt = confidence_to_float(conf_str)
    colors   = get_risk_colors(risk)
    pname    = report.get("patient_name", "Patient")

    # ── Row 1: Gauge + Stats ──────────────────────────────────────────────────
    col_gauge, col_stats = st.columns([1, 2], gap="medium")

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
                &nbsp;·&nbsp;
                Backend: <em>{report.get('llm_backend_used','N/A')}</em>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_stats:
        concerns = ml_result.get("possible_concerns", []) if ml_result else []
        chips = [
            ("⚠️", len(report.get("red_flags", [])),      "Red Flags"),
            ("📋", len(report.get("preop_checklist", [])), "Pre-op Tasks"),
            ("💊", len(report.get("surgical_options", [])),"Recommendations"),
            ("🔢", st.session_state.n_preds,               "Assessments Run"),
        ]
        chip_cols = st.columns(4)
        for col, (icon, val, lbl) in zip(chip_cols, chips):
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
                <div class="sm-card-title">🏷️ AI-Detected Concerns</div>
                {tags}
            </div>""", unsafe_allow_html=True)

    # ── AI Summary ────────────────────────────────────────────────────────────
    summary = report.get("ai_summary", "")
    if summary:
        st.markdown(f"""
        <div class="ai-summary-box">
            <div class="ai-summary-title">🤖 AI Clinical Summary</div>
            {summary}
        </div>""", unsafe_allow_html=True)

    # ── Row 2: Left + Right columns ───────────────────────────────────────────
    col_left, col_right = st.columns([3, 2], gap="medium")

    with col_left:
        # Probable Diagnosis
        dx = report.get("probable_diagnosis", "")
        if dx:
            st.markdown(f"""
            <div class="sm-card">
                <div class="sm-card-title">🩺 Probable Diagnosis</div>
                <div class="dx-box">{dx}</div>
                <div style="font-size:0.70rem;color:var(--text-light);margin-top:0.5rem;">
                    ⚠️ AI-generated clinical impression only — not a confirmed diagnosis.
                </div>
            </div>""", unsafe_allow_html=True)

        # Surgical Recommendations
        options = report.get("surgical_options", [])
        if options:
            recs_html = "".join(f"""
            <div class="rec-item">
                <div class="rec-num">{i}</div>
                <div class="rec-text">{opt}</div>
            </div>""" for i, opt in enumerate(options, 1))
            st.markdown(f"""
            <div class="sm-card">
                <div class="sm-card-title">🔪 Surgical Recommendations</div>
                {recs_html}
            </div>""", unsafe_allow_html=True)

        # Contraindications
        contra = report.get("contraindications", [])
        if contra:
            items = "".join(
                f'<div style="display:flex;gap:0.6rem;align-items:flex-start;margin-bottom:0.5rem;'
                f'font-size:0.83rem;color:var(--text-mid);">'
                f'<span style="color:#E53935;font-size:1rem;flex-shrink:0;">✗</span> {c}</div>'
                for c in contra
            )
            st.markdown(f"""
            <div class="sm-card" style="border-left:3px solid #E53935">
                <div class="sm-card-title" style="color:#C62828">🚫 Contraindications</div>
                {items}
            </div>""", unsafe_allow_html=True)

        # Retrieved Guidelines
        guidelines = report.get("retrieved_guidelines", [])
        if guidelines:
            gl_html = ""
            for g in guidelines[:3]:
                src     = g.get("source", "Guideline")
                title   = g.get("title",  src)
                excerpt = str(g.get("excerpt", g.get("text", "")))[:280]
                gl_html += f"""
                <div style="border:1px solid var(--border);border-radius:var(--radius-sm);
                            padding:0.75rem 1rem;margin-bottom:0.6rem;background:#FAFCFF;">
                    <div style="font-size:0.72rem;font-weight:700;color:var(--navy);margin-bottom:0.3rem;">
                        📄 {title or src}
                    </div>
                    <div style="font-size:0.78rem;color:var(--text-mid);line-height:1.5;">{excerpt}…</div>
                </div>"""
            st.markdown(f"""
            <div class="sm-card">
                <div class="sm-card-title">📚 Retrieved Clinical Guidelines</div>
                {gl_html}
            </div>""", unsafe_allow_html=True)

    with col_right:
        # Red Flags
        red_flags = report.get("red_flags", [])
        if red_flags:
            flags_html = ""
            for rf in red_flags:
                lab      = rf.get("lab",      rf.get("name", "Unknown"))
                reason   = rf.get("reason",   rf.get("surgery_risk", "Clinical review required"))
                severity = rf.get("severity", "MODERATE")
                item_cls, badge_cls = severity_css(severity)
                flags_html += f"""
                <div class="red-flag-item {item_cls}">
                    <div><span class="rf-severity {badge_cls}">{severity}</span></div>
                    <div>
                        <div class="rf-lab">⚗️ {lab}</div>
                        <div class="rf-reason">{str(reason)[:180]}{'…' if len(str(reason))>180 else ''}</div>
                    </div>
                </div>"""
            st.markdown(f"""
            <div class="sm-card" style="border-top:3px solid #E53935">
                <div class="sm-card-title" style="color:#B71C1C">🚨 Red Flag Alerts</div>
                {flags_html}
            </div>""", unsafe_allow_html=True)

        # Pre-op Checklist
        checklist = report.get("preop_checklist", [])
        if checklist:
            for i in range(len(checklist)):
                if i not in st.session_state.checks:
                    st.session_state.checks[i] = False

            done  = sum(st.session_state.checks.values())
            total = len(checklist)
            pct   = int(done / total * 100) if total else 0

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

            for i, item in enumerate(checklist):
                checked = st.session_state.checks.get(i, False)
                new_val = st.checkbox(item, value=checked, key=f"chk_{i}_{abs(hash(item))%99999}")
                st.session_state.checks[i] = new_val

            st.markdown("</div>", unsafe_allow_html=True)

    # ── Export ────────────────────────────────────────────────────────────────
    st.markdown("---")
    ec1, ec2, _ = st.columns([1, 1, 2])
    with ec1:
        st.download_button(
            label     = "⬇️ Export JSON Report",
            data      = json.dumps(report, indent=2, default=str),
            file_name = f"surgimind_{pname.replace(' ','_')}.json",
            mime      = "application/json",
        )
    with ec2:
        if st.button("🔄 New Assessment"):
            st.session_state.report    = None
            st.session_state.ml_result = None
            st.session_state.checks    = {}
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