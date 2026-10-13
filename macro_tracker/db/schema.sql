-- Esquema v1. Fechas en ISO-8601 (YYYY-MM-DD); nutrientes de alimentos por 100 g.

CREATE TABLE profile (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    sex                 TEXT    NOT NULL CHECK (sex IN ('M', 'F')),
    birth_date          TEXT    NOT NULL,
    height_cm           REAL    NOT NULL CHECK (height_cm > 0),
    activity_level      TEXT    NOT NULL
        CHECK (activity_level IN ('sedentary', 'light', 'moderate', 'active', 'very_active')),
    goal                TEXT    NOT NULL CHECK (goal IN ('maintain', 'gain', 'lose')),
    rate_kg_week        REAL    NOT NULL DEFAULT 0 CHECK (rate_kg_week >= 0),
    protein_g_kg_min    REAL    NOT NULL DEFAULT 1.6 CHECK (protein_g_kg_min > 0),
    protein_g_kg_max    REAL    NOT NULL DEFAULT 2.2 CHECK (protein_g_kg_max >= protein_g_kg_min),
    fat_g_kg_min        REAL    NOT NULL DEFAULT 0.6 CHECK (fat_g_kg_min >= 0),
    fat_pct_kcal        REAL    NOT NULL DEFAULT 0.25 CHECK (fat_pct_kcal >= 0 AND fat_pct_kcal < 1),
    bmr_method_pref     TEXT    NOT NULL DEFAULT 'auto' CHECK (bmr_method_pref IN ('auto', 'mifflin')),
    min_valid_day_kcal  REAL    NOT NULL DEFAULT 1000 CHECK (min_valid_day_kcal >= 0),
    updated_at          TEXT    NOT NULL
);

CREATE TABLE body_log (
    date            TEXT PRIMARY KEY,
    weight_kg       REAL CHECK (weight_kg IS NULL OR weight_kg > 0),
    body_fat_pct    REAL CHECK (body_fat_pct IS NULL OR (body_fat_pct >= 3 AND body_fat_pct <= 60)),
    body_fat_source TEXT CHECK (body_fat_source IS NULL OR body_fat_source IN ('measured', 'self_estimate', 'navy')),
    waist_cm        REAL CHECK (waist_cm IS NULL OR waist_cm > 0),
    neck_cm         REAL CHECK (neck_cm IS NULL OR neck_cm > 0),
    hip_cm          REAL CHECK (hip_cm IS NULL OR hip_cm > 0),
    note            TEXT,
    CHECK (body_fat_pct IS NULL OR body_fat_source IS NOT NULL)
);

CREATE TABLE foods (
    id            INTEGER PRIMARY KEY,
    uid           TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    brand         TEXT,
    name_norm     TEXT    NOT NULL,          -- nombre + marca sin acentos ni mayúsculas
    source        TEXT    NOT NULL CHECK (source IN ('custom', 'off', 'recipe')),
    barcode       TEXT UNIQUE,
    kcal_100g     REAL    NOT NULL CHECK (kcal_100g >= 0),
    protein_100g  REAL    NOT NULL CHECK (protein_100g >= 0),
    carbs_100g    REAL    NOT NULL CHECK (carbs_100g >= 0),
    fat_100g      REAL    NOT NULL CHECK (fat_100g >= 0),
    serving_g     REAL CHECK (serving_g IS NULL OR serving_g > 0),
    serving_label TEXT,
    data_flag     TEXT,                       -- p. ej. 'kcal_mismatch' en datos de OFF
    archived      INTEGER NOT NULL DEFAULT 0,
    off_fetched_at TEXT,
    created_at    TEXT    NOT NULL
);
CREATE INDEX idx_foods_name_norm ON foods (name_norm);

CREATE TABLE recipes (
    food_id        INTEGER PRIMARY KEY REFERENCES foods (id) ON DELETE CASCADE,
    total_yield_g  REAL NOT NULL CHECK (total_yield_g > 0),
    servings       REAL NOT NULL DEFAULT 1 CHECK (servings > 0)
);

CREATE TABLE recipe_items (
    id                   INTEGER PRIMARY KEY,
    recipe_food_id       INTEGER NOT NULL REFERENCES recipes (food_id) ON DELETE CASCADE,
    ingredient_food_id   INTEGER NOT NULL REFERENCES foods (id) ON DELETE RESTRICT,
    grams                REAL    NOT NULL CHECK (grams > 0)
);
CREATE INDEX idx_recipe_items_recipe ON recipe_items (recipe_food_id);

CREATE TABLE food_log (
    id          INTEGER PRIMARY KEY,
    uid         TEXT    NOT NULL UNIQUE,
    date        TEXT    NOT NULL,
    meal        TEXT    NOT NULL CHECK (meal IN ('breakfast', 'lunch', 'dinner', 'snack')),
    food_id     INTEGER NOT NULL REFERENCES foods (id) ON DELETE RESTRICT,
    grams       REAL    NOT NULL CHECK (grams > 0),
    kcal        REAL    NOT NULL,            -- snapshot al registrar
    protein_g   REAL    NOT NULL,
    carbs_g     REAL    NOT NULL,
    fat_g       REAL    NOT NULL,
    created_at  TEXT    NOT NULL
);
CREATE INDEX idx_food_log_date ON food_log (date);

CREATE TABLE day_status (
    date           TEXT PRIMARY KEY,
    food_complete  INTEGER CHECK (food_complete IN (0, 1))   -- override manual de "día válido"
);

CREATE TABLE targets (
    effective_from  TEXT PRIMARY KEY,
    kcal            REAL NOT NULL CHECK (kcal > 0),
    protein_g       REAL NOT NULL CHECK (protein_g >= 0),
    carbs_g         REAL NOT NULL CHECK (carbs_g >= 0),
    fat_g           REAL NOT NULL CHECK (fat_g >= 0),
    tdee_source     TEXT NOT NULL CHECK (tdee_source IN ('formula', 'data', 'manual')),
    bmr_method      TEXT,
    note            TEXT
);

CREATE TABLE schema_version (
    version INTEGER NOT NULL
);
INSERT INTO schema_version (version) VALUES (1);
