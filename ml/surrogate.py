"""
Surrogate Model Bundle Definition
Encapsulates preprocessors, regressors, classifiers, and uncertainty estimators.
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer

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

class SurrogateModelBundle:
    """
    Wraps the trained preprocessor, regressors, classifiers, and uncertainty estimators.
    """
    def __init__(
        self,
        preprocessor: ColumnTransformer,
        regressors: Dict[str, Any],
        uncertainties: Dict[str, float],
        quantile_models: Dict[str, Dict[str, Any]],
        classifier: Any,
        constraint_classifiers: Dict[str, Any],
        metadata: Dict[str, Any],
    ):
        self.preprocessor = preprocessor
        self.regressors = regressors
        self.uncertainties = uncertainties
        self.quantile_models = quantile_models
        self.classifier = classifier
        self.constraint_classifiers = constraint_classifiers
        self.metadata = metadata

    def predict(self, df_input: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Run inference on a single or batch dataframe of inputs.
        Returns predicted values, +- ranges (95% CI or 10-90 quantile spread),
        pass/fail boolean, and constraint violation breakdown.
        """
        X_trans = self.preprocessor.transform(df_input)

        preds = {}
        uncertainties = {}
        for target in REGRESSION_TARGETS:
            model = self.regressors[target]
            y_pred = model.predict(X_trans)
            preds[target] = y_pred

            # Uncertainty interval calculation
            if (
                target in self.quantile_models
                and "q10" in self.quantile_models[target]
                and "q90" in self.quantile_models[target]
            ):
                q10 = self.quantile_models[target]["q10"].predict(X_trans)
                q90 = self.quantile_models[target]["q90"].predict(X_trans)
                spread = np.abs(q90 - q10) / 2.0
                uncertainties[target] = spread
            else:
                std_err = self.uncertainties.get(target, 0.05)
                uncertainties[target] = np.full_like(y_pred, std_err * 1.96)

        # Classification
        clf_pred = self.classifier.predict(X_trans)
        clf_prob = (
            self.classifier.predict_proba(X_trans)[:, 1]
            if hasattr(self.classifier, "predict_proba")
            else clf_pred
        )

        constraint_preds = {}
        for c_target, c_model in self.constraint_classifiers.items():
            constraint_preds[c_target] = c_model.predict(X_trans)

        n_samples = len(df_input)
        results = []
        for i in range(n_samples):
            item = {
                "regression": {t: float(preds[t][i]) for t in REGRESSION_TARGETS},
                "uncertainty": {t: float(uncertainties[t][i]) for t in REGRESSION_TARGETS},
                "meets_all_requirements": bool(clf_pred[i] == 1),
                "pass_probability": float(clf_prob[i]),
                "fail_reasons": [],
            }
            if (
                constraint_preds["fail_temperature"][i] == 1
                or preds["peak_cell_temp_c"][i] > df_input["max_cell_temp_c"].iloc[i]
            ):
                item["fail_reasons"].append("temperature")
            if (
                constraint_preds["fail_charge_time"][i] == 1
                or preds["charge_time_h"][i] > df_input["max_charge_time_h"].iloc[i]
            ):
                item["fail_reasons"].append("charge_time")
            if (
                constraint_preds["fail_cost"][i] == 1
                or preds["pack_cost_inr"][i] > df_input["max_pack_cost_inr"].iloc[i]
            ):
                item["fail_reasons"].append("cost")
            if (
                constraint_preds["fail_energy"][i] == 1
                or preds["usable_energy_wh"][i] < df_input["min_usable_energy_wh"].iloc[i]
            ):
                item["fail_reasons"].append("energy")
            if constraint_preds["fail_charge_rate"][i] == 1:
                item["fail_reasons"].append("charge_rate")

            # Consistency check
            if item["fail_reasons"]:
                item["meets_all_requirements"] = False

            results.append(item)

        return results
