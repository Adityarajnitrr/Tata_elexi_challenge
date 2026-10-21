"""
Generate synthetic dataset for battery pack performance surrogate models.
Uses Latin Hypercube / stratified random sampling across input domains
and simulates ground-truth outputs using physics_model.py, adding realistic measurement noise.
"""

import os
import sys
import time
import numpy as np
import pandas as pd
from typing import Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.physics_model import simulate_pack

def generate_dataset(
    n_samples: int = 55000,
    seed: int = 42,
    output_path: str = "data/synthetic_dataset.csv",
    add_noise: bool = True
) -> pd.DataFrame:
    print(f"Generating {n_samples} synthetic battery pack samples...")
    start_time = time.time()
    rng = np.random.default_rng(seed)

    cell_choices = ["18650 NMC 2.5 Ah", "21700 NMC 4.0 Ah", "26650 LFP 3.0 Ah"]
    cooling_choices = ["none", "spr", "fan"]
    th_choices = ["c", "e"]
    derate_choices = [False, True]

    # Sample inputs
    cells = rng.choice(cell_choices, size=n_samples)
    series_cells = rng.integers(1, 21, size=n_samples)  # 1 to 20
    parallel_strings = rng.integers(1, 11, size=n_samples)  # 1 to 10
    charge_rate_c = np.round(rng.uniform(0.2, 3.0, size=n_samples), 3)
    ambient_temp_c = np.round(rng.uniform(0.0, 50.0, size=n_samples), 1)
    max_cell_temp_c = np.round(rng.uniform(35.0, 60.0, size=n_samples), 1)
    min_usable_energy_wh = np.round(rng.uniform(20.0, 500.0, size=n_samples), 1)
    max_charge_time_h = np.round(rng.uniform(0.5, 4.0, size=n_samples), 2)
    max_pack_cost_inr = np.round(rng.uniform(1000.0, 20000.0, size=n_samples), 0)
    th_positions = rng.choice(th_choices, size=n_samples)
    coolings = rng.choice(cooling_choices, size=n_samples)
    deratings = rng.choice(derate_choices, size=n_samples)

    records = []
    for i in range(n_samples):
        res = simulate_pack(
            cell_type=cells[i],
            series_cells=int(series_cells[i]),
            parallel_strings=int(parallel_strings[i]),
            charge_rate_c=float(charge_rate_c[i]),
            ambient_temp_c=float(ambient_temp_c[i]),
            max_cell_temp_c=float(max_cell_temp_c[i]),
            min_usable_energy_wh=float(min_usable_energy_wh[i]),
            max_charge_time_h=float(max_charge_time_h[i]),
            max_pack_cost_inr=float(max_pack_cost_inr[i]),
            bms_thermistor_position=th_positions[i],
            cooling_type=coolings[i],
            bms_thermal_derating=bool(deratings[i]),
        )

        # Baseline outputs
        peak_temp = res.peak_cell_temp_c
        charge_time = res.charge_time_h
        heat_w = res.heat_at_charge_w
        eff_c = res.effective_charge_rate_c
        usable_e = res.usable_energy_wh
        cost = res.pack_cost_inr
        mass = res.mass_kg
        energy_dens = res.energy_density_wh_per_l

        # Small Gaussian noise to mimic sensor/measurement scatter
        if add_noise:
            # ~ ±0.3°C temperature noise
            peak_temp += rng.normal(0.0, 0.25)
            # ~ ±1.5% heating noise
            heat_w = max(0.0, heat_w + rng.normal(0.0, 0.015 * max(heat_w, 0.1)))
            # ~ ±0.5% timing noise
            charge_time = max(0.1, charge_time + rng.normal(0.0, 0.005 * charge_time))
            # ~ ±0.2% mass scatter
            mass = max(0.05, mass + rng.normal(0.0, 0.002))
            # recalculate density from noisy values
            if res.volume_l > 0:
                energy_dens = usable_e / res.volume_l

        # Re-check requirements against measured/noisy values
        fail_reasons = []
        if peak_temp > max_cell_temp_c[i]:
            fail_reasons.append("temperature")
        if charge_time > max_charge_time_h[i]:
            fail_reasons.append("charge_time")
        if cost > max_pack_cost_inr[i]:
            fail_reasons.append("cost")
        if usable_e < min_usable_energy_wh[i]:
            fail_reasons.append("energy")
        from ml.physics_model import resolve_cell_spec
        c_spec = resolve_cell_spec(cells[i])
        if eff_c > c_spec.max_c_rate + 1e-9:
            fail_reasons.append("charge_rate")

        meets_all = len(fail_reasons) == 0

        records.append({
            # Inputs
            "cell_type": cells[i],
            "series_cells": int(series_cells[i]),
            "parallel_strings": int(parallel_strings[i]),
            "charge_rate_c": float(charge_rate_c[i]),
            "ambient_temp_c": float(ambient_temp_c[i]),
            "max_cell_temp_c": float(max_cell_temp_c[i]),
            "min_usable_energy_wh": float(min_usable_energy_wh[i]),
            "max_charge_time_h": float(max_charge_time_h[i]),
            "max_pack_cost_inr": float(max_pack_cost_inr[i]),
            "bms_thermistor_position": th_positions[i],
            "cooling_type": coolings[i],
            "bms_thermal_derating": int(deratings[i]),
            # Regression Targets
            "peak_cell_temp_c": round(peak_temp, 3),
            "charge_time_h": round(charge_time, 4),
            "heat_at_charge_w": round(heat_w, 3),
            "effective_charge_rate_c": round(eff_c, 4),
            "usable_energy_wh": round(usable_e, 2),
            "pack_cost_inr": round(cost, 1),
            "mass_kg": round(mass, 4),
            "energy_density_wh_per_l": round(energy_dens, 2),
            # Classification Targets
            "meets_all_requirements": int(meets_all),
            "fail_temperature": int("temperature" in fail_reasons),
            "fail_charge_time": int("charge_time" in fail_reasons),
            "fail_cost": int("cost" in fail_reasons),
            "fail_energy": int("energy" in fail_reasons),
            "fail_charge_rate": int("charge_rate" in fail_reasons),
            "fail_reasons_str": ";".join(fail_reasons),
        })

    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    elapsed = time.time() - start_time
    print(f"Dataset generated successfully in {elapsed:.2f}s: {output_path} ({len(df)} rows, {len(df.columns)} columns)")
    return df

if __name__ == "__main__":
    generate_dataset()
