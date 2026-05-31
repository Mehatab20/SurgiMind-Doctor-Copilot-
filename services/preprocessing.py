# =============================================================================
# services/preprocessing.py
# SurgiMind – AI Surgical Decision Support Assistant
#
# PURPOSE:
#   Loads, cleans, and merges all raw MIMIC-III style CSV datasets into a
#   single analysis-ready DataFrame.
#
# DATASETS USED:
#   - ADMISSIONS.csv        : Admission records (diagnosis, type, dates)
#   - PATIENTS.csv          : Patient demographics (DOB, gender)
#   - LABEVENTS.csv         : Lab test results per patient/admission
#   - D_LABITEMS.csv        : Lab item label dictionary
#   - structured_medical_records.csv : Free-text clinical notes
#
# OUTPUT:
#   A merged pandas DataFrame with cleaned columns ready for feature engineering.
# =============================================================================

import os
import sys
import pandas as pd
import numpy as np

# Make sure imports work regardless of CWD
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.helpers import get_dataset_path, log


# =============================================================================
# INDIVIDUAL LOADERS
# =============================================================================

def load_admissions() -> pd.DataFrame:
    """
    Loads ADMISSIONS.csv.
    Keeps columns relevant for surgical risk:
        subject_id, hadm_id, admittime, admission_type, diagnosis
    Cleans text and parses dates.
    """
    path = get_dataset_path("ADMISSIONS.csv")
    log(f"Loading admissions from: {path}")

    df = pd.read_csv(path, low_memory=False)

    # ── Keep only relevant columns ──────────────────────────────────────────
    cols = ["subject_id", "hadm_id", "admittime", "admission_type",
            "diagnosis", "hospital_expire_flag"]
    df = df[[c for c in cols if c in df.columns]].copy()

    # ── Parse admission date ─────────────────────────────────────────────────
    if "admittime" in df.columns:
        df["admittime"] = pd.to_datetime(df["admittime"], errors="coerce")

    # ── Normalise text columns to lowercase, strip whitespace ────────────────
    for col in ["admission_type", "diagnosis"]:
        if col in df.columns:
            df[col] = df[col].fillna("unknown").str.lower().str.strip()

    # ── Drop duplicates ──────────────────────────────────────────────────────
    df.drop_duplicates(subset=["subject_id", "hadm_id"], inplace=True)

    log(f"Admissions loaded: {len(df)} records")
    return df


def load_patients() -> pd.DataFrame:
    """
    Loads PATIENTS.csv.
    Keeps subject_id, gender, dob, expire_flag.
    """
    path = get_dataset_path("PATIENTS.csv")
    log(f"Loading patients from: {path}")

    df = pd.read_csv(path, low_memory=False)

    cols = ["subject_id", "gender", "dob", "expire_flag"]
    df = df[[c for c in cols if c in df.columns]].copy()

    # ── Parse date of birth ──────────────────────────────────────────────────
    if "dob" in df.columns:
        df["dob"] = pd.to_datetime(df["dob"], errors="coerce")

    # ── Normalise gender ─────────────────────────────────────────────────────
    if "gender" in df.columns:
        df["gender"] = df["gender"].fillna("unknown").str.lower().str.strip()

    df.drop_duplicates(subset=["subject_id"], inplace=True)

    log(f"Patients loaded: {len(df)} records")
    return df


def load_lab_items() -> pd.DataFrame:
    """
    Loads D_LABITEMS.csv (the lab item label dictionary).
    Returns itemid → label mapping.
    """
    path = get_dataset_path("D_LABITEMS.csv")
    log(f"Loading lab item dictionary from: {path}")

    df = pd.read_csv(path, low_memory=False)

    cols = ["itemid", "label", "category"]
    df = df[[c for c in cols if c in df.columns]].copy()

    if "label" in df.columns:
        df["label"] = df["label"].str.lower().str.strip()

    log(f"Lab items dictionary loaded: {len(df)} items")
    return df


def load_lab_events(lab_items: pd.DataFrame) -> pd.DataFrame:
    """
    Loads LABEVENTS.csv and joins with lab item labels.
    Summarises per (subject_id, hadm_id): count of abnormal flags.

    Args:
        lab_items (pd.DataFrame): Output of load_lab_items()

    Returns:
        pd.DataFrame with columns [subject_id, hadm_id, abnormal_lab_count,
                                    abnormal_lab_summary]
    """
    path = get_dataset_path("LABEVENTS.csv")
    log(f"Loading lab events from: {path}")

    # ── Read only needed columns to save memory ──────────────────────────────
    usecols = ["subject_id", "hadm_id", "itemid", "flag"]
    df = pd.read_csv(path, usecols=usecols, low_memory=False)

    # ── Keep only rows where hadm_id is present ──────────────────────────────
    df = df[df["hadm_id"].notna()].copy()
    df["hadm_id"] = df["hadm_id"].astype(int)

    # ── Normalise flag ───────────────────────────────────────────────────────
    df["flag"] = df["flag"].fillna("normal").str.lower().str.strip()

    # ── Join with lab item labels ─────────────────────────────────────────────
    df = df.merge(lab_items[["itemid", "label"]], on="itemid", how="left")
    df["label"] = df["label"].fillna("unknown test")

    # ── Flag as abnormal if flag column contains 'abnormal' ──────────────────
    df["is_abnormal"] = df["flag"].str.contains("abnormal", na=False)

    # ── Summarise: count of abnormal tests per admission ─────────────────────
    abn = (
        df[df["is_abnormal"]]
        .groupby(["subject_id", "hadm_id"])["label"]
        .apply(lambda x: " ".join(x.unique()))
        .reset_index()
        .rename(columns={"label": "abnormal_lab_summary"})
    )

    count = (
        df[df["is_abnormal"]]
        .groupby(["subject_id", "hadm_id"])
        .size()
        .reset_index(name="abnormal_lab_count")
    )

    result = abn.merge(count, on=["subject_id", "hadm_id"], how="outer")
    result["abnormal_lab_summary"] = result["abnormal_lab_summary"].fillna("")
    result["abnormal_lab_count"] = result["abnormal_lab_count"].fillna(0).astype(int)

    log(f"Lab events summarised: {len(result)} admission-level records")
    return result


# =============================================================================
# AGE COMPUTATION
# =============================================================================

def compute_age(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds an 'age' column based on dob and admittime.
    Removes rows where age is outside a valid range (0–120).

    Args:
        df (pd.DataFrame): Merged admissions + patients DataFrame

    Returns:
        pd.DataFrame with 'age' column added, invalid rows removed
    """
    log("Computing patient age at admission...")

    if "admittime" not in df.columns or "dob" not in df.columns:
        log("Missing admittime or dob – age will be set to NaN", level="WARNING")
        df["age"] = np.nan
        return df

    df["age"] = (
        (df["admittime"] - df["dob"]).dt.days / 365.25
    ).round(1)

    # MIMIC-III de-identifies patients >89 by shifting DOB far back.
    # Cap those ages at 90 rather than dropping them.
    df.loc[df["age"] > 120, "age"] = 90.0

    # Remove clearly invalid (negative ages)
    before = len(df)
    df = df[df["age"] >= 0].copy()
    log(f"Removed {before - len(df)} records with invalid age. Remaining: {len(df)}")

    return df


# =============================================================================
# MAIN PREPROCESSING ENTRY POINT
# =============================================================================

def preprocess_data() -> pd.DataFrame:
    """
    Master preprocessing function.
    Loads, cleans, and merges all datasets into a single DataFrame.

    Returns:
        pd.DataFrame: Cleaned, merged dataset ready for feature engineering
    """
    log("=" * 60)
    log("Starting data preprocessing pipeline...")
    log("=" * 60)

    # ── 1. Load each dataset ─────────────────────────────────────────────────
    admissions = load_admissions()
    patients   = load_patients()
    lab_items  = load_lab_items()
    lab_events = load_lab_events(lab_items)

    # ── 2. Merge admissions + patients on subject_id ─────────────────────────
    log("Merging admissions and patients...")
    df = admissions.merge(patients, on="subject_id", how="left")

    # ── 3. Compute age ───────────────────────────────────────────────────────
    df = compute_age(df)

    # ── 4. Merge lab event summaries ─────────────────────────────────────────
    log("Merging lab event summaries...")
    df = df.merge(lab_events, on=["subject_id", "hadm_id"], how="left")
    df["abnormal_lab_summary"] = df["abnormal_lab_summary"].fillna("")
    df["abnormal_lab_count"]   = df["abnormal_lab_count"].fillna(0).astype(int)

    # ── 5. Drop rows missing critical columns ────────────────────────────────
    critical_cols = ["subject_id", "hadm_id", "diagnosis"]
    before = len(df)
    df.dropna(subset=critical_cols, inplace=True)
    log(f"Dropped {before - len(df)} rows with missing critical fields.")

    # ── 6. Final shape report ────────────────────────────────────────────────
    log(f"Preprocessing complete. Final dataset shape: {df.shape}")
    log("=" * 60)

    return df
