"""
Recommender Engine for Battery Pack Design
Searches the design space (S, P, C-rate, cooling type, BMS derating)
to find the top 3 cheapest viable configurations satisfying all user requirements.
"""

import os
import sys
from typing import Dict, List, Any, Optional

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.physics_model import simulate_pack, resolve_cell_spec

def recommend_configurations(
    min_usable_energy_wh: float = 60.0,
    max_charge_time_h: float = 2.0,
    max_pack_cost_inr: float = 4000.0,
    max_cell_temp_c: float = 45.0,
    ambient_temp_c: float = 38.0,
    cell_type: str = "18650 NMC 2.5 Ah",
    bms_thermistor_position: str = "c",
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """
    Search the design space for configurations meeting all constraints,
    ranked by lowest cost.
    """
    cell_spec = resolve_cell_spec(cell_type)
    candidates = []

    # Design search grid
    s_values = range(2, 15)  # 2S to 14S
    p_values = range(1, 7)   # 1P to 6P
    c_rates = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    # Filter c_rates within cell's max C rating
    valid_c_rates = [c for c in c_rates if c <= cell_spec.max_c_rate + 1e-6]
    if not valid_c_rates:
        valid_c_rates = [cell_spec.max_c_rate]

    coolings = ["none", "spr", "fan"]
    deratings = [False, True]

    for s in s_values:
        for p in p_values:
            # Quick energy pruning check
            approx_energy = cell_spec.voltage * s * cell_spec.ah * p * 0.9
            if approx_energy < min_usable_energy_wh * 0.95:
                continue

            for cool in coolings:
                for dr in deratings:
                    for c_rate in valid_c_rates:
                        res = simulate_pack(
                            cell_type=cell_type,
                            series_cells=s,
                            parallel_strings=p,
                            charge_rate_c=c_rate,
                            ambient_temp_c=ambient_temp_c,
                            max_cell_temp_c=max_cell_temp_c,
                            min_usable_energy_wh=min_usable_energy_wh,
                            max_charge_time_h=max_charge_time_h,
                            max_pack_cost_inr=max_pack_cost_inr,
                            bms_thermistor_position=bms_thermistor_position,
                            cooling_type=cool,
                            bms_thermal_derating=dr,
                        )

                        if res.meets_all_requirements:
                            cooling_label = {
                                "none": "Passive enclosure",
                                "spr": "Aluminium spreader",
                                "fan": "Forced air fan",
                            }.get(cool, cool)

                            candidates.append({
                                "series_cells": s,
                                "parallel_strings": p,
                                "cell_type": cell_spec.name,
                                "cooling_type": cool,
                                "cooling_label": cooling_label,
                                "bms_thermal_derating": dr,
                                "charge_rate_c": c_rate,
                                "effective_charge_rate_c": round(res.effective_charge_rate_c, 2),
                                "usable_energy_wh": round(res.usable_energy_wh, 1),
                                "pack_cost_inr": round(res.pack_cost_inr, 0),
                                "peak_cell_temp_c": round(res.peak_cell_temp_c, 1),
                                "charge_time_h": round(res.charge_time_h, 2),
                                "mass_kg": round(res.mass_kg, 2),
                                "heat_at_charge_w": round(res.heat_at_charge_w, 1),
                                "temp_safety_margin_pct": round((max_cell_temp_c - res.peak_cell_temp_c) / max_cell_temp_c * 100, 1),
                                "cost_safety_margin_pct": round((max_pack_cost_inr - res.pack_cost_inr) / max_pack_cost_inr * 100, 1),
                            })

    if not candidates:
        # Fallback: if no configuration meets all requirements strictly within the grid,
        # return the closest 3 with lowest penalty
        return []

    # Sort candidates by cost ascending, then by thermal safety margin descending
    candidates.sort(key=lambda x: (x["pack_cost_inr"], -x["temp_safety_margin_pct"], x["charge_time_h"]))

    # Deduplicate functionally identical designs
    seen = set()
    unique_candidates = []
    for c in candidates:
        key = (c["series_cells"], c["parallel_strings"], c["cooling_type"], c["bms_thermal_derating"], c["charge_rate_c"])
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)
        if len(unique_candidates) >= top_k:
            break

    # Add explanations
    for rank, item in enumerate(unique_candidates, 1):
        reasons = [f"Rank #{rank}: INR {int(item['pack_cost_inr']):,}"]
        if rank == 1:
            reasons.append("Lowest cost viable solution")
        if item["cooling_type"] == "none":
            reasons.append("Saves weight & cost with passive cooling")
        elif item["cooling_type"] == "spr":
            reasons.append("Aluminium spreader keeps temperature controlled")
        else:
            reasons.append("Forced cooling provides maximum thermal headroom")

        if item["bms_thermal_derating"]:
            reasons.append("BMS derating active for thermal safety")
        reasons.append(f"{item['usable_energy_wh']} Wh usable in {item['charge_time_h']}h @ {item['peak_cell_temp_c']} deg C")
        item["explanation"] = " | ".join(reasons)

    return unique_candidates

if __name__ == "__main__":
    recs = recommend_configurations()
    print(f"Found {len(recs)} top recommendations:")
    for r in recs:
        print(f" -> {r['series_cells']}S{r['parallel_strings']}P, Cool={r['cooling_type']}, Derate={r['bms_thermal_derating']}, Cost=INR {r['pack_cost_inr']}, PeakTemp={r['peak_cell_temp_c']}C")
        print(f"    {r['explanation']}")
