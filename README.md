# Predictive Maintenance for an Industrial Injection Pump

Predictive and prescriptive maintenance project for an industrial centrifugal
injection pump, developed using physically consistent synthetic data, process
variables, and typical operating protection thresholds.

The project aims to detect abnormal conditions, classify failure modes, and,
in later stages, generate maintenance and operational recommendations.

## Project status

- Physics-informed synthetic data generator: completed.
- Final 15-day dataset: generated and validated.
- Interactive visualizer: completed.
- Exploratory data analysis: next step.
- Multiclass predictive model: pending.
- Prescriptive module: pending.

## Synthetic dataset

The current version generates data at a sampling frequency of one second. The
final dataset used during development contains:

- 1,296,000 records.
- 15 continuous days of operation.
- 150 failure events.
- 10 events for each failure class.
- 83.60% of records under normal operation.
- No duplicate timestamps and no missing values.
- Variations in failure duration, severity, location, and subtype.
- Shutdowns, trips, startups, and gradual recoveries.

The generated CSV files are not stored in Git because of their size. The
repository includes the generator and the Excel configuration file required to
reproduce them.

## Main variables

### Hydraulic variables

- `Suction_Filter_DP`: suction filter differential pressure.
- `Suction_Pressure`: suction pressure.
- `Discharge_Pressure`: discharge pressure.
- `Suction_Flow`: suction flow rate.
- `Wellhead_Pressure`: wellhead pressure.
- `Injection_Valve_Position`: injection valve position.

### Motor and variable frequency drive

- `VFD_Frequency_Actual`: actual VFD frequency.
- `Motor_Current`: motor current.
- `Pump_Running`: pump status (`1` running, `0` stopped).

### Vibration measurements

- `Pump_Vibration_Free_End`
- `Pump_Vibration_Coupling_End`
- `Motor_Vibration_Free_End`
- `Motor_Vibration_Coupling_End`

### Temperature measurements

- Pump and motor bearing temperatures at both ends.
- Six motor winding temperatures: phases 1, 2, and 3, channels A and B.

## Failure classes

| Code | Class |
|---:|---|
| 0 | Normal operation |
| 1 | Clogged suction filter |
| 2 | Low suction pressure |
| 3 | High discharge pressure |
| 4 | Cavitation |
| 5 | Motor overload |
| 6 | Bearing failure |
| 7 | Low discharge pressure |
| 8 | High winding temperature |
| 9 | High bearing temperature |
| 10 | High pump or motor vibration |
| 11 | Low suction flow |
| 12 | High motor current |
| 13 | High wellhead pressure |
| 14 | Low wellhead pressure or possible pipeline rupture |
| 15 | High suction flow |

## Repository structure

```text
predictive-maintenance-injection-pump/
├── data/
│   ├── raw/                         # External reference dataset (ignored)
│   ├── processed/                   # Generated datasets (ignored)
│   └── Rangos_y_protecciones_bomba_inyeccion.xlsx
├── notebooks/
│   └── 00_exploracion_MBG12_original.ipynb
├── reports/
│   └── figures/
├── src/
│   ├── generador_dataset_bomba.py
│   └── visualizador_dataset.py
├── .gitignore
├── README.md
└── requirements.txt
```

## Installation

Requirement: Python 3.10 or later.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

In Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Generate a short test dataset

```bash
python src/generador_dataset_bomba.py \
  --config data/Rangos_y_protecciones_bomba_inyeccion.xlsx \
  --days 0.2 \
  --sample-seconds 1 \
  --output-dir data/processed/prueba
```

## Generate the 15-day dataset

```bash
python src/generador_dataset_bomba.py \
  --config data/Rangos_y_protecciones_bomba_inyeccion.xlsx \
  --days 15 \
  --sample-seconds 1 \
  --seed 74145 \
  --events-per-class 10 \
  --output-dir data/processed/dataset_definitivo_15d
```

The generator produces:

- `dataset_bomba_inyeccion.csv`
- `informe_validacion.json`
- `series_principales.png`
- `distribucion_clases.png`

## Interactive visualizer

```bash
streamlit run src/visualizador_dataset.py
```

The dashboard allows users to:

- Select the start and end dates and times.
- View the complete available time range.
- See when the pump is running or stopped.
- Select individual signals.
- Review alarms, trips, and events.
- Analyze failure subtypes, locations, and severity levels.
- Limit the number of plotted points without modifying the metrics or dataset.

## Data leakage prevention

The following columns are labels or post-event information and must not be used
as input features for the predictive model:

- `Failure_Code`
- `Failure_Name`
- `Event_ID`
- `Fault_Subtype`
- `Fault_Location`
- `Severity`
- `Alarm_Active`
- `Trip_Active`
- `Operating_State`

The training, validation, and test sets will be split by events or temporal
blocks instead of randomly splitting consecutive rows.

## Technologies

- Python
- pandas and NumPy
- Matplotlib and Plotly
- Streamlit
- scikit-learn (modeling stage)

## Limitations

The dataset is synthetic and was created using operating ranges, physical
relationships, and protection logic defined for this project. The results can
be used to develop and demonstrate the analytical workflow, but any model
intended for production must be validated and recalibrated using real field
data.

## Author

Cristian Pérez — Control Engineer with experience in industrial automation,
control systems, and artificial intelligence integration.
