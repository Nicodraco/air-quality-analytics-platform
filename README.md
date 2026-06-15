# Plataforma Inteligente de Monitoreo Ambiental

**Grupo 6** - Gestión de la Información - I Semestre 2026  
Universidad Tecnológica de Panamá

Plataforma de análisis ambiental con arquitectura **Medallion**, **Data Warehouse** (Modelo Estrella), integración **AEMET + MITECO**, predicciones ML, alertas OMS y resúmenes con LLM.

Documento de requisitos: [`docs/PRD.md`](docs/PRD.md)

---

## Arquitectura

```
AEMET + MITECO → Bronze (MinIO/JSON) → Silver (Parquet) → Gold (PostgreSQL)
                                                              ↓
                                    Dashboard | ML | Alertas | LLM
```

| Capa | Formato | Ubicación |
|---|---|---|
| Bronze | JSON | MinIO `bronze/aemet/`, `bronze/miteco/` |
| Silver | Parquet | `data/silver/` |
| Gold | SQL | PostgreSQL (Modelo Estrella) |

---

## Requisitos

- Python 3.10+
- Docker + Docker Compose (MinIO + PostgreSQL)
- API Key AEMET ([opendata.aemet.es](https://opendata.aemet.es))

---

## Instalación

```bash
cd Parcial2_TopicosEspeciales

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Infraestructura (MinIO + PostgreSQL)
docker compose up -d

# Variables de entorno (usa tu .env con API_KEY_AEMET)
cp .env.example .env   # solo si aún no tienes .env
```

### Variables `.env` principales

```env
API_KEY_AEMET=tu_clave_aemet
URL_BUSQUEDA_MITECO=https://miteco.gob.es
URL_DATASTORE_MITECO=https://datos.gob.es/apidata/catalog/dataset
LLM_API_KEY=tu_clave_opcional
```

---

## Ejecución

### Pipeline completo (ETL Medallion)

```bash
python src/pipeline/run_pipeline.py
```

Pasos: Ingesta AEMET/MITECO → Bronze → Silver → Gold → ML → Alertas → Resumen LLM

### Pipeline automatizado (cada hora)

```bash
python src/pipeline/scheduler.py
```

### Dashboard Streamlit

```bash
streamlit run src/dashboard/app.py
```

### Componentes individuales

```bash
python src/ingestion/aemet.py
python src/ingestion/miteco.py
python src/silver/transform.py
python src/gold/loader.py
python src/ml/predict.py
python src/ml/alerts.py
python src/llm/summaries.py
```

---

## Modelo Estrella (Gold)

| Tabla | Descripción |
|---|---|
| `fact_environmental_measures` | Hechos: clima + contaminantes |
| `dim_date` | Dimensión temporal |
| `dim_station` | Estaciones AEMET/MITECO |
| `dim_location` | Geografía (región, municipio, coords) |
| `dim_pollutant` | Contaminantes y límites legales |

---

## Estructura del proyecto

```
├── docs/PRD.md
├── docker-compose.yml
├── data/
│   ├── bronze/          # Fallback local JSON
│   └── silver/          # Parquet normalizado
├── reports/             # Alertas + resúmenes IA
├── models/              # Modelos ML
└── src/
    ├── config.py
    ├── ingestion/       # AEMET, MITECO
    ├── bronze/          # MinIO storage
    ├── silver/          # Transformaciones
    ├── gold/            # PostgreSQL DW
    ├── pipeline/        # ETL + scheduler
    ├── ml/              # Predicción + alertas
    ├── llm/             # Resúmenes diarios
    ├── dashboard/       # Streamlit
    └── utils/           # Mapas Folium
```

---

## Servicios Docker

| Servicio | Puerto | Credenciales |
|---|---|---|
| MinIO API | 9000 | minioadmin / minioadmin123 |
| MinIO Console | 9001 | minioadmin / minioadmin123 |
| PostgreSQL | 5432 | ambiental / ambiental123 |

---

## Entregables PRD

- [x] Arquitectura Medallion
- [x] Data Lake (MinIO + Parquet)
- [x] Data Warehouse PostgreSQL
- [x] Modelo Estrella
- [x] ETL automatizado
- [x] Dashboard + Folium
- [x] Predicciones ML (Random Forest)
- [x] Alertas OMS
- [x] Resúmenes LLM
- [x] Docker Compose
- [x] Documentación técnica
