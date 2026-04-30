PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    file_hash TEXT,
    display_name TEXT,
    source_type TEXT,
    page_count INTEGER,
    created_at TEXT NOT NULL,
    last_scanned_at TEXT,
    extraction_status TEXT,
    extraction_error TEXT
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    width REAL,
    height REAL,
    rotation INTEGER,
    page_type TEXT,
    text_hash TEXT,
    image_cache_path TEXT,
    needs_review INTEGER DEFAULT 0,
    extraction_status TEXT,
    extraction_error TEXT,
    UNIQUE(document_id, page_number)
);

CREATE TABLE IF NOT EXISTS text_blocks (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    x0 REAL,
    y0 REAL,
    x1 REAL,
    y1 REAL,
    text TEXT,
    block_type TEXT,
    source TEXT,
    confidence REAL
);

CREATE TABLE IF NOT EXISTS vector_blocks (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    x0 REAL,
    y0 REAL,
    x1 REAL,
    y1 REAL,
    primitive_count INTEGER,
    line_count INTEGER,
    curve_count INTEGER,
    rect_count INTEGER,
    layer_name TEXT,
    color TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS regions (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    region_type TEXT,
    x0 REAL,
    y0 REAL,
    x1 REAL,
    y1 REAL,
    source TEXT,
    confidence REAL,
    image_crop_path TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS material_candidates (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    region_id INTEGER REFERENCES regions(id) ON DELETE SET NULL,
    raw_text TEXT,
    raw_material_phrase TEXT,
    raw_shape_phrase TEXT,
    raw_dimension_phrase TEXT,
    parsed_quantity REAL,
    parsed_unit TEXT,
    parsed_thickness REAL,
    parsed_width REAL,
    parsed_height REAL,
    parsed_length REAL,
    normalized_family TEXT,
    normalized_spec TEXT,
    normalized_shape TEXT,
    normalized_thickness REAL,
    normalized_width REAL,
    normalized_height REAL,
    normalized_length REAL,
    normalized_unit TEXT,
    normalization_confidence REAL,
    normalization_status TEXT,
    normalization_rule_ids TEXT,
    review_required INTEGER DEFAULT 1,
    candidate_status TEXT,
    confidence REAL,
    reviewer_notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS takeoff_lines (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER REFERENCES material_candidates(id) ON DELETE SET NULL,
    material TEXT,
    profile TEXT,
    dimensions TEXT,
    quantity REAL,
    unit TEXT,
    area REAL,
    weight REAL,
    source_document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    source_page_id INTEGER REFERENCES pages(id) ON DELETE SET NULL,
    source_region_id INTEGER REFERENCES regions(id) ON DELETE SET NULL,
    status TEXT,
    review_notes TEXT,
    reviewed_by TEXT,
    reviewed_at TEXT,
    exported_at TEXT
);

CREATE TABLE IF NOT EXISTS normalization_rules (
    id INTEGER PRIMARY KEY,
    scope TEXT,
    client_name TEXT,
    rule_type TEXT,
    raw_pattern TEXT,
    normalized_value_json TEXT,
    confidence REAL,
    created_by TEXT,
    created_at TEXT,
    last_used_at TEXT,
    use_count INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS normalization_events (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER REFERENCES material_candidates(id) ON DELETE SET NULL,
    raw_text TEXT,
    old_normalized_json TEXT,
    new_normalized_json TEXT,
    action TEXT,
    user_note TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS dxf_measurements (
    id INTEGER PRIMARY KEY,
    path TEXT,
    file_hash TEXT,
    part_number TEXT,
    units_guess TEXT,
    outer_area REAL,
    net_area REAL,
    perimeter REAL,
    bbox_width REAL,
    bbox_height REAL,
    hole_count INTEGER,
    slot_count INTEGER,
    layer_summary_json TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS companion_sessions (
    id INTEGER PRIMARY KEY,
    token_hash TEXT,
    created_at TEXT,
    last_seen_at TEXT,
    label TEXT,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS companion_actions (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES companion_sessions(id) ON DELETE SET NULL,
    action TEXT,
    target_type TEXT,
    target_id INTEGER,
    old_value_json TEXT,
    new_value_json TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS app_events (
    id INTEGER PRIMARY KEY,
    event_type TEXT,
    message TEXT,
    context_json TEXT,
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_pages_document ON pages(document_id);
CREATE INDEX IF NOT EXISTS idx_text_blocks_page ON text_blocks(page_id);
CREATE INDEX IF NOT EXISTS idx_regions_page ON regions(page_id);
CREATE INDEX IF NOT EXISTS idx_candidates_page ON material_candidates(page_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON material_candidates(candidate_status);
CREATE INDEX IF NOT EXISTS idx_takeoff_status ON takeoff_lines(status);
CREATE INDEX IF NOT EXISTS idx_rules_scope_type ON normalization_rules(scope, rule_type, active);
