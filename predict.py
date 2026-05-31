# =============================================================================
# predict.py
# SurgiMind – AI Surgical Decision Support Assistant
#
# PURPOSE:
#   Standalone prediction script. Demonstrates how to call predict_risk()
#   with sample patient inputs and display the structured output.
#
# USAGE:
#   python predict.py
#
# PREREQUISITES:
#   python training/train_model.py   (must be run first)
# =============================================================================

import os
import sys

# ── Ensure project root is on PYTHONPATH ─────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from services.prediction_service import predict_risk
from utils.helpers               import log, pretty_print_prediction


# =============================================================================
# SAMPLE PATIENTS
# Each dict maps to the predict_risk() argument signature.
# =============================================================================

SAMPLE_PATIENTS = [
    {
        "label"        : "Patient A – High Risk (Sepsis, elderly)",
        "diagnosis"    : "sepsis",
        "admission_type": "emergency",
        "gender"       : "male",
        "age"          : 74,
        "abnormal_lab_summary": "glucose creatinine lactate"
    },
    {
        "label"        : "Patient B – Medium Risk (Diabetes + Hypertension)",
        "diagnosis"    : "diabetes mellitus with hypertension",
        "admission_type": "urgent",
        "gender"       : "female",
        "age"          : 55,
        "abnormal_lab_summary": ""
    },
    {
        "label"        : "Patient C – Low Risk (Routine elective)",
        "diagnosis"    : "elective knee replacement",
        "admission_type": "elective",
        "gender"       : "male",
        "age"          : 42,
        "abnormal_lab_summary": ""
    },
    {
        "label"        : "Patient D – High Risk (Cardiac arrest)",
        "diagnosis"    : "cardiac arrest",
        "admission_type": "emergency",
        "gender"       : "female",
        "age"          : 68,
        "abnormal_lab_summary": "troponin sodium potassium"
    },
    {
        "label"        : "Patient E – Medium Risk (Pneumonia)",
        "diagnosis"    : "pneumonia",
        "admission_type": "emergency",
        "gender"       : "male",
        "age"          : 61,
        "abnormal_lab_summary": "wbc"
    },
]


# =============================================================================
# MAIN
# =============================================================================

def main():
    log("=" * 60)
    log("SurgiMind – Prediction Demo")
    log("=" * 60)

    for i, patient in enumerate(SAMPLE_PATIENTS, start=1):
        label = patient.pop("label")   # remove non-API field
        print(f"\n{'─' * 60}")
        print(f"  Test {i}: {label}")
        print(f"{'─' * 60}")

        try:
            result = predict_risk(**patient)
            pretty_print_prediction(result)

        except FileNotFoundError as e:
            print(f"\n[ERROR] {e}")
            print("  → Run `python training/train_model.py` first.\n")
            sys.exit(1)

        except ValueError as e:
            print(f"\n[INPUT ERROR] {e}\n")

        except Exception as e:
            print(f"\n[UNEXPECTED ERROR] {e}\n")

    log("All predictions complete.")


if __name__ == "__main__":
    main()
