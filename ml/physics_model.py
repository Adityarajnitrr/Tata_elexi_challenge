"""
Physics-based Battery Pack Design Simulator
Ports the lumped-parameter electro-thermal and cost models from the web application.
Serves as the ground-truth model for synthetic dataset generation and baseline verification.
"""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple, Union, Any

@dataclass
class CellSpec:
    name: str
    ah: float          # Capacity (Ah)
    voltage: float     # Nominal cell voltage (V)
    resistance: float  # Internal resistance (Ohms)
    max_c_rate: float  # Max recommended charge rate (C)
    mass_g: float      # Cell mass (grams)
    cost_inr: float    # Cell cost in INR
    ovp: float         # Over-voltage protection threshold (V)
    uvp: float         # Under-voltage protection threshold (V)
    ocp_multiplier: float # Multiplier for over-current protection (x Ah)
    diameter_mm: float # Cell diameter in mm
    length_mm: float   # Cell length in mm

CELL_REGISTRY: Dict[str, CellSpec] = {
    "a": CellSpec(
        name="18650 NMC 2.5 Ah",
        ah=2.5,
        voltage=3.6,
        resistance=0.035,
        max_c_rate=1.0,
        mass_g=47.0,
        cost_inr=180.0,
        ovp=4.2,
        uvp=2.5,
        ocp_multiplier=5.0,
        diameter_mm=18.0,
        length_mm=65.0,
    ),
    "b": CellSpec(
        name="21700 NMC 4.0 Ah",
        ah=4.0,
        voltage=3.6,
        resistance=0.020,
        max_c_rate=0.75,
        mass_g=69.0,
        cost_inr=260.0,
        ovp=4.2,
        uvp=2.5,
        ocp_multiplier=8.0,
        diameter_mm=21.0,
        length_mm=70.0,
    ),
    "c": CellSpec(
        name="26650 LFP 3.0 Ah",
        ah=3.0,
        voltage=3.2,
        resistance=0.030,
        max_c_rate=1.0,
        mass_g=85.0,
        cost_inr=300.0,
        ovp=3.65,
        uvp=2.0,
        ocp_multiplier=6.0,
        diameter_mm=26.0,
        length_mm=65.0,
    ),
}

@dataclass
class CoolingSpec:
    name: str
    rth: float        # Thermal resistance (K/W)
    mass_g: float     # Added mass (grams)
    cost_inr: float   # Added cost (INR)
    spatial_spread: float # Temperature gradient factor (e.g. 0.35 passive, 0.25 spreader, 0.15 fan)

COOLING_REGISTRY: Dict[str, CoolingSpec] = {
    "none": CoolingSpec("Passive enclosure", rth=9.0, mass_g=0.0, cost_inr=0.0, spatial_spread=0.35),
    "spr": CoolingSpec("Aluminium spreader", rth=5.5, mass_g=60.0, cost_inr=150.0, spatial_spread=0.25),
    "fan": CoolingSpec("Forced air", rth=3.0, mass_g=180.0, cost_inr=400.0, spatial_spread=0.15),
}

def resolve_cell_spec(cell_identifier: str) -> CellSpec:
    """Normalize and look up cell specifications."""
    cell_id_lower = str(cell_identifier).strip().lower()
    if cell_id_lower in CELL_REGISTRY:
        return CELL_REGISTRY[cell_id_lower]
    for key, spec in CELL_REGISTRY.items():
        if cell_id_lower in spec.name.lower() or spec.name.lower() in cell_id_lower:
            return spec
    # Default to 18650 NMC if unknown
    return CELL_REGISTRY["a"]

def resolve_cooling_spec(cooling_identifier: str) -> Tuple[str, CoolingSpec]:
    """Normalize and look up cooling specifications."""
    cool_lower = str(cooling_identifier).strip().lower()
    if cool_lower in COOLING_REGISTRY:
        return cool_lower, COOLING_REGISTRY[cool_lower]
    if "spread" in cool_lower or "alu" in cool_lower or cool_lower == "spr":
        return "spr", COOLING_REGISTRY["spr"]
    if "fan" in cool_lower or "air" in cool_lower or "forced" in cool_lower:
        return "fan", COOLING_REGISTRY["fan"]
    return "none", COOLING_REGISTRY["none"]

def resolve_thermistor_position(position_identifier: str) -> str:
    """Normalize thermistor position to 'c' (centre hot-spot) or 'e' (edge)."""
    pos_lower = str(position_identifier).strip().lower()
    if "edge" in pos_lower or "corner" in pos_lower or pos_lower == "e":
        return "e"
    return "c"

@dataclass
class SimulationResult:
    cell_name: str
    series_cells: int
    parallel_strings: int
    nominal_voltage_v: float
    nominal_capacity_ah: float
    usable_energy_wh: float
    pack_resistance_ohm: float
    mass_kg: float
    volume_l: float
    energy_density_wh_per_l: float
    pack_cost_inr: float
    requested_charge_rate_c: float
    effective_charge_rate_c: float
    heat_at_charge_w: float
    peak_cell_temp_c: float
    charge_time_h: float
    derated: bool
    meets_all_requirements: bool
    fail_reasons: List[str] = field(default_factory=list)
    bms_thermistor_reading_c: float = 0.0
    thermal_time_constant_s: float = 0.0
    steady_state_delta_t_c: float = 0.0

def simulate_pack(
    cell_type: str = "18650 NMC 2.5 Ah",
    series_cells: int = 4,
    parallel_strings: int = 2,
    charge_rate_c: float = 1.0,
    ambient_temp_c: float = 38.0,
    max_cell_temp_c: float = 45.0,
    min_usable_energy_wh: float = 60.0,
    max_charge_time_h: float = 2.0,
    max_pack_cost_inr: float = 4000.0,
    bms_thermistor_position: str = "c",
    cooling_type: str = "none",
    bms_thermal_derating: bool = False,
    resistance_variation: float = 1.0,  # multiplier for R (e.g. 1.0 normal, 2.0 ageing)
) -> SimulationResult:
    """
    Simulate the pack performance using the identical physics formulas from index.html.
    """
    cell = resolve_cell_spec(cell_type)
    cool_key, cool = resolve_cooling_spec(cooling_type)
    th_pos = resolve_thermistor_position(bms_thermistor_position)

    s = int(series_cells)
    p = int(parallel_strings)
    nc = s * p
    ah = cell.ah * p
    vn = cell.voltage * s
    eu = vn * ah * 0.9  # 90% DoD usable energy

    # Resistance: internal cells in series/parallel + 2 mOhm per series weld link
    cell_r = cell.resistance * resistance_variation
    r_pack = cell_r * s / p + (s + 1) * 0.002

    # Mass & Cost
    mass_kg = (nc * cell.mass_g + cool.mass_g + 150.0) / 1000.0
    bms_cost = 650.0 if bms_thermal_derating else 400.0
    cost_inr = nc * cell.cost_inr + cool.cost_inr + bms_cost

    # Volume (rough packing estimate from cell dimensions)
    pack_l_mm = cell.length_mm + 20.0
    pack_w_mm = p * cell.diameter_mm * 1.3
    pack_h_mm = s * cell.diameter_mm * 1.3
    volume_l = (pack_l_mm * pack_w_mm * pack_h_mm) / 1e6
    energy_density = eu / volume_l if volume_l > 0 else 0.0

    # Lumped thermal run helper
    def run_thermal(c_rate: float) -> Tuple[float, float, float, float, float, float]:
        i_current = c_rate * ah
        q_heat = i_current * i_current * r_pack
        dt_steady = q_heat * cool.rth
        tau_seconds = mass_kg * 1000.0 * cool.rth  # Cp = 1000 J/kg·K
        time_hours = 0.8 / c_rate + 0.3
        # First-order lumped transient temperature at end of charge
        exponent = - (time_hours * 3600.0) / tau_seconds if tau_seconds > 0 else -10.0
        te = ambient_temp_c + dt_steady * (1.0 - math.exp(exponent))
        return i_current, q_heat, dt_steady, tau_seconds, time_hours, te

    # Spatial geometry function matching index.html geo()
    def geo_func(s_count: int, p_count: int):
        def f(c_idx: int, r_idx: int) -> float:
            norm_c = (c_idx - (s_count - 1) / 2.0) / max(1.0, (s_count - 1) / 2.0)
            norm_r = (r_idx - (p_count - 1) / 2.0) / max(1.0, (p_count - 1) / 2.0)
            return math.sqrt((norm_c * norm_c + norm_r * norm_r) / 2.0)

        min_m = 9.0
        for c_i in range(s_count):
            for r_i in range(p_count):
                min_m = min(min_m, f(c_i, r_i))
        return lambda c_i, r_i: f(c_i, r_i) - min_m

    g = geo_func(s, p)
    sc = [round((s - 1) / 2.0), round((p - 1) / 2.0)] if th_pos == "c" else [0, 0]
    sensor_fraction = 1.0 - cool.spatial_spread * g(sc[0], sc[1])

    def thermistor_reading(te_val: float) -> float:
        return ambient_temp_c + (te_val - ambient_temp_c) * sensor_fraction

    c_current = float(charge_rate_c)
    i_val, q_val, dt_val, tau_val, th_val, te_val = run_thermal(c_current)
    derated = False

    # Iterative BMS derating
    if bms_thermal_derating:
        while thermistor_reading(te_val) > max_cell_temp_c and c_current > 0.1:
            c_current *= 0.97
            i_val, q_val, dt_val, tau_val, th_val, te_val = run_thermal(c_current)
            derated = True

    sensor_temp = thermistor_reading(te_val)

    # Requirement checks
    fail_reasons: List[str] = []
    if te_val > max_cell_temp_c:
        fail_reasons.append("temperature")
    if th_val > max_charge_time_h:
        fail_reasons.append("charge_time")
    if cost_inr > max_pack_cost_inr:
        fail_reasons.append("cost")
    if eu < min_usable_energy_wh:
        fail_reasons.append("energy")
    if c_current > cell.max_c_rate + 1e-9:
        fail_reasons.append("charge_rate")

    meets_all = len(fail_reasons) == 0

    return SimulationResult(
        cell_name=cell.name,
        series_cells=s,
        parallel_strings=p,
        nominal_voltage_v=vn,
        nominal_capacity_ah=ah,
        usable_energy_wh=eu,
        pack_resistance_ohm=r_pack,
        mass_kg=mass_kg,
        volume_l=volume_l,
        energy_density_wh_per_l=energy_density,
        pack_cost_inr=cost_inr,
        requested_charge_rate_c=float(charge_rate_c),
        effective_charge_rate_c=c_current,
        heat_at_charge_w=q_val,
        peak_cell_temp_c=te_val,
        charge_time_h=th_val,
        derated=derated,
        meets_all_requirements=meets_all,
        fail_reasons=fail_reasons,
        bms_thermistor_reading_c=sensor_temp,
        thermal_time_constant_s=tau_val,
        steady_state_delta_t_c=dt_val,
    )
