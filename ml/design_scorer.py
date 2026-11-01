"""
Multi-Criteria Safety-First Design Scorer
Applies hard safety constraints first, then scores remaining designs.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import math

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.config import (
    MIN_TEMP_SAFETY_MARGIN,
    MIN_TIME_SAFETY_MARGIN,
    MIN_COST_SAFETY_MARGIN,
    MIN_ENERGY_SAFETY_MARGIN,
    MAX_CELL_TEMP_ABSOLUTE,
    MAX_CELL_TO_CELL_DELTA_T,
    DEFAULT_SCORING_WEIGHTS,
)


@dataclass
class SafetyCheck:
    """Result of hard safety constraint checks"""
    passes: bool
    violations: List[str]
    temp_margin_pct: float
    time_margin_pct: float
    cost_margin_pct: float
    energy_margin_pct: float
    cell_to_cell_delta_t: float


@dataclass
class DesignScore:
    """Multi-criteria score for a design"""
    total_score: float  # 0-100
    safety_score: float
    lifetime_score: float
    performance_score: float
    cost_score: float
    
    passes_safety: bool
    violations: List[str]
    recommendation_reason: str


def check_hard_safety_constraints(
    peak_cell_temp_c: float,
    max_cell_temp_limit_c: float,
    charge_time_h: float,
    max_charge_time_h: float,
    pack_cost_inr: float,
    max_pack_cost_inr: float,
    usable_energy_wh: float,
    min_usable_energy_wh: float,
    chemistry: str = "NMC",
    cell_to_cell_delta_t: float = 0.0,
    min_temp_margin: float = MIN_TEMP_SAFETY_MARGIN,
    min_time_margin: float = MIN_TIME_SAFETY_MARGIN,
    min_cost_margin: float = MIN_COST_SAFETY_MARGIN,
    min_energy_margin: float = MIN_ENERGY_SAFETY_MARGIN,
) -> SafetyCheck:
    """
    Apply hard safety constraints. Any violation = design rejected.
    
    Args:
        All design parameters and their limits
        min_*_margin: Minimum safety margins in %
        
    Returns:
        SafetyCheck with pass/fail and violation details
    """
    violations = []
    
    # Calculate margins
    temp_margin_pct = ((max_cell_temp_limit_c - peak_cell_temp_c) / max_cell_temp_limit_c) * 100.0 if max_cell_temp_limit_c > 0 else 0.0
    time_margin_pct = ((max_charge_time_h - charge_time_h) / max_charge_time_h) * 100.0 if max_charge_time_h > 0 else 0.0
    cost_margin_pct = ((max_pack_cost_inr - pack_cost_inr) / max_pack_cost_inr) * 100.0 if max_pack_cost_inr > 0 else 0.0
    energy_margin_pct = ((usable_energy_wh - min_usable_energy_wh) / min_usable_energy_wh) * 100.0 if min_usable_energy_wh > 0 else 0.0
    
    # CONSTRAINT 1: Temperature safety margin
    if temp_margin_pct < min_temp_margin:
        violations.append(f"Temperature margin {temp_margin_pct:.1f}% < {min_temp_margin}% minimum")
    
    # CONSTRAINT 2: Absolute temperature limit by chemistry
    abs_max = MAX_CELL_TEMP_ABSOLUTE.get(chemistry, MAX_CELL_TEMP_ABSOLUTE["NMC"])
    if peak_cell_temp_c > abs_max:
        violations.append(f"Cell temperature {peak_cell_temp_c:.1f}°C exceeds absolute {chemistry} limit {abs_max}°C")
    
    # CONSTRAINT 3: Cell-to-cell temperature difference
    if cell_to_cell_delta_t > MAX_CELL_TO_CELL_DELTA_T:
        violations.append(f"Cell-to-cell ΔT {cell_to_cell_delta_t:.1f}°C exceeds {MAX_CELL_TO_CELL_DELTA_T}°C limit")
    
    # CONSTRAINT 4: Charge time margin (less critical but still checked)
    if time_margin_pct < min_time_margin:
        violations.append(f"Charge time margin {time_margin_pct:.1f}% < {min_time_margin}% minimum")
    
    # CONSTRAINT 5: Energy requirement met
    if energy_margin_pct < min_energy_margin:
        violations.append(f"Energy margin {energy_margin_pct:.1f}% < {min_energy_margin}% minimum")
    
    # CONSTRAINT 6: Cost within budget (softer constraint)
    if cost_margin_pct < min_cost_margin:
        violations.append(f"Cost margin {cost_margin_pct:.1f}% < {min_cost_margin}% minimum")
    
    passes = len(violations) == 0
    
    return SafetyCheck(
        passes=passes,
        violations=violations,
        temp_margin_pct=temp_margin_pct,
        time_margin_pct=time_margin_pct,
        cost_margin_pct=cost_margin_pct,
        energy_margin_pct=energy_margin_pct,
        cell_to_cell_delta_t=cell_to_cell_delta_t,
    )


def score_design(
    peak_cell_temp_c: float,
    max_cell_temp_limit_c: float,
    charge_time_h: float,
    max_charge_time_h: float,
    pack_cost_inr: float,
    max_pack_cost_inr: float,
    usable_energy_wh: float,
    min_usable_energy_wh: float,
    energy_density_wh_per_l: float,
    soh: float = 1.0,
    chemistry: str = "NMC",
    cell_to_cell_delta_t: float = 0.0,
    weights: Optional[Dict[str, float]] = None,
) -> DesignScore:
    """
    Score a design using multi-criteria analysis.
    First checks hard safety constraints, then computes score if passed.
    
    Args:
        All design parameters
        weights: Custom scoring weights (default: safety 40%, lifetime 25%, performance 15%, cost 20%)
        
    Returns:
        DesignScore with breakdown
    """
    if weights is None:
        weights = DEFAULT_SCORING_WEIGHTS
    
    # Step 1: Hard safety checks
    safety_check = check_hard_safety_constraints(
        peak_cell_temp_c=peak_cell_temp_c,
        max_cell_temp_limit_c=max_cell_temp_limit_c,
        charge_time_h=charge_time_h,
        max_charge_time_h=max_charge_time_h,
        pack_cost_inr=pack_cost_inr,
        max_pack_cost_inr=max_pack_cost_inr,
        usable_energy_wh=usable_energy_wh,
        min_usable_energy_wh=min_usable_energy_wh,
        chemistry=chemistry,
        cell_to_cell_delta_t=cell_to_cell_delta_t,
    )
    
    if not safety_check.passes:
        # Failed hard constraints - return zero score
        return DesignScore(
            total_score=0.0,
            safety_score=0.0,
            lifetime_score=0.0,
            performance_score=0.0,
            cost_score=0.0,
            passes_safety=False,
            violations=safety_check.violations,
            recommendation_reason="REJECTED: " + "; ".join(safety_check.violations),
        )
    
    # Step 2: Compute individual scores (0-100 scale)
    
    # SAFETY SCORE: Based on all safety margins
    # Higher margin = higher score
    safety_score = (
        min(100.0, safety_check.temp_margin_pct * 2.0) * 0.50 +  # Temperature most critical
        min(100.0, safety_check.time_margin_pct * 2.0) * 0.20 +
        min(100.0, safety_check.cost_margin_pct * 2.0) * 0.15 +
        min(100.0, safety_check.energy_margin_pct * 2.0) * 0.15
    )
    
    # LIFETIME SCORE: Based on SOH and thermal stress
    # Lower temperature = better lifetime
    # Higher SOH = better starting point
    temp_stress_factor = max(0.0, 1.0 - (peak_cell_temp_c - 25.0) / 40.0)  # Normalized: 25°C=1.0, 65°C=0.0
    lifetime_score = (soh * 100.0 * 0.6) + (temp_stress_factor * 100.0 * 0.4)
    
    # PERFORMANCE SCORE: Energy density and charge time
    # Normalize energy density (typical range 100-400 Wh/L)
    energy_density_norm = min(1.0, energy_density_wh_per_l / 400.0)
    # Normalize charge time (faster = better, but within limit)
    charge_time_norm = max(0.0, 1.0 - (charge_time_h / max_charge_time_h))
    performance_score = (energy_density_norm * 100.0 * 0.5) + (charge_time_norm * 100.0 * 0.5)
    
    # COST SCORE: Lower cost = higher score (within budget)
    # Normalize cost: at 50% of budget = 100 score, at 100% budget = 0 score
    cost_utilization = pack_cost_inr / max_pack_cost_inr if max_pack_cost_inr > 0 else 1.0
    cost_score = max(0.0, (1.0 - cost_utilization) * 100.0 * 2.0)  # Cheaper is better
    
    # Step 3: Weighted total score
    total_score = (
        safety_score * weights["safety"] +
        lifetime_score * weights["lifetime"] +
        performance_score * weights["performance"] +
        cost_score * weights["cost"]
    )
    
    # Generate recommendation reason
    reason_parts = []
    reason_parts.append(f"Safety margin: {safety_check.temp_margin_pct:.1f}%")
    reason_parts.append(f"Cost: ₹{pack_cost_inr:.0f} ({cost_utilization*100:.0f}% of budget)")
    reason_parts.append(f"Score: {total_score:.1f}/100")
    
    if safety_check.temp_margin_pct < 20:
        reason_parts.append("⚠ Low safety margin")
    if soh < 0.9:
        reason_parts.append(f"SOH: {soh*100:.0f}%")
    
    recommendation_reason = "PASSED: " + " | ".join(reason_parts)
    
    return DesignScore(
        total_score=total_score,
        safety_score=safety_score,
        lifetime_score=lifetime_score,
        performance_score=performance_score,
        cost_score=cost_score,
        passes_safety=True,
        violations=[],
        recommendation_reason=recommendation_reason,
    )


def rank_designs(
    designs: List[Dict],
    weights: Optional[Dict[str, float]] = None,
) -> List[Tuple[int, DesignScore, Dict]]:
    """
    Rank multiple designs by safety-first scoring.
    
    Args:
        designs: List of design dictionaries with all parameters
        weights: Optional custom scoring weights
        
    Returns:
        List of (index, score, design) tuples, sorted by total_score descending
    """
    scored = []
    
    for idx, design in enumerate(designs):
        score = score_design(
            peak_cell_temp_c=design["peak_cell_temp_c"],
            max_cell_temp_limit_c=design["max_cell_temp_limit_c"],
            charge_time_h=design["charge_time_h"],
            max_charge_time_h=design["max_charge_time_h"],
            pack_cost_inr=design["pack_cost_inr"],
            max_pack_cost_inr=design["max_pack_cost_inr"],
            usable_energy_wh=design["usable_energy_wh"],
            min_usable_energy_wh=design["min_usable_energy_wh"],
            energy_density_wh_per_l=design.get("energy_density_wh_per_l", 200.0),
            soh=design.get("soh", 1.0),
            chemistry=design.get("chemistry", "NMC"),
            cell_to_cell_delta_t=design.get("cell_to_cell_delta_t", 0.0),
            weights=weights,
        )
        scored.append((idx, score, design))
    
    # Sort by total_score descending (highest first)
    scored.sort(key=lambda x: x[1].total_score, reverse=True)
    
    return scored


# ═══════════════════════════════════════════════════════════════════════════
# UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════

def _test_design_scorer():
    """Test scoring logic."""
    print("Design Scorer Test:")
    print("=" * 70)
    
    # Test Case 1: Unsafe design (low margin)
    print("\n1. UNSAFE DESIGN (3.4% margin):")
    score1 = score_design(
        peak_cell_temp_c=43.5,
        max_cell_temp_limit_c=45.0,
        charge_time_h=1.8,
        max_charge_time_h=2.0,
        pack_cost_inr=2560,
        max_pack_cost_inr=4000,
        usable_energy_wh=72,
        min_usable_energy_wh=60,
        energy_density_wh_per_l=250,
        soh=1.0,
    )
    print(f"  Passes Safety: {score1.passes_safety}")
    print(f"  Total Score: {score1.total_score:.1f}")
    print(f"  Reason: {score1.recommendation_reason}")
    assert not score1.passes_safety, "Should fail safety check"
    
    # Test Case 2: Safe design
    print("\n2. SAFE DESIGN (20% margin):")
    score2 = score_design(
        peak_cell_temp_c=36.0,
        max_cell_temp_limit_c=45.0,
        charge_time_h=1.5,
        max_charge_time_h=2.0,
        pack_cost_inr=3200,
        max_pack_cost_inr=4000,
        usable_energy_wh=75,
        min_usable_energy_wh=60,
        energy_density_wh_per_l=280,
        soh=1.0,
    )
    print(f"  Passes Safety: {score2.passes_safety}")
    print(f"  Total Score: {score2.total_score:.1f}")
    print(f"  Safety: {score2.safety_score:.1f}, Lifetime: {score2.lifetime_score:.1f}")
    print(f"  Performance: {score2.performance_score:.1f}, Cost: {score2.cost_score:.1f}")
    print(f"  Reason: {score2.recommendation_reason}")
    assert score2.passes_safety, "Should pass safety check"
    assert score2.total_score > 50, "Should have decent score"
    
    # Test Case 3: Ranking multiple designs
    print("\n3. RANKING MULTIPLE DESIGNS:")
    designs = [
        {"name": "Baseline", "peak_cell_temp_c": 43.5, "max_cell_temp_limit_c": 45, "charge_time_h": 1.8, "max_charge_time_h": 2.0, "pack_cost_inr": 2560, "max_pack_cost_inr": 4000, "usable_energy_wh": 72, "min_usable_energy_wh": 60, "energy_density_wh_per_l": 250},
        {"name": "Option A", "peak_cell_temp_c": 36.0, "max_cell_temp_limit_c": 45, "charge_time_h": 1.5, "max_charge_time_h": 2.0, "pack_cost_inr": 3200, "max_pack_cost_inr": 4000, "usable_energy_wh": 75, "min_usable_energy_wh": 60, "energy_density_wh_per_l": 280},
        {"name": "Option B", "peak_cell_temp_c": 34.2, "max_cell_temp_limit_c": 45, "charge_time_h": 1.7, "max_charge_time_h": 2.0, "pack_cost_inr": 3810, "max_pack_cost_inr": 4000, "usable_energy_wh": 75, "min_usable_energy_wh": 60, "energy_density_wh_per_l": 280},
    ]
    
    ranked = rank_designs(designs)
    for idx, (orig_idx, score, design) in enumerate(ranked):
        print(f"  #{idx+1}: {design['name']} - Score: {score.total_score:.1f}, Safe: {score.passes_safety}")
    
    # Best design should be Option A or B (both safe), not Baseline (unsafe)
    best_design_name = designs[ranked[0][0]]["name"]
    assert best_design_name != "Baseline", "Baseline should not be recommended"
    
    print("\n✓ All tests passed")


if __name__ == "__main__":
    _test_design_scorer()
