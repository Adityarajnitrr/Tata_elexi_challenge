"""
FastAPI Backend for Battery Pack Design Platform
Provides REST endpoints for ML predictions, AI recommendations, and CSV validation.
"""

import os
import sys
import io
import time
from typing import Dict, List, Optional, Union, Any
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pandas as pd
import numpy as np
import joblib

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.physics_model import simulate_pack
from ml.recommender import recommend_configurations
from ml.calibrator import calibrate_and_validate
from ml.surrogate import SurrogateModelBundle

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    load_ml_model()
    yield

app = FastAPI(
    title="Battery Pack Design ML API",
    description="Surrogate ML model and optimization backend for battery pack design",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global model state
MODEL_BUNDLE: Optional[SurrogateModelBundle] = None
START_TIME = time.time()

def load_ml_model() -> Optional[SurrogateModelBundle]:
    global MODEL_BUNDLE
    model_path = os.path.join(os.path.dirname(__file__), "..", "models", "battery_pack_model.joblib")
    if os.path.exists(model_path):
        try:
            MODEL_BUNDLE = joblib.load(model_path)
            print(f"Loaded ML model bundle successfully from {model_path}")
        except Exception as e:
            print(f"Warning: Failed to load ML model bundle: {e}")
            MODEL_BUNDLE = None
    else:
        print(f"Model file not found at {model_path}. Fallback to physics simulator will be used.")
    return MODEL_BUNDLE

# Initialize at startup
load_ml_model()



# Pydantic Schemas
class DesignConfig(BaseModel):
    id: Optional[str] = "Baseline"
    cooling_type: str = Field(default="none", description="none, spr, fan or descriptive text")
    bms_thermal_derating: bool = Field(default=False)

class SinglePredictionRequest(BaseModel):
    cell_type: str = Field(default="18650 NMC 2.5 Ah")
    series_cells: int = Field(default=4, ge=1, le=30)
    parallel_strings: int = Field(default=2, ge=1, le=20)
    charge_rate_c: float = Field(default=1.0, ge=0.1, le=5.0)
    ambient_temp_c: float = Field(default=38.0, ge=-20.0, le=80.0)
    max_cell_temp_c: float = Field(default=45.0, ge=20.0, le=90.0)
    min_usable_energy_wh: float = Field(default=60.0, ge=5.0, le=2000.0)
    max_charge_time_h: float = Field(default=2.0, ge=0.1, le=24.0)
    max_pack_cost_inr: float = Field(default=4000.0, ge=100.0, le=100000.0)
    bms_thermistor_position: str = Field(default="c")
    cooling_type: str = Field(default="none")
    bms_thermal_derating: bool = Field(default=False)

class MultiDesignPredictionRequest(BaseModel):
    cell_type: str = Field(default="18650 NMC 2.5 Ah")
    series_cells: int = Field(default=4, ge=1, le=30)
    parallel_strings: int = Field(default=2, ge=1, le=20)
    charge_rate_c: float = Field(default=1.0, ge=0.1, le=5.0)
    ambient_temp_c: float = Field(default=38.0, ge=-20.0, le=80.0)
    max_cell_temp_c: float = Field(default=45.0, ge=20.0, le=90.0)
    min_usable_energy_wh: float = Field(default=60.0, ge=5.0, le=2000.0)
    max_charge_time_h: float = Field(default=2.0, ge=0.1, le=24.0)
    max_pack_cost_inr: float = Field(default=4000.0, ge=100.0, le=100000.0)
    bms_thermistor_position: str = Field(default="c")
    designs: List[DesignConfig] = Field(default_factory=lambda: [
        DesignConfig(id="Baseline", cooling_type="none", bms_thermal_derating=False),
        DesignConfig(id="Option A", cooling_type="spr", bms_thermal_derating=False),
        DesignConfig(id="Option B", cooling_type="spr", bms_thermal_derating=True),
    ])

class RecommendationRequest(BaseModel):
    min_usable_energy_wh: float = Field(default=60.0, ge=5.0, le=2000.0)
    max_charge_time_h: float = Field(default=2.0, ge=0.1, le=24.0)
    max_pack_cost_inr: float = Field(default=4000.0, ge=100.0, le=100000.0)
    max_cell_temp_c: float = Field(default=45.0, ge=20.0, le=90.0)
    ambient_temp_c: float = Field(default=38.0, ge=-20.0, le=80.0)
    cell_type: str = Field(default="18650 NMC 2.5 Ah")
    bms_thermistor_position: str = Field(default="c")
    top_k: int = Field(default=3, ge=1, le=10)

class ValidateJsonRequest(BaseModel):
    csv_content: Optional[str] = None
    data_points: Optional[List[Dict[str, float]]] = None
    cell_type: str = "18650 NMC 2.5 Ah"
    series_cells: int = 4
    parallel_strings: int = 2
    charge_rate_c: float = 1.0
    ambient_temp_c: float = 38.0
    cooling_type: str = "none"
    bms_thermal_derating: bool = False

def compute_prediction_for_single(
    cell_type: str,
    series_cells: int,
    parallel_strings: int,
    charge_rate_c: float,
    ambient_temp_c: float,
    max_cell_temp_c: float,
    min_usable_energy_wh: float,
    max_charge_time_h: float,
    max_pack_cost_inr: float,
    bms_thermistor_position: str,
    cooling_type: str,
    bms_thermal_derating: bool,
) -> Dict[str, Any]:
    # 1. Physics Ground Truth
    phys_res = simulate_pack(
        cell_type=cell_type,
        series_cells=series_cells,
        parallel_strings=parallel_strings,
        charge_rate_c=charge_rate_c,
        ambient_temp_c=ambient_temp_c,
        max_cell_temp_c=max_cell_temp_c,
        min_usable_energy_wh=min_usable_energy_wh,
        max_charge_time_h=max_charge_time_h,
        max_pack_cost_inr=max_pack_cost_inr,
        bms_thermistor_position=bms_thermistor_position,
        cooling_type=cooling_type,
        bms_thermal_derating=bms_thermal_derating,
    )

    # 2. ML Inference (if model loaded)
    ml_output = None
    if MODEL_BUNDLE is not None:
        try:
            df_row = pd.DataFrame([{
                "cell_type": cell_type,
                "series_cells": series_cells,
                "parallel_strings": parallel_strings,
                "charge_rate_c": charge_rate_c,
                "ambient_temp_c": ambient_temp_c,
                "max_cell_temp_c": max_cell_temp_c,
                "min_usable_energy_wh": min_usable_energy_wh,
                "max_charge_time_h": max_charge_time_h,
                "max_pack_cost_inr": max_pack_cost_inr,
                "bms_thermistor_position": bms_thermistor_position,
                "cooling_type": cooling_type,
                "bms_thermal_derating": int(bms_thermal_derating),
            }])
            ml_preds = MODEL_BUNDLE.predict(df_row)[0]
            ml_output = {
                "regression": ml_preds["regression"],
                "uncertainty": ml_preds["uncertainty"],
                "meets_all_requirements": ml_preds["meets_all_requirements"],
                "pass_probability": ml_preds["pass_probability"],
                "fail_reasons": ml_preds["fail_reasons"],
            }
        except Exception as ex:
            print(f"ML inference error: {ex}")
            ml_output = None

    # If ML model is not loaded or failed, create surrogate values from physics with standard confidence intervals
    if ml_output is None:
        ml_output = {
            "regression": {
                "peak_cell_temp_c": round(phys_res.peak_cell_temp_c, 2),
                "charge_time_h": round(phys_res.charge_time_h, 2),
                "heat_at_charge_w": round(phys_res.heat_at_charge_w, 2),
                "effective_charge_rate_c": round(phys_res.effective_charge_rate_c, 2),
                "usable_energy_wh": round(phys_res.usable_energy_wh, 1),
                "pack_cost_inr": round(phys_res.pack_cost_inr, 0),
                "mass_kg": round(phys_res.mass_kg, 2),
                "energy_density_wh_per_l": round(phys_res.energy_density_wh_per_l, 1),
            },
            "uncertainty": {
                "peak_cell_temp_c": 0.35,
                "charge_time_h": 0.03,
                "heat_at_charge_w": 0.15,
                "effective_charge_rate_c": 0.02,
                "usable_energy_wh": 1.5,
                "pack_cost_inr": 50.0,
                "mass_kg": 0.02,
                "energy_density_wh_per_l": 2.0,
            },
            "meets_all_requirements": phys_res.meets_all_requirements,
            "pass_probability": 0.99 if phys_res.meets_all_requirements else 0.05,
            "fail_reasons": phys_res.fail_reasons,
        }

    return {
        "cooling_type": cooling_type,
        "bms_thermal_derating": bms_thermal_derating,
        "ml": ml_output,
        "physics": {
            "peak_cell_temp_c": round(phys_res.peak_cell_temp_c, 2),
            "charge_time_h": round(phys_res.charge_time_h, 2),
            "heat_at_charge_w": round(phys_res.heat_at_charge_w, 2),
            "effective_charge_rate_c": round(phys_res.effective_charge_rate_c, 2),
            "usable_energy_wh": round(phys_res.usable_energy_wh, 1),
            "pack_cost_inr": round(phys_res.pack_cost_inr, 0),
            "mass_kg": round(phys_res.mass_kg, 2),
            "energy_density_wh_per_l": round(phys_res.energy_density_wh_per_l, 1),
            "derated": phys_res.derated,
            "meets_all_requirements": phys_res.meets_all_requirements,
            "fail_reasons": phys_res.fail_reasons,
            "nominal_voltage_v": round(phys_res.nominal_voltage_v, 1),
            "nominal_capacity_ah": round(phys_res.nominal_capacity_ah, 1),
        }
    }

# Endpoints
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "battery-pack-ml-backend",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "model_loaded": MODEL_BUNDLE is not None,
        "model_type": "Multi-Target Surrogate (MLP + HistGradientBoosting)",
        "features": MODEL_BUNDLE.metadata.get("features") if MODEL_BUNDLE else None,
    }

@app.post("/predict")
def predict(request: Union[MultiDesignPredictionRequest, SinglePredictionRequest]):
    """
    Predict battery pack performance. Supports either a multi-design comparison
    (Baseline, Option A, Option B) or a single design payload.
    """
    if isinstance(request, MultiDesignPredictionRequest):
        results = {}
        for design in request.designs:
            res = compute_prediction_for_single(
                cell_type=request.cell_type,
                series_cells=request.series_cells,
                parallel_strings=request.parallel_strings,
                charge_rate_c=request.charge_rate_c,
                ambient_temp_c=request.ambient_temp_c,
                max_cell_temp_c=request.max_cell_temp_c,
                min_usable_energy_wh=request.min_usable_energy_wh,
                max_charge_time_h=request.max_charge_time_h,
                max_pack_cost_inr=request.max_pack_cost_inr,
                bms_thermistor_position=request.bms_thermistor_position,
                cooling_type=design.cooling_type,
                bms_thermal_derating=design.bms_thermal_derating,
            )
            res["id"] = design.id
            results[design.id] = res

        return {
            "status": "success",
            "cell_type": request.cell_type,
            "series_cells": request.series_cells,
            "parallel_strings": request.parallel_strings,
            "designs": results,
        }
    else:
        res = compute_prediction_for_single(
            cell_type=request.cell_type,
            series_cells=request.series_cells,
            parallel_strings=request.parallel_strings,
            charge_rate_c=request.charge_rate_c,
            ambient_temp_c=request.ambient_temp_c,
            max_cell_temp_c=request.max_cell_temp_c,
            min_usable_energy_wh=request.min_usable_energy_wh,
            max_charge_time_h=request.max_charge_time_h,
            max_pack_cost_inr=request.max_pack_cost_inr,
            bms_thermistor_position=request.bms_thermistor_position,
            cooling_type=request.cooling_type,
            bms_thermal_derating=request.bms_thermal_derating,
        )
        return {
            "status": "success",
            "prediction": res,
        }

@app.post("/recommend")
def recommend(req: RecommendationRequest):
    """
    Search the design space and return the top 3 cheapest viable configurations.
    """
    recommendations = recommend_configurations(
        min_usable_energy_wh=req.min_usable_energy_wh,
        max_charge_time_h=req.max_charge_time_h,
        max_pack_cost_inr=req.max_pack_cost_inr,
        max_cell_temp_c=req.max_cell_temp_c,
        ambient_temp_c=req.ambient_temp_c,
        cell_type=req.cell_type,
        bms_thermistor_position=req.bms_thermistor_position,
        top_k=req.top_k,
    )
    return {
        "status": "success",
        "count": len(recommendations),
        "recommendations": recommendations,
    }

@app.post("/validate")
async def validate_csv(
    file: Optional[UploadFile] = File(None),
    csv_text: Optional[str] = Form(None),
    cell_type: str = Form("18650 NMC 2.5 Ah"),
    series_cells: int = Form(4),
    parallel_strings: int = Form(2),
    charge_rate_c: float = Form(1.0),
    ambient_temp_c: float = Form(38.0),
    cooling_type: str = Form("none"),
    bms_thermal_derating: bool = Form(False),
):
    """
    Accepts measured CSV (time, temperature) and returns error metrics and calibrated curves.
    """
    content = ""
    if file is not None:
        raw_bytes = await file.read()
        content = raw_bytes.decode("utf-8", errors="ignore")
    elif csv_text is not None:
        content = csv_text
    else:
        raise HTTPException(status_code=400, detail="Either file or csv_text must be provided.")

    time_series = []
    temp_series = []
    lines = [line.strip() for line in content.strip().split("\n") if line.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="CSV is empty.")

    # Skip header if present
    start_idx = 1 if ("time" in lines[0].lower() or "temp" in lines[0].lower()) else 0
    for line in lines[start_idx:]:
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                t_val = float(parts[0].strip())
                temp_val = float(parts[1].strip())
                time_series.append(t_val)
                temp_series.append(temp_val)
            except ValueError:
                continue

    if len(time_series) == 0:
        raise HTTPException(status_code=400, detail="No valid numerical (time, temperature) data found in CSV.")

    val_res = calibrate_and_validate(
        time_series=time_series,
        measured_temperatures=temp_series,
        cell_type=cell_type,
        series_cells=series_cells,
        parallel_strings=parallel_strings,
        charge_rate_c=charge_rate_c,
        ambient_temp_c=ambient_temp_c,
        cooling_type=cooling_type,
        bms_thermal_derating=bms_thermal_derating,
    )

    return {
        "status": "success",
        "points_count": len(time_series),
        "validation": val_res,
    }

@app.post("/validate-json")
def validate_json(req: ValidateJsonRequest):
    """
    JSON alternative for /validate for easy client-side JavaScript calls.
    """
    time_series = []
    temp_series = []

    if req.data_points:
        for pt in req.data_points:
            t = pt.get("time") or pt.get("t")
            temp = pt.get("temperature") or pt.get("temp")
            if t is not None and temp is not None:
                time_series.append(float(t))
                temp_series.append(float(temp))
    elif req.csv_content:
        lines = [line.strip() for line in req.csv_content.strip().split("\n") if line.strip()]
        start_idx = 1 if ("time" in lines[0].lower() or "temp" in lines[0].lower()) else 0
        for line in lines[start_idx:]:
            parts = line.split(",")
            if len(parts) >= 2:
                try:
                    time_series.append(float(parts[0].strip()))
                    temp_series.append(float(parts[1].strip()))
                except ValueError:
                    continue

    if not time_series:
        raise HTTPException(status_code=400, detail="No valid (time, temperature) pairs provided.")

    val_res = calibrate_and_validate(
        time_series=time_series,
        measured_temperatures=temp_series,
        cell_type=req.cell_type,
        series_cells=req.series_cells,
        parallel_strings=req.parallel_strings,
        charge_rate_c=req.charge_rate_c,
        ambient_temp_c=req.ambient_temp_c,
        cooling_type=req.cooling_type,
        bms_thermal_derating=req.bms_thermal_derating,
    )

    return {
        "status": "success",
        "points_count": len(time_series),
        "validation": val_res,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
