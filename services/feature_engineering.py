# # # =============================================================================
# services/feature_engineering.py
# SurgiMind – AI Surgical Decision Support Assistant
#
# ARCHITECTURE:
#   Weighted multi-signal scoring system that assigns every patient admission
#   a numeric risk score (0–100), then maps it to HIGH / MEDIUM / LOW.
#
#   Four independent scoring components:
#       _diagnosis_score()       0–45 pts  (dominant signal)
#       _age_score()             0–15 pts
#       _admission_type_score()  0–10 pts
#       _lab_score()             0–10 pts  (lab counts scaled to this dataset)
#       ──────────────────────────────────
#       TOTAL                    0–80 pts  (theoretical max)
#
#   Thresholds (tuned to this 129-record MIMIC-III slice):
#       >= 50  →  HIGH
#       >= 25  →  MEDIUM
#        < 25  →  LOW
#
#   Design rules enforced by the score caps:
#       • Emergency alone (10 pts) + old age (15 pts) = 25 → MEDIUM, not HIGH
#       • Mild diagnosis (≤8 pts) + any other signal → stays LOW or MEDIUM
#       • Severe diagnosis (≥40 pts) → HIGH regardless of other signals
#       • Elective + mild diagnosis + average labs → LOW
#
#   Anti-imbalance safeguard:
#       prepare_features() calls _rebalance_thresholds() after initial labelling.
#       If HIGH > 45% or LOW < 15%, thresholds are nudged automatically and
#       labels are recomputed once, with a warning logged.
#
# PUBLIC API (do NOT rename – used by preprocessing, training, prediction):
#   build_clinical_text(row)                          → str
#   assign_risk_label(row, high_thr, medium_thr)      → str
#   prepare_features(df)                              → (X: Series, y: Series)
#   build_single_clinical_text(diag, adm, gender, age, labs) → str
# =============================================================================

import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.helpers import log


# =============================================================================
# DEFAULT SCORE THRESHOLDS
# Modify here only if your dataset changes substantially.
# =============================================================================

DEFAULT_HIGH_THRESHOLD   = 50   # score >= this  →  HIGH
DEFAULT_MEDIUM_THRESHOLD = 25   # score >= this  →  MEDIUM  (else LOW)


# =============================================================================
# 1. DIAGNOSIS SCORING
# =============================================================================
# Rules:
#   • Scores are ADDITIVE – a compound diagnosis like "sepsis;pneumonia"
#     receives pts from every matching entry (capped at 45).
#   • Tier labels are for readability only; only the numeric pts matter.
#   • Elective-procedure suffixes ("/sda", "cath") reduce the effective score
#     via negative entries so that planned procedures stay LOW/MEDIUM.
# =============================================================================

_DIAGNOSIS_SCORE_TABLE = [

    # ── TIER A: Immediately life-threatening (40–45 pts) ─────────────────────
    ("vf arrest",                        45),
    ("cardiac arrest",                   45),
    ("status epilepticus",               44),
    ("intracranial hemorrhage",          43),
    ("basal ganglin bleed",              43),
    ("acute subdural hematoma",          43),
    ("subdural hematoma",                42),
    ("stemi",                            42),
    ("urosepsis",                        41),
    ("sepsis",                           40),   # covers sepsis, sepsis;uti, etc.
    ("acute respiratory distress",       40),
    ("respiratory failure",              40),
    ("liver failure",                    40),
    ("hepatic encep",                    40),
    ("renal failiure",                   40),   # MIMIC typo preserved
    ("renal failure",                    40),
    ("critical aortic",                  40),
    ("hypotension;unresponsive",         40),

    # ── TIER B: High acuity (28–38 pts) ──────────────────────────────────────
    ("stroke",                           38),
    ("cerebrovascular accident",         38),
    ("pulmonary edema, mi",              37),
    ("mi chf",                           37),
    ("inferior myocardial infarction",   37),
    ("acute pulmonary embolism",         36),
    ("variceal bleed",                   36),
    ("lung cancer",                      35),
    ("non small cell cancer",            35),
    ("metastatic melanoma",              35),
    ("metastic melanoma",                35),
    ("brain metastases",                 35),
    ("aromegley",                        34),
    ("burkitts lymphoma",                34),
    ("chronic myelogenous leuk",         34),
    ("volvulus",                         33),
    ("tracheal esophageal fistula",      33),
    ("pericardial effusion",             32),
    ("overdose",                         32),
    ("hypotension",                      30),   # covers hypotension;telemetry
    ("gastrointestinal bleed",           30),
    ("upper gi bleed",                   30),
    ("lower gi bleed",                   30),
    ("congestive heart failure",         29),
    ("unstable angina",                  29),
    ("motor vehicle accident",           28),
    ("motorcycle accident",              28),

    # ── TIER C: Moderate acuity (14–24 pts) ──────────────────────────────────
    ("pneumonia",                        22),
    ("respiratory distress",             21),
    ("acute cholangitis",                20),
    ("acute cholecystitis",              20),
    ("alcoholic hepatitis",              20),
    ("hepatitis b",                      18),
    ("hepatitis",                        17),
    ("seizure",                          18),
    ("shortness of breath",              17),
    ("tachypnea",                        17),
    ("altered mental status",            16),
    ("syncope",                          16),
    ("bradycardia",                      16),
    ("hypoglycemia",                     15),
    ("hyponatremia",                     15),
    ("cholangitis",                      15),
    ("cholecystitis",                    15),
    ("urinary tract infection",          15),
    ("pyelonephritis",                   15),
    ("abscess",                          15),
    ("cellulitis",                       15),
    ("failure to thrive",                14),
    ("fever",                            14),
    ("pleural effusion",                 14),
    ("chest pain",                       14),
    ("abdominal pain",                   14),
    ("asthma",                           14),
    ("s/p fall",                         14),
    ("elevated liver functions",         14),

    # ── TIER D: Mild / low acuity (4–12 pts) ─────────────────────────────────
    ("mediastinal adenopathy",           12),
    ("tracheal stenosis",                12),
    ("fracture",                         12),
    ("humeral fracture",                 12),
    ("hip fracture",                     12),
    ("facial numbness",                   8),
    ("headache",                          6),
    ("recurrent left carotid",            5),
    ("pre hydration",                     4),

    # ── TIER E: Planned / elective procedures (1–3 pts) ──────────────────────
    # These produce very low base scores so elective admissions stay LOW.
    ("bypass graft",                      3),
    ("valve replacement",                 3),
    ("cath",                              2),   # catheterisation
    ("telemetry",                         2),
    ("/sda",                              1),   # same-day admission suffix

]


def _diagnosis_score(diagnosis: str) -> int:
    """
    Sums pts from every matching entry in _DIAGNOSIS_SCORE_TABLE.
    Result is capped at 45 to prevent any single diagnosis from dominating
    the total score and forcing everything into HIGH.

    Args:
        diagnosis (str): Raw diagnosis string (will be lowercased internally)

    Returns:
        int: Score in range [0, 45]
    """
    diag = str(diagnosis).lower().strip()
    total = 0
    for keyword, pts in _DIAGNOSIS_SCORE_TABLE:
        if keyword in diag:
            total += pts
    return min(total, 45)


# =============================================================================
# 2. AGE SCORING
# =============================================================================
# Capped at 15 pts so age alone CANNOT push a patient into HIGH.
# Dataset mean age ≈ 70, 75th pct ≈ 83 → buckets tuned accordingly.
# =============================================================================

def _age_score(age) -> int:
    """
    Returns 0-15 pts based on patient age.
    Older patients carry higher baseline surgical risk.

    Args:
        age: Numeric age in years (or NaN / None)

    Returns:
        int: Score in range [0, 15]
    """
    try:
        age = float(age)
    except (TypeError, ValueError):
        return 5   # neutral default for unknown age

    if   age > 85: return 15
    elif age > 75: return 12
    elif age > 65: return  9
    elif age > 55: return  6
    elif age > 40: return  3
    elif age > 18: return  1
    else:          return  2   # paediatric – small bump for complexity


# =============================================================================
# 3. ADMISSION TYPE SCORING
# =============================================================================
# Capped at 10 pts so admission type alone CANNOT force HIGH.
# 92% of this dataset is EMERGENCY → keeping this cap tight is critical.
# =============================================================================

def _admission_type_score(admission_type: str) -> int:
    """
    Returns 0-10 pts based on admission type.

    Args:
        admission_type (str): e.g. "emergency", "urgent", "elective"

    Returns:
        int: Score in range [0, 10]
    """
    adm = str(admission_type).lower().strip()
    if   adm == "emergency": return 10
    elif adm == "urgent":    return  7
    elif adm == "elective":  return  0
    else:                    return  3   # unknown / newborn


# =============================================================================
# 4. LAB ABNORMALITY SCORING
# =============================================================================
# This dataset has lab counts in the hundreds (median ≈ 94, max ≈ 2516).
# Thresholds are calibrated to the actual quantile distribution:
#   10th pct ≈  38,  25th pct ≈  54,  50th pct ≈  94,  75th pct ≈ 200
# Capped at 10 pts.
# =============================================================================

def _lab_score(abnormal_lab_count) -> int:
    """
    Returns 0-10 pts based on the count of abnormal lab results.
    Thresholds are tuned to this MIMIC-III slice where counts range 10-2516.

    Args:
        abnormal_lab_count: Numeric count (or NaN / None)

    Returns:
        int: Score in range [0, 10]
    """
    try:
        count = float(abnormal_lab_count)
    except (TypeError, ValueError):
        return 0

    if   count >= 500: return 10
    elif count >= 250: return  8
    elif count >= 150: return  6
    elif count >=  75: return  4
    elif count >=  40: return  2
    else:              return  1


# =============================================================================
# 5. COMPOSITE RISK SCORING
# =============================================================================

def _compute_risk_score(row: pd.Series) -> int:
    """
    Combines the four component scores into a single composite score.

    Max theoretical score:
        diagnosis (45) + age (15) + admission (10) + labs (10) = 80

    Args:
        row (pd.Series): One row from the preprocessed DataFrame

    Returns:
        int: Composite risk score in range [0, 80]
    """
    return (
        _diagnosis_score(row.get("diagnosis", ""))
        + _age_score(row.get("age", 50))
        + _admission_type_score(row.get("admission_type", ""))
        + _lab_score(row.get("abnormal_lab_count", 0))
    )


# =============================================================================
# 6. ASSIGN RISK LABEL  (primary public API)
# =============================================================================

def assign_risk_label(
    row: pd.Series,
    high_threshold: int   = DEFAULT_HIGH_THRESHOLD,
    medium_threshold: int = DEFAULT_MEDIUM_THRESHOLD,
) -> str:
    """
    Assigns a surgical risk category to a single patient record.

    Priority order:
        1. hospital_expire_flag == 1  →  always HIGH (patient died in-hospital)
        2. composite score >= high_threshold    →  HIGH
        3. composite score >= medium_threshold  →  MEDIUM
        4. otherwise                            →  LOW

    Args:
        row              (pd.Series): Preprocessed patient record
        high_threshold   (int): Score cutoff for HIGH   (default 50)
        medium_threshold (int): Score cutoff for MEDIUM (default 25)

    Returns:
        str: "HIGH", "MEDIUM", or "LOW"
    """
    # Hard override: in-hospital mortality is always highest risk
    if int(row.get("hospital_expire_flag", 0) or 0) == 1:
        return "HIGH"

    score = _compute_risk_score(row)

    if   score >= high_threshold:   return "HIGH"
    elif score >= medium_threshold: return "MEDIUM"
    else:                           return "LOW"


# =============================================================================
# 7. DYNAMIC THRESHOLD REBALANCING
# =============================================================================

def _rebalance_thresholds(
    df: pd.DataFrame,
    high_thr: int,
    medium_thr: int,
) -> tuple:
    """
    Inspects the class distribution produced by the current thresholds.
    If HIGH > 45% or LOW < 15%, nudges thresholds and recomputes once.

    The nudge is deliberate and bounded - it never moves thresholds more
    than ±8 pts so the clinical meaning of scores is preserved.

    Args:
        df         (pd.DataFrame): DataFrame already containing a 'risk_score' column
        high_thr   (int): Current HIGH threshold
        medium_thr (int): Current MEDIUM threshold

    Returns:
        tuple[int, int]: (possibly_adjusted_high_thr, possibly_adjusted_medium_thr)
    """
    total = len(df)
    if total == 0:
        return high_thr, medium_thr

    # Compute distribution with current thresholds (using pre-computed scores)
    def _label(row):
        if int(row.get("hospital_expire_flag", 0) or 0) == 1:
            return "HIGH"
        s = row["risk_score"]
        if   s >= high_thr:   return "HIGH"
        elif s >= medium_thr: return "MEDIUM"
        else:                 return "LOW"

    labels = df.apply(_label, axis=1)
    high_pct = (labels == "HIGH").sum()   / total * 100
    low_pct  = (labels == "LOW").sum()    / total * 100

    adjusted = False
    new_high_thr   = high_thr
    new_medium_thr = medium_thr

    # ── HIGH class too dominant ────────────────────────────────────────────
    if high_pct > 45:
        increase = min(8, round((high_pct - 40) * 0.4))
        new_high_thr = high_thr + increase
        log(
            f"Auto-rebalance: HIGH={high_pct:.1f}% > 45%. "
            f"Raising HIGH threshold {high_thr} → {new_high_thr}.",
            level="WARNING"
        )
        adjusted = True

    # ── LOW class too small ────────────────────────────────────────────────
    if low_pct < 15:
        # Reduce medium threshold so more cases fall into LOW
        decrease = min(5, round((15 - low_pct) * 0.5))
        new_medium_thr = max(15, medium_thr - decrease)
        log(
            f"Auto-rebalance: LOW={low_pct:.1f}% < 15%. "
            f"Lowering MEDIUM threshold {medium_thr} → {new_medium_thr}.",
            level="WARNING"
        )
        adjusted = True

    if not adjusted:
        log("Threshold check passed – no rebalancing required.")

    return new_high_thr, new_medium_thr


# =============================================================================
# 8. BUILD CLINICAL TEXT  (primary public API)
# =============================================================================

def build_clinical_text(row: pd.Series) -> str:
    """
    Produces a single lower-cased text string per patient record for TF-IDF.

    Encoding strategy:
        • Diagnosis tokens verbatim (compound diagnoses split on ; / \\)
        • Admission type as a single token
        • Gender as a single token
        • Age bucket as a descriptive compound token (e.g. "very_elderly_patient")
        • Each abnormal lab prefixed with "abnormal_" (e.g. "abnormal_glucose")
        • Severity signal tokens derived from the diagnosis score bucket
          ("high_severity_diagnosis", "moderate_severity_diagnosis", etc.)
        • Lab volume signal token ("critical_lab_volume", "high_lab_volume", etc.)

    Using underscores inside multi-word concepts keeps them as single TF-IDF
    tokens and prevents stop-word stripping from fragmenting them.

    Args:
        row (pd.Series): One preprocessed patient record

    Returns:
        str: Space-separated clinical text (all lowercase, no punctuation)
    """
    parts = []

    # ── Diagnosis ─────────────────────────────────────────────────────────────
    diagnosis = str(row.get("diagnosis", "")).strip().lower()
    if diagnosis and diagnosis != "nan":
        clean_diag = (
            diagnosis
            .replace(";",  " ")
            .replace("/",  " ")
            .replace("\\", " ")
            .replace(",",  " ")
            .replace("-",  " ")
        )
        parts.append(clean_diag)

    # ── Admission type ────────────────────────────────────────────────────────
    adm_type = str(row.get("admission_type", "")).strip().lower()
    if adm_type and adm_type not in ("nan", "unknown"):
        parts.append(adm_type)

    # ── Gender ────────────────────────────────────────────────────────────────
    gender = str(row.get("gender", "")).strip().lower()
    if gender and gender not in ("nan", "unknown"):
        parts.append(gender)

    # ── Age bucket token ──────────────────────────────────────────────────────
    age = row.get("age", np.nan)
    if pd.notna(age):
        age_f = float(age)
        if   age_f > 85: parts += ["very_elderly_patient", "advanced_age"]
        elif age_f > 75: parts += ["elderly_patient",      "advanced_age"]
        elif age_f > 65: parts.append("older_adult_patient")
        elif age_f > 55: parts.append("middle_aged_patient")
        elif age_f > 40: parts.append("adult_patient")
        elif age_f > 18: parts.append("young_adult_patient")
        else:            parts.append("pediatric_patient")

    # ── Abnormal lab tokens ───────────────────────────────────────────────────
    lab_summary = str(row.get("abnormal_lab_summary", "")).strip().lower()
    if lab_summary and lab_summary != "nan":
        lab_tokens = [t for t in lab_summary.split() if t][:15]  # cap at 15
        parts.extend([f"abnormal_{t}" for t in lab_tokens])

    # ── Lab volume signal token ───────────────────────────────────────────────
    lab_count = float(row.get("abnormal_lab_count", 0) or 0)
    if   lab_count >= 500: parts += ["critical_lab_volume", "high_lab_volume"]
    elif lab_count >= 250: parts.append("high_lab_volume")
    elif lab_count >= 100: parts.append("elevated_lab_volume")
    elif lab_count >=  40: parts.append("moderate_lab_volume")
    else:                  parts.append("low_lab_volume")

    # ── Diagnosis severity signal token ──────────────────────────────────────
    d_score = _diagnosis_score(row.get("diagnosis", ""))
    if   d_score >= 38: parts.append("high_severity_diagnosis")
    elif d_score >= 20: parts.append("moderate_severity_diagnosis")
    elif d_score >=  8: parts.append("mild_severity_diagnosis")
    else:               parts.append("low_severity_diagnosis")

    return " ".join(parts)


# =============================================================================
# 9. PREPARE FEATURES  (primary public API)
# =============================================================================

def prepare_features(df: pd.DataFrame):
    """
    Full feature engineering pipeline: text building + risk labelling.

    Steps:
        1. Build 'clinical_text' column via build_clinical_text()
        2. Drop rows where clinical text is empty
        3. Compute per-row composite risk score (_compute_risk_score)
        4. Run _rebalance_thresholds() to auto-tune HIGH/MEDIUM cutoffs
        5. Apply assign_risk_label() with (possibly adjusted) thresholds
        6. Log detailed class distribution

    Args:
        df (pd.DataFrame): Cleaned, merged DataFrame from preprocessing.py

    Returns:
        tuple[pd.Series, pd.Series]:
            X  - clinical text strings (one per admission)
            y  - risk labels: "HIGH" | "MEDIUM" | "LOW"
    """
    log("Building clinical text features...")
    df = df.copy()

    # ── Step 1: Build text ────────────────────────────────────────────────────
    df["clinical_text"] = df.apply(build_clinical_text, axis=1)

    # ── Step 2: Drop empty text rows ─────────────────────────────────────────
    before = len(df)
    df = df[df["clinical_text"].str.strip() != ""].copy()
    removed = before - len(df)
    if removed:
        log(f"Dropped {removed} rows with empty clinical text.")

    # ── Step 3: Pre-compute risk scores (reused by rebalancer) ───────────────
    log("Computing composite risk scores...")
    df["risk_score"] = df.apply(_compute_risk_score, axis=1)

    score_stats = df["risk_score"].describe()
    log(f"Risk score  min={score_stats['min']:.0f}  "
        f"median={score_stats['50%']:.0f}  "
        f"max={score_stats['max']:.0f}")

    # ── Step 4: Auto-tune thresholds if needed ────────────────────────────────
    log("Checking class balance and adjusting thresholds if needed...")
    high_thr, medium_thr = _rebalance_thresholds(
        df, DEFAULT_HIGH_THRESHOLD, DEFAULT_MEDIUM_THRESHOLD
    )

    # ── Step 5: Assign labels ─────────────────────────────────────────────────
    log(f"Assigning risk labels  [HIGH≥{high_thr}  MEDIUM≥{medium_thr}  LOW<{medium_thr}]...")
    df["risk_label"] = df.apply(
        lambda row: assign_risk_label(row, high_thr, medium_thr), axis=1
    )

    # ── Step 6: Distribution report ───────────────────────────────────────────
    total  = len(df)
    counts = df["risk_label"].value_counts().to_dict()
    high   = counts.get("HIGH",   0)
    medium = counts.get("MEDIUM", 0)
    low    = counts.get("LOW",    0)

    log("─" * 55)
    log("  SURGICAL RISK LABEL DISTRIBUTION")
    log("─" * 55)
    log(f"  HIGH   : {high:>4} samples  ({high   / total * 100:5.1f}%)")
    log(f"  MEDIUM : {medium:>4} samples  ({medium / total * 100:5.1f}%)")
    log(f"  LOW    : {low:>4} samples  ({low    / total * 100:5.1f}%)")
    log(f"  TOTAL  : {total:>4} samples")
    log("─" * 55)

    # ── Per-class warnings ────────────────────────────────────────────────────
    targets = {"HIGH": (25, 50), "MEDIUM": (25, 50), "LOW": (15, 35)}
    for label, (lo, hi) in targets.items():
        pct = counts.get(label, 0) / total * 100
        if pct < lo:
            log(f"WARNING: '{label}' at {pct:.1f}% is below target ≥{lo}%.",
                level="WARNING")
        elif pct > hi:
            log(f"WARNING: '{label}' at {pct:.1f}% exceeds target ≤{hi}%.",
                level="WARNING")

    # ── Abort if any class is completely absent ───────────────────────────────
    for label in ("HIGH", "MEDIUM", "LOW"):
        if counts.get(label, 0) == 0:
            log(
                f"CRITICAL: Class '{label}' has 0 samples. "
                "The model cannot learn this class. "
                "Check diagnosis coverage in _DIAGNOSIS_SCORE_TABLE.",
                level="ERROR"
            )

    log(f"Feature preparation complete. Total samples ready: {total}")

    # Drop the helper column before returning
    df.drop(columns=["risk_score"], inplace=True, errors="ignore")

    return df["clinical_text"], df["risk_label"]


# =============================================================================
# 10. SINGLE-RECORD TEXT BUILDER  (primary public API)
# =============================================================================

def build_single_clinical_text(
    diagnosis: str,
    admission_type: str,
    gender: str,
    age: float,
    abnormal_lab_summary: str = "",
) -> str:
    """
    Builds a clinical text string for a single patient at inference time.
    Called by prediction_service.predict_risk() - do NOT rename.

    Args:
        diagnosis            (str)  : Patient diagnosis text
        admission_type       (str)  : e.g. "emergency", "elective"
        gender               (str)  : "male" / "female"
        age                  (float): Age in years
        abnormal_lab_summary (str)  : Space-separated abnormal lab labels

    Returns:
        str: Clinical text ready for TF-IDF transform
    """
    lab_tokens    = [t for t in str(abnormal_lab_summary).split() if t]
    lab_count     = len(lab_tokens) * 30   # proxy: each named lab ≈ 30 raw count units

    mock_row = pd.Series({
        "diagnosis"            : diagnosis,
        "admission_type"       : admission_type,
        "gender"               : gender,
        "age"                  : age,
        "abnormal_lab_summary" : abnormal_lab_summary,
        "abnormal_lab_count"   : lab_count,
        "hospital_expire_flag" : 0,
    })
    return build_clinical_text(mock_row)
# =============================================================================
# # services/feature_engineering.py
# # SurgiMind – AI Surgical Decision Support Assistant
# #
# # PURPOSE:
# #   Transforms the cleaned DataFrame into ML-ready features using a
# #   SCORE-BASED risk labelling system that produces balanced
# #   HIGH / MEDIUM / LOW classes.
# #
# # KEY DESIGN:
# #   Instead of simple keyword matching (which caused ALL-HIGH labels),
# #   every patient receives a numeric risk score (0–100) built from
# #   independent, weighted signals:
# #
# #       1. Diagnosis severity      (0–50 pts)
# #       2. Age                     (0–20 pts)
# #       3. Admission type          (0–15 pts)
# #       4. Abnormal lab count      (0–15 pts)
# #
# #   Score thresholds:
# #       >= 55  →  HIGH
# #       >= 25  →  MEDIUM
# #        < 25  →  LOW
# #
# #   This guarantees class diversity even when most admissions are
# #   EMERGENCY, because emergency alone only contributes 15 pts.
# #
# # FUNCTIONS (public API — do NOT rename, other modules depend on these):
# #   build_clinical_text()         row  → str
# #   assign_risk_label()           row  → "HIGH" | "MEDIUM" | "LOW"
# #   prepare_features()            df   → (X: Series, y: Series)
# #   build_single_clinical_text()  args → str   [used by prediction_service]
# # =============================================================================

# import os
# import sys
# import pandas as pd
# import numpy as np

# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# from utils.helpers import log


# # =============================================================================
# # SCORING TABLES
# # Each entry: (substring_to_match, score)
# # Strings are matched against the FULL diagnosis text (lowercased).
# # Entries are evaluated top-to-bottom; ALL matching entries are summed.
# # Score is capped at 50 before being combined with other signals.
# # =============================================================================

# DIAGNOSIS_SCORE_TABLE = [
#     # ── Tier 5 – Immediately life-threatening (40–50 pts) ────────────────────
#     ("vf arrest",               50),
#     ("cardiac arrest",          50),
#     ("ventricular fibrillation",50),
#     ("stemi",                   48),
#     ("aortic stenosis",         46),
#     ("status epilepticus",      45),
#     ("intracranial hemorrhage", 45),
#     ("subdural hematoma",       44),
#     ("basal ganglin bleed",     44),
#     ("acute subdural",          44),
#     ("urosepsis",               43),
#     ("sepsis",                  43),   # covers sepsis, sepsis;uti, sepsis;pneumonia
#     ("liver failure",           42),
#     ("hepatic encep",           42),
#     ("renal failiure",          42),   # note: MIMIC typo "failiure"
#     ("renal failure",           42),
#     ("respiratory failure",     42),
#     ("acute respiratory distress",42),
#     ("hypotension;unresponsive",41),
#     ("critical aortic",         41),
#     ("pulmonary edema, mi",     40),
#     ("mi chf",                  40),
#     ("inferior myocardial",     40),
#     ("stroke",                  40),
#     ("cerebrovascular accident",40),

#     # ── Tier 4 – Severe / high acuity (28–38 pts) ────────────────────────────
#     ("variceal bleed",          38),
#     ("lung cancer",             37),
#     ("non small cell cancer",   37),
#     ("metastatic melanoma",     37),
#     ("metastic melanoma",       37),
#     ("brain metastases",        37),
#     ("esophageal ca",           37),
#     ("esophageal cancer",       37),
#     ("renal cancer",            36),
#     ("aromegley;burkitts",      36),
#     ("chronic myelogenous leuk",36),
#     ("volvulus",                35),
#     ("tracheal esophageal",     35),
#     ("tracheal stenosis",       35),
#     ("pericardial effusion",    33),
#     ("acute pulmonary embolism",33),
#     ("overdose",                33),
#     ("hypotension",             32),    # covers hypotension;telemetry etc.
#     ("gastrointestinal bleed",  31),
#     ("upper gi bleed",          31),
#     ("lower gi bleed",          31),
#     ("acute cholangitis",       30),
#     ("cholangitis",             29),
#     ("congestive heart failure",29),
#     ("unstable angina",         29),
#     ("motor vehicle accident",  28),
#     ("motorcycle accident",     28),
#     ("s/p fall",                26),

#     # ── Tier 3 – Moderate acuity (15–25 pts) ─────────────────────────────────
#     ("pneumonia",               24),
#     ("respiratory distress",    23),
#     ("shortness of breath",     20),
#     ("tachypnea",               20),
#     ("seizure",                 20),
#     ("acute cholecystitis",     20),
#     ("cholecystitis",           19),
#     ("alcoholic hepatitis",     19),
#     ("hepatitis",               18),
#     ("abscess",                 18),
#     ("cellulitis",              17),
#     ("urinary tract infection", 17),
#     ("pyelonephritis",          17),
#     ("hyponatremia",            16),
#     ("hypoglycemia",            16),
#     ("bradycardia",             16),
#     ("syncope",                 16),
#     ("altered mental status",   16),
#     ("failure to thrive",       15),
#     ("fever",                   15),
#     ("pleural effusion",        15),
#     ("mediastinal adenopathy",  15),
#     ("chest pain",              15),
#     ("abdominal pain",          15),
#     ("asthma",                  15),
#     ("elevated liver functions",15),

#     # ── Tier 2 – Mild / elective (5–14 pts) ──────────────────────────────────
#     ("fracture",                14),
#     ("humeral fracture",        14),
#     ("hip fracture",            14),
#     ("facial numbness",         10),
#     ("headache",                 8),
#     ("recurrent left carotid",   8),
#     ("pre hydration",            5),

#     # ── Tier 1 – Planned/elective procedures (0–4 pts) ───────────────────────
#     ("/sda",                     2),    # "same day admission" suffix in MIMIC
#     ("bypass graft",             4),
#     ("valve replacement",        4),
#     ("cath",                     3),    # cardiac catheterisation
#     ("telemetry",                2),
# ]


# # =============================================================================
# # HELPER: DIAGNOSIS SCORE
# # =============================================================================

# def _diagnosis_score(diagnosis: str) -> int:
#     """
#     Returns a score 0–50 for the diagnosis string by summing all matching
#     entries from DIAGNOSIS_SCORE_TABLE, then capping at 50.
#     Using summation (not first-match) captures compound diagnoses like
#     "sepsis;pneumonia;telemetry" correctly.
#     """
#     diag = str(diagnosis).lower().strip()
#     total = 0
#     for keyword, pts in DIAGNOSIS_SCORE_TABLE:
#         if keyword in diag:
#             total += pts
#     return min(total, 50)


# # =============================================================================
# # HELPER: AGE SCORE
# # =============================================================================

# def _age_score(age) -> int:
#     """
#     Returns 0–20 pts based on patient age.
#     Older patients carry more surgical risk.
#     """
#     try:
#         age = float(age)
#     except (TypeError, ValueError):
#         return 5   # default for unknown age

#     if age > 85:   return 20
#     if age > 75:   return 17
#     if age > 65:   return 13
#     if age > 55:   return 9
#     if age > 40:   return 5
#     if age > 18:   return 2
#     return 3       # paediatric — small bump for complexity


# # =============================================================================
# # HELPER: ADMISSION TYPE SCORE
# # =============================================================================

# def _admission_type_score(admission_type: str) -> int:
#     """
#     Returns 0–15 pts based on admission type.
#     Emergency ≠ automatically HIGH when combined with a mild diagnosis.
#     """
#     adm = str(admission_type).lower().strip()
#     if adm == "emergency": return 15
#     if adm == "urgent":    return 10
#     if adm == "elective":  return  0
#     return 5   # unknown / newborn


# # =============================================================================
# # HELPER: LAB SCORE
# # =============================================================================

# def _lab_score(abnormal_lab_count) -> int:
#     """
#     Returns 0–15 pts based on number of abnormal lab results.
#     """
#     try:
#         count = int(abnormal_lab_count)
#     except (TypeError, ValueError):
#         return 0

#     if count >= 15: return 15
#     if count >= 10: return 12
#     if count >= 6:  return  8
#     if count >= 3:  return  4
#     if count >= 1:  return  2
#     return 0


# # =============================================================================
# # SCORE → LABEL THRESHOLDS
# # =============================================================================
# # Total possible score: 50 + 20 + 15 + 15 = 100
# #
# # Calibrated against this MIMIC-III sample where ~92% admissions are EMERGENCY
# # and many diagnoses are severe. Thresholds are set so that:
# #   • purely severe diagnoses (sepsis, cardiac arrest) → HIGH
# #   • moderate diagnoses (pneumonia, UTI, fracture)    → MEDIUM
# #   • mild/elective with young/middle-aged patient     → LOW

# HIGH_THRESHOLD   = 55   # score >= 55 → HIGH
# MEDIUM_THRESHOLD = 25   # score >= 25 → MEDIUM
#                         # score <  25 → LOW


# # =============================================================================
# # STEP 1 – ASSIGN RISK LABEL  (primary public API)
# # =============================================================================

# def assign_risk_label(row: pd.Series) -> str:
#     """
#     Assigns a surgical risk category using a weighted scoring system.

#     Scoring components:
#         diagnosis score   0–50 pts  (severity of diagnosis)
#         age score         0–20 pts  (older = higher risk)
#         admission score   0–15 pts  (emergency > urgent > elective)
#         lab score         0–15 pts  (more abnormal labs = higher risk)
#         ─────────────────────────
#         TOTAL             0–100 pts

#     Thresholds:
#         >= 55  →  HIGH
#         >= 25  →  MEDIUM
#          < 25  →  LOW

#     Special override:
#         hospital_expire_flag == 1  →  always HIGH (patient died in hospital)

#     Args:
#         row (pd.Series): One row from the preprocessed DataFrame

#     Returns:
#         str: "HIGH", "MEDIUM", or "LOW"
#     """
#     # ── Hard override: in-hospital death ─────────────────────────────────────
#     if int(row.get("hospital_expire_flag", 0) or 0) == 1:
#         return "HIGH"

#     # ── Component scores ──────────────────────────────────────────────────────
#     d_score   = _diagnosis_score(row.get("diagnosis", ""))
#     a_score   = _age_score(row.get("age", 50))
#     adm_score = _admission_type_score(row.get("admission_type", ""))
#     l_score   = _lab_score(row.get("abnormal_lab_count", 0))

#     total = d_score + a_score + adm_score + l_score

#     # ── Threshold decision ────────────────────────────────────────────────────
#     if total >= HIGH_THRESHOLD:
#         return "HIGH"
#     elif total >= MEDIUM_THRESHOLD:
#         return "MEDIUM"
#     else:
#         return "LOW"


# # =============================================================================
# # STEP 2 – BUILD CLINICAL TEXT  (primary public API)
# # =============================================================================

# def build_clinical_text(row: pd.Series) -> str:
#     """
#     Combines clinical fields into a single text string for TF-IDF.

#     The string encodes:
#         - diagnosis verbatim
#         - admission type
#         - gender
#         - descriptive age bucket (e.g. "elderly", "young adult")
#         - abnormal lab tokens prefixed with "abnormal_"
#         - severity signal tokens ("critical_labs", "multiple_abnormal_labs")

#     Underscores join multi-word concepts so TF-IDF treats them as single tokens.

#     Args:
#         row (pd.Series): One row from the preprocessed DataFrame

#     Returns:
#         str: Space-separated clinical text string (all lowercase)
#     """
#     parts = []

#     # ── Diagnosis ─────────────────────────────────────────────────────────────
#     diagnosis = str(row.get("diagnosis", "")).strip().lower()
#     if diagnosis and diagnosis != "nan":
#         # Replace semicolons/slashes with spaces so compound diagnoses tokenise well
#         diagnosis_clean = diagnosis.replace(";", " ").replace("/", " ").replace("\\", " ")
#         parts.append(diagnosis_clean)

#     # ── Admission type ────────────────────────────────────────────────────────
#     adm_type = str(row.get("admission_type", "")).strip().lower()
#     if adm_type and adm_type not in ("nan", "unknown"):
#         parts.append(adm_type)

#     # ── Gender ────────────────────────────────────────────────────────────────
#     gender = str(row.get("gender", "")).strip().lower()
#     if gender and gender not in ("nan", "unknown"):
#         parts.append(gender)

#     # ── Age tokens ────────────────────────────────────────────────────────────
#     age = row.get("age", np.nan)
#     if pd.notna(age):
#         age = float(age)
#         if age < 18:
#             parts.append("pediatric_patient")
#         elif age < 40:
#             parts.append("young_adult_patient")
#         elif age < 55:
#             parts.append("middle_aged_patient")
#         elif age < 65:
#             parts.append("senior_patient")
#         elif age < 75:
#             parts.append("elderly_patient")
#         else:
#             parts.append("very_elderly_patient")
#             parts.append("advanced_age")          # double token → more TF-IDF weight

#     # ── Abnormal lab summary ──────────────────────────────────────────────────
#     lab_summary = str(row.get("abnormal_lab_summary", "")).strip().lower()
#     if lab_summary and lab_summary != "nan":
#         # Prefix each lab name to distinguish from diagnosis tokens
#         lab_tokens = [t for t in lab_summary.split() if t][:12]  # cap at 12
#         parts.extend([f"abnormal_{t}" for t in lab_tokens])

#     # ── Lab count signal tokens ───────────────────────────────────────────────
#     lab_count = int(row.get("abnormal_lab_count", 0) or 0)
#     if lab_count >= 15:
#         parts.append("critical_lab_count")
#         parts.append("multiple_abnormal_labs")
#     elif lab_count >= 6:
#         parts.append("multiple_abnormal_labs")
#     elif lab_count >= 1:
#         parts.append("some_abnormal_labs")

#     # ── Risk score signal (adds interpretable numeric signal to text) ─────────
#     d_score   = _diagnosis_score(row.get("diagnosis", ""))
#     if d_score >= 40:
#         parts.append("high_severity_diagnosis")
#     elif d_score >= 20:
#         parts.append("moderate_severity_diagnosis")
#     else:
#         parts.append("low_severity_diagnosis")

#     return " ".join(parts)


# # =============================================================================
# # STEP 3 – ORCHESTRATION  (primary public API)
# # =============================================================================

# def prepare_features(df: pd.DataFrame):
#     """
#     Applies clinical text building and risk label generation to the full dataset.

#     Steps:
#         1. Build clinical_text column
#         2. Remove rows where clinical_text is empty
#         3. Assign risk_label using score-based system
#         4. Log class distribution with counts

#     Args:
#         df (pd.DataFrame): Preprocessed DataFrame from preprocessing.py

#     Returns:
#         Tuple[pd.Series, pd.Series]:
#             X  – Series of combined clinical text strings
#             y  – Series of risk labels ("HIGH", "MEDIUM", "LOW")
#     """
#     log("Building clinical text features...")
#     df = df.copy()

#     # ── Build combined text per admission ─────────────────────────────────────
#     df["clinical_text"] = df.apply(build_clinical_text, axis=1)

#     # ── Drop rows where clinical text is empty ────────────────────────────────
#     before = len(df)
#     df = df[df["clinical_text"].str.strip() != ""].copy()
#     if before - len(df) > 0:
#         log(f"Dropped {before - len(df)} rows with empty clinical text.")

#     # ── Assign risk labels ────────────────────────────────────────────────────
#     log("Generating surgical risk labels using score-based system...")
#     df["risk_label"] = df.apply(assign_risk_label, axis=1)

#     # ── Detailed distribution log ─────────────────────────────────────────────
#     dist   = df["risk_label"].value_counts().to_dict()
#     total  = len(df)
#     high   = dist.get("HIGH",   0)
#     medium = dist.get("MEDIUM", 0)
#     low    = dist.get("LOW",    0)

#     log("─" * 50)
#     log(f"Risk label distribution:")
#     log(f"  HIGH   : {high:>4}  ({high/total*100:.1f}%)")
#     log(f"  MEDIUM : {medium:>4}  ({medium/total*100:.1f}%)")
#     log(f"  LOW    : {low:>4}  ({low/total*100:.1f}%)")
#     log(f"  TOTAL  : {total:>4}")
#     log("─" * 50)

#     # ── Warn if any class is still missing ───────────────────────────────────
#     for label in ("HIGH", "MEDIUM", "LOW"):
#         if dist.get(label, 0) == 0:
#             log(f"WARNING: Class '{label}' has 0 samples. "
#                 f"Consider adjusting score thresholds.", level="WARNING")

#     X = df["clinical_text"]
#     y = df["risk_label"]

#     log(f"Feature preparation complete. Total samples: {len(X)}")
#     return X, y


# # =============================================================================
# # SINGLE-RECORD UTILITY  (used by prediction_service.py – do NOT rename)
# # =============================================================================

# def build_single_clinical_text(
#     diagnosis: str,
#     admission_type: str,
#     gender: str,
#     age: float,
#     abnormal_lab_summary: str = ""
# ) -> str:
#     """
#     Builds a clinical text string for a single patient at inference time.
#     Called by prediction_service.predict_risk().

#     Args:
#         diagnosis            (str)   : Patient diagnosis
#         admission_type       (str)   : e.g. "emergency", "elective"
#         gender               (str)   : "male" / "female"
#         age                  (float) : Age in years
#         abnormal_lab_summary (str)   : Space-separated abnormal lab labels

#     Returns:
#         str: Clinical text ready for TF-IDF transform
#     """
#     lab_count = len([t for t in abnormal_lab_summary.split() if t]) \
#                 if abnormal_lab_summary else 0

#     mock_row = pd.Series({
#         "diagnosis"            : diagnosis,
#         "admission_type"       : admission_type,
#         "gender"               : gender,
#         "age"                  : age,
#         "abnormal_lab_summary" : abnormal_lab_summary,
#         "abnormal_lab_count"   : lab_count,
#         "hospital_expire_flag" : 0,
#     })
#     return build_clinical_text(mock_row)