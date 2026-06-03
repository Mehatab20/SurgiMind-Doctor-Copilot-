# =============================================================================
# rag_module/llm_reasoning.py
# SurgiMind – LLM Reasoning Script
#
# WHAT THIS DOES:
#   1. Accepts a structured ML output dict (from predict_risk())
#      + patient form data
#   2. Calls RAG to retrieve relevant surgical guidelines
#   3. Sends everything to a local Ollama instance (Llama 3 / Mistral)
#      OR falls back to Groq API if Ollama is not running
#      OR generates a high-quality rule-based report if neither is available
#   4. Returns a fully structured clinical AI report dict
#
# HOW TO RUN OLLAMA LOCALLY:
#   1. Install:  https://ollama.com/download
#   2. Pull model:  ollama pull llama3
#                OR ollama pull mistral
#   3. Start:    ollama serve           (runs on http://localhost:11434)
#   4. This script auto-detects Ollama and uses it.
#
# HOW TO USE THIS SCRIPT STANDALONE:
#   python -m rag_module.llm_reasoning
#
# HOW TO USE AS A MODULE:
#   from rag_module.llm_reasoning import generate_report
#   report = generate_report(ml_output, patient_data)
#
# OUTPUT FORMAT:
#   {
#     "probable_diagnosis"    : str,
#     "surgical_options"      : list[str],     # marked as RECOMMENDATIONS
#     "red_flags"             : list[dict],    # {"lab": str, "reason": str, "severity": str}
#     "contraindications"     : list[str],
#     "preop_checklist"       : list[str],
#     "ai_summary"            : str,
#     "retrieved_guidelines"  : list[dict],    # raw RAG chunks
#     "llm_backend_used"      : str,           # "ollama" | "groq" | "rule-based"
#     "model_used"            : str,
#   }
# =============================================================================

from __future__ import annotations

import os
import re
import json
import time
import logging
from typing import Optional

log = logging.getLogger("SurgiMind.LLM")
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")

# ── Ollama config ─────────────────────────────────────────────────────────────
OLLAMA_BASE_URL   = "http://localhost:11434"
OLLAMA_MODEL      = "qwen2.5:1.5b"  # <--- REMOVED os.getenv to stop phi3 from loading
OLLAMA_TIMEOUT    = 300    # seconds – LLM generation can take a moment

# ── Groq fallback config ──────────────────────────────────────────────────────
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL        = "llama3-8b-8192"

# ── Lab abnormality reference table ──────────────────────────────────────────
# Used by the rule-based red-flag detector and to enrich the LLM prompt
LAB_RED_FLAG_TABLE: dict[str, dict] = {
    "lactate": {
        "normal_range" : "0.5–2.0 mmol/L",
        "high_concern" : "> 4.0 mmol/L",
        "surgery_risk" : "Severe tissue hypoperfusion; anaesthetic mortality risk very high. "
                         "Indicates shock physiology. Elective surgery absolutely contraindicated.",
        "severity"     : "CRITICAL",
    },
    "creatinine": {
        "normal_range" : "0.6–1.2 mg/dL",
        "high_concern" : "> 2.0 mg/dL",
        "surgery_risk" : "Acute kidney injury. Renal blood flow impaired. Contrast dye and "
                         "NSAIDs contraindicated. Risk of post-operative renal failure high.",
        "severity"     : "HIGH",
    },
    "troponin": {
        "normal_range" : "< 0.04 ng/mL",
        "high_concern" : "> 0.1 ng/mL",
        "surgery_risk" : "Active myocardial injury or NSTEMI. Non-emergent surgery must be "
                         "deferred. Cardiology evaluation mandatory before any procedure.",
        "severity"     : "CRITICAL",
    },
    "inr": {
        "normal_range" : "0.9–1.1",
        "high_concern" : "> 1.5",
        "surgery_risk" : "Coagulopathy present. Haemostasis cannot be guaranteed intraoperatively. "
                         "FFP or Vitamin K required before proceeding.",
        "severity"     : "HIGH",
    },
    "pt": {
        "normal_range" : "11–13.5 seconds",
        "high_concern" : "> 18 seconds",
        "surgery_risk" : "Prolonged prothrombin time indicates clotting factor deficiency "
                         "(liver disease or anticoagulation). Active bleeding risk intraoperatively.",
        "severity"     : "HIGH",
    },
    "ptt": {
        "normal_range" : "25–35 seconds",
        "high_concern" : "> 50 seconds",
        "surgery_risk" : "Elevated PTT indicates intrinsic pathway coagulopathy. "
                         "Heparin effect or haemophilia must be ruled out.",
        "severity"     : "HIGH",
    },
    "potassium": {
        "normal_range" : "3.5–5.0 mEq/L",
        "high_concern" : "> 5.5 mEq/L",
        "surgery_risk" : "Hyperkalaemia causes cardiac arrhythmias under anaesthesia. "
                         "Correct to < 5.0 mEq/L before elective surgery.",
        "severity"     : "HIGH",
    },
    "sodium": {
        "normal_range" : "136–145 mEq/L",
        "high_concern" : "< 125 or > 155 mEq/L",
        "surgery_risk" : "Severe dysnatraemia causes cerebral oedema or osmotic demyelination. "
                         "Correct cautiously before surgery.",
        "severity"     : "MODERATE",
    },
    "glucose": {
        "normal_range" : "70–140 mg/dL",
        "high_concern" : "> 300 or < 60 mg/dL",
        "surgery_risk" : "Uncontrolled hyperglycaemia impairs wound healing and immune response. "
                         "Hypoglycaemia is a life-threatening anaesthetic emergency.",
        "severity"     : "MODERATE",
    },
    "wbc": {
        "normal_range" : "4.5–11.0 × 10³/μL",
        "high_concern" : "> 15 or < 2.0 × 10³/μL",
        "surgery_risk" : "Leukocytosis suggests active infection or inflammatory response. "
                         "Leukopenia increases surgical site infection risk dramatically.",
        "severity"     : "MODERATE",
    },
    "ph": {
        "normal_range" : "7.35–7.45",
        "high_concern" : "< 7.2",
        "surgery_risk" : "Severe metabolic acidosis profoundly impairs myocardial contractility "
                         "and coagulation enzyme function. Anaesthetic mortality risk extreme.",
        "severity"     : "CRITICAL",
    },
    "platelets": {
        "normal_range" : "150–400 × 10³/μL",
        "high_concern" : "< 50 × 10³/μL",
        "surgery_risk" : "Thrombocytopenia prevents adequate haemostasis. Platelet transfusion "
                         "required before most surgical procedures.",
        "severity"     : "HIGH",
    },
    "haemoglobin": {
        "normal_range" : "12.0–17.5 g/dL",
        "high_concern" : "< 7.0 g/dL",
        "surgery_risk" : "Severe anaemia reduces oxygen-carrying capacity. "
                         "Transfuse to > 8 g/dL before elective surgery. "
                         "Iron studies and cause assessment required.",
        "severity"     : "MODERATE",
    },
    "hemoglobin": {
        "normal_range" : "12.0–17.5 g/dL",
        "high_concern" : "< 7.0 g/dL",
        "surgery_risk" : "Severe anaemia reduces oxygen-carrying capacity. "
                         "Transfuse to > 8 g/dL before elective surgery.",
        "severity"     : "MODERATE",
    },
    "bilirubin": {
        "normal_range" : "0.1–1.2 mg/dL",
        "high_concern" : "> 3.0 mg/dL",
        "surgery_risk" : "Hyperbilirubinaemia indicates hepatic dysfunction. "
                         "Child-Pugh score should be calculated. "
                         "High mortality risk for major surgery in Child-Pugh C.",
        "severity"     : "HIGH",
    },
}


# =============================================================================
# STEP 1 – RED FLAG DETECTOR
# =============================================================================

def detect_red_flags(abnormal_labs: list[str]) -> list[dict]:
    """
    Maps abnormal lab names to clinical red flags with severity ratings.

    Args:
        abnormal_labs: List of abnormal lab name strings from ML output
                       e.g. ["lactate", "creatinine", "troponin"]

    Returns:
        List of red flag dicts:
        [{"lab": str, "normal_range": str, "high_concern": str,
          "surgery_risk": str, "severity": str}]
    """
    flags = []
    seen  = set()

    for lab in abnormal_labs:
        # Clean the lab name (remove "abnormal_" prefix if present)
        lab_clean = lab.lower().strip()
        lab_clean = re.sub(r"^abnormal[_\s]+", "", lab_clean)

        if lab_clean in seen:
            continue
        seen.add(lab_clean)

        if lab_clean in LAB_RED_FLAG_TABLE:
            info = LAB_RED_FLAG_TABLE[lab_clean]
            flags.append({
                "lab"         : lab_clean.upper(),
                "normal_range": info["normal_range"],
                "high_concern": info["high_concern"],
                "surgery_risk": info["surgery_risk"],
                "severity"    : info["severity"],
            })
        else:
            # Unknown lab – generic flag
            flags.append({
                "lab"         : lab_clean.upper(),
                "normal_range": "See reference range",
                "high_concern": "Elevated / abnormal",
                "surgery_risk": f"Abnormal {lab_clean} level detected. "
                                "Clinical correlation and specialist review recommended.",
                "severity"    : "MODERATE",
            })

    # Sort by severity: CRITICAL → HIGH → MODERATE
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2}
    flags.sort(key=lambda f: severity_order.get(f["severity"], 3))

    return flags


# =============================================================================
# STEP 2 – PROMPT BUILDER
# =============================================================================

def _build_ollama_prompt(
    ml_output    : dict,
    patient_data : dict,
    rag_context  : str,
    red_flags    : list[dict],
) -> str:
    """
    Constructs the full prompt for the LLM.
    Includes ML prediction, patient vitals/labs, RAG context, and red flags.
    """
    risk      = ml_output.get("risk_level",       "UNKNOWN")
    confidence= ml_output.get("confidence",       "N/A")
    concerns  = ml_output.get("possible_concerns",  [])
    clin_text = ml_output.get("clinical_text",    "")

    name      = patient_data.get("patient_name",  "Unknown")
    age       = patient_data.get("age",           "Unknown")
    gender    = patient_data.get("gender",        "Unknown")
    adm_type  = patient_data.get("admission_type","Unknown")
    diagnosis = patient_data.get("diagnosis",     "Unknown")
    symptoms  = patient_data.get("symptoms",      "Not specified")
    surgery   = patient_data.get("surgery_type",  "Not specified")

    # Vitals & Labs block
    labs = {
        "Blood Pressure": patient_data.get("blood_pressure"),
        "Heart Rate"    : patient_data.get("heart_rate"),
        "Glucose"       : patient_data.get("glucose"),
        "Creatinine"    : patient_data.get("creatinine"),
        "WBC"           : patient_data.get("wbc"),
        "Lactate"       : patient_data.get("lactate"),
        "Sodium"        : patient_data.get("sodium"),
        "Potassium"     : patient_data.get("potassium"),
        "Troponin"      : patient_data.get("troponin"),
    }
    labs_lines = "\n".join(
        f"  {k}: {v}" for k, v in labs.items() if v not in (None, "", "0")
    ) or "  Not provided"

    # Red flags block
    if red_flags:
        rf_lines = "\n".join(
            f"  [{f['severity']}] {f['lab']}: {f['surgery_risk'][:120]}…"
            for f in red_flags
        )
    else:
        rf_lines = "  None detected"

    # Concerns block
    concerns_str = ", ".join(concerns) if concerns else "None"

    return f"""You are a senior surgical AI consultant. Generate a structured clinical decision support report.

=== PATIENT ===
Name       : {name}
Age/Gender : {age} / {gender}
Admission  : {adm_type}
Diagnosis  : {diagnosis}
Symptoms   : {symptoms}
Surgery Req: {surgery}

=== VITALS AND LABS ===
{labs_lines}

=== AI RISK ASSESSMENT ===
Risk Level  : {risk}  (Confidence: {confidence})
AI Concerns : {concerns_str}
Clinical Text: {clin_text}

=== ABNORMAL LAB RED FLAGS ===
{rf_lines}

=== RETRIEVED SURGICAL GUIDELINES (from knowledge base) ===
{rag_context}

=== INSTRUCTIONS ===
Based on ALL the above information, generate a clinical AI report in this EXACT JSON format.
Return ONLY valid JSON. No markdown. No explanation. No code fences.

{{
  "probable_diagnosis": "One paragraph clinical impression (NOT a confirmed diagnosis)",
  "surgical_options": [
    "RECOMMENDATION 1: [specific procedure + rationale]",
    "RECOMMENDATION 2: [specific procedure + rationale]",
    "RECOMMENDATION 3: [specific procedure + rationale]"
  ],
  "red_flags": [
    {{"lab": "LAB_NAME", "reason": "Why this is a contraindication for surgery", "severity": "CRITICAL|HIGH|MODERATE"}},
    {{"lab": "LAB_NAME", "reason": "...", "severity": "..."}}
  ],
  "contraindications": [
    "Contraindication 1",
    "Contraindication 2"
  ],
  "preop_checklist": [
    "Test or action 1",
    "Test or action 2",
    "Test or action 3",
    "Test or action 4",
    "Test or action 5"
  ],
  "ai_summary": "A 4-5 sentence professional doctor-style clinical summary."
}}"""


# =============================================================================
# STEP 3 – OLLAMA BACKEND
# =============================================================================

def _call_ollama(prompt: str) -> Optional[str]:
    """
    Sends the prompt to a locally running Ollama instance.

    Returns:
        Raw LLM response string, or None if Ollama is unavailable.
    """
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model"  : OLLAMA_MODEL,
        "prompt" : prompt,
        "stream" : False,
        "options": {
            "temperature": 0.2,   # low temperature for consistent clinical output
            "num_predict": 1500,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url     = f"{OLLAMA_BASE_URL}/api/generate",
        data    = payload,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )

    
    
    try:
        log.info(f"Calling Ollama ({OLLAMA_MODEL}) at {OLLAMA_BASE_URL}…")
        t0 = time.time()

        log.info("Sending request to Ollama...")

        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))

            log.info("Received response from Ollama")

            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            print("OLLAMA RESPONSE KEYS:", body.keys())

            log.info("Received response from Ollama")

            print("RESPONSE LENGTH:", len(body.get("response", "")))

            text = body.get("response", "").strip()

            log.info(f"Ollama responded in {time.time()-t0:.1f}s "
                    f"({len(text)} chars)")
            return text if text else None

    except urllib.error.URLError as e:
        log.warning(f"Ollama not reachable ({e}). Trying fallback…")
        return None
    except Exception as e:
        log.error(f"Ollama error: {e}")
        return None


def _is_ollama_running() -> bool:
    """Quick health-check: returns True if Ollama is up."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=3):
            return True
    except Exception:
        return False


# =============================================================================
# STEP 4 – GROQ FALLBACK
# =============================================================================

def _call_groq(prompt: str) -> Optional[str]:
    """
    Calls Groq API as fallback when Ollama is unavailable.
    Requires GROQ_API_KEY environment variable.

    Returns:
        Raw LLM response string, or None if Groq fails.
    """
    if not GROQ_API_KEY:
        log.info("GROQ_API_KEY not set – skipping Groq fallback.")
        return None

    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model"      : GROQ_MODEL,
        "max_tokens" : 1500,
        "temperature": 0.2,
        "messages"   : [
            {
                "role"   : "system",
                "content": ("You are a senior surgical AI consultant. "
                            "Return ONLY valid JSON. No markdown, no explanations."),
            },
            {"role": "user", "content": prompt},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        url     = "https://api.groq.com/openai/v1/chat/completions",
        data    = payload,
        headers = {
            "Content-Type" : "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}",
        },
        method  = "POST",
    )

    try:
        log.info(f"Calling Groq ({GROQ_MODEL})…")
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=60) as resp:
            body    = json.loads(resp.read().decode("utf-8"))
            text    = body["choices"][0]["message"]["content"].strip()
            log.info(f"Groq responded in {time.time()-t0:.1f}s")
            return text if text else None

    except Exception as e:
        log.error(f"Groq error: {e}")
        return None


# =============================================================================
# STEP 5 – JSON PARSER
# =============================================================================

def _parse_llm_response(raw: str) -> Optional[dict]:
    """
    Parses the LLM's response as JSON.
    Handles common issues: markdown fences, leading/trailing text,
    incomplete JSON.

    Returns:
        Parsed dict or None if parsing fails.
    """
    if not raw:
        return None

    # Strip markdown code fences
    raw = re.sub(r"```(?:json)?", "", raw).strip()

    # Find the first { ... } block
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start == -1 or end == 0:
        return None

    json_str = raw[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try to extract partial valid JSON by truncating at last complete field
        try:
            # Remove the last incomplete field if any
            cleaned = re.sub(r',\s*"[^"]*"\s*:\s*[^,}\]]*$', "", json_str)
            cleaned += "}"
            return json.loads(cleaned)
        except Exception:
            log.warning("Could not parse LLM JSON response.")
            return None


# =============================================================================
# STEP 6 – RULE-BASED FALLBACK REPORT
# =============================================================================

def _rule_based_report(
    ml_output    : dict,
    patient_data : dict,
    red_flags    : list[dict],
    rag_chunks   : list,
) -> dict:
    """
    Generates a high-quality structured report using only medical rules
    (no LLM required). Used when both Ollama and Groq are unavailable.
    """
    risk     = ml_output.get("risk_level",       "MEDIUM")
    conf     = ml_output.get("confidence",       "N/A")
    concerns = ml_output.get("possible_concerns", [])
    diag     = patient_data.get("diagnosis",     "unspecified condition")
    age      = patient_data.get("age",           "Unknown")
    adm      = patient_data.get("admission_type","Unknown")

    concerns_str = ", ".join(concerns[:3]) if concerns else "clinical risk factors"

    # ── Probable Diagnosis ────────────────────────────────────────────────────
    probable_dx = (
        f"Based on the clinical presentation of {diag} in a {age}-year-old "
        f"patient admitted as {adm}, with AI-identified concerns including "
        f"{concerns_str}, the probable clinical picture is consistent with "
        f"a {risk.lower()} acuity surgical risk scenario. "
        "This assessment is generated by AI and must be confirmed by a qualified clinician."
    )

    # ── Surgical Options by risk level ────────────────────────────────────────
    if risk == "HIGH":
        options = [
            "RECOMMENDATION 1: Emergency surgical consultation for source control "
            "(if intra-abdominal pathology confirmed by imaging)",
            "RECOMMENDATION 2: Damage control surgery approach – abbreviated procedure "
            "to achieve haemostasis and contamination control, followed by ICU stabilisation "
            "and return to theatre in 24-48 hours",
            "RECOMMENDATION 3: Minimally invasive or percutaneous drainage where feasible "
            "(e.g., CT-guided abscess drainage) as bridge to definitive surgery",
        ]
    elif risk == "MEDIUM":
        options = [
            "RECOMMENDATION 1: Semi-elective surgical management after 24-48 hours of "
            "medical optimisation of comorbidities",
            "RECOMMENDATION 2: Laparoscopic approach preferred to reduce post-operative "
            "pulmonary and wound complications",
            "RECOMMENDATION 3: Interventional radiology-guided procedures as alternative "
            "to open surgery where anatomically feasible",
        ]
    else:  # LOW
        options = [
            "RECOMMENDATION 1: Planned elective surgery with standard pre-operative workup",
            "RECOMMENDATION 2: Laparoscopic or minimally invasive technique preferred",
            "RECOMMENDATION 3: Day-case or 23-hour admission pathway appropriate "
            "given low-risk profile",
        ]

    # ── Red flags from lab table ──────────────────────────────────────────────
    structured_rf = [
        {"lab": f["lab"], "reason": f["surgery_risk"], "severity": f["severity"]}
        for f in red_flags
    ]
    if not structured_rf and risk == "HIGH":
        structured_rf = [{
            "lab"     : "CLINICAL STATUS",
            "reason"  : "High-risk classification by AI based on clinical profile. "
                        "Immediate specialist review required.",
            "severity": "HIGH",
        }]

    # ── Contraindications ─────────────────────────────────────────────────────
    if risk == "HIGH":
        contra = [
            "Elective or semi-elective surgery contraindicated until haemodynamic stabilisation",
            "Anaesthetic risk graded ASA IV or higher – anaesthesiology assessment mandatory",
            "Coagulopathy must be corrected before any surgical incision",
            "ICU-level monitoring required pre- and post-operatively",
        ]
    elif risk == "MEDIUM":
        contra = [
            "Uncontrolled comorbidities (e.g., uncontrolled diabetes, uncontrolled hypertension) "
            "should be optimised before elective surgery",
            "High-risk anaesthetic techniques should be avoided where alternatives exist",
        ]
    else:
        contra = ["No major contraindications identified at this time. Standard precautions apply."]

    # ── Pre-op Checklist ──────────────────────────────────────────────────────
    base_checklist = [
        "Full blood count (CBC) with differential",
        "Comprehensive metabolic panel (CMP): electrolytes, renal function, LFTs",
        "Coagulation panel: PT, PTT, INR",
        "Type and screen (or crossmatch if major surgery)",
        "12-lead ECG",
        "Chest X-ray (PA and lateral)",
        "Urinalysis and urine culture",
    ]
    if risk == "HIGH":
        base_checklist += [
            "Arterial blood gas (ABG)",
            "Blood cultures x2 before antibiotics",
            "Serial lactate measurements every 2 hours",
            "Central venous access and invasive arterial monitoring",
            "ICU bed confirmation and intensivist consultation",
            "Cardiology / relevant specialist clearance",
            "Informed consent with documented risk discussion",
        ]
    elif risk == "MEDIUM":
        base_checklist += [
            "Echocardiogram if cardiac function unknown",
            "Pulmonary function tests if respiratory disease",
            "Endocrinology review if HbA1c > 8.5%",
            "Anaesthesiology pre-assessment clinic",
        ]

    # ── AI Summary ────────────────────────────────────────────────────────────
    summary = (
        f"This AI-generated clinical report identifies a {risk} surgical risk level "
        f"(confidence: {conf}) for this patient presenting with {diag}. "
        f"Key clinical concerns include {concerns_str}. "
    )
    if risk == "HIGH":
        summary += (
            "Immediate haemodynamic stabilisation is the priority. "
            "Elective surgical intervention should be deferred until the patient is optimised. "
            "Emergency or damage-control surgical approaches should be considered only with "
            "full specialist team involvement and ICU backup."
        )
    elif risk == "MEDIUM":
        summary += (
            "A period of medical optimisation prior to surgery is recommended. "
            "Enhanced anaesthetic monitoring and a senior surgical team are advised. "
            "Post-operative high-dependency care should be arranged in advance."
        )
    else:
        summary += (
            "The patient appears suitable for planned surgical management under standard protocols. "
            "Routine pre-operative assessment and consent are sufficient. "
            "No escalation of care is indicated at this time."
        )

    # ── Retrieved guidelines summary ──────────────────────────────────────────
    guideline_refs = [
        {"source": c.source, "title": c.title, "excerpt": c.text[:200]}
        for c in rag_chunks[:3]
    ] if rag_chunks else []

    return {
        "probable_diagnosis"   : probable_dx,
        "surgical_options"     : options,
        "red_flags"            : structured_rf,
        "contraindications"    : contra,
        "preop_checklist"      : base_checklist,
        "ai_summary"           : summary,
        "retrieved_guidelines" : guideline_refs,
        "llm_backend_used"     : "rule-based",
        "model_used"           : "SurgiMind Clinical Rules Engine v1.0",
    }


# =============================================================================
# PUBLIC API
# =============================================================================

def generate_report(
    ml_output    : dict,
    patient_data : dict,
    top_k_rag    : int = 3,
) -> dict:
    """
    Main entry point. Generates a complete structured clinical AI report.

    Args:
        ml_output    : Output dict from predict_risk(). Expected keys:
                       risk_level, confidence, possible_concerns, clinical_text
        patient_data : Patient form fields dict. Expected keys:
                       patient_name, age, gender, admission_type, diagnosis,
                       symptoms, surgery_type, blood_pressure, heart_rate,
                       glucose, creatinine, wbc, lactate, sodium, potassium, troponin
        top_k_rag    : Number of guideline chunks to retrieve (default 3)

    Returns:
        Structured report dict with keys:
        probable_diagnosis, surgical_options, red_flags, contraindications,
        preop_checklist, ai_summary, retrieved_guidelines,
        llm_backend_used, model_used
    """
    log.info("="*55)
    log.info("SurgiMind LLM Reasoning Engine – Generating Report")
    log.info("="*55)

    # ── Step 1: Detect red flags from abnormal labs ───────────────────────────
    abnormal_labs = _extract_abnormal_labs(ml_output, patient_data)
    red_flags     = detect_red_flags(abnormal_labs)
    log.info(f"Detected {len(red_flags)} red flags from {len(abnormal_labs)} abnormal labs")

    # ── Step 2: RAG retrieval ─────────────────────────────────────────────────
    try:
        from rag_module.rag_engine import retrieve_for_ml_output, retrieve_protocols_as_context
        rag_chunks   = retrieve_for_ml_output(ml_output, top_k=top_k_rag)
        rag_context  = retrieve_protocols_as_context(
            ml_output.get("clinical_text", ml_output.get("diagnosis", "surgery")),
            top_k=top_k_rag,
        )
        log.info(f"RAG retrieved {len(rag_chunks)} guideline chunks")
    except Exception as e:
        log.warning(f"RAG retrieval failed: {e} – proceeding without guidelines")
        rag_chunks  = []
        rag_context = "No guidelines retrieved."

    # ── Step 3: Build LLM prompt ──────────────────────────────────────────────
    prompt = _build_ollama_prompt(ml_output, patient_data, rag_context, red_flags)

    # ── Step 4: Try Ollama first ──────────────────────────────────────────────
    llm_raw    = None
    backend    = "rule-based"
    model_used = "SurgiMind Clinical Rules Engine v1.0"

    print("OLLAMA RUNNING:", _is_ollama_running())
    print("OLLAMA MODEL:", OLLAMA_MODEL)

    if _is_ollama_running():
        log.info(f"Ollama is running – using {OLLAMA_MODEL}")
        llm_raw    = _call_ollama(prompt)
        backend    = "ollama"
        model_used = OLLAMA_MODEL
    else:
        log.info("Ollama not running – trying Groq API…")

    # ── Step 5: Groq fallback ─────────────────────────────────────────────────
    if llm_raw is None and GROQ_API_KEY:
        llm_raw    = _call_groq(prompt)
        backend    = "groq"
        model_used = GROQ_MODEL

    # ── Step 6: Parse LLM JSON ────────────────────────────────────────────────
    if llm_raw:
        parsed = _parse_llm_response(llm_raw)
        if parsed:
            # Inject metadata and RAG chunks into the parsed report
            parsed["llm_backend_used"]  = backend
            parsed["model_used"]        = model_used
            parsed["retrieved_guidelines"] = [
                {"source": c.source, "title": c.title, "excerpt": c.text[:300]}
                for c in rag_chunks
            ]
            # Merge with rule-based red flags if LLM didn't generate them properly
            if not parsed.get("red_flags"):
                parsed["red_flags"] = [
                    {"lab": f["lab"], "reason": f["surgery_risk"], "severity": f["severity"]}
                    for f in red_flags
                ]
            log.info(f"Report generated via {backend} ({model_used})")
            return parsed
        else:
            log.warning("LLM returned unparseable response – using rule-based fallback")

    # ── Step 7: Rule-based fallback ───────────────────────────────────────────
    log.info("Using rule-based clinical report engine")
    return _rule_based_report(ml_output, patient_data, red_flags, rag_chunks)


# =============================================================================
# HELPER – EXTRACT ABNORMAL LABS
# =============================================================================

def _extract_abnormal_labs(ml_output: dict, patient_data: dict) -> list[str]:
    """
    Combines abnormal lab signals from:
    - ml_output["possible_concerns"] (e.g. ["Sepsis", "Advanced Age"])
    - ml_output["clinical_text"]     (e.g. "abnormal_lactate abnormal_creatinine")
    - patient_data vitals that are in the abnormal range

    Returns:
        Deduplicated list of abnormal lab name strings.
    """
    labs = set()

    # From clinical_text tokens like "abnormal_lactate"
    clinical = ml_output.get("clinical_text", "")
    for token in clinical.split():
        if token.startswith("abnormal_"):
            labs.add(token.replace("abnormal_", ""))

    # From concerns that look like lab names
    for concern in ml_output.get("possible_concerns", []):
        concern_lower = concern.lower()
        for lab_name in LAB_RED_FLAG_TABLE:
            if lab_name in concern_lower:
                labs.add(lab_name)

    # From patient vitals with known threshold breaches
    thresholds = {
        "lactate"  : (lambda v: float(v) > 2.0),
        "creatinine": (lambda v: float(v) > 1.2),
        "troponin" : (lambda v: float(v) > 0.04),
        "wbc"      : (lambda v: float(v) > 11.0 or float(v) < 4.5),
        "glucose"  : (lambda v: float(v) > 140 or float(v) < 70),
        "potassium": (lambda v: float(v) > 5.0 or float(v) < 3.5),
        "sodium"   : (lambda v: float(v) > 145 or float(v) < 136),
    }
    for lab, check in thresholds.items():
        val = patient_data.get(lab)
        if val not in (None, "", 0):
            try:
                if check(val):
                    labs.add(lab)
            except (TypeError, ValueError):
                pass

    return list(labs)


# =============================================================================
# CLI SELF-TEST  –  python -m rag_module.llm_reasoning
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  SurgiMind LLM Reasoning Engine – Self-Test")
    print("="*60)

    # ── Test case 1: HIGH risk sepsis patient ─────────────────────────────────
    ml_out_high = {
        "risk_level"       : "HIGH",
        "confidence"       : "91%",
        "possible_concerns": ["Sepsis", "Advanced Age (>70)", "Multiple Abnormal Labs"],
        "clinical_text"    : (
            "sepsis emergency male very_elderly_patient advanced_age "
            "abnormal_lactate abnormal_creatinine abnormal_wbc "
            "high_severity_diagnosis critical_lab_volume"
        ),
    }
    patient_high = {
        "patient_name"   : "John Smith",
        "age"            : 74,
        "gender"         : "male",
        "admission_type" : "emergency",
        "diagnosis"      : "sepsis",
        "symptoms"       : "fever, hypotension, altered mental status, oliguria",
        "surgery_type"   : "exploratory laparotomy for suspected perforation",
        "blood_pressure" : "82/50",
        "heart_rate"     : 118,
        "glucose"        : 245,
        "creatinine"     : 3.2,
        "wbc"            : 18.4,
        "lactate"        : 4.8,
        "sodium"         : 132,
        "potassium"      : 5.8,
        "troponin"       : 0.09,
    }

    print("\n--- Test 1: HIGH risk septic patient ---")
    report = generate_report(ml_out_high, patient_high)

    print(f"\n  Backend used : {report['llm_backend_used']}")
    print(f"  Model used   : {report['model_used']}")
    print(f"\n  Probable Dx  : {report['probable_diagnosis'][:120]}…")
    print(f"\n  Surgical Options ({len(report['surgical_options'])}):")
    for opt in report["surgical_options"]:
        print(f"    • {opt[:80]}…")
    print(f"\n  Red Flags ({len(report['red_flags'])}):")
    for rf in report["red_flags"]:
        print(f"    [{rf['severity']}] {rf['lab']}: {rf['reason'][:60]}…")
    print(f"\n  Pre-op Checklist ({len(report['preop_checklist'])} items):")
    for item in report["preop_checklist"][:5]:
        print(f"    ✓ {item}")
    print(f"\n  Guidelines retrieved: {len(report['retrieved_guidelines'])}")
    print(f"\n  AI Summary: {report['ai_summary'][:200]}…")

    # ── Test case 2: LOW risk elective patient ────────────────────────────────
    ml_out_low = {
        "risk_level"       : "LOW",
        "confidence"       : "78%",
        "possible_concerns": ["Elective procedure"],
        "clinical_text"    : "elective knee replacement elective young adult patient low_severity_diagnosis",
    }
    patient_low = {
        "patient_name"  : "Jane Doe",
        "age"           : 45,
        "gender"        : "female",
        "admission_type": "elective",
        "diagnosis"     : "osteoarthritis – knee replacement",
        "symptoms"      : "chronic knee pain, reduced mobility",
        "surgery_type"  : "total knee arthroplasty",
        "glucose"       : 95,
        "creatinine"    : 0.8,
    }

    print("\n\n--- Test 2: LOW risk elective patient ---")
    report2 = generate_report(ml_out_low, patient_low)
    print(f"  Risk Summary: {report2['ai_summary'][:180]}…")
    print(f"  Contraindications: {report2['contraindications']}")

    print("\n\n[LLM Reasoning Self-Test Complete]\n")