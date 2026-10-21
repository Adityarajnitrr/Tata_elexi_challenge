# Battery Energy System Design Platform

A comprehensive web-based tool for designing and validating battery pack systems, built for the hackathon challenge: "Reusable Digital Platform for Designing Battery Energy System".

## Features

### 1. **Overview Tab**
- **3-option comparison**: Baseline, Option A, Option B
- Real-time pass/fail indicators
- Interactive pack configuration (cell type, S/P, charge rate, temperature limits)
- Cell temperature heat map with visual indicators
- Temperature-vs-time charging curves
- Design check log with errors, warnings, and info messages
- Requirement traceability matrix
- Smart recommendations based on cost optimization

### 2. **Validation Tab**
- Import measured temperature data via CSV
- Overlay measured vs. simulated data
- Calculate model error percentage
- Visual comparison charts
- Diagnostic guidance for high errors

**CSV Format:**
```
time,temperature
0,38
300,40.5
600,42.1
...
```

### 3. **Electrical & Protection Tab**
- Per-cell current calculations
- I²R heating analysis (cell + busbar links)
- Fuse and busbar sizing recommendations
- BMS protection limits table (OVP/UVP/OCP/OTP)
- All calculations show formulas and assumptions

### 4. **Analysis Tab**
- **Cost Breakdown**: Visual bars showing cells, cooling, BMS, enclosure costs
- **Safety Margins**: Color-coded bars for temperature, time, cost, energy margins
  - Green: >20% margin (safe)
  - Yellow: 10-20% margin (warning)
  - Red: <10% margin (critical)
- **Sensitivity Analysis**: Pack temperature vs. ambient temperature curves
- **Cell Variation & Ageing**:
  - Toggle ±10% resistance variation
  - Toggle 2x resistance for end-of-life simulation
  - Monte Carlo worst-case analysis

### 5. **Assumptions Tab**
- Complete list of all assumptions with explanations
- Data source references
- Safety precautions and limitations
- Export report functionality:
  - **JSON export**: Complete design data, requirements, results
  - **PDF export**: Print-to-PDF guidance for comprehensive reports

## Key Innovations

### 1. Traceability
Every result traces back to:
- Requirement (e.g., R1: Usable energy ≥ 60 Wh)
- Component (e.g., 18650 NMC cell, 2.5 Ah)
- Assumption (e.g., 90% usable capacity)
- Model (e.g., Electrical model: Eu = Vn × Ah × 0.9)
- Evidence source (e.g., Datasheet, thermal model)

### 2. Interface Conflict Detection
Automatically detects impossible-to-resolve conflicts:
- Example: Both C-rate AND thermal limit violated
- Suggests: Multi-parameter changes needed (can't fix with single adjustment)

### 3. Real-time Performance
- All calculations complete in <200ms
- Instant feedback on parameter changes
- No backend required - runs entirely in browser

### 4. Engineering Quality
- All formulas documented
- Physical units clearly labeled
- Assumptions explicitly stated
- Limitations prominently displayed

## Technical Details

### Thermal Model
- **Type**: Lumped first-order
- **Heat generation**: Q = I²R (ohmic only)
- **Differential equation**: dT/dt = (Q - (T-Ta)/Rth) / (m·Cp)
- **Parameters**:
  - Cell resistance: From datasheet
  - Link resistance: 2 mΩ per busbar/weld
  - Thermal resistance: 9 K/W (passive), 5.5 K/W (spreader), 3 K/W (fan)
  - Heat capacity: 1000 J/kg·K

### Electrical Model
- **Nominal voltage**: Cell voltage × series count
- **Capacity**: Cell Ah × parallel count
- **Usable energy**: 0.9 × Vn × Ah (90% depth of discharge)
- **Charge time**: 0.8/C (CC phase) + 0.3h (CV taper)

### BMS Derating Algorithm
1. Start with user-specified C-rate
2. Calculate thermistor reading (includes spatial gradient)
3. If thermistor > limit: reduce C-rate by 3%
4. Repeat until thermistor ≤ limit or C < 0.1
5. Flag if derating doesn't prevent hot-spot violation

## Validation Guidelines

1. **Model accuracy**: ±3°C typical for well-mixed packs
2. **If error > 3°C**: Check thermal mass, verify Rth, review contact resistance
3. **Always test physical prototypes** before production
4. **Use CFD** for detailed hot-spot analysis in high-power applications

## Limitations

- Screening tool, not safety certification
- Lumped thermal model (single temperature per cell)
- Does not model: entropic heating, vibration, contact resistance drift
- Mechanical design (housing, mounting) not covered
- Cost estimates are approximate (₹, 2024 India)

## Usage

1. **Open** `index.html` in a modern browser
2. **Configure** requirements in the left sidebar
3. **Compare** designs in the Overview tab
4. **Validate** with measured data in Validation tab
5. **Analyze** costs, margins, sensitivity in Analysis tab
6. **Export** results as JSON or print to PDF

## File Structure

```
docs/
├── index.html                    # Complete application (HTML/CSS/JS)
├── sample-temperature-data.csv   # Example CSV for validation
└── README.md                     # This file
```

## Browser Compatibility

- Chrome/Edge: ✓ Full support
- Firefox: ✓ Full support
- Safari: ✓ Full support
- Requires: ES6+, CSS Grid, SVG

## License

Built for hackathon demonstration. Code provided as-is for educational purposes.

---

**Version**: 1.0  
**Last updated**: 2026-10-19
