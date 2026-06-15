# PRD - Plataforma Inteligente de Monitoreo Ambiental

**Proyecto:** Parcial 2 - Tópicos Especiales  
**Grupo 6** - Gestión de la Información - I Semestre 2026  
**Universidad Tecnológica de Panamá**

---

## 1. Descripción General

Diseñar e implementar una plataforma de análisis ambiental capaz de integrar datos meteorológicos y de calidad del aire provenientes de APIs públicas, almacenarlos bajo una arquitectura Medallion, transformarlos en un Data Warehouse basado en Modelo Estrella y generar visualizaciones, predicciones y resúmenes inteligentes mediante IA.

---

## 2. Objetivos

La plataforma debe permitir:

- Ingestar datos meteorológicos desde **AEMET**.
- Ingestar datos de calidad del aire desde **MITECO**.
- Automatizar la actualización de datos.
- Implementar una arquitectura **Medallion**.
- Construir un **Data Warehouse** con **Modelo Estrella**.
- Visualizar indicadores ambientales en dashboards y mapas.
- Predecir tendencias futuras.
- Generar alertas automáticas.
- Crear resúmenes diarios mediante **LLM**.

---

## 3. APIs Utilizadas

### AEMET OpenData

- **API Key:** requerida (`API_KEY_AEMET` en `.env`)
- **Endpoint inicial:**  
  `https://opendata.aemet.es/opendata/api/valores/climatologicos/inventarioestaciones/todasestaciones/`

**Datos obtenidos:**

- Temperatura
- Humedad
- Precipitación
- Velocidad del viento
- Presión atmosférica
- Ubicación de estaciones

### MITECO

- **URLs configurables:** `URL_BUSQUEDA_MITECO`, `URL_DATASTORE_MITECO`
- **Portal:** https://miteco.gob.es

**Datos obtenidos:**

- PM10, PM2.5, NO2, SO2, O3, CO
- Comunidad autónoma, municipio, latitud, longitud

---

## 4. Arquitectura Medallion

### Bronze Layer

| Atributo | Valor |
|---|---|
| Objetivo | Datos crudos sin transformaciones |
| Formato | JSON |
| Ubicación | MinIO (`bronze/aemet/`, `bronze/miteco/`) |
| Estructura | `yyyy/mm/dd/` |
| Características | Historización completa |

### Silver Layer

| Atributo | Valor |
|---|---|
| Objetivo | Limpieza y normalización |
| Formato | Parquet |
| Ubicación | `silver/` |
| Tablas | `silver_weather`, `silver_air_quality`, `silver_stations` |

**Transformaciones:** deduplicación, fechas, coordenadas, nulos, unidades, enriquecimiento geográfico.

### Gold Layer

| Atributo | Valor |
|---|---|
| Objetivo | Datasets analíticos para negocio |
| Ubicación | PostgreSQL Data Warehouse |
| Modelo | Estrella |

**Tablas:** `fact_environmental_measures`, `dim_date`, `dim_station`, `dim_location`, `dim_pollutant`

---

## 5. Arquitectura General

```
               +----------------+
               |   AEMET API    |
               +--------+-------+
                        |
               +--------v-------+
               |  MITECO API    |
               +--------+-------+
                        |
                        v
                +---------------+
                | Python Ingest |
                +-------+-------+
                        |
                        v
                +---------------+
                |     MinIO     |
                |    Bronze     |
                +-------+-------+
                        |
                        v
                +---------------+
                | Python Silver |
                +-------+-------+
                        |
                        v
                +---------------+
                | PostgreSQL DW |
                | Gold Layer    |
                +-------+-------+
                        |
          +-------------+-------------+
          |                           |
          v                           v
   +-------------+            +-------------+
   | Streamlit   |            | ML Models   |
   | Dashboard   |            | + Alertas   |
   +------+------+            +------+------+
          |                          |
          +------------+-------------+
                       |
                       v
               +---------------+
               | OpenAI/Ollama |
               | Daily Summary |
               +---------------+
```

---

## 6. Modelo Estrella

### Tabla de hechos: `fact_environmental_measures`

**Métricas:** temperature, humidity, precipitation, wind_speed, pm10, pm25, no2, so2, o3, co

**Claves:** date_key, station_key, location_key

### Dimensiones

| Tabla | Campos principales |
|---|---|
| `dim_date` | date_key, full_date, day, month, year, quarter, week |
| `dim_station` | station_key, station_id, station_name, source, station_type |
| `dim_location` | location_key, country, region, province, municipality, latitude, longitude |
| `dim_pollutant` | pollutant_key, pollutant_name, unit, legal_limit |

---

## 7. Pipeline de Datos

| Fase | Frecuencia | Herramienta | Destino |
|---|---|---|---|
| Extracción | Cada hora | Python + Requests | APIs AEMET/MITECO |
| Bronze | Tras extracción | MinIO client | JSON en MinIO |
| Silver | Tras Bronze | Pandas | Parquet |
| Gold | Tras Silver | SQLAlchemy | PostgreSQL |

---

## 8. Analítica - KPIs

- Temperatura promedio
- Humedad promedio
- PM10 / PM2.5 promedio
- NO2 promedio
- Índice de calidad del aire
- Estaciones críticas

---

## 9. Visualización Geográfica

- **Herramienta:** Folium
- **Capas:** estaciones meteorológicas, calidad del aire, heatmaps, alertas
- **Colores:** Verde = Bueno, Amarillo = Moderado, Rojo = Crítico

---

## 10. Machine Learning

**Objetivo:** Predecir niveles de contaminación.

**Variables:** temperatura, humedad, viento, precipitación, históricos de contaminantes.

| Fase | Modelo |
|---|---|
| 1 | Random Forest Regressor |
| 2 | XGBoost (futuro) |
| 3 | Prophet (futuro) |

**Horizontes:** 24 h, 48 h, 7 días.

---

## 11. IA Generativa

1. Consultar Data Warehouse
2. Obtener KPIs
3. Construir prompt
4. Enviar al LLM
5. Generar reporte en `reports/`

---

## 12. Sistema de Alertas

**Condiciones (límites OMS):**

- PM10 > 45 µg/m³ (24 h)
- PM2.5 > 15 µg/m³ (24 h)
- NO2 > 25 µg/m³ (24 h)

**Salida:** dashboard, archivo `reports/alerts_*.json`, resumen IA.

---

## 13. Entregables

- [x] Arquitectura Medallion
- [x] Data Lake (MinIO Bronze + Silver Parquet)
- [x] Data Warehouse PostgreSQL
- [x] Modelo Estrella
- [x] ETL automatizado (scheduler horario)
- [x] Dashboard Streamlit
- [x] Mapas Folium
- [x] Predicciones ML
- [x] Resúmenes IA
- [x] Docker Compose
- [x] Documentación técnica

---

## 14. Implementación en este repositorio

| Componente | Ruta |
|---|---|
| Configuración | `src/config.py` |
| Ingesta AEMET | `src/ingestion/aemet.py` |
| Ingesta MITECO | `src/ingestion/miteco.py` |
| Bronze (MinIO) | `src/bronze/storage.py` |
| Silver | `src/silver/transform.py` |
| Gold (DW) | `src/gold/loader.py`, `src/gold/schema.sql` |
| Pipeline | `src/pipeline/run_pipeline.py` |
| Scheduler | `src/pipeline/scheduler.py` |
| ML | `src/ml/predict.py` |
| Alertas | `src/ml/alerts.py` |
| LLM | `src/llm/summaries.py` |
| Dashboard | `src/dashboard/app.py` |
| Mapas | `src/utils/maps.py` |
| Infra | `docker-compose.yml` |
