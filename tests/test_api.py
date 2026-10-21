"""
Unit tests for FastAPI endpoints: /health, /predict, /recommend, /validate
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert data["model_loaded"] is True

def test_predict_endpoint_multi_design():
    payload = {
        "cell_type": "18650 NMC 2.5 Ah",
        "series_cells": 4,
        "parallel_strings": 2,
        "charge_rate_c": 1.0,
        "ambient_temp_c": 38.0,
        "max_cell_temp_c": 45.0,
        "min_usable_energy_wh": 60.0,
        "max_charge_time_h": 2.0,
        "max_pack_cost_inr": 4000.0,
        "bms_thermistor_position": "c",
        "designs": [
            {"id": "Baseline", "cooling_type": "none", "bms_thermal_derating": False},
            {"id": "Option A", "cooling_type": "spr", "bms_thermal_derating": False},
            {"id": "Option B", "cooling_type": "spr", "bms_thermal_derating": True},
        ]
    }
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "designs" in data
    designs = data["designs"]
    assert "Baseline" in designs
    assert "Option A" in designs
    assert "Option B" in designs

    # Check structure of Baseline prediction
    baseline = designs["Baseline"]
    assert "ml" in baseline
    assert "physics" in baseline
    assert "peak_cell_temp_c" in baseline["ml"]["regression"]
    assert "charge_time_h" in baseline["ml"]["regression"]
    assert "usable_energy_wh" in baseline["ml"]["regression"]
    assert "pack_cost_inr" in baseline["ml"]["regression"]
    assert "uncertainty" in baseline["ml"]
    assert "meets_all_requirements" in baseline["ml"]
    assert "fail_reasons" in baseline["ml"]

    # Verify Baseline peak temp ~48°C (violates max 45°C)
    assert baseline["physics"]["peak_cell_temp_c"] > 45.0
    assert "temperature" in baseline["physics"]["fail_reasons"]

    # Option B meets all
    assert designs["Option B"]["physics"]["meets_all_requirements"] is True

def test_recommend_endpoint():
    payload = {
        "min_usable_energy_wh": 60.0,
        "max_charge_time_h": 2.0,
        "max_pack_cost_inr": 4000.0,
        "max_cell_temp_c": 45.0,
        "ambient_temp_c": 38.0,
        "cell_type": "18650 NMC 2.5 Ah",
        "bms_thermistor_position": "c",
        "top_k": 3,
    }
    response = client.post("/recommend", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["count"] <= 3
    assert len(data["recommendations"]) > 0
    first = data["recommendations"][0]
    assert "series_cells" in first
    assert "parallel_strings" in first
    assert "pack_cost_inr" in first
    assert "explanation" in first

def test_validate_json_endpoint():
    payload = {
        "csv_content": "time,temperature\n0,38\n300,40.2\n600,41.8\n900,42.9\n1200,43.7\n1500,44.2\n1800,44.6",
        "cell_type": "18650 NMC 2.5 Ah",
        "series_cells": 4,
        "parallel_strings": 2,
        "charge_rate_c": 1.0,
        "ambient_temp_c": 38.0,
        "cooling_type": "spr",
        "bms_thermal_derating": True,
    }
    response = client.post("/validate-json", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "validation" in data
    val = data["validation"]
    assert "mae_c" in val
    assert "rmse_c" in val
    assert "calibrated_rth" in val
    assert "comparison" in val
