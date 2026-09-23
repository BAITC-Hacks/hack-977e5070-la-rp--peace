-- Backend database schema, applied once to a new SQLite file by models.create_schema().
-- Tables follow stage 1 of the methodology (methodology/01_document_parsing.md, §9);
-- document_files and documents.doc_set are backend additions; the entity tables implement
-- stage 2 (methodology/02_entity_extraction.md). No migrations: to change the
-- schema, delete the database file. SQLite 3.38+ with JSON functions.
-- PRAGMA foreign_keys is also set on every connection by db.make_engine().
PRAGMA foreign_keys = ON;
BEGIN;

-- Одна строка — один документ. original_text не меняется после разбора.
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL CHECK (trim(file_name) <> ''),
    source_format TEXT NOT NULL CHECK (trim(source_format) <> ''),
    file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes >= 0),
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64 AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    -- Реквизиты из содержания, а не из имени файла или времени загрузки.
    title TEXT CHECK (title IS NULL OR trim(title) <> ''),
    document_type TEXT CHECK (document_type IS NULL OR trim(document_type) <> ''),
    organization TEXT CHECK (organization IS NULL OR trim(organization) <> ''),
    revision TEXT CHECK (revision IS NULL OR trim(revision) <> ''),
    approved_by TEXT CHECK (approved_by IS NULL OR trim(approved_by) <> ''),
    approval_document_type TEXT CHECK (approval_document_type IS NULL OR trim(approval_document_type) <> ''),
    approval_number TEXT CHECK (approval_number IS NULL OR trim(approval_number) <> ''),
    -- Даты документа — YYYY-MM-DD, неизвестные значения — NULL.
    document_created_on TEXT CHECK (document_created_on IS NULL OR (
        length(document_created_on) = 10
        AND document_created_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND date(document_created_on, '+0 days') IS NOT NULL
        AND date(document_created_on, '+0 days') = document_created_on
    )),
    approved_on TEXT CHECK (approved_on IS NULL OR (
        length(approved_on) = 10
        AND approved_on GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND date(approved_on, '+0 days') IS NOT NULL
        AND date(approved_on, '+0 days') = approved_on
    )),
    effective_from TEXT CHECK (effective_from IS NULL OR (
        length(effective_from) = 10
        AND effective_from GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
        AND date(effective_from, '+0 days') IS NOT NULL
        AND date(effective_from, '+0 days') = effective_from
    )),
    -- Источники реквизитов, статусы извлечения и альтернативные значения.
    metadata_evidence TEXT NOT NULL DEFAULT '{}' CHECK (
        CASE WHEN json_valid(metadata_evidence) THEN json_type(metadata_evidence) = 'object' ELSE 0 END
    ),
    -- Встроенные свойства файла (автор, технические даты и т. п.), если доступны.
    file_metadata TEXT NOT NULL DEFAULT '{}' CHECK (
        CASE WHEN json_valid(file_metadata) THEN json_type(file_metadata) = 'object' ELSE 0 END
    ),
    -- NULL до извлечения текста: файл регистрируется до обработки.
    original_text TEXT CHECK (
        original_text IS NULL OR (length(original_text) > 0 AND instr(original_text, char(0)) = 0)
    ),
    -- JSON-массив {start, end, location}: диапазоны и координаты в исходном файле.
    source_map TEXT NOT NULL DEFAULT '[]' CHECK (
        CASE WHEN json_valid(source_map) THEN json_type(source_map) = 'array' ELSE 0 END
    ),
    -- JSON-объект с проверенным профилем агента; до профилирования — NULL.
    parsing_profile TEXT CHECK (
        CASE
            WHEN parsing_profile IS NULL THEN 1
            WHEN json_valid(parsing_profile) THEN json_type(parsing_profile) = 'object'
            ELSE 0
        END
    ),
    parse_status text NOT NULL DEFAULT 'pending'
        CHECK (parse_status IN ('pending', 'parsed', 'needs_review', 'validated')),
    -- Время регистрации файла в системе, не дата создания документа.
    uploaded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- Backend: which side of the comparison the user uploaded the document for.
    doc_set TEXT CHECK (doc_set IS NULL OR doc_set IN ('before', 'after', 'regulatory', 'benchmark')),
    -- Backend: progress of stage 2 (organisational entities) for this document.
    entities_status TEXT NOT NULL DEFAULT 'not_started' CHECK (entities_status IN (
        'not_started', 'running', 'done', 'needs_review', 'failed'
    )),
    -- Backend: progress of stage 4.1 (function collisions) and 4.2 (function cascade).
    collisions_status TEXT NOT NULL DEFAULT 'not_started' CHECK (collisions_status IN (
        'not_started', 'running', 'done', 'needs_review', 'failed'
    )),
    cascade_status TEXT NOT NULL DEFAULT 'not_started' CHECK (cascade_status IN (
        'not_started', 'running', 'done', 'needs_review', 'failed'
    )),
    activities_status TEXT NOT NULL DEFAULT 'not_started' CHECK (activities_status IN ('not_started', 'running', 'done', 'needs_review', 'failed')),
    CONSTRAINT documents_parsed_requires_text
        CHECK (parse_status NOT IN ('parsed', 'validated') OR original_text IS NOT NULL)
) STRICT;

CREATE TABLE document_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL
        REFERENCES documents (id) ON DELETE CASCADE,
    -- Родитель в дереве текста того же документа; NULL для верхнего уровня.
    parent_id INTEGER,
    -- Позиция среди соседей с 0. Номер/буква marker не является уникальным ID.
    position integer NOT NULL CHECK (position >= 0),
    node_type text NOT NULL CHECK (node_type IN (
        'section', 'clause', 'heading', 'list', 'list_item',
        'table', 'table_row', 'table_cell', 'text', 'service'
    )),
    marker text CHECK (marker IS NULL OR trim(marker) <> ''),
    -- Собственный текст без текста детей; продолжения — дочерние текстовые узлы.
    text text NOT NULL DEFAULT '',
    -- [start, end) в символах Unicode original_text, не в байтах или UTF-16.
    -- Диапазон родителя включает дочерние узлы.
    source_start integer NOT NULL CHECK (source_start >= 0),
    source_end integer NOT NULL,
    CONSTRAINT document_nodes_source_range CHECK (source_end > source_start),
    CONSTRAINT document_nodes_not_own_parent CHECK (parent_id IS NOT id),
    CONSTRAINT document_nodes_document_identity UNIQUE (document_id, id),
    CONSTRAINT document_nodes_parent_same_document
        FOREIGN KEY (document_id, parent_id)
        REFERENCES document_nodes (document_id, id)
        ON DELETE CASCADE
) STRICT;

-- Порядок уникален среди детей одного родителя и отдельно среди корней.
CREATE UNIQUE INDEX document_nodes_child_position
    ON document_nodes (document_id, parent_id, position)
    WHERE parent_id IS NOT NULL;

CREATE UNIQUE INDEX document_nodes_root_position
    ON document_nodes (document_id, position)
    WHERE parent_id IS NULL;

CREATE TABLE parsing_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL
        REFERENCES documents (id) ON DELETE CASCADE,
    -- NULL для замечания ко всему документу или ещё не выделенному фрагменту.
    node_id INTEGER,
    issue_type text NOT NULL CHECK (issue_type IN (
        'empty_content', 'ambiguous_boundary', 'ambiguous_parent',
        'numbering_gap', 'uncovered_text', 'other'
    )),
    message text NOT NULL CHECK (trim(message) <> ''),
    -- 1 — блокирующее, 0 — неблокирующее. Статус validated проверяет приложение.
    is_blocking INTEGER NOT NULL DEFAULT 1 CHECK (is_blocking IN (0, 1)),
    -- Временные метки — TEXT в UTC, ISO 8601, например 2026-09-23T10:00:00.000Z.
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CONSTRAINT parsing_issues_node_same_document
        FOREIGN KEY (document_id, node_id)
        REFERENCES document_nodes (document_id, id)
        ON DELETE CASCADE
) STRICT;

CREATE INDEX parsing_issues_document_node
    ON parsing_issues (document_id, node_id);

-- Backend: uploaded bytes, one row per document; the methodology keeps only the extracted text.
CREATE TABLE document_files (
    document_id INTEGER PRIMARY KEY REFERENCES documents (id) ON DELETE CASCADE,
    content BLOB NOT NULL
) STRICT;

-- Stage 2: organisational objects of ONE document. Composite keys (document_id, id) keep every
-- parent, relation and source inside the same document.
CREATE TABLE entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    parent_id INTEGER,
    parent_status TEXT NOT NULL CHECK (parent_status IN ('resolved', 'root', 'unknown', 'ambiguous')),
    -- JSON array of entity ids of this document offered as parents when parent_status = 'ambiguous'.
    parent_candidates TEXT NOT NULL DEFAULT '[]' CHECK (
        CASE WHEN json_valid(parent_candidates) THEN json_type(parent_candidates) = 'array' ELSE 0 END
    ),
    name TEXT NOT NULL CHECK (trim(name) <> ''),
    -- JSON array of other names and abbreviations found in the document.
    aliases TEXT NOT NULL DEFAULT '[]' CHECK (
        CASE WHEN json_valid(aliases) THEN json_type(aliases) = 'array' ELSE 0 END
    ),
    entity_type TEXT NOT NULL CHECK (trim(entity_type) <> ''),
    -- Normalised category (entity_type keeps the document's wording); later stages compare
    -- objects of one category. 'unclear' is flagged for review.
    category TEXT NOT NULL DEFAULT 'unclear' CHECK (category IN (
        'organization', 'governing_body', 'block', 'department', 'division', 'group', 'position',
        'collective', 'other', 'unclear'
    )),
    position_type TEXT,
    level TEXT,
    -- JSON array of {role, scope}; every role is backed by an entity_sources row.
    roles TEXT NOT NULL DEFAULT '[]' CHECK (
        CASE WHEN json_valid(roles) THEN json_type(roles) = 'array' ELSE 0 END
    ),
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'checked', 'needs_review')),
    CONSTRAINT entities_document_identity UNIQUE (document_id, id),
    CONSTRAINT entities_not_own_parent CHECK (parent_id IS NOT id),
    CONSTRAINT entities_parent_matches_status CHECK (
        (parent_id IS NULL) = (parent_status IN ('root', 'unknown', 'ambiguous'))
    ),
    CONSTRAINT entities_parent_same_document
        FOREIGN KEY (document_id, parent_id) REFERENCES entities (document_id, id)
) STRICT;

CREATE TABLE entity_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    from_entity_id INTEGER NOT NULL,
    to_entity_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL CHECK (relation_type IN (
        'functional_subordination', 'administrative_management', 'reports_to', 'membership', 'other'
    )),
    conditions TEXT,
    CONSTRAINT entity_relations_document_identity UNIQUE (document_id, id),
    CONSTRAINT entity_relations_distinct CHECK (from_entity_id <> to_entity_id),
    CONSTRAINT entity_relations_from_same_document
        FOREIGN KEY (document_id, from_entity_id) REFERENCES entities (document_id, id) ON DELETE CASCADE,
    CONSTRAINT entity_relations_to_same_document
        FOREIGN KEY (document_id, to_entity_id) REFERENCES entities (document_id, id) ON DELETE CASCADE
) STRICT;

-- Verbatim evidence: quote_start/quote_end index into document_nodes.text of node_id.
CREATE TABLE entity_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    entity_id INTEGER,
    relation_id INTEGER,
    node_id INTEGER NOT NULL,
    quote TEXT NOT NULL CHECK (trim(quote) <> ''),
    quote_start INTEGER NOT NULL CHECK (quote_start >= 0),
    quote_end INTEGER NOT NULL,
    -- JSON array of what the quote supports: name, type, parent, position_type, level, role:<r>, relation.
    supports TEXT NOT NULL CHECK (
        CASE WHEN json_valid(supports) THEN json_type(supports) = 'array' ELSE 0 END
    ),
    -- Root node of the block whose answer produced the source; NULL for the whole-document review.
    -- A re-run replaces a block's contribution by this key and keeps it when the block fails.
    block_node_id INTEGER,
    CONSTRAINT entity_sources_range CHECK (quote_end > quote_start),
    CONSTRAINT entity_sources_one_owner CHECK ((entity_id IS NULL) <> (relation_id IS NULL)),
    CONSTRAINT entity_sources_entity_same_document
        FOREIGN KEY (document_id, entity_id) REFERENCES entities (document_id, id) ON DELETE CASCADE,
    CONSTRAINT entity_sources_relation_same_document
        FOREIGN KEY (document_id, relation_id) REFERENCES entity_relations (document_id, id) ON DELETE CASCADE,
    CONSTRAINT entity_sources_node_same_document
        FOREIGN KEY (document_id, node_id) REFERENCES document_nodes (document_id, id) ON DELETE CASCADE,
    CONSTRAINT entity_sources_block_same_document
        FOREIGN KEY (document_id, block_node_id) REFERENCES document_nodes (document_id, id) ON DELETE CASCADE
) STRICT;

-- Processing mark for every block sent to the model: a failed request is never "none".
CREATE TABLE entity_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    node_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('found', 'none', 'needs_clarification', 'failed')),
    message TEXT,
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    CONSTRAINT entity_blocks_node_same_document
        FOREIGN KEY (document_id, node_id) REFERENCES document_nodes (document_id, id) ON DELETE CASCADE
) STRICT;

CREATE TABLE entity_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    entity_id INTEGER,
    relation_id INTEGER,
    issue_type TEXT NOT NULL CHECK (issue_type IN (
        'ambiguous_parent', 'ambiguous_merge', 'unsupported_attribute', 'block_failed', 'cycle', 'other'
    )),
    message TEXT NOT NULL CHECK (trim(message) <> ''),
    is_blocking INTEGER NOT NULL DEFAULT 0 CHECK (is_blocking IN (0, 1)),
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CONSTRAINT entity_issues_entity_same_document
        FOREIGN KEY (document_id, entity_id) REFERENCES entities (document_id, id) ON DELETE CASCADE,
    CONSTRAINT entity_issues_relation_same_document
        FOREIGN KEY (document_id, relation_id) REFERENCES entity_relations (document_id, id) ON DELETE CASCADE
) STRICT;

-- Stage 3 (methodology/03_activity_extraction.md): what is assigned to the entities of ONE
-- document. One record = one provision for ONE entity: a provision of several participants is
-- stored once per participant, linked by participation, participant_designation and
-- participant_entity_ids. Composite keys (document_id, id) keep records, entities, sources and
-- nodes inside the same document.
CREATE TABLE activity_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    -- The planned block whose answer produced the record; a re-run of the block replaces its records.
    block_node_id INTEGER NOT NULL,
    -- Shared by the records split from one provision (one per participant); stable across re-runs.
    provision_key TEXT NOT NULL CHECK (length(provision_key) = 16),
    -- NULL = unresolved role or undisclosed remainder of a group; note explains what to clarify.
    entity_id INTEGER,
    -- How the text names this participant, e.g. «уполномоченный им работник».
    designation TEXT NOT NULL CHECK (trim(designation) <> ''),
    record_type TEXT NOT NULL CHECK (record_type IN (
        'goal', 'task', 'function', 'duty', 'right', 'prohibition', 'other'
    )),
    -- Full standalone wording (intro phrase + sub-item); the verbatim words live in activity_sources.
    formulation TEXT NOT NULL CHECK (trim(formulation) <> ''),
    specificity TEXT NOT NULL CHECK (specificity IN ('specific', 'generalized', 'needs_clarification')),
    participation TEXT NOT NULL CHECK (participation IN ('individual', 'each', 'joint', 'alternative', 'unclear')),
    -- Original wording of the participant circle, e.g. «Главный аудитор или уполномоченный им работник».
    participant_designation TEXT NOT NULL CHECK (trim(participant_designation) <> ''),
    -- JSON array of the OTHER known participants' entity ids (same document, checked by the backend).
    participant_entity_ids TEXT NOT NULL DEFAULT '[]' CHECK (
        CASE WHEN json_valid(participant_entity_ids) THEN json_type(participant_entity_ids) = 'array' ELSE 0 END
    ),
    -- NULL when the document does not state it; never invented.
    condition TEXT CHECK (condition IS NULL OR trim(condition) <> ''),
    deadline TEXT CHECK (deadline IS NULL OR trim(deadline) <> ''),
    periodicity TEXT CHECK (periodicity IS NULL OR trim(periodicity) <> ''),
    note TEXT CHECK (note IS NULL OR trim(note) <> ''),
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'checked', 'needs_review')),
    CONSTRAINT activity_records_document_identity UNIQUE (document_id, id),
    CONSTRAINT activity_records_unresolved_needs_note CHECK (entity_id IS NOT NULL OR note IS NOT NULL),
    CONSTRAINT activity_records_block_same_document
        FOREIGN KEY (document_id, block_node_id) REFERENCES document_nodes (document_id, id) ON DELETE CASCADE,
    CONSTRAINT activity_records_entity_same_document
        FOREIGN KEY (document_id, entity_id) REFERENCES entities (document_id, id) ON DELETE CASCADE
) STRICT;

-- Verbatim evidence of a record: quote_start/quote_end index document_nodes.text of node_id.
CREATE TABLE activity_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    record_id INTEGER NOT NULL,
    node_id INTEGER NOT NULL,
    quote TEXT NOT NULL CHECK (trim(quote) <> ''),
    quote_start INTEGER NOT NULL CHECK (quote_start >= 0),
    quote_end INTEGER NOT NULL,
    -- JSON array: formulation, type, condition, deadline, periodicity, participation, specificity,
    -- entity, membership.
    supports TEXT NOT NULL CHECK (
        CASE WHEN json_valid(supports) THEN json_type(supports) = 'array' ELSE 0 END
    ),
    CONSTRAINT activity_sources_range CHECK (quote_end > quote_start),
    CONSTRAINT activity_sources_record_same_document
        FOREIGN KEY (document_id, record_id) REFERENCES activity_records (document_id, id) ON DELETE CASCADE,
    CONSTRAINT activity_sources_node_same_document
        FOREIGN KEY (document_id, node_id) REFERENCES document_nodes (document_id, id) ON DELETE CASCADE
) STRICT;

-- Processing mark of every planned block in the latest run: a failed request is never "none".
CREATE TABLE activity_blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    node_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('found', 'none', 'needs_clarification', 'failed')),
    message TEXT,
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    CONSTRAINT activity_blocks_node_same_document
        FOREIGN KEY (document_id, node_id) REFERENCES document_nodes (document_id, id) ON DELETE CASCADE
) STRICT;

CREATE TABLE activity_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    record_id INTEGER,
    issue_type TEXT NOT NULL CHECK (issue_type IN (
        'unclear_type', 'unresolved_entity', 'unclear_participation', 'unclear', 'block_failed', 'other'
    )),
    message TEXT NOT NULL CHECK (trim(message) <> ''),
    is_blocking INTEGER NOT NULL DEFAULT 0 CHECK (is_blocking IN (0, 1)),
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CONSTRAINT activity_issues_record_same_document
        FOREIGN KEY (document_id, record_id) REFERENCES activity_records (document_id, id) ON DELETE CASCADE
) STRICT;

-- Stage 4 shared: cached embedding vectors of analysis texts, keyed by model, text format and the
-- SHA-256 of the exact embedded text (vectors are float64 little-endian bytes).
CREATE TABLE embedding_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL CHECK (trim(model) <> ''),
    text_format TEXT NOT NULL CHECK (trim(text_format) <> ''),
    text_sha256 TEXT NOT NULL CHECK (length(text_sha256) = 64),
    dimensions INTEGER NOT NULL CHECK (dimensions > 0),
    vector BLOB NOT NULL,
    CONSTRAINT embedding_cache_identity UNIQUE (model, text_format, text_sha256)
) STRICT;

-- Stage 4.1 tables (function collisions) go below this line.

-- Stage 4.1 (methodology/04_1_function_collisions.md): pairs of function/duty assignments of ONE
-- document selected by embeddings (similarity strictly above 0.75) and verified by the model.
-- A re-run deletes and rewrites all of these rows in one transaction. Composite keys
-- (document_id, id) keep views, pairs, records and sources inside the same document.

-- Coverage of the latest run: compared sides and pairs per search path (allowed / above threshold).
CREATE TABLE collision_runs (
    document_id INTEGER PRIMARY KEY REFERENCES documents (id) ON DELETE CASCADE,
    threshold REAL NOT NULL,
    embedding_model TEXT NOT NULL CHECK (trim(embedding_model) <> ''),
    metric TEXT NOT NULL CHECK (trim(metric) <> ''),
    text_format TEXT NOT NULL CHECK (trim(text_format) <> ''),
    compared_records INTEGER NOT NULL CHECK (compared_records >= 0),
    compared_views INTEGER NOT NULL CHECK (compared_views >= 0),
    context_records INTEGER NOT NULL CHECK (context_records >= 0),
    local_pairs INTEGER NOT NULL CHECK (local_pairs >= 0),
    local_above INTEGER NOT NULL CHECK (local_above >= 0 AND local_above <= local_pairs),
    category_pairs INTEGER NOT NULL CHECK (category_pairs >= 0),
    category_above INTEGER NOT NULL CHECK (category_above >= 0 AND category_above <= category_pairs),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

-- One consolidated view of a joint assignment: the records of one provision_key with participation
-- 'joint'. Analytical only: it creates no entity and assigns nothing to the participants' parent.
CREATE TABLE collision_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    provision_key TEXT NOT NULL CHECK (length(provision_key) = 16),
    record_type TEXT NOT NULL CHECK (record_type IN ('function', 'duty')),
    formulation TEXT NOT NULL CHECK (trim(formulation) <> ''),
    -- JSON arrays: known participants, their resolved parents and their categories.
    participant_entity_ids TEXT NOT NULL CHECK (
        CASE WHEN json_valid(participant_entity_ids)
            THEN json_type(participant_entity_ids) = 'array' AND json_array_length(participant_entity_ids) > 0
            ELSE 0 END
    ),
    parent_entity_ids TEXT NOT NULL DEFAULT '[]' CHECK (
        CASE WHEN json_valid(parent_entity_ids) THEN json_type(parent_entity_ids) = 'array' ELSE 0 END
    ),
    categories TEXT NOT NULL DEFAULT '[]' CHECK (
        CASE WHEN json_valid(categories) THEN json_type(categories) = 'array' ELSE 0 END
    ),
    -- The exact text that was embedded (format activity-v1).
    embedded_text TEXT NOT NULL CHECK (trim(embedded_text) <> ''),
    CONSTRAINT collision_views_document_identity UNIQUE (document_id, id),
    CONSTRAINT collision_views_one_per_provision UNIQUE (document_id, provision_key)
) STRICT;

-- Source records of a view (the stage 3 records stay unchanged).
CREATE TABLE collision_view_records (
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    view_id INTEGER NOT NULL,
    record_id INTEGER NOT NULL,
    PRIMARY KEY (view_id, record_id),
    CONSTRAINT collision_view_records_view_same_document
        FOREIGN KEY (document_id, view_id) REFERENCES collision_views (document_id, id) ON DELETE CASCADE,
    CONSTRAINT collision_view_records_record_same_document
        FOREIGN KEY (document_id, record_id) REFERENCES activity_records (document_id, id) ON DELETE CASCADE
) STRICT;

-- One row per unordered pair of sides, however many search paths found it.
CREATE TABLE collision_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    -- Sorted side keys, e.g. 'R12|V3': swapping the sides gives the same pair.
    pair_key TEXT NOT NULL CHECK (trim(pair_key) <> ''),
    side_a_kind TEXT NOT NULL CHECK (side_a_kind IN ('record', 'view')),
    side_a_record_id INTEGER,
    side_a_view_id INTEGER,
    side_b_kind TEXT NOT NULL CHECK (side_b_kind IN ('record', 'view')),
    side_b_record_id INTEGER,
    side_b_view_id INTEGER,
    -- JSON array of 'local' / 'category'; details say which participants gave each basis.
    bases TEXT NOT NULL CHECK (
        CASE WHEN json_valid(bases) THEN json_type(bases) = 'array' AND json_array_length(bases) > 0 ELSE 0 END
    ),
    basis_details TEXT NOT NULL CHECK (
        CASE WHEN json_valid(basis_details) THEN json_type(basis_details) = 'array' ELSE 0 END
    ),
    -- Raw cosine similarity; only pairs strictly above the threshold are stored.
    similarity REAL NOT NULL CHECK (similarity > 0.75 AND similarity <= 1.000001),
    embedding_model TEXT NOT NULL CHECK (trim(embedding_model) <> ''),
    metric TEXT NOT NULL CHECK (trim(metric) <> ''),
    text_format TEXT NOT NULL CHECK (trim(text_format) <> ''),
    question_id TEXT NOT NULL CHECK (trim(question_id) <> ''),
    status TEXT NOT NULL CHECK (status IN ('checked', 'error')),
    verdict TEXT CHECK (verdict IS NULL OR verdict IN ('collision', 'no_collision', 'insufficient_data')),
    explanation TEXT,
    error TEXT,
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    CONSTRAINT collision_pairs_document_identity UNIQUE (document_id, id),
    CONSTRAINT collision_pairs_one_per_pair UNIQUE (document_id, pair_key),
    CONSTRAINT collision_pairs_side_a CHECK (
        (side_a_kind = 'record' AND side_a_record_id IS NOT NULL AND side_a_view_id IS NULL)
        OR (side_a_kind = 'view' AND side_a_view_id IS NOT NULL AND side_a_record_id IS NULL)
    ),
    CONSTRAINT collision_pairs_side_b CHECK (
        (side_b_kind = 'record' AND side_b_record_id IS NOT NULL AND side_b_view_id IS NULL)
        OR (side_b_kind = 'view' AND side_b_view_id IS NOT NULL AND side_b_record_id IS NULL)
    ),
    CONSTRAINT collision_pairs_distinct_sides CHECK (
        side_a_record_id IS NOT side_b_record_id OR side_a_view_id IS NOT side_b_view_id
    ),
    -- An error is never a verdict; a verdict always carries its explanation.
    CONSTRAINT collision_pairs_outcome CHECK (
        (status = 'checked' AND verdict IS NOT NULL AND trim(coalesce(explanation, '')) <> '' AND error IS NULL)
        OR (status = 'error' AND verdict IS NULL AND trim(coalesce(error, '')) <> '')
    ),
    CONSTRAINT collision_pairs_a_record_same_document
        FOREIGN KEY (document_id, side_a_record_id) REFERENCES activity_records (document_id, id) ON DELETE CASCADE,
    CONSTRAINT collision_pairs_a_view_same_document
        FOREIGN KEY (document_id, side_a_view_id) REFERENCES collision_views (document_id, id) ON DELETE CASCADE,
    CONSTRAINT collision_pairs_b_record_same_document
        FOREIGN KEY (document_id, side_b_record_id) REFERENCES activity_records (document_id, id) ON DELETE CASCADE,
    CONSTRAINT collision_pairs_b_view_same_document
        FOREIGN KEY (document_id, side_b_view_id) REFERENCES collision_views (document_id, id) ON DELETE CASCADE
) STRICT;

-- Verified evidence of a verdict: quote_start/quote_end index document_nodes.text of node_id.
CREATE TABLE collision_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    pair_id INTEGER NOT NULL,
    node_id INTEGER NOT NULL,
    quote TEXT NOT NULL CHECK (trim(quote) <> ''),
    quote_start INTEGER NOT NULL CHECK (quote_start >= 0),
    quote_end INTEGER NOT NULL,
    -- JSON array of side_a, side_b, context.
    supports TEXT NOT NULL CHECK (
        CASE WHEN json_valid(supports) THEN json_type(supports) = 'array' ELSE 0 END
    ),
    CONSTRAINT collision_sources_range CHECK (quote_end > quote_start),
    CONSTRAINT collision_sources_pair_same_document
        FOREIGN KEY (document_id, pair_id) REFERENCES collision_pairs (document_id, id) ON DELETE CASCADE,
    CONSTRAINT collision_sources_node_same_document
        FOREIGN KEY (document_id, node_id) REFERENCES document_nodes (document_id, id) ON DELETE CASCADE
) STRICT;

-- Stage 4.2 tables (function cascade) go below this line.

COMMIT;
