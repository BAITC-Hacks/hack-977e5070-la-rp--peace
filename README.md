# la(rp)-peace — ИИ-агент «Анализ организационной структуры и функционала»

Прототип агента, который сравнивает организационные документы «до» и «после» реорганизации,
находит потерю и дублирование функций и даёт объяснимое заключение со ссылками на пункты
исходных документов.

## Запуск

Нужны [uv](https://docs.astral.sh/uv/) и Docker.

```bash
uv sync
docker compose up -d db
uv run uvicorn la_rp_peace.api.app:create_app --factory --reload
```

API: <http://localhost:8000>, интерактивная документация: <http://localhost:8000/docs>.
Настройки — переменные окружения или `.env` (см. `.env.example`).

Загрузить документ:

```bash
curl -F set=before -F "file=@test_data/<файл>.docx" http://localhost:8000/api/documents
```

## Проверки

```bash
uv run ruff format . && uv run ruff check --fix .
uv run mypy .
uv run pytest -q          # без Docker: тесты используют SQLite в памяти
```

## Архитектура

- `src/la_rp_peace/ingestion` — разбор Word/PDF/Excel в дерево пунктов с якорями для цитирования
  (`п. 5.3.2 «а»`); на них ссылается каждый вывод агента.
- `src/la_rp_peace/api` — FastAPI, PostgreSQL через SQLAlchemy.
- `src/la_rp_peace/analysis` — этапы сравнения по методологии.
- `frontend/` — интерфейс на SvelteKit.

Подробнее: [`.agents/backend.md`](.agents/backend.md), [`.agents/frontend.md`](.agents/frontend.md).

## Команда

la(rp)-peace
