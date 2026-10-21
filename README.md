# Battery Pack Design Platform (with ML Surrogate Engine)

A digital battery pack engineering and validation platform featuring an integrated **Machine Learning (ML) surrogate modeling layer**, physics-informed ground-truth simulation, cost-optimal design recommendation, and experimental data calibration.

---

## 🚀 Key Features

### 1. **Integrated ML Surrogate Model & Uncertainty Bounds**
- **Dual-Engine Architecture**: Real-time comparison between first-principles physics simulator and ML surrogate predictions.
- **Uncertainty Quantification**: Displays ±1.96σ confidence intervals for peak temperature, charge time, heat generation, usable energy, and pack cost.
- **High Surrogate Accuracy**: $R^2 > 0.998$ across continuous electro-thermal parameters; peak temperature MAE $< 0.74^\circ\text{C}$.
- **Zero UI Rewrite**: Elegant integration into the existing Overview, Electrical & Protection, Analysis, and Validation tabs.
- **Graceful Offline Fallback**: Live status badge in the header (`ML Online` / `ML Offline`) falling back seamlessly to client-side physics if the backend is stopped.

### 2. **AI Design Recommender**
- Searches over 1,000+ pack configurations across series strings ($S$), parallel cells ($P$), charge rates ($C$), cooling systems, and BMS derating.
- Returns the **top 3 cheapest viable configurations** that strictly meet all five user constraints.
- Includes a **"Apply to Baseline Design"** one-click button to configure all sidebar controls automatically.

### 3. **Experimental Validation & Model Calibration**
- Import measured battery charge test CSV data (`time(s), temperature(°C)`).
- Visual comparison chart overlaying **Physical Simulation (dashed blue)**, **ML Calibrated Model (solid green)**, and **Measured Test Points (red dots)**.
- Fits effective thermal resistance ($R_{th}$) to diagnose thermal grease contact quality, interface resistance, and pack thermal mass discrepancies.

### 4. **Analysis & Safety Margins (Bug Fixed)**
- Fixed the previous `NaN%` issue in **Safety Margins** (Cost and Energy margins) with defensive numeric guards against undefined values and divide-by-zero.

---

## 📁 Project Structure

```
tataelexi_llm_model/
├── backend/
│   ├── __init__.py
│   └── main.py                     # FastAPI backend (REST API, CORS, Pydantic schemas)
├── data/
│   └── synthetic_dataset.csv       # 55,000+ physics-labeled samples with measurement noise
├── ml/
│   ├── __init__.py
│   ├── physics_model.py            # Ground-truth simulator port (electro-thermal ODE + BMS)
│   ├── surrogate.py                # SurrogateModelBundle (preprocessor + regressors + classifiers)
│   ├── generate_data.py            # Synthetic dataset generator with Latin Hypercube sampling
│   ├── train.py                    # Training pipeline comparing GBR vs MLP, evaluation & plots
│   ├── recommender.py              # Design space search engine for cheapest valid packs
│   └── calibrator.py               # Curve fitting and residual error calibration from CSV
├── models/
│   └── battery_pack_model.joblib   # Trained and serialized surrogate model bundle (6.18 MB)
├── reports/
│   ├── evaluation_metrics.json     # Comprehensive test and validation metrics JSON
│   ├── evaluation_report.md        # Detailed evaluation report
│   └── predicted_vs_actual.png     # Scatter plots of actual vs predicted across all 8 targets
├── tests/
│   ├── __init__.py
│   ├── test_physics_model.py       # Unit tests verifying against screenshot baseline values
│   └── test_api.py                 # Unit tests verifying API endpoints and response schemas
├── docs/                           # Documentation assets
├── index.html                      # Single-page web application (frontend)
├── sample-temperature-data.csv     # Example measured validation CSV
├── requirements.txt                # Python dependencies
├── run_backend.bat                 # One-command batch script to start FastAPI backend
├── start.ps1                       # One-command PowerShell launcher (backend + browser)
└── README.md                       # Project documentation
```

---

## ⚡ Quick Start (One Command)

### Option A: PowerShell Launcher
```powershell
.\start.ps1
```
This automatically verifies the model, launches the FastAPI server at `http://localhost:8000`, and opens `index.html` in your default browser.

### Option B: Windows Batch Launcher
Double-click `run_backend.bat` or run:
```cmd
run_backend.bat
```
Then double-click `index.html` to open the app.

---

## 🛠️ Manual Setup & Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Generate Synthetic Dataset (Optional - pre-generated included)
To regenerate 55,000 synthetic samples:
```bash
python -m ml.generate_data
```

### 3. Train Surrogate Models & Generate Reports
```bash
python -m ml.train
```

### 4. Run Unit Tests
```bash
python -m pytest tests/
```
All 7 unit tests will execute, checking:
1. Ground-truth physics simulator matches screenshot values (4S2P Baseline, Option A, Option B).
2. FastAPI `/health` endpoint response and model loading.
3. `/predict` multi-design response schema and uncertainty ranges.
4. `/recommend` configuration search.
5. `/validate-json` calibration and curve generation.

### 5. Start the FastAPI Backend
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 📊 Model Evaluation Summary

The surrogate modeling pipeline compared **Gradient Boosting (HistGradientBoosting)** against a **Multi-Layer Perceptron (MLP)** on an 80/10/10 train/val/test split across 55,000 samples.

| Target Parameter | Model Selected | Test MAE | Test RMSE | $R^2$ Score | Uncertainty (±1σ) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Peak Cell Temp (°C)** | MLP | 0.7397 °C | 1.0545 °C | **0.9986** | ±1.05 °C |
| **Charge Time (h)** | MLP | 0.0417 h | 0.1054 h | **0.9963** | ±0.11 h |
| **Heat at Charge (W)** | MLP | 2.8804 W | 4.2328 W | **0.9978** | ±4.23 W |
| **Effective C-Rate (C)** | MLP | 0.0123 C | 0.0224 C | **0.9992** | ±0.02 C |
| **Usable Energy (Wh)** | HistGradientBoosting | 1.8800 Wh | 2.4570 Wh | **1.0000** | ±2.46 Wh |
| **Pack Cost (₹)** | HistGradientBoosting | ₹77.63 | ₹100.19 | **0.9999** | ±₹100.17 |
| **Mass (kg)** | HistGradientBoosting | 0.0214 kg | 0.0285 kg | **0.9999** | ±0.03 kg |
| **Energy Density (Wh/L)**| HistGradientBoosting | 0.0002 Wh/L| 0.0002 Wh/L| **1.0000** | ±0.00 Wh/L |

### Classification (`meets_all_requirements`):
- **Accuracy**: 98.67%
- **F1 Score**: 0.6971
- **Constraint-Specific F1 Scores**: Temperature: 0.9539, Charge Time: 0.9726, Cost: 0.9911, Energy: 0.9898, C-Rate Rating: 0.9926.

Visual scatter plots are available at [`reports/predicted_vs_actual.png`](reports/predicted_vs_actual.png).

---

## 🌐 API Reference

Interactive Swagger documentation is available at `http://localhost:8000/docs`.

### 1. `POST /predict`
Evaluates single or multiple pack configurations.
```json
{
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
    {"id": "Baseline", "cooling_type": "none", "bms_thermal_derating": false},
    {"id": "Option A", "cooling_type": "spr", "bms_thermal_derating": false},
    {"id": "Option B", "cooling_type": "spr", "bms_thermal_derating": true}
  ]
}
```

### 2. `POST /recommend`
Returns the top 3 cheapest viable configurations meeting all specified requirements.

### 3. `POST /validate` or `POST /validate-json`
Accepts measured CSV points (`time,temperature`) and calculates baseline error, calibrated thermal resistance ($R_{th}$), and diagnostic explanations.

### 4. `GET /health`
Returns service status, model load state, and uptime.
