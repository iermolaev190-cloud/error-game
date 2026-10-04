# WORLD//ERROR

Persistent multiplayer world engine.

Telegram — только интерфейс. AI — только интерфейс/помощник, не источник истины.
Один игровой Telegram-чат = один независимый `WORLD INSTANCE`.

> Статус: **шаг 0 — структура репозитория**. Игровой код ещё не написан.

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
├── AGENTS.md
├── MASTER_SPEC.md
├── CODING_RULES.md
├── README.md
├── .env.example
├── docs/
│   ├── canon/
│   ├── design/
│   └── archive/
├── src/            # код (появится в коммите 1)
├── tests/          # тесты, в корне, по MASTER_SPEC.md §12
├── content/        # контент мира, отдельно от кода
└── migrations/     # Alembic
```

Правило слоёв: `src/world_error/domain/` не импортирует `sqlalchemy`, `alembic`, `aiogram`, `pydantic`,
`infrastructure`, `interfaces`, `bootstrap`.

---

## Стек

- Python 3.12
- SQLAlchemy 2.x + Alembic
- Pydantic v2 / pydantic-settings
- pytest
- Локально — SQLite, прод-цель — PostgreSQL
- `aiogram` — только на фазе Telegram (Phase 23 roadmap)

---

## Разработка

Один вертикальный срез за раз. Перед большой задачей: прочитать канон → посмотреть код → предложить план →
дождаться подтверждения → реализовать маленькими шагами → добавить тесты → коммит.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest -q
```

Порядок работ: шаг 0 (структура) → коммит 1 (фундамент: WorldInstance, Event Engine skeleton, минимальный
WorldState, persistence, save/load/restart, тест изоляции A/B) → коммит 2 (Character, Location, MOVE, INSPECT,
Information + Knowledge) → канон-коммит (статусы Canonical, правило DM/INSTANCE, актуализация §2/§12).
