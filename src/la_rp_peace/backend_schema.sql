-- Backend additions to methodology/01_document_parsing.sql, applied right after it on a new
-- database. Only what the methodology leaves to "the existing storage mechanism".
BEGIN;

-- Uploaded bytes, one row per document; the methodology keeps only the extracted text.
CREATE TABLE document_files (
    document_id INTEGER PRIMARY KEY REFERENCES documents (id) ON DELETE CASCADE,
    content BLOB NOT NULL
) STRICT;

-- Which side of the comparison the user uploaded the document for.
ALTER TABLE documents ADD COLUMN doc_set TEXT
    CHECK (doc_set IS NULL OR doc_set IN ('before', 'after', 'regulatory', 'benchmark'));

COMMIT;
