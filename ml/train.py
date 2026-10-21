"""
Train and evaluate ML surrogate models for battery pack design.
Compares Gradient Boosting (HistGradientBoosting / XGBoost) vs MLP.
Computes MAE, RMSE, R2, Accuracy, F1, uncertainty estimates, and saves artifacts with joblib.
"""

import os
import sys
import json
import time
from typing import Dict, Any, List, Tuple
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Feature definitions
NUMERIC_FEATURES = [
    "series_cells",
    "parallel_strings",
    "charge_rate_c",
    "ambient_temp_c",
    "max_cell_temp_c",
    "min_usable_energy_wh",
    "max_charge_time_h",
    "max_pack_cost_inr",
    "bms_thermal_derating",
]

CATEGORICAL_FEATURES = [
    "cell_type",
    "bms_thermistor_position",
    "cooling_type",
]

REGRESSION_TARGETS = [
    "peak_cell_temp_c",
    "charge_time_h",
    "heat_at_charge_w",
    "effective_charge_rate_c",
    "usable_energy_wh",
    "pack_cost_inr",
    "mass_kg",
    "energy_density_wh_per_l",
]

CLASSIFICATION_TARGET = "meets_all_requirements"
CONSTRAINT_FAIL_TARGETS = [
    "fail_temperature",
    "fail_charge_time",
    "fail_cost",
    "fail_energy",
    "fail_charge_rate",
]

from ml.surrogate import SurrogateModelBundle, REGRESSION_TARGETS

def train_and_evaluate(
    data_path: str = "data/synthetic_dataset.csv",
    models_dir: str = "models",
    reports_dir: str = "reports",
) -> Dict[str, Any]:
    print(f"Loading dataset from {data_path}...")
    df = pd.read_csv(data_path)
    n = len(df)
    print(f"Dataset loaded: {n} samples.")

    # 80/10/10 train/val/test split
    train_idx = int(n * 0.8)
    val_idx = int(n * 0.9)

    df_train = df.iloc[:train_idx].copy()
    df_val = df.iloc[train_idx:val_idx].copy()
    df_test = df.iloc[val_idx:].copy()

    print(f"Split sizes: Train={len(df_train)}, Val={len(df_val)}, Test={len(df_test)}")

    # Preprocessing
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ]
    )
    X_train = preprocessor.fit_transform(df_train[NUMERIC_FEATURES + CATEGORICAL_FEATURES])
    X_val = preprocessor.transform(df_val[NUMERIC_FEATURES + CATEGORICAL_FEATURES])
    X_test = preprocessor.transform(df_test[NUMERIC_FEATURES + CATEGORICAL_FEATURES])

    # Model comparisons: Gradient Boosting vs MLP
    print("\n--- Comparing Regressors: Gradient Boosting vs MLP ---")
    regressor_comparison = {}
    best_regressors = {}
    quantile_models = {}
    uncertainties = {}

    for target in REGRESSION_TARGETS:
        y_train = df_train[target].values
        y_val = df_val[target].values
        y_test = df_test[target].values

        # 1. Gradient Boosting (HistGradientBoostingRegressor is extremely fast and robust)
        gbr = HistGradientBoostingRegressor(max_iter=150, min_samples_leaf=20, random_state=42)
        t0 = time.time()
        gbr.fit(X_train, y_train)
        t_gbr = time.time() - t0
        gbr_val_pred = gbr.predict(X_val)
        gbr_mae = mean_absolute_error(y_val, gbr_val_pred)
        gbr_rmse = float(np.sqrt(mean_squared_error(y_val, gbr_val_pred)))
        gbr_r2 = r2_score(y_val, gbr_val_pred)

        # 2. MLP Regressor
        mlp = MLPRegressor(hidden_layer_sizes=(64, 32), max_iter=100, random_state=42, early_stopping=True)
        t0 = time.time()
        mlp.fit(X_train, y_train)
        t_mlp = time.time() - t0
        mlp_val_pred = mlp.predict(X_val)
        mlp_mae = mean_absolute_error(y_val, mlp_val_pred)
        mlp_rmse = float(np.sqrt(mean_squared_error(y_val, mlp_val_pred)))
        mlp_r2 = r2_score(y_val, mlp_val_pred)

        regressor_comparison[target] = {
            "GBR": {"MAE": round(gbr_mae, 4), "RMSE": round(gbr_rmse, 4), "R2": round(gbr_r2, 4), "fit_time_s": round(t_gbr, 2)},
            "MLP": {"MAE": round(mlp_mae, 4), "RMSE": round(mlp_rmse, 4), "R2": round(mlp_r2, 4), "fit_time_s": round(t_mlp, 2)},
        }
        print(f"Target '{target}': GBR R2={gbr_r2:.4f} (RMSE={gbr_rmse:.3f}) | MLP R2={mlp_r2:.4f} (RMSE={mlp_rmse:.3f})")

        # Select best model based on val RMSE
        chosen_model = gbr if gbr_rmse <= mlp_rmse else mlp
        chosen_type = "GBR" if chosen_model is gbr else "MLP"
        best_regressors[target] = chosen_model

        # Train Quantile Regressors for key targets (peak_temp, charge_time, heat) for uncertainty bounds
        if target in ["peak_cell_temp_c", "charge_time_h", "heat_at_charge_w"]:
            q10_model = HistGradientBoostingRegressor(loss="quantile", quantile=0.10, max_iter=100, random_state=42)
            q90_model = HistGradientBoostingRegressor(loss="quantile", quantile=0.90, max_iter=100, random_state=42)
            q10_model.fit(X_train, y_train)
            q90_model.fit(X_train, y_train)
            quantile_models[target] = {"q10": q10_model, "q90": q90_model}

        # Calculate residual std error on validation set
        val_resids = y_val - chosen_model.predict(X_val)
        uncertainties[target] = float(np.std(val_resids))

    # Evaluate best regressors on Test Set
    test_metrics_regression = {}
    test_predictions = {}
    for target in REGRESSION_TARGETS:
        y_test = df_test[target].values
        model = best_regressors[target]
        y_pred = model.predict(X_test)
        test_predictions[target] = y_pred
        test_metrics_regression[target] = {
            "MAE": float(mean_absolute_error(y_test, y_pred)),
            "RMSE": float(np.sqrt(mean_squared_error(y_test, y_pred))),
            "R2": float(r2_score(y_test, y_pred)),
            "residual_std": float(np.std(y_test - y_pred)),
        }

    # Classifier Comparison
    print("\n--- Comparing Classifiers: Gradient Boosting vs MLP ---")
    y_clf_train = df_train[CLASSIFICATION_TARGET].values
    y_clf_val = df_val[CLASSIFICATION_TARGET].values
    y_clf_test = df_test[CLASSIFICATION_TARGET].values

    gbc = HistGradientBoostingClassifier(max_iter=150, min_samples_leaf=20, random_state=42)
    gbc.fit(X_train, y_clf_train)
    gbc_val_pred = gbc.predict(X_val)
    gbc_acc = accuracy_score(y_clf_val, gbc_val_pred)
    gbc_f1 = f1_score(y_clf_val, gbc_val_pred, zero_division=0)

    mlp_clf = MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=100, random_state=42, early_stopping=True)
    mlp_clf.fit(X_train, y_clf_train)
    mlp_val_pred = mlp_clf.predict(X_val)
    mlp_acc = accuracy_score(y_clf_val, mlp_val_pred)
    mlp_f1 = f1_score(y_clf_val, mlp_val_pred, zero_division=0)

    classifier_comparison = {
        "GBR/GBC": {"accuracy": round(gbc_acc, 4), "f1": round(gbc_f1, 4)},
        "MLP": {"accuracy": round(mlp_acc, 4), "f1": round(mlp_f1, 4)},
    }
    print(f"Meets Requirements: GBC Acc={gbc_acc:.4f}, F1={gbc_f1:.4f} | MLP Acc={mlp_acc:.4f}, F1={mlp_f1:.4f}")

    best_classifier = gbc if gbc_f1 >= mlp_f1 else mlp_clf

    # Test evaluation for classifier
    clf_test_pred = best_classifier.predict(X_test)
    test_metrics_classification = {
        "accuracy": float(accuracy_score(y_clf_test, clf_test_pred)),
        "precision": float(precision_score(y_clf_test, clf_test_pred, zero_division=0)),
        "recall": float(recall_score(y_clf_test, clf_test_pred, zero_division=0)),
        "f1": float(f1_score(y_clf_test, clf_test_pred, zero_division=0)),
    }

    # Train individual constraint classifiers
    constraint_classifiers = {}
    constraint_metrics = {}
    for c_target in CONSTRAINT_FAIL_TARGETS:
        c_clf = HistGradientBoostingClassifier(max_iter=100, random_state=42)
        c_clf.fit(X_train, df_train[c_target].values)
        c_test_pred = c_clf.predict(X_test)
        constraint_classifiers[c_target] = c_clf
        constraint_metrics[c_target] = {
            "accuracy": float(accuracy_score(df_test[c_target].values, c_test_pred)),
            "f1": float(f1_score(df_test[c_target].values, c_test_pred, zero_division=0)),
        }

    # Save Bundle
    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)

    metadata = {
        "date_trained": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_samples": n,
        "features": {"numeric": NUMERIC_FEATURES, "categorical": CATEGORICAL_FEATURES},
        "regression_targets": REGRESSION_TARGETS,
        "classification_target": CLASSIFICATION_TARGET,
        "test_metrics_regression": test_metrics_regression,
        "test_metrics_classification": test_metrics_classification,
        "regressor_comparison": regressor_comparison,
        "classifier_comparison": classifier_comparison,
    }

    bundle = SurrogateModelBundle(
        preprocessor=preprocessor,
        regressors=best_regressors,
        uncertainties=uncertainties,
        quantile_models=quantile_models,
        classifier=best_classifier,
        constraint_classifiers=constraint_classifiers,
        metadata=metadata,
    )

    model_path = os.path.join(models_dir, "battery_pack_model.joblib")
    joblib.dump(bundle, model_path)
    print(f"\nModel artifact saved to {model_path} ({os.path.getsize(model_path) / 1024 / 1024:.2f} MB)")

    # Save evaluation report JSON
    metrics_path = os.path.join(reports_dir, "evaluation_metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metrics saved to {metrics_path}")

    # Generate predicted vs actual plot for regression targets
    plot_path = os.path.join(reports_dir, "predicted_vs_actual.png")
    fig, axes = plt.subplots(2, 4, figsize=(18, 9))
    axes = axes.flatten()

    target_labels = {
        "peak_cell_temp_c": "Peak Cell Temp (°C)",
        "charge_time_h": "Charge Time (h)",
        "heat_at_charge_w": "Heat at Charge (W)",
        "effective_charge_rate_c": "Effective C-Rate (C)",
        "usable_energy_wh": "Usable Energy (Wh)",
        "pack_cost_inr": "Pack Cost (₹)",
        "mass_kg": "Mass (kg)",
        "energy_density_wh_per_l": "Energy Density (Wh/L)",
    }

    # Subsample 1500 points for clear visualization
    sample_indices = np.random.choice(len(df_test), size=min(1500, len(df_test)), replace=False)
    for idx, target in enumerate(REGRESSION_TARGETS):
        ax = axes[idx]
        y_true = df_test[target].values[sample_indices]
        y_pred = test_predictions[target][sample_indices]
        r2 = test_metrics_regression[target]["R2"]
        rmse = test_metrics_regression[target]["RMSE"]

        ax.scatter(y_true, y_pred, alpha=0.35, edgecolors="none", color="#2a6fa8", s=18)
        # 1:1 line
        min_val = min(np.min(y_true), np.min(y_pred))
        max_val = max(np.max(y_true), np.max(y_pred))
        ax.plot([min_val, max_val], [min_val, max_val], "r--", linewidth=1.5, label="Ideal 1:1")
        ax.set_title(f"{target_labels.get(target, target)}\n$R^2$={r2:.4f}, RMSE={rmse:.3f}", fontsize=11, fontweight="bold")
        ax.set_xlabel("Actual (Physics Simulator)", fontsize=9)
        ax.set_ylabel("Predicted (ML Surrogate)", fontsize=9)
        ax.grid(True, linestyle=":", alpha=0.5)

    plt.tight_layout()
    plt.savefig(plot_path, dpi=200)
    plt.close()
    print(f"Predicted-vs-actual plot saved to {plot_path}")

    # Generate Markdown Report
    report_md_path = os.path.join(reports_dir, "evaluation_report.md")
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write("# Battery Pack ML Surrogate Model Evaluation Report\n\n")
        f.write(f"- **Trained On**: {metadata['date_trained']}\n")
        f.write(f"- **Total Dataset Samples**: {n:,}\n")
        f.write(f"- **Train/Val/Test Split**: 80% / 10% / 10% ({len(df_train):,} / {len(df_val):,} / {len(df_test):,})\n\n")

        f.write("## 1. Regression Targets Evaluation (Test Set)\n\n")
        f.write("| Target | MAE | RMSE | $R^2$ Score | Residual Std (±1σ) |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for target in REGRESSION_TARGETS:
            m = test_metrics_regression[target]
            lbl = target_labels.get(target, target)
            f.write(f"| **{lbl}** | {m['MAE']:.4f} | {m['RMSE']:.4f} | **{m['R2']:.4f}** | ±{m['residual_std']:.4f} |\n")

        f.write("\n## 2. Model Comparison: Gradient Boosting vs MLP (Validation Set)\n\n")
        f.write("| Target | GBR RMSE | GBR $R^2$ | MLP RMSE | MLP $R^2$ | Best Selected |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for target, comp in regressor_comparison.items():
            g = comp["GBR"]
            m = comp["MLP"]
            best = "HistGradientBoosting" if g["RMSE"] <= m["RMSE"] else "MLP"
            f.write(f"| {target} | {g['RMSE']:.4f} | {g['R2']:.4f} | {m['RMSE']:.4f} | {m['R2']:.4f} | **{best}** |\n")

        f.write("\n## 3. Classification Evaluation (Meets All Requirements)\n\n")
        f.write("| Metric | Score |\n")
        f.write("| :--- | :--- |\n")
        for k, v in test_metrics_classification.items():
            f.write(f"| **{k.capitalize()}** | {v:.4f} ({v*100:.2f}%) |\n")

        f.write("\n## 4. Constraint Classifiers (Test Set)\n\n")
        f.write("| Constraint | Accuracy | F1 Score |\n")
        f.write("| :--- | :--- | :--- |\n")
        for c, m in constraint_metrics.items():
            f.write(f"| {c} | {m['accuracy']*100:.2f}% | {m['f1']:.4f} |\n")

        f.write("\n## 5. Predicted vs Actual Visual Plot\n\n")
        f.write("![Predicted vs Actual](predicted_vs_actual.png)\n")

    print(f"Evaluation report written to {report_md_path}")
    return metadata

if __name__ == "__main__":
    train_and_evaluate()
