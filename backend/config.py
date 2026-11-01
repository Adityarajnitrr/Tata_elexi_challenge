"""
Centralized Configuration and Constants
All magic numbers, assumptions, and thresholds are documented here.
"""

from typing import Dict
from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════════════════
# THERMAL MODEL CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

# Entropy coefficients dU/dT (mV/K) for different chemistries at 50% SOC
# Source: Onda et al. (2006), Bernardi et al. (1985)
ENTROPY_COEFFICIENTS = {
    "NMC": -0.30,  # mV/K (exothermic on charge, endothermic on discharge)
    "LFP": -0.15,  # mV/K (lower entropy change)
    "NCA": -0.35,  # mV/K
}

# Charge transfer resistance (Rct) at reference temperature (25°C), mOhm
# Source: Typical EIS measurements
RCT_REF = {
    "NMC": 15.0,  # mOhm
    "LFP": 20.0,  # mOhm
    "NCA": 12.0,  # mOhm
}

# Diffusion resistance (Rdiff) at reference temperature, mOhm
RDIFF_REF = {
    "NMC": 8.0,  # mOhm
    "LFP": 10.0,  # mOhm
    "NCA": 6.0,  # mOhm
}

# Arrhenius activation energy (eV) for resistance temperature dependence
# Source: Electrochemical literature
EA_RESISTANCE = 0.25  # eV (typical for Li-ion)

# ═══════════════════════════════════════════════════════════════════════════
# AGING / SOH MODEL CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

# Resistance increase factor with aging
# R_aged = R_new * (1 + K_R * (1 - SOH))
# Source: Field data, Tesla / BMW battery packs typically show 1.5-2x at 80% SOH
K_RESISTANCE_AGING = 2.5  # At 80% SOH: R ≈ 1.5x, at 60% SOH: R ≈ 2x

# Capacity retention scaling
# Cap_aged = Cap_new * SOH
# (Direct proportionality by definition)

# Entropy and polarization also degrade (less active material)
K_ENTROPY_AGING = 1.0  # Linear scaling with SOH
K_POLARIZATION_AGING = 1.5  # Polarization increases faster than ohmic

# ═══════════════════════════════════════════════════════════════════════════
# SAFETY CONSTRAINTS
# ═══════════════════════════════════════════════════════════════════════════

# Minimum safety margins (%)
MIN_TEMP_SAFETY_MARGIN = 15.0  # % - stricter for automotive/industrial
MIN_TIME_SAFETY_MARGIN = 10.0  # %
MIN_COST_SAFETY_MARGIN = 5.0   # %
MIN_ENERGY_SAFETY_MARGIN = 5.0 # %

# Absolute maximum cell temperatures (°C) by chemistry
MAX_CELL_TEMP_ABSOLUTE = {
    "NMC": 60.0,  # °C
    "LFP": 70.0,  # °C (more thermally stable)
    "NCA": 55.0,  # °C (less stable)
}

# Maximum cell-to-cell temperature difference (°C)
MAX_CELL_TO_CELL_DELTA_T = 5.0  # °C

# ═══════════════════════════════════════════════════════════════════════════
# MULTI-CRITERIA SCORING WEIGHTS
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_SCORING_WEIGHTS = {
    "safety": 0.40,      # Most important
    "lifetime": 0.25,    # SOH-aware longevity
    "performance": 0.15, # Energy density, charge time
    "cost": 0.20,        # Economic factor
}

# ═══════════════════════════════════════════════════════════════════════════
# CONFLICT DETECTION RULES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ConflictRule:
    id: str
    name: str
    domains: list
    check_fn: callable
    threshold: float
    severity: str  # "critical", "warning", "info"
    message: str
    suggested_fix: str

# Rule catalog will be built in conflict_engine.py

# ═══════════════════════════════════════════════════════════════════════════
# ML MODEL HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════

ML_HEALTH_CHECK_INTERVAL_S = 30.0  # Poll every 30 seconds
ML_TIMEOUT_S = 2.0  # Timeout for health check request

# ═══════════════════════════════════════════════════════════════════════════
# PHYSICAL CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

FARADAY_CONSTANT = 96485.3329  # C/mol
GAS_CONSTANT = 8.314  # J/(mol·K)
ABSOLUTE_ZERO_C = -273.15  # °C
KELVIN_OFFSET = 273.15  # K

# ═══════════════════════════════════════════════════════════════════════════
# DOCUMENTATION REFERENCES
# ═══════════════════════════════════════════════════════════════════════════

REFERENCES = {
    "entropy": "Onda et al. (2006), Bernardi et al. (1985)",
    "resistance_aging": "Tesla/BMW field data, Schmalstieg et al. (2014)",
    "activation_energy": "Electrochemical Impedance Spectroscopy literature",
    "safety_margins": "UN 38.3, IEC 62619, automotive OEM requirements",
}
