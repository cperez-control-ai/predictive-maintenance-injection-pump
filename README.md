# Generador sintético de bomba de inyección — versión 1.1

Esta versión usa el Excel confirmado como fuente de rangos y clases. Añade parada
sostenida, enfriamiento, recuperación gradual y evidencia del umbral antes del disparo.

## 1. Instalar dependencias

```bash
python -m pip install -r requirements.txt
```

## 2. Prueba corta

```bash
python src/generador_dataset_bomba.py \
  --config data/Rangos_y_protecciones_bomba_inyeccion.xlsx \
  --days 0.05 \
  --sample-seconds 1 \
  --output-dir data/processed/prueba_v11
```

## 3. Abrir el visualizador

```bash
streamlit run src/visualizador_dataset.py
```

Si se usa otra carpeta de salida, la ruta del CSV puede cambiarse desde la barra
lateral del visualizador.

## 4. Generar siete días

```bash
python src/generador_dataset_bomba.py \
  --config data/Rangos_y_protecciones_bomba_inyeccion.xlsx \
  --days 7 \
  --sample-seconds 1 \
  --seed 74145 \
  --output-dir data/processed/dataset_7_dias
```

Las columnas `Operating_State`, `Failure_Code`, `Failure_Name`, `Alarm_Active`,
`Trip_Active` y `Event_ID` son estados o etiquetas. No deben utilizarse como
entradas del modelo que predice fallas desde sensores.
