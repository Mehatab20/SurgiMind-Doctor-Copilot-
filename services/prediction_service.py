# =============================================================================
# services/prediction_service.py
# SurgiMind – AI Surgical Decision Support Assistant
#
# PURPOSE:
#   Exposes a single reusable function predict_risk() that:
#       1. Accepts clinical patient inputs
#       2. Builds the clinical text string
#       3. Transforms it with the saved TF-IDF vectoriser
#       4. Predicts surgical risk with the saved RandomForest model
#       5. Returns a structured JSON-friendly dictionary
#
# FLASK INTEGRATION EXAMPLE:
#   from services.prediction_service import predict_risk
#   result = predict_risk("sepsis", "emergency", "male", 72)
#   return jsonify(result)
# =============================================================================

import os
import sys
import joblib
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.helpers import get_model_path, log, validate_inputs
from services.feature_engineering import build_single_clinical_text

# =============================================================================
# MODEL PATHS
# =============================================================================

MODEL_PATH     = get_model_path("risk_model.pkl")
VECTORIZER_PATH = get_model_path("tfidf_vectorizer.pkl")


# =============================================================================
# CONCERN DETECTOR
# =============================================================================

# Maps keywords found in the clinical text to human-readable concern labels.
# These are surfaced in the prediction output to explain the risk rating.
CONCERN_MAP = {
    "sepsis"           : "Sepsis",
    "septic"           : "Sepsis",
    "cardiac arrest"   : "Cardiac Arrest",
    "heart failure"    : "Heart Failure",
    "stroke"           : "Stroke",
    "renal failure"    : "Renal Failure",
    "kidney failure"   : "Kidney Failure",
    "cancer"           : "Cancer",
    "carcinoma"        : "Cancer / Carcinoma",
    "shock"            : "Haemodynamic Shock",
    "hepatic failure"  : "Hepatic Failure",
    "liver failure"    : "Liver Failure",
    "respiratory failure": "Respiratory Failure",
    "elderly"          : "Advanced Age (>70)",
    "advanced age"     : "Advanced Age (>70)",
    "multiple abnormal labs": "Multiple Abnormal Lab Results",
    "diabetes"         : "Diabetes",
    "hypertension"     : "Hypertension",
    "pneumonia"        : "Pneumonia",
    "fracture"         : "Fracture",
    "infection"        : "Infection",
    "trauma"           : "Trauma",
    "hemorrhage"       : "Haemorrhage / Bleeding",
    "haemorrhage"      : "Haemorrhage / Bleeding",
    "pancreatitis"     : "Pancreatitis",
    "aneurysm"         : "Aortic Aneurysm",
    "myocardial"       : "Myocardial Infarction (Heart Attack)",
    "pulmonary embolism": "Pulmonary Embolism",
}


def detect_concerns(clinical_text: str) -> list:
    """
    Scans the clinical text for known high/medium risk keywords
    and returns a list of human-readable concern strings.

    Args:
        clinical_text (str): Combined clinical text string

    Returns:
        list[str]: Detected clinical concerns (may be empty)
    """
    found = []
    text_lower = clinical_text.lower()

    for keyword, label in CONCERN_MAP.items():
        if keyword in text_lower and label not in found:
            found.append(label)

    return found


# =============================================================================
# MODEL LOADER (singleton pattern – loads once per process)
# =============================================================================

_model      = None
_vectorizer = None


def load_model():
    """
    Loads the trained RandomForest model and TF-IDF vectoriser from disk.
    Uses a simple module-level cache so files are read only once per process.

    Raises:
        FileNotFoundError: If model or vectoriser files are missing
    """
    global _model, _vectorizer

    if _model is not None and _vectorizer is not None:
        return  # already loaded

    # ── Load model ────────────────────────────────────────────────────────────
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Model file not found at: {MODEL_PATH}\n"
            "Run: python training/train_model.py"
        )

    # ── Load vectoriser ───────────────────────────────────────────────────────
    if not os.path.exists(VECTORIZER_PATH):
        raise FileNotFoundError(
            f"Vectoriser file not found at: {VECTORIZER_PATH}\n"
            "Run: python training/train_model.py"
        )

    log("Loading trained model and vectoriser...")
    _model      = joblib.load(MODEL_PATH)
    _vectorizer = joblib.load(VECTORIZER_PATH)
    log("Model and vectoriser loaded successfully.")


# =============================================================================
# MAIN PREDICTION FUNCTION
# =============================================================================

def predict_risk(
    diagnosis: str,
    admission_type: str,
    gender: str,
    age,
    abnormal_lab_summary: str = ""
) -> dict:
    """
    Predicts surgical risk for a single patient.

    Args:
        diagnosis            (str)  : Patient diagnosis text
                                      e.g. "sepsis", "diabetes mellitus"
        admission_type       (str)  : Admission type
                                      e.g. "emergency", "elective", "urgent"
        gender               (str)  : Patient gender ("male" / "female" / "m" / "f")
        age                  (int/float): Patient age in years
        abnormal_lab_summary (str)  : Optional space-separated abnormal lab labels
                                      e.g. "glucose creatinine lactate"

    Returns:
        dict: {
            "risk_level"       : "HIGH" | "MEDIUM" | "LOW",
            "confidence"       : "92%",
            "possible_concerns": ["Sepsis", "Advanced Age (>70)"],
            "clinical_text"    : "sepsis emergency male elderly advanced age"
        }

    Raises:
        ValueError       : On invalid inputs
        FileNotFoundError: If model files are missing
        RuntimeError     : On unexpected prediction failure
    """
    try:
        # ── 1. Validate inputs ────────────────────────────────────────────────
        validate_inputs(diagnosis, admission_type, gender, age)

        # ── 2. Ensure model is loaded ─────────────────────────────────────────
        load_model()

        # ── 3. Build clinical text ────────────────────────────────────────────
        clinical_text = build_single_clinical_text(
            diagnosis            = str(diagnosis).strip().lower(),
            admission_type       = str(admission_type).strip().lower(),
            gender               = str(gender).strip().lower(),
            age                  = float(age),
            abnormal_lab_summary = str(abnormal_lab_summary).strip().lower()
        )

        log(f"Clinical text built: '{clinical_text}'")

        # ── 4. Vectorise ──────────────────────────────────────────────────────
        X_vec = _vectorizer.transform([clinical_text])

        # ── 5. Predict class and probability ─────────────────────────────────
        predicted_class = _model.predict(X_vec)[0]            # "HIGH" etc.
        probabilities   = _model.predict_proba(X_vec)[0]      # array of probs

        # Map class index to label for confidence score
        class_labels    = list(_model.classes_)
        class_index     = class_labels.index(predicted_class)
        confidence_pct  = round(float(probabilities[class_index]) * 100, 1)

        # ── 6. Detect possible concerns ───────────────────────────────────────
        concerns = detect_concerns(clinical_text)
        if not concerns:
            concerns = [f"{predicted_class.title()} risk admission"]

        # ── 7. Build structured output ────────────────────────────────────────
        result = {
            "risk_level"       : predicted_class,
            "confidence"       : f"{confidence_pct}%",
            "possible_concerns": concerns,
            "clinical_text"    : clinical_text,   # useful for debugging / audit
        }

        log(f"Prediction completed: {result['risk_level']} ({result['confidence']})")
        return result

    except (ValueError, FileNotFoundError):
        raise   # re-raise input / file errors as-is

    except Exception as e:
        raise RuntimeError(f"Unexpected error during prediction: {e}") from e
