-- Gold Layer: Modelo Estrella - Data Warehouse ambiental

CREATE TABLE IF NOT EXISTS dim_date (
    date_key        SERIAL PRIMARY KEY,
    full_date       DATE NOT NULL UNIQUE,
    day             SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,
    year            SMALLINT NOT NULL,
    quarter         SMALLINT NOT NULL,
    week            SMALLINT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_station (
    station_key     SERIAL PRIMARY KEY,
    station_id      VARCHAR(50) NOT NULL,
    station_name    VARCHAR(200),
    source          VARCHAR(50) NOT NULL,
    station_type    VARCHAR(50),
    UNIQUE (station_id, source)
);

CREATE TABLE IF NOT EXISTS dim_location (
    location_key    SERIAL PRIMARY KEY,
    country         VARCHAR(100),
    region          VARCHAR(100),
    province        VARCHAR(100),
    municipality    VARCHAR(200),
    latitude        DECIMAL(9, 6),
    longitude       DECIMAL(9, 6),
    UNIQUE (country, region, municipality, latitude, longitude)
);

CREATE TABLE IF NOT EXISTS dim_pollutant (
    pollutant_key   SERIAL PRIMARY KEY,
    pollutant_name  VARCHAR(50) NOT NULL UNIQUE,
    unit            VARCHAR(20),
    legal_limit     DECIMAL(10, 2)
);

CREATE TABLE IF NOT EXISTS fact_environmental_measures (
    fact_key        BIGSERIAL PRIMARY KEY,
    date_key        INTEGER REFERENCES dim_date(date_key),
    station_key     INTEGER REFERENCES dim_station(station_key),
    location_key    INTEGER REFERENCES dim_location(location_key),
    measured_at     TIMESTAMP WITH TIME ZONE,
    temperature     DECIMAL(8, 2),
    humidity        DECIMAL(8, 2),
    precipitation   DECIMAL(8, 2),
    wind_speed      DECIMAL(8, 2),
    pm10            DECIMAL(8, 2),
    pm25            DECIMAL(8, 2),
    no2             DECIMAL(8, 2),
    so2             DECIMAL(8, 2),
    o3              DECIMAL(8, 2),
    co              DECIMAL(8, 2),
    aqi_index       DECIMAL(8, 2),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fact_date ON fact_environmental_measures(date_key);
CREATE INDEX IF NOT EXISTS idx_fact_station ON fact_environmental_measures(station_key);
CREATE INDEX IF NOT EXISTS idx_fact_measured_at ON fact_environmental_measures(measured_at);

-- Límites legales / OMS
INSERT INTO dim_pollutant (pollutant_name, unit, legal_limit) VALUES
    ('pm10', 'µg/m³', 45.0),
    ('pm25', 'µg/m³', 15.0),
    ('no2', 'µg/m³', 25.0),
    ('so2', 'µg/m³', 40.0),
    ('o3', 'µg/m³', 100.0),
    ('co', 'µg/m³', 4000.0)
ON CONFLICT (pollutant_name) DO NOTHING;
