# la(rp)-peace — ИИ-агент «Анализ организационной структуры и функционала»

Прототип агента, который сравнивает организационные документы «до» и «после» реорганизации,
находит потерю и дублирование функций и даёт объяснимое заключение со ссылками на пункты
исходных документов.

## Запуск

Нужен [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run uvicorn la_rp_peace.api.app:create_app --factory --reload
```

API: <http://localhost:8000>, интерактивная документация: <http://localhost:8000/docs>.
Данные хранятся в одном файле SQLite `data/larp.sqlite3`. Для разбора документов нужны
`OPENAI_API_KEY` и `OPENAI_MODEL` в `.env` (см. `.env.example`): структуру и реквизиты
каждого документа определяет ИИ-профиль, который затем проверяется по исходному тексту.

Загрузить документ:

```bash
curl -F set=before -F "file=@test_data/<файл>.docx" http://localhost:8000/api/documents
```

## Проверки

```bash
uv run ruff format . && uv run ruff check --fix .
uv run mypy .
uv run pytest -q          # офлайн, с записанными ответами модели
uv run pytest -q -m live  # реальные вызовы OpenAI
```

## Архитектура

- `src/la_rp_peace/ingestion` — извлечение текста Word/PDF/Excel с картой позиций, ИИ-профиль
  разбора (регулярные выражения и правила вложенности от модели, проверяемые кодом), дерево
  разделов и пунктов по методологии `methodology/01_document_parsing.md`, карточка реквизитов
  с цитатами-подтверждениями.
- `src/la_rp_peace/sources.py` — каждая цитата проверяется дословно по тексту узла и
  указывает раздел, пункт и страницу/абзац оригинала.
- `src/la_rp_peace/api` — FastAPI, SQLite через SQLAlchemy.
- `src/la_rp_peace/analysis` — этапы сравнения по методологии.
- `frontend/` — интерфейс на SvelteKit.

Подробнее: [`.agents/backend.md`](.agents/backend.md), [`.agents/frontend.md`](.agents/frontend.md).

## Команда

la(rp)-peace
