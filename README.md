# Predictive Maintenance for an Industrial Injection Pump

Proyecto de mantenimiento predictivo y prescriptivo para una bomba centrífuga de
inyección industrial, desarrollado a partir de datos sintéticos físicamente
coherentes, variables de proceso y protecciones típicas de operación.

El proyecto busca detectar condiciones anormales, clasificar modos de falla y,
en etapas posteriores, generar recomendaciones de mantenimiento y operación.

## Estado del proyecto

- Generador sintético físico-informado: completado.
- Dataset definitivo de 15 días: generado y validado.
- Visualizador interactivo: completado.
- Análisis exploratorio de datos: próximo paso.
- Modelo predictivo multiclase: pendiente.
- Módulo prescriptivo: pendiente.

## Dataset sintético

La versión actual genera datos con frecuencia de muestreo de un segundo. El
dataset definitivo utilizado durante el desarrollo contiene:

- 1.296.000 registros.
- 15 días continuos de operación.
- 150 eventos de falla.
- 10 eventos por cada clase de falla.
- 83,60 % de registros en operación normal.
- Cero timestamps duplicados y cero valores faltantes.
- Variación de duración, severidad, ubicación y subtipo de falla.
- Paradas, disparos, arranques y recuperaciones graduales.

Los archivos CSV generados no se almacenan en Git debido a su tamaño. El
repositorio incluye el generador y el archivo Excel de configuración necesario
para reproducirlos.

## Variables principales

### Variables hidráulicas

- `Suction_Filter_DP`: presión diferencial del filtro de succión.
- `Suction_Pressure`: presión de succión.
- `Discharge_Pressure`: presión de descarga.
- `Suction_Flow`: caudal de succión.
- `Wellhead_Pressure`: presión en el cabezal del pozo.
- `Injection_Valve_Position`: posición de la válvula de inyección.

### Motor y variador

- `VFD_Frequency_Actual`: frecuencia real del variador.
- `Motor_Current`: corriente del motor.
- `Pump_Running`: estado de la bomba (`1` encendida, `0` apagada).

### Vibraciones

- `Pump_Vibration_Free_End`
- `Pump_Vibration_Coupling_End`
- `Motor_Vibration_Free_End`
- `Motor_Vibration_Coupling_End`

### Temperaturas

- Temperaturas de rodamientos de bomba y motor, en ambos extremos.
- Seis temperaturas de devanados del motor: fases 1, 2 y 3, canales A y B.

## Clases de falla

| Código | Clase |
|---:|---|
| 0 | Operación normal |
| 1 | Filtro de succión obstruido |
| 2 | Baja presión de succión |
| 3 | Alta presión de descarga |
| 4 | Cavitación |
| 5 | Sobrecarga del motor |
| 6 | Falla de rodamiento |
| 7 | Baja presión de descarga |
| 8 | Alta temperatura de devanados |
| 9 | Alta temperatura de rodamientos |
| 10 | Alta vibración en bomba o motor |
| 11 | Bajo caudal de succión |
| 12 | Alta corriente del motor |
| 13 | Alta presión en el cabezal del pozo |
| 14 | Baja presión del cabezal o posible ruptura de tubería |
| 15 | Alto caudal de succión |

## Estructura del repositorio

```text
predictive-maintenance-injection-pump/
├── data/
│   ├── raw/                         # Dataset externo de referencia (ignorado)
│   ├── processed/                   # Datasets generados (ignorados)
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

## Instalación

Requisitos: Python 3.10 o superior.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

En Windows PowerShell, la activación del entorno es:

```powershell
.venv\Scripts\Activate.ps1
```

## Generar una prueba corta

```bash
python src/generador_dataset_bomba.py \
  --config data/Rangos_y_protecciones_bomba_inyeccion.xlsx \
  --days 0.2 \
  --sample-seconds 1 \
  --output-dir data/processed/prueba
```

## Generar el dataset de 15 días

```bash
python src/generador_dataset_bomba.py \
  --config data/Rangos_y_protecciones_bomba_inyeccion.xlsx \
  --days 15 \
  --sample-seconds 1 \
  --seed 74145 \
  --events-per-class 10 \
  --output-dir data/processed/dataset_definitivo_15d
```

El generador produce:

- `dataset_bomba_inyeccion.csv`
- `informe_validacion.json`
- `series_principales.png`
- `distribucion_clases.png`

## Visualizador interactivo

```bash
streamlit run src/visualizador_dataset.py
```

El panel permite:

- Seleccionar fecha y hora inicial y final.
- Consultar el periodo total disponible.
- Visualizar cuándo la bomba está encendida o apagada.
- Seleccionar señales individuales.
- Revisar alarmas, disparos y eventos.
- Analizar subtipos, ubicaciones y severidades.
- Limitar los puntos dibujados sin modificar las métricas ni el dataset.

## Prevención de fuga de información

Las siguientes columnas son etiquetas o información posterior al evento y no
deben utilizarse como entradas del modelo predictivo:

- `Failure_Code`
- `Failure_Name`
- `Event_ID`
- `Fault_Subtype`
- `Fault_Location`
- `Severity`
- `Alarm_Active`
- `Trip_Active`
- `Operating_State`

La separación de entrenamiento, validación y prueba se realizará por eventos o
bloques temporales, no mediante una división aleatoria de filas consecutivas.

## Tecnologías

- Python
- pandas y NumPy
- Matplotlib y Plotly
- Streamlit
- scikit-learn (etapa de modelado)

## Limitaciones

El dataset es sintético y está construido con rangos, relaciones físicas y
lógicas de protección definidas para el proyecto. Los resultados permiten
desarrollar y demostrar el flujo analítico, pero un modelo destinado a producción
debe validarse y recalibrarse con datos reales de campo.

## Autor

Cristian Pérez — Ingeniero de Control con experiencia en automatización
industrial, sistemas de control e integración de inteligencia artificial.

