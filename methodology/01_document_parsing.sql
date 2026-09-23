-- Этап 1: исходные документы, дерево текста и замечания парсинга.
-- SQLite 3.38+ с JSON-функциями; не миграция существующего ORM/API.
-- Однократная инициализация отдельного файла БД.
-- PRAGMA нужно выполнять на КАЖДОМ соединении до открытия транзакции.
PRAGMA foreign_keys = ON;
BEGIN;

-- Одна строка — один документ. original_text не меняется после разбора.
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL CHECK (trim(file_name) <> ''),
    source_format TEXT NOT NULL CHECK (trim(source_format) <> ''),
    revision TEXT CHECK (revision IS NULL OR trim(revision) <> ''),
    original_text TEXT NOT NULL
        CHECK (length(original_text) > 0 AND instr(original_text, char(0)) = 0),
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
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
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

COMMIT;
