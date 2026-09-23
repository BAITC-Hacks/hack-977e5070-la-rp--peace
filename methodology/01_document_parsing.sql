-- Этап 1: исходные документы, дерево текста и замечания парсинга.
-- Предлагаемая структура для PostgreSQL 16; не миграция существующего ORM/API.
-- Однократная инициализация отдельной схемы в PostgreSQL.
BEGIN;

CREATE SCHEMA document_parsing;

CREATE TABLE document_parsing.documents (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_name text NOT NULL CHECK (btrim(file_name) <> ''),
    source_format text NOT NULL CHECK (btrim(source_format) <> ''),
    revision text CHECK (revision IS NULL OR btrim(revision) <> ''),
    original_text text NOT NULL CHECK (char_length(original_text) > 0),
    source_map jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(source_map) = 'array'),
    parsing_profile jsonb
        CHECK (parsing_profile IS NULL OR jsonb_typeof(parsing_profile) = 'object'),
    parse_status text NOT NULL DEFAULT 'pending'
        CHECK (parse_status IN ('pending', 'parsed', 'needs_review', 'validated')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE document_parsing.document_nodes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL
        REFERENCES document_parsing.documents (id) ON DELETE CASCADE,
    parent_id bigint,
    position integer NOT NULL CHECK (position >= 0),
    node_type text NOT NULL CHECK (node_type IN (
        'section', 'clause', 'heading', 'list', 'list_item',
        'table', 'table_row', 'table_cell', 'text', 'service'
    )),
    marker text CHECK (marker IS NULL OR btrim(marker) <> ''),
    text text NOT NULL DEFAULT '',
    source_start integer NOT NULL CHECK (source_start >= 0),
    source_end integer NOT NULL,
    CONSTRAINT document_nodes_source_range CHECK (source_end > source_start),
    CONSTRAINT document_nodes_not_own_parent CHECK (parent_id IS DISTINCT FROM id),
    CONSTRAINT document_nodes_document_identity UNIQUE (document_id, id),
    CONSTRAINT document_nodes_parent_same_document
        FOREIGN KEY (document_id, parent_id)
        REFERENCES document_parsing.document_nodes (document_id, id)
        ON DELETE CASCADE
);

-- Порядок уникален среди детей одного родителя и отдельно среди корней.
CREATE UNIQUE INDEX document_nodes_child_position
    ON document_parsing.document_nodes (document_id, parent_id, position)
    WHERE parent_id IS NOT NULL;

CREATE UNIQUE INDEX document_nodes_root_position
    ON document_parsing.document_nodes (document_id, position)
    WHERE parent_id IS NULL;

CREATE TABLE document_parsing.parsing_issues (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL
        REFERENCES document_parsing.documents (id) ON DELETE CASCADE,
    node_id bigint,
    issue_type text NOT NULL CHECK (issue_type IN (
        'empty_content', 'ambiguous_boundary', 'ambiguous_parent',
        'numbering_gap', 'uncovered_text', 'other'
    )),
    message text NOT NULL CHECK (btrim(message) <> ''),
    is_blocking boolean NOT NULL DEFAULT true,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT parsing_issues_node_same_document
        FOREIGN KEY (document_id, node_id)
        REFERENCES document_parsing.document_nodes (document_id, id)
        ON DELETE CASCADE
);

CREATE INDEX parsing_issues_document_node
    ON document_parsing.parsing_issues (document_id, node_id);

COMMENT ON TABLE document_parsing.documents IS
    'Одна строка — один документ; original_text содержит неизменяемое текстовое представление исходника.';
COMMENT ON COLUMN document_parsing.documents.revision IS
    'Редакция при наличии; отсутствие номера редакции не препятствует парсингу.';
COMMENT ON COLUMN document_parsing.documents.source_map IS
    'Массив {start, end, location}: диапазон в original_text и доступные координаты страницы, абзаца или ячейки оригинала.';
COMMENT ON COLUMN document_parsing.documents.parsing_profile IS
    'Проверенный JSON-профиль агента: паттерны, правила иерархии, примеры, изученные диапазоны. До профилирования — NULL.';
COMMENT ON COLUMN document_parsing.documents.parse_status IS
    'pending: ожидает разбора; parsed: разобран; needs_review: нужна проверка; validated: проверен приложением.';
COMMENT ON COLUMN document_parsing.document_nodes.parent_id IS
    'Родитель в дереве текста того же документа; NULL для верхнего уровня. Это не организационная принадлежность.';
COMMENT ON COLUMN document_parsing.document_nodes.position IS
    'Порядковая позиция среди элементов одного родителя, начиная с 0.';
COMMENT ON COLUMN document_parsing.document_nodes.marker IS
    'Исходный номер или маркер: 5.3.2, а, -; NULL при отсутствии. Не является уникальным идентификатором.';
COMMENT ON COLUMN document_parsing.document_nodes.text IS
    'Собственный текст без текста детей. Продолжения после дочерних списков сохраняются текстовыми узлами в исходном порядке.';
COMMENT ON COLUMN document_parsing.document_nodes.source_start IS
    'Начало диапазона в original_text: индекс символа Unicode с 0, не байтовое смещение и не индекс UTF-16.';
COMMENT ON COLUMN document_parsing.document_nodes.source_end IS
    'Исключающая правая граница диапазона в original_text. Диапазон родителя включает дочерние узлы.';
COMMENT ON COLUMN document_parsing.parsing_issues.node_id IS
    'Узел с замечанием; NULL для замечания ко всему документу или ещё не выделенному фрагменту.';
COMMENT ON COLUMN document_parsing.parsing_issues.is_blocking IS
    'Открытое блокирующее замечание не позволяет приложению присвоить документу статус validated.';

COMMIT;
