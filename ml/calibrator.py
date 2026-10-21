"""
Validation and Calibration Module
Compares measured temperature profiles from CSV against physics and ML predictions.
Calibrates residual error and effective thermal resistance (Rth).
"""

import os
import sys
import math
from typing import Dict, List, Any, Tuple
import numpy as np
from scipy.optimize import curve_fit

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.physics_model import simulate_pack, resolve_cell_spec, resolve_cooling_spec

def calibrate_and_validate(
    time_series: List[float],
    measured_temperatures: List[float],
    cell_type: str = "18650 NMC 2.5 Ah",
    series_cells: int = 4,
    parallel_strings: int = 2,
    charge_rate_c: float = 1.0,
    ambient_temp_c: float = 38.0,
    cooling_type: str = "none",
    bms_thermal_derating: bool = False,
) -> Dict[str, Any]:
    """
    Compare measured temperature data against simulated curve and fit calibrated parameters.
    """
    if len(time_series) == 0 or len(time_series) != len(measured_temperatures):
        raise ValueError("time_series and measured_temperatures must have equal non-zero length.")

    t_arr = np.array(time_series, dtype=float)
    t_meas = np.array(measured_temperatures, dtype=float)

    # 1. Physics simulation baseline
    res = simulate_pack(
        cell_type=cell_type,
        series_cells=series_cells,
        parallel_strings=parallel_strings,
        charge_rate_c=charge_rate_c,
        ambient_temp_c=ambient_temp_c,
        cooling_type=cooling_type,
        bms_thermal_derating=bms_thermal_derating,
    )

    _, cool = resolve_cooling_spec(cooling_type)
    cell = resolve_cell_spec(cell_type)
    nc = series_cells * parallel_strings
    mass_kg = (nc * cell.mass_g + cool.mass_g + 150.0) / 1000.0
    ah = cell.ah * parallel_strings
    c_used = res.effective_charge_rate_c
    i_curr = c_used * ah
    r_pack = res.pack_resistance_ohm
    q_heat = i_curr * i_curr * r_pack

    # Model predicted temperature over time: T(t) = Ta + Q * Rth * (1 - exp(-t / (mass * Cp * Rth)))
    def temp_model(t, rth):
        tau = mass_kg * 1000.0 * rth  # Cp = 1000 J/kg·K
        dt = q_heat * rth
        tau_safe = max(tau, 1.0)
        return ambient_temp_c + dt * (1.0 - np.exp(-t / tau_safe))

    nominal_rth = cool.rth
    t_pred = temp_model(t_arr, nominal_rth)

    # Baseline errors
    errors = np.abs(t_meas - t_pred)
    mae = float(np.mean(errors))
    rmse = float(np.sqrt(np.mean((t_meas - t_pred) ** 2)))
    max_err = float(np.max(errors))

    # 2. Calibrate effective Rth from data
    try:
        popt, _ = curve_fit(temp_model, t_arr, t_meas, p0=[nominal_rth], bounds=(0.5, 30.0))
        calibrated_rth = float(popt[0])
    except Exception:
        calibrated_rth = nominal_rth

    t_cal = temp_model(t_arr, calibrated_rth)
    cal_errors = np.abs(t_meas - t_cal)
    cal_mae = float(np.mean(cal_errors))
    cal_rmse = float(np.sqrt(np.mean((t_meas - t_cal) ** 2)))
    cal_max_err = float(np.max(cal_errors))

    # Diagnostic recommendation
    diagnostic = "Model accuracy is good (error <= 3°C)."
    if mae > 3.0 or max_err > 4.0:
        diagnostic = (
            f"High error detected (MAE={mae:.2f}°C, Max={max_err:.2f}°C). "
            f"Calibrated thermal resistance is {calibrated_rth:.2f} K/W (nominal: {nominal_rth:.2f} K/W). "
            f"Root cause: check pack thermal mass, verify heatsink thermal grease/interface contact resistance, "
            f"and check cell internal resistance drift."
        )

    comparison_points = []
    for i in range(len(t_arr)):
        comparison_points.append({
            "time_s": float(t_arr[i]),
            "measured_c": round(float(t_meas[i]), 2),
            "predicted_c": round(float(t_pred[i]), 2),
            "calibrated_c": round(float(t_cal[i]), 2),
            "error_c": round(float(errors[i]), 2),
        })

    return {
        "nominal_rth": nominal_rth,
        "calibrated_rth": round(calibrated_rth, 3),
        "mae_c": round(mae, 2),
        "rmse_c": round(rmse, 2),
        "max_error_c": round(max_err, 2),
        "calibrated_mae_c": round(cal_mae, 2),
        "calibrated_rmse_c": round(cal_rmse, 2),
        "calibrated_max_error_c": round(cal_max_err, 2),
        "diagnostic": diagnostic,
        "comparison": comparison_points,
    }
