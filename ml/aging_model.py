"""
Battery Aging / SOH Model
Models degradation effects on resistance, capacity, and thermal behavior.
"""

from typing import Dict, Tuple
from dataclasses import dataclass

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.config import K_RESISTANCE_AGING, K_ENTROPY_AGING, K_POLARIZATION_AGING


@dataclass
class AgingFactors:
    """Multipliers for various cell properties based on SOH"""
    soh: float
    resistance_multiplier: float  # R_aged = R_new * this
    capacity_multiplier: float    # Cap_aged = Cap_new * this
    entropy_multiplier: float     # Entropy coefficient scaling
    polarization_multiplier: float  # R_ct and R_diff scaling


def compute_aging_factors(soh: float) -> AgingFactors:
    """
    Compute degradation multipliers based on SOH.
    
    Args:
        soh: State of Health (0.0 to 1.0), where 1.0 = BOL, 0.8 = EOL
        
    Returns:
        AgingFactors with all multipliers
        
    Example:
        At 80% SOH:
        - Resistance: ~1.5x (50% increase)
        - Capacity: 0.8x (20% loss)
        - Entropy: 0.8x (proportional to active material)
        - Polarization: ~1.6x (60% increase)
    """
    soh = max(0.5, min(1.0, soh))  # Clamp between 50% and 100%
    
    # Resistance increase: R_aged = R_new * (1 + K_R * (1 - SOH))
    # At 80% SOH with K=2.5: R = R_new * (1 + 2.5 * 0.2) = 1.5 * R_new
    r_mult = 1.0 + K_RESISTANCE_AGING * (1.0 - soh)
    
    # Capacity: direct proportionality
    cap_mult = soh
    
    # Entropy: scales with active material
    entropy_mult = soh ** K_ENTROPY_AGING
    
    # Polarization: increases faster (SEI growth, lithium plating)
    polar_mult = 1.0 + K_POLARIZATION_AGING * (1.0 - soh)
    
    return AgingFactors(
        soh=soh,
        resistance_multiplier=r_mult,
        capacity_multiplier=cap_mult,
        entropy_multiplier=entropy_mult,
        polarization_multiplier=polar_mult,
    )


def apply_aging_to_cell_specs(
    base_capacity_ah: float,
    base_resistance_ohm: float,
    soh: float
) -> Tuple[float, float]:
    """
    Apply aging to cell specifications.
    
    Returns:
        (aged_capacity_ah, aged_resistance_ohm)
    """
    factors = compute_aging_factors(soh)
    return (
        base_capacity_ah * factors.capacity_multiplier,
        base_resistance_ohm * factors.resistance_multiplier,
    )


def get_soh_scenarios() -> Dict[str, float]:
    """
    Return standard SOH test scenarios.
    
    Returns:
        {"BOL": 1.0, "MID": 0.9, "EOL": 0.8}
    """
    return {
        "BOL": 1.00,   # Beginning of Life (new cell)
        "MID": 0.90,   # Mid-Life (10% capacity fade)
        "EOL": 0.80,   # End of Life (20% capacity fade, typical warranty threshold)
    }


def get_worst_case_soh() -> float:
    """Return worst-case SOH for conservative design validation."""
    return 0.80  # 80% EOL


# ═══════════════════════════════════════════════════════════════════════════
# UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════

def _test_aging_model():
    """Test aging calculations."""
    scenarios = get_soh_scenarios()
    
    print("Aging Model Test:")
    print("=" * 60)
    
    for name, soh in scenarios.items():
        factors = compute_aging_factors(soh)
        print(f"\n{name} (SOH={soh*100:.0f}%):")
        print(f"  Resistance multiplier: {factors.resistance_multiplier:.2f}x")
        print(f"  Capacity multiplier: {factors.capacity_multiplier:.2f}x")
        print(f"  Entropy multiplier: {factors.entropy_multiplier:.2f}x")
        print(f"  Polarization multiplier: {factors.polarization_multiplier:.2f}x")
    
    # Test cell specs application
    print("\n" + "=" * 60)
    print("Example: 2.5 Ah cell with 35 mΩ resistance")
    
    for name, soh in scenarios.items():
        cap_aged, r_aged = apply_aging_to_cell_specs(2.5, 0.035, soh)
        print(f"  {name}: {cap_aged:.2f} Ah, {r_aged*1000:.1f} mΩ")
    
    # Assertions
    factors_eol = compute_aging_factors(0.8)
    assert 1.4 <= factors_eol.resistance_multiplier <= 1.6, "EOL resistance should be ~1.5x"
    assert abs(factors_eol.capacity_multiplier - 0.8) < 0.01, "EOL capacity should be 80%"
    
    print("\n✓ All tests passed")


if __name__ == "__main__":
    _test_aging_model()
