"""
Unit tests for the physics model against the screenshots and known requirements.
"""

import pytest
from ml.physics_model import simulate_pack

def test_screenshot_baseline_values():
    """
    Screenshot Baseline:
    4S2P 18650 NMC 2.5Ah, 1C charge, 38°C ambient, max 45°C,
    Cooling: Passive enclosure ('none'), BMS derating: False
    Expected:
    - Pack: 14.4 V / 5.0 Ah
    - Usable energy: ~65 Wh (64.8 Wh)
    - Effective charge rate: 1.00 C (5.0 A)
    - Heat at charge: 2.0 W
    - Peak cell temp: ~48.2 °C
    - Charge time: 1.10 h
    - Mass: ~0.53 kg (0.526 kg)
    - Cost: ₹1,840
    - Fails 1 requirement (temperature > 45°C)
    """
    res = simulate_pack(
        cell_type="18650 NMC 2.5 Ah",
        series_cells=4,
        parallel_strings=2,
        charge_rate_c=1.0,
        ambient_temp_c=38.0,
        max_cell_temp_c=45.0,
        min_usable_energy_wh=60.0,
        max_charge_time_h=2.0,
        max_pack_cost_inr=4000.0,
        bms_thermistor_position="c",
        cooling_type="none",
        bms_thermal_derating=False,
    )
    assert round(res.nominal_voltage_v, 1) == 14.4
    assert round(res.nominal_capacity_ah, 1) == 5.0
    assert round(res.usable_energy_wh) == 65
    assert round(res.pack_cost_inr) == 1840
    assert round(res.mass_kg, 2) == 0.53
    assert round(res.heat_at_charge_w, 1) == 2.0
    assert round(res.peak_cell_temp_c, 1) == 48.2
    assert round(res.charge_time_h, 2) == 1.10
    assert res.effective_charge_rate_c == 1.0
    assert not res.derated
    assert not res.meets_all_requirements
    assert "temperature" in res.fail_reasons

def test_screenshot_option_a_values():
    """
    Screenshot Option A:
    4S2P, 1C, 38°C ambient, cooling: Aluminium spreader ('spr'), derating: False
    Expected:
    - Peak cell temp: ~45.8 °C
    - Charge time: 1.10 h
    - Cost: ₹1,990
    - Mass: ~0.59 kg
    - Fails 1 requirement (temperature > 45°C)
    """
    res = simulate_pack(
        cell_type="18650 NMC 2.5 Ah",
        series_cells=4,
        parallel_strings=2,
        charge_rate_c=1.0,
        ambient_temp_c=38.0,
        max_cell_temp_c=45.0,
        min_usable_energy_wh=60.0,
        max_charge_time_h=2.0,
        max_pack_cost_inr=4000.0,
        bms_thermistor_position="c",
        cooling_type="spr",
        bms_thermal_derating=False,
    )
    assert round(res.peak_cell_temp_c, 1) == 45.8
    assert round(res.charge_time_h, 2) == 1.10
    assert round(res.pack_cost_inr) == 1990
    assert round(res.mass_kg, 2) == 0.59
    assert not res.meets_all_requirements
    assert "temperature" in res.fail_reasons

def test_screenshot_option_b_values():
    """
    Screenshot Option B:
    4S2P, 1C, 38°C ambient, cooling: Aluminium spreader ('spr'), derating: True
    Expected:
    - Derated charge rate: ~0.91 C (4.6 A)
    - Heat at charge: ~1.7 W
    - Peak cell temp: ~44.7 °C (<= 45°C)
    - Charge time: ~1.18 h
    - Cost: ₹2,240
    - Meets all requirements: True
    """
    res = simulate_pack(
        cell_type="18650 NMC 2.5 Ah",
        series_cells=4,
        parallel_strings=2,
        charge_rate_c=1.0,
        ambient_temp_c=38.0,
        max_cell_temp_c=45.0,
        min_usable_energy_wh=60.0,
        max_charge_time_h=2.0,
        max_pack_cost_inr=4000.0,
        bms_thermistor_position="c",
        cooling_type="spr",
        bms_thermal_derating=True,
    )
    assert round(res.effective_charge_rate_c, 2) == 0.91
    assert round(res.heat_at_charge_w, 1) == 1.7
    assert round(res.peak_cell_temp_c, 1) == 44.7
    assert round(res.charge_time_h, 2) == 1.18
    assert round(res.pack_cost_inr) == 2240
    assert res.derated
    assert res.meets_all_requirements
    assert len(res.fail_reasons) == 0
