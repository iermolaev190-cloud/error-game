# WORLD//ERROR

Persistent multiplayer world engine.

Telegram — только интерфейс. AI — только интерфейс/помощник, не источник истины.
Один игровой Telegram-чат = один независимый `WORLD INSTANCE`.

> Статус: **коммит 2 «Первый игровой цикл»**. AI, Telegram, NPC, экономика, фракции и предметы не реализованы.

---

## Канон

Входные документы (корень репозитория):

1. `AGENTS.md` — правила работы агента.
2. `MASTER_SPEC.md` — точка входа, приоритет при конфликте.
3. `CODING_RULES.md` — жёсткие правила кода.

Содержательный канон — `docs/canon/`:

- `11_WORLD_STATE_V1.txt` — состояние мира;
- `12_TIME_AND_TIMELINE_V1.txt` — время;
- `14_MULTIPLAYER_V1.txt` — мультиплеер и инстансы;
- `15_ECONOMY_V1.txt` — экономика (целевая система, в MVP — только деньги, предметы и простая торговля);
- `19_MVP_V1_FOR_AI.txt` — что доказывает MVP;
- `20_TECH_ARCHITECTURE_V1_FOR_AI.txt` — как строим.

`docs/design/` — детали, если в каноне чего-то нет. `docs/archive/` — устаревшие версии документов.
При конфликте: `docs/canon/*` и `MASTER_SPEC.md` важнее `docs/design/*`.

---

## Структура

```text
.
├── AGENTS.md, MASTER_SPEC.md, CODING_RULES.md, README.md
├── docs/{canon,design,archive}/
├── content/                 # контент мира: определения, не состояние
│   ├── manifest.json        # version + start_location
│   ├── locations/*.json     # LocationDefinition + граф связей
│   └── information/*.json   # content (что узнаёт игрок) и truth (канон)
├── migrations/              # Alembic
├── src/world_error/
│   ├── domain/              # правила мира: world, events, characters, locations,
│   │                        # information, knowledge, content, shared
│   ├── application/         # intents/commands, services (World Engine), ports
│   ├── infrastructure/      # db (таблицы, репозитории, UoW), content loader
│   ├── interfaces/cli/      # временный интерфейс (Telegram — позже)
│   └── bootstrap/           # config, container
└── tests/{unit,integration,invariants,scenarios}/
```

Правило слоёв: `src/world_error/domain/` не импортирует `sqlalchemy`, `alembic`, `aiogram`,
`pydantic`, `infrastructure`, `interfaces`, `bootstrap` (проверяется `tests/test_layering.py`).

Разделение, на котором держится проект:

```text
CONTENT (content/, immutable определения)
    ↓
INSTANCE STATE (БД: world_instances, location_states, characters, information, knowledge)
    ↓
KNOWLEDGE (что субъект считает правдой)  ≠  TRUTH (канонический факт из контента)
```

---

## Стек

- Python 3.12, SQLAlchemy 2.x + Alembic, pydantic v2 / pydantic-settings, pytest
- Локально — SQLite, прод-цель — PostgreSQL
- `aiogram` — только на фазе Telegram (Phase 23 roadmap)

---

## Разработка

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m pytest
```

Тесты используют свой basetemp `.pytest_tmp/` (в `.gitignore`), чтобы прогон не зависел от `%TEMP%`.

### Временный CLI

```powershell
.venv\Scripts\python -m world_error create-world --chat-id -1001 --seed 42 --environment TEST
.venv\Scripts\python -m world_error create-character --world-id <wi_id> --player-id player-1 --name "Аня"
.venv\Scripts\python -m world_error move --world-id <wi_id> --character-id <ch_id> --to forest
.venv\Scripts\python -m world_error move --world-id <wi_id> --character-id <ch_id> --to old_station
.venv\Scripts\python -m world_error inspect --world-id <wi_id> --character-id <ch_id> --target damaged_radio
.venv\Scripts\python -m world_error share --world-id <wi_id> --character-id <ch_a> --to-character-id <ch_b> --information damaged_radio
.venv\Scripts\python -m world_error show-character --world-id <wi_id> --character-id <ch_id>
.venv\Scripts\python -m world_error events <wi_id>
```

Канонический факт (`truth`) в интерфейс не выводится: игрок видит только знание персонажа.
Для каждой записи знания `show-character` печатает строку `KNOWLEDGE_PROVENANCE <claim_type> <source> <source_ref>`,
по которой видна цепочка происхождения: у наблюдения `source_ref` — сам наблюдатель, у переданного знания —
тот, кто им поделился.

### Порядок работ

Один вертикальный срез за раз: шаг 0 (структура) → коммит 1 (фундамент: WorldInstance, Event Engine,
persistence, save/load/restart, изоляция A/B) → коммит 2 (Character, Location, MOVE, INSPECT,
Information + Knowledge) → канон-коммит (статусы Canonical, правило DM/INSTANCE, актуализация §2/§12
MASTER_SPEC).
