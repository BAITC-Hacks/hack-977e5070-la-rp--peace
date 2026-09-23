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

COMMIT;
