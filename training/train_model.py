# =============================================================================
# training/train_model.py
# SurgiMind – AI Surgical Decision Support Assistant
#
# PURPOSE:
#   End-to-end training script. Run once to:
#       1. Preprocess all datasets
#       2. Build features and risk labels
#       3. Train TF-IDF + RandomForest pipeline
#       4. Evaluate with accuracy, classification report, confusion matrix
#       5. Save model and vectoriser to models/
#
# USAGE:
#   python training/train_model.py
# =============================================================================

import os
import sys

# ── Ensure project root is on PYTHONPATH ─────────────────────────────────────
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import joblib
import numpy as np
import matplotlib
matplotlib.use("Agg")          # non-interactive backend (safe for servers)
import matplotlib.pyplot as plt

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble                import RandomForestClassifier
from sklearn.model_selection         import train_test_split
from sklearn.metrics                 import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay
)

from services.preprocessing      import preprocess_data
from services.feature_engineering import prepare_features
from utils.helpers                import get_model_path, log


# =============================================================================
# CONFIGURATION
# =============================================================================

TFIDF_CONFIG = dict(
    stop_words   = "english",
    max_features = 5000,
    ngram_range  = (1, 2),    # unigrams + bigrams for better medical phrase capture
)

RF_CONFIG = dict(
    n_estimators = 100,
    random_state = 42,
    n_jobs       = -1,        # use all CPU cores
    class_weight = "balanced" # handles class imbalance automatically
)

TEST_SIZE    = 0.20
RANDOM_STATE = 42


# =============================================================================
# TRAINING PIPELINE
# =============================================================================

def train():
    """
    Full training pipeline:
        preprocess → feature engineer → vectorise → train → evaluate → save
    """
    log("=" * 60)
    log("SurgiMind – Model Training Started")
    log("=" * 60)

    # ── STEP 1: Preprocess data ───────────────────────────────────────────────
    df = preprocess_data()

    if df.empty:
        log("Preprocessing returned empty DataFrame. Aborting.", level="ERROR")
        sys.exit(1)

    # ── STEP 2: Build features + labels ───────────────────────────────────────
    log("Building features and risk labels...")
    X, y = prepare_features(df)

    if len(X) == 0:
        log("No features generated. Aborting.", level="ERROR")
        sys.exit(1)

    log(f"Total labelled samples: {len(X)}")

    # ── STEP 3: Train / test split ────────────────────────────────────────────
    log(f"Splitting data: {int((1-TEST_SIZE)*100)}% train / {int(TEST_SIZE*100)}% test...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size    = TEST_SIZE,
        random_state = RANDOM_STATE,
        stratify     = y           # preserve class proportions
    )
    log(f"Train set: {len(X_train)} samples | Test set: {len(X_test)} samples")

    # ── STEP 4: TF-IDF Vectorisation ─────────────────────────────────────────
    log("Creating TF-IDF vectors...")
    vectorizer = TfidfVectorizer(**TFIDF_CONFIG)

    X_train_vec = vectorizer.fit_transform(X_train)   # fit on train ONLY
    X_test_vec  = vectorizer.transform(X_test)        # transform test

    log(f"TF-IDF vocabulary size: {len(vectorizer.vocabulary_)}")

    # ── STEP 5: Train model ───────────────────────────────────────────────────
    log("Training RandomForestClassifier...")
    model = RandomForestClassifier(**RF_CONFIG)
    model.fit(X_train_vec, y_train)
    log("Training complete.")

    # ── STEP 6: Evaluation ────────────────────────────────────────────────────
    log("=" * 60)
    log("Evaluating model...")

    y_pred = model.predict(X_test_vec)

    accuracy  = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    recall    = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1        = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    log(f"Accuracy  : {accuracy:.4f}  ({accuracy*100:.2f}%)")
    log(f"Precision : {precision:.4f}")
    log(f"Recall    : {recall:.4f}")
    log(f"F1-Score  : {f1:.4f}")

    print("\n── Classification Report ──────────────────────────────────────")
    print(classification_report(y_test, y_pred, zero_division=0))

    # ── Confusion matrix ──────────────────────────────────────────────────────
    log("Generating confusion matrix...")
    labels = sorted(model.classes_)
    cm     = confusion_matrix(y_test, y_pred, labels=labels)

    fig, ax = plt.subplots(figsize=(7, 5))
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=labels)
    disp.plot(ax=ax, colorbar=True, cmap="Blues")
    ax.set_title("SurgiMind – Confusion Matrix")
    plt.tight_layout()

    cm_path = get_model_path("confusion_matrix.png")
    plt.savefig(cm_path)
    plt.close()
    log(f"Confusion matrix saved to: {cm_path}")

    # ── STEP 7: Save model and vectoriser ─────────────────────────────────────
    log("Saving model and vectoriser...")

    model_path      = get_model_path("risk_model.pkl")
    vectorizer_path = get_model_path("tfidf_vectorizer.pkl")

    joblib.dump(model,      model_path)
    joblib.dump(vectorizer, vectorizer_path)

    log(f"Model saved to     : {model_path}")
    log(f"Vectoriser saved to: {vectorizer_path}")

    log("=" * 60)
    log("Training pipeline complete. Ready for predictions.")
    log("=" * 60)

    return model, vectorizer


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    try:
        train()
    except KeyboardInterrupt:
        log("Training interrupted by user.", level="WARNING")
    except Exception as e:
        log(f"Training failed: {e}", level="ERROR")
        raise
