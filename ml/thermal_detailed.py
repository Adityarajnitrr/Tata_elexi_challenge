"""
Detailed Multi-Component Thermal Model
Q_total = Q_ohmic + Q_kinetic + Q_polarization + Q_entropic

Units:
- Current (I): Amperes (A)
- Resistance (R): Ohms (Ω)
- Voltage (V): Volts (V)
- Temperature (T): Kelvin (K) or Celsius (°C)
- Power/Heat (Q): Watts (W)
"""

import math
from typing import Dict, Tuple
from dataclasses import dataclass

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.config import (
    ENTROPY_COEFFICIENTS,
    RCT_REF,
    RDIFF_REF,
    EA_RESISTANCE,
    GAS_CONSTANT,
    KELVIN_OFFSET,
)


@dataclass
class HeatBreakdown:
    """Complete heat generation breakdown"""
    q_ohmic_w: float          # I²R Joule/ohmic heat (W)
    q_kinetic_w: float        # I·η_act activation overpotential heat (W)
    q_polarization_w: float   # I·η_conc or I²·R_diff concentration polarization (W)
    q_entropic_w: float       # -I·T·(dU/dT) reversible/entropic heat (W)
    q_total_w: float          # Sum of all components (W)
    
    # Metadata
    current_a: float
    temperature_c: float
    soc: float
    chemistry: str


def get_chemistry_from_cell_name(cell_name: str) -> str:
    """Extract chemistry type from cell name."""
    name_lower = cell_name.lower()
    if "nmc" in name_lower:
        return "NMC"
    elif "lfp" in name_lower:
        return "LFP"
    elif "nca" in name_lower:
        return "NCA"
    return "NMC"  # Default


def temperature_corrected_resistance(
    r_ref: float,
    t_ref_c: float,
    t_actual_c: float,
    ea_ev: float = EA_RESISTANCE
) -> float:
    """
    Arrhenius correction for resistance:
    R(T) = R_ref * exp(Ea/R * (1/T - 1/T_ref))
    
    Args:
        r_ref: Resistance at reference temperature (Ω)
        t_ref_c: Reference temperature (°C), typically 25°C
        t_actual_c: Actual temperature (°C)
        ea_ev: Activation energy (eV)
        
    Returns:
        Temperature-corrected resistance (Ω)
    """
    t_ref_k = t_ref_c + KELVIN_OFFSET
    t_actual_k = t_actual_c + KELVIN_OFFSET
    
    # Ea in Joules: ea_ev * e * N_A / N_A = ea_ev * e (in J/mol when multiplied by Faraday)
    # Simplified: exp(Ea * (1/T - 1/T_ref))
    ea_j_per_mol = ea_ev * 1.602e-19 * 6.022e23  # Convert eV to J/mol
    
    exponent = (ea_j_per_mol / GAS_CONSTANT) * (1.0 / t_actual_k - 1.0 / t_ref_k)
    return r_ref * math.exp(exponent)


def soc_dependent_entropy(
    chemistry: str,
    soc: float
) -> float:
    """
    Entropy coefficient dU/dT as a function of SOC.
    Simplified: constant for now, but can be extended with lookup table.
    
    Args:
        chemistry: "NMC", "LFP", "NCA"
        soc: State of charge (0.0 to 1.0)
        
    Returns:
        dU/dT in V/K (converted from mV/K)
    """
    base_coeff_mv_per_k = ENTROPY_COEFFICIENTS.get(chemistry, ENTROPY_COEFFICIENTS["NMC"])
    
    # For more accuracy, add SOC dependency:
    # Typically entropic coefficient is more negative at mid-SOC
    # Simplified model: scale by a factor
    soc_factor = 1.0 + 0.3 * math.sin(math.pi * soc)  # Peak at 50% SOC
    
    return (base_coeff_mv_per_k * soc_factor) / 1000.0  # Convert mV/K to V/K


def compute_heat_generation(
    current_a: float,
    cell_voltage_v: float,
    r_ohm: float,
    temperature_c: float,
    soc: float,
    chemistry: str,
    is_charging: bool = True,
    soh: float = 1.0,
) -> HeatBreakdown:
    """
    Compute all 4 components of heat generation.
    
    Args:
        current_a: Cell current (A), positive for charge
        cell_voltage_v: Nominal cell voltage (V)
        r_ohm: Ohmic resistance at reference temp (Ω)
        temperature_c: Cell temperature (°C)
        soc: State of charge (0.0-1.0)
        chemistry: "NMC", "LFP", "NCA"
        is_charging: True for charge, False for discharge
        soh: State of health (0.0-1.0), affects resistance and polarization
        
    Returns:
        HeatBreakdown with all components
    """
    
    # Temperature correction for all resistances
    r_ohm_corrected = temperature_corrected_resistance(r_ohm, 25.0, temperature_c)
    
    # 1. OHMIC HEAT: Q_ohmic = I² * R_ohm (W)
    q_ohmic = current_a * current_a * r_ohm_corrected
    
    # 2. KINETIC/ACTIVATION HEAT: Q_kinetic = I * η_act (W)
    # η_act from Butler-Volmer or simplified via charge-transfer resistance:
    # η_act ≈ I * R_ct
    r_ct_ref = RCT_REF.get(chemistry, RCT_REF["NMC"]) / 1000.0  # Convert mOhm to Ohm
    r_ct = temperature_corrected_resistance(r_ct_ref, 25.0, temperature_c) * (1.0 + (1.0 - soh) * 1.5)
    eta_act = current_a * r_ct
    q_kinetic = current_a * eta_act
    
    # 3. POLARIZATION/CONCENTRATION HEAT: Q_polarization = I * η_conc or I² * R_diff (W)
    # η_conc due to concentration gradients, modeled via diffusion resistance
    r_diff_ref = RDIFF_REF.get(chemistry, RDIFF_REF["NMC"]) / 1000.0  # Convert mOhm to Ohm
    r_diff = temperature_corrected_resistance(r_diff_ref, 25.0, temperature_c) * (1.0 + (1.0 - soh) * 2.0)
    q_polarization = current_a * current_a * r_diff
    
    # 4. ENTROPIC/REVERSIBLE HEAT: Q_entropic = -I * T * (dU/dT) (W)
    # Sign: negative on charge (endothermic), positive on discharge (exothermic)
    temperature_k = temperature_c + KELVIN_OFFSET
    du_dt = soc_dependent_entropy(chemistry, soc)  # V/K
    
    # Apply SOH scaling (less active material)
    du_dt_scaled = du_dt * soh
    
    # Heat contribution (sign matters)
    # For charging: current > 0, dU/dT < 0 (NMC), so -I*T*dU/dT > 0 (exothermic entropy production)
    # Actually: entropic heat is absorbed during charge (endothermic) if dU/dT < 0
    # Correct sign: Q_entropic = -I * T * dU/dT
    # For NMC: dU/dT ≈ -0.3 mV/K, so during charge (I>0): Q = -I*T*(-0.0003) = +I*T*0.0003 (heat generated)
    # During discharge (I<0): Q = -(-I)*T*(-0.0003) = -I*T*0.0003 (heat absorbed, cooling)
    
    sign_factor = 1.0 if is_charging else -1.0
    q_entropic = -sign_factor * current_a * temperature_k * du_dt_scaled
    
    # TOTAL HEAT
    q_total = q_ohmic + q_kinetic + q_polarization + q_entropic
    
    return HeatBreakdown(
        q_ohmic_w=q_ohmic,
        q_kinetic_w=q_kinetic,
        q_polarization_w=q_polarization,
        q_entropic_w=q_entropic,
        q_total_w=q_total,
        current_a=current_a,
        temperature_c=temperature_c,
        soc=soc,
        chemistry=chemistry,
    )


def compute_pack_heat_detailed(
    pack_current_a: float,
    cell_voltage_v: float,
    cell_r_ohm: float,
    series_cells: int,
    parallel_strings: int,
    temperature_c: float,
    soc: float,
    chemistry: str,
    is_charging: bool = True,
    soh: float = 1.0,
    link_resistance_ohm: float = 0.002,
) -> Dict[str, float]:
    """
    Compute heat for entire pack.
    
    Returns:
        Dictionary with breakdown per cell and pack totals
    """
    # Current per cell in parallel configuration
    cell_current_a = pack_current_a / parallel_strings
    
    # Series resistance: each cell in series adds resistance
    # Pack R_ohm = cell_R * S / P + link_resistance * (S+1)
    
    # Heat per cell
    cell_heat = compute_heat_generation(
        current_a=cell_current_a,
        cell_voltage_v=cell_voltage_v,
        r_ohm=cell_r_ohm,
        temperature_c=temperature_c,
        soc=soc,
        chemistry=chemistry,
        is_charging=is_charging,
        soh=soh,
    )
    
    # Link heat (ohmic only in busbars/welds)
    num_links = series_cells + 1
    link_heat_w = pack_current_a * pack_current_a * link_resistance_ohm * num_links
    
    # Total pack heat
    total_cell_heat_w = cell_heat.q_total_w * series_cells * parallel_strings
    total_pack_heat_w = total_cell_heat_w + link_heat_w
    
    return {
        "q_ohmic_per_cell_w": cell_heat.q_ohmic_w,
        "q_kinetic_per_cell_w": cell_heat.q_kinetic_w,
        "q_polarization_per_cell_w": cell_heat.q_polarization_w,
        "q_entropic_per_cell_w": cell_heat.q_entropic_w,
        "q_total_per_cell_w": cell_heat.q_total_w,
        "q_links_total_w": link_heat_w,
        "q_pack_total_w": total_pack_heat_w,
        "q_ohmic_pack_total_w": cell_heat.q_ohmic_w * series_cells * parallel_strings,
        "q_kinetic_pack_total_w": cell_heat.q_kinetic_w * series_cells * parallel_strings,
        "q_polarization_pack_total_w": cell_heat.q_polarization_w * series_cells * parallel_strings,
        "q_entropic_pack_total_w": cell_heat.q_entropic_w * series_cells * parallel_strings,
    }


# ═══════════════════════════════════════════════════════════════════════════
# UNIT TESTS (can be moved to separate test file)
# ═══════════════════════════════════════════════════════════════════════════

def _test_heat_generation():
    """Basic sanity tests."""
    # Test case: 10A charging at 25°C, NMC cell
    heat = compute_heat_generation(
        current_a=10.0,
        cell_voltage_v=3.6,
        r_ohm=0.035,
        temperature_c=25.0,
        soc=0.5,
        chemistry="NMC",
        is_charging=True,
        soh=1.0,
    )
    
    print("Test: 10A charge, NMC, 25°C, 100% SOH")
    print(f"  Q_ohmic: {heat.q_ohmic_w:.2f} W")
    print(f"  Q_kinetic: {heat.q_kinetic_w:.2f} W")
    print(f"  Q_polarization: {heat.q_polarization_w:.2f} W")
    print(f"  Q_entropic: {heat.q_entropic_w:.2f} W")
    print(f"  Q_total: {heat.q_total_w:.2f} W")
    
    # Assertions
    assert heat.q_ohmic_w > 0, "Ohmic heat must be positive"
    assert heat.q_kinetic_w > 0, "Kinetic heat must be positive"
    assert heat.q_polarization_w > 0, "Polarization heat must be positive"
    # Entropic can be positive or negative depending on sign of dU/dT and charge/discharge
    assert heat.q_total_w > 0, "Total heat must be positive during charge"
    
    print("✓ All tests passed")


if __name__ == "__main__":
    _test_heat_generation()
