# =============================================================================
# utils/helpers.py
# SurgiMind – AI Surgical Decision Support Assistant
#
# PURPOSE:
#   Shared utility functions used across the pipeline.
#   Includes path resolution, logging helpers, and output formatters.
# =============================================================================

import os
import json
from datetime import datetime


# =============================================================================
# PATH HELPERS
# =============================================================================

def get_project_root() -> str:
    """
    Returns the absolute path to the SurgiMind project root.
    Resolves relative to this file's location so it works from any CWD.
    """
    # utils/ is one level below project root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def get_dataset_path(filename: str) -> str:
    """
    Returns the full path to a file inside the dataset/ folder.

    Args:
        filename (str): e.g. "ADMISSIONS.csv"

    Returns:
        str: Full absolute path
    """
    return os.path.join(get_project_root(), "dataset", filename)


def get_model_path(filename: str) -> str:
    """
    Returns the full path to a file inside the models/ folder.

    Args:
        filename (str): e.g. "risk_model.pkl"

    Returns:
        str: Full absolute path
    """
    models_dir = os.path.join(get_project_root(), "models")
    os.makedirs(models_dir, exist_ok=True)  # create if missing
    return os.path.join(models_dir, filename)


# =============================================================================
# LOGGING HELPERS
# =============================================================================

def log(message: str, level: str = "INFO") -> None:
    """
    Prints a timestamped log message to the console.

    Args:
        message (str): The message to print
        level (str): Log level label – INFO, WARNING, ERROR, SUCCESS
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


# =============================================================================
# OUTPUT HELPERS
# =============================================================================

def pretty_print_prediction(result: dict) -> None:
    """
    Pretty-prints the prediction result dictionary to console.

    Args:
        result (dict): Prediction output from predict_risk()
    """
    print("\n" + "=" * 50)
    print("       SURGIMIND PREDICTION RESULT")
    print("=" * 50)
    print(json.dumps(result, indent=4))
    print("=" * 50 + "\n")


def validate_inputs(diagnosis: str, admission_type: str, gender: str, age) -> bool:
    """
    Validates that prediction inputs are non-empty and age is reasonable.

    Args:
        diagnosis      (str): Patient diagnosis text
        admission_type (str): Type of admission
        gender         (str): Patient gender
        age            (int/float): Patient age

    Returns:
        bool: True if all inputs are valid, raises ValueError otherwise
    """
    if not diagnosis or not str(diagnosis).strip():
        raise ValueError("Diagnosis cannot be empty.")

    if not admission_type or not str(admission_type).strip():
        raise ValueError("Admission type cannot be empty.")

    if not gender or not str(gender).strip():
        raise ValueError("Gender cannot be empty.")

    try:
        age_val = float(age)
    except (TypeError, ValueError):
        raise ValueError(f"Age must be a number. Got: {age}")

    if age_val < 0 or age_val > 120:
        raise ValueError(f"Age must be between 0 and 120. Got: {age_val}")

    return True
