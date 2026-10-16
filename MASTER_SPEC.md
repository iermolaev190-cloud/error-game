# MASTER_SPEC.md — WORLD//ERROR

Status: Canonical
**Версия:** 1.0
**Назначение:** Единая точка входа для разработки. Ссылается на канонические документы, не дублирует их.

> Если что-то в этом файле противоречит `docs/canon/*` — приоритет у `docs/canon/*`.
> Если что-то в `docs/design/*` противоречит этому файлу или `docs/canon/*` — приоритет у этого файла и `docs/canon/*`.

---

## 1. Что такое WORLD//ERROR

`WORLD//ERROR` — это persistent multiplayer world engine.

Не Telegram-бот с квестами.
Не LLM-песочница.
Не набор скриптов.

Это система, в которой:

- существует независимый `WORLD INSTANCE`;
- состояние мира меняется через события;
- игроки видят не истину, а информацию о мире;
- NPC живут своей жизнью с ограниченным знанием;
- действия имеют последствия, в том числе отложенные;
- AI не является источником истины;
- Telegram является только интерфейсом.

Ключевая формула:

```text
WORLD STATE
    ↓
PLAYER INTENT
    ↓
WORLD ENGINE
    ↓
EVENT
    ↓
STATE TRANSITION
    ↓
CONSEQUENCE
    ↓
KNOWLEDGE
    ↓
AI / PRESENTATION
    ↓
PLAYER
```

Обратный порядок запрещён.

---

## 2. Канонические документы

Приоритет чтения для coding AI:

1. `AGENTS.md` — правила работы агента (корень репозитория).
2. `MASTER_SPEC.md` — этот файл (корень репозитория).
3. `CODING_RULES.md` — жёсткие правила кода (корень репозитория).
4. `docs/canon/19_MVP_V1_FOR_AI.txt` — что доказываем в MVP.
5. `docs/canon/20_TECH_ARCHITECTURE_V1_FOR_AI.txt` — как строим.
6. `docs/canon/11_WORLD_STATE_V1.txt` — состояние мира.
7. `docs/canon/12_TIME_AND_TIMELINE_V1.txt` — время.
8. `docs/canon/14_MULTIPLAYER_V1.txt` — мультиплеер и инстансы.
9. `docs/canon/15_ECONOMY_V1.txt` — экономика: канон для **целевой** системы.
   В MVP действует ограничение из §9: деньги + предметы + простая торговля;
   производство, рынки, налоги и макроэкономика в MVP не входят.

Фактическая раскладка документации:

- корень: 3 входных документа (`AGENTS.md`, `MASTER_SPEC.md`, `CODING_RULES.md`) и `README.md`;
- `docs/canon/` — 6 содержательных канонических документов (V1), перечислены в пп. 4–9;
- `docs/design/` — 15 документов деталей: `00_VISION`, `01_WORLD_RULES`, `02_PLAYER`, `03_WORLD`,
  `04_LOCATIONS`, `05_NPCS`, `06_FACTIONS`, `07_KNOWLEDGE`, `08_INFORMATION`,
  `09_CLUES_AND_DOCUMENTS`, `10_EVENTS`, `13_CONSEQUENCES`, `16_AI_SYSTEM`, `17_ARG_LAYER`,
  `21_ROADMAP`. Использовать только если в каноне чего-то нет;
- `docs/archive/` — 6 устаревших версий (`11_WORLD_STATE`, `12_TIME_AND_TIMELINE`,
  `14_MULTIPLAYER`, `15_ECONOMY`, `19_MVP`, `20_TECH_ARCHITECTURE`). Источником истины не являются
  и при конфликтах не используются.

Если возникает конфликт — использовать `docs/canon/*` (V1) и этот файл.

---

## 3. Жёсткие архитектурные правила

Их нельзя нарушать ни при каких обстоятельствах.

1. **Один Telegram-чат = один независимый `WORLD INSTANCE`.**
2. **Telegram — адаптер, не движок.**
3. **AI — интерфейс/помощник, не источник истины.**
4. **Все значимые изменения состояния идут через `EVENT`.**
5. **База данных хранит состояние и историю, но не содержит игровую логику.**
6. **Данные разных `WORLD INSTANCE` не смешиваются.**
7. **`PLAYER KNOWLEDGE` ≠ `WORLD TRUTH`.**
8. **Знание NPC ограничено его источниками.**
9. **AI никогда не мутирует каноническое состояние напрямую.**
10. **Не создавать God Object / `GameManager`.**
11. **Не переписывать архитектуру ради одной функции.**
12. **Не добавлять систему, если она не отвечает на 5 вопросов** (см. §8).
13. **Не подключать AI раньше, чем World Engine работает сам.**
14. **Не строить микросервисы на старте. Начинать с modular monolith.**
15. **Если новое требование конфликтует с архитектурой — остановиться и объяснить конфликт, а не обходить.**
16. **Игровой `INSTANCE` создаётся только групповым Telegram-чатом. DM — не `INSTANCE`, а персональный канал внутри активного `INSTANCE`; `world_instance_id` обязателен для любой игровой операции, включая DM. Активный `INSTANCE` определяется сессией или последним групповым чатом пользователя.**

---

## 4. Основные сущности

Минимальный набор для MVP.

### Global / Content

- `ContentDefinition` — глобальные неизменяемые шаблоны: предметы, NPC, локации, документы.
- `ContentVersion` — версия контента.

### Instance-scoped

Всё, что принадлежит конкретному `WORLD_INSTANCE`:

- `WorldInstance` — сам мир.
- `WorldState` — текущее состояние мира.
- `Character` — персонаж игрока.
- `Player` — аккаунт игрока (может иметь персонажей в разных инстансах).
- `Location` — состояние локации.
- `NPC` — конкретный NPC в мире.
- `Faction` — организация.
- `Item` — конкретный экземпляр предмета.
- `Information` — информационный объект.
- `Knowledge` — знание конкретного субъекта.
- `Relationship` — отношение между субъектами.
- `Event` — изменение мира.
- `Transaction` — атомарная операция (торговля, передача).
- `ScheduledEvent` — будущее событие.
- `Snapshot` — снимок состояния.
- `Investigation` — расследование (появляется позже).

### Пример минимальной модели

```text
WorldInstance
├── id
├── telegram_chat_id
├── seed
├── current_time
├── world_tick
├── state_version
├── content_version
├── status
└── created_at
```

```text
Character
├── id
├── world_instance_id
├── player_id
├── name
├── status
├── location_id
├── attributes
├── inventory_ref
├── knowledge_ref
├── relationships_ref
└── history_ref
```

```text
Event
├── id
├── world_instance_id
├── type
├── actor
├── target
├── cause
├── payload
├── created_at
├── executed_at
└── result
```

---

## 5. Поток обработки запроса

Каждый игровой запрос проходит строго этот путь.

```text
Telegram Update
    ↓
Telegram Adapter
    ↓
Resolve USER
    ↓
Resolve CHAT
    ↓
Resolve WORLD INSTANCE
    ↓
Intent (парсинг естественного языка или команда)
    ↓
Application Layer
    ↓
World Engine
    ↓
Authorization
    ↓
Validation
    ↓
Event
    ↓
State Transition (transaction)
    ↓
Knowledge Update
    ↓
Consequences
    ↓
Action Result
    ↓
AI / Template
    ↓
Telegram Adapter
    ↓
Message
```

Запрещённый поток:

```text
Telegram handler → LLM → Database
```

---

## 6. Границы AI

AI **может**:

- интерпретировать естественный язык в `Intent`;
- вести диалог от лица NPC в рамках его знаний;
- формулировать тексты документов;
- суммировать и анализировать информацию для игрока;
- переводить и адаптировать стиль.

AI **не может**:

- менять `WorldState`;
- решать, произошло ли событие;
- решать, существует ли объект;
- решать, кто умер;
- решать, кому принадлежит предмет;
- менять экономику;
- раскрывать секреты вне knowledge filter;
- получать доступ ко всей базе мира.

Схема:

```text
WORLD DATABASE
    ↓
ACCESS CONTROL
    ↓
KNOWLEDGE FILTER
    ↓
AI CONTEXT
    ↓
AI OUTPUT
    ↓
VALIDATOR
    ↓
PLAYER
```

---

## 7. Изоляция WORLD INSTANCE

Критическое правило.

```text
INSTANCE A    X    INSTANCE B
```

Каждая изменяемая игровая сущность обязана иметь `world_instance_id`:

- Character
- Location
- NPC
- Item instance
- Faction
- Event
- Knowledge
- Information
- Relationship
- Transaction
- Investigation

Исключение: глобальные `ContentDefinition`, не содержащие instance-специфичного состояния.

Любая игровая операция выполняется только в контексте конкретного instance:

```text
handle_intent(world_instance_id, actor_id, intent)
```

### DM и INSTANCE

```text
GROUP CHAT  →  WORLD INSTANCE                      (создаёт мир)
DM          →  персональный канал внутри INSTANCE  (мир не создаёт)
```

- Игровой `INSTANCE` создаётся **только** групповым Telegram-чатом.
- DM — не `INSTANCE`: это персональный вид того же мира (личное знание, инвентарь, приватные действия).
- `world_instance_id` обязателен для любой игровой операции, включая DM.
- Активный `INSTANCE` для DM определяется сессией или последним групповым чатом пользователя.
- `DM chat_id` не может быть единственным идентификатором мира.

---

## 8. Правило добавления новых систем

Перед добавлением любой системы задать пять вопросов:

1. Какая сущность меняется?
2. Какое событие происходит?
3. Какое состояние меняется?
4. Какое знание меняется?
5. Что может произойти дальше?

Если ответов нет — система не добавляется.

Контент добавляется только если связан минимум с двумя существующими системами.

---

## 9. Область MVP

MVP доказывает **ядро**, а не масштаб.

### Входит в MVP

- `WORLD INSTANCE` с изоляцией.
- `WORLD STATE` с persistence.
- `EVENT ENGINE` с event log.
- `SNAPSHOTS` и recovery.
- `PLAYER / CHARACTER`.
- 5–8 связанных локаций.
- Базовые действия: `MOVE`, `SEARCH`, `INSPECT`, `TAKE`, `USE`, `GIVE`, `TALK`, `SHARE`.
- `INFORMATION` и `KNOWLEDGE`.
- `MULTIPLAYER` на 3–10 игроков.
- 5–10 значимых NPC.
- 2–3 фракции.
- `CONSEQUENCES` (в том числе отложенные).
- `TIME` (event-driven).
- Одно настоящее расследование.
- Простая экономика: деньги, предметы, простая торговля (`15_ECONOMY_V1` — целевая система, не MVP).
- `DEATH` и создание нового персонажа.
- `LEGACY` (минимум одна механика).
- `AI` как intent parser и NPC dialogue.
- `TELEGRAM` как group + DM.
- Один внешний `ARG` элемент.
- Базовый `ADMIN / DEBUG`.

### Не входит в MVP

- Большая карта.
- Сотни NPC.
- Полноценная политика.
- Полноценная макроэкономика.
- Сложная боевая система.
- Сложный crafting.
- Кросс-инстанс механики.
- Масштабная процедурная генерация.
- Полноценный ARG.
- Микросервисы.

---

## 10. Первый вертикальный срез

Первый реально программируемый кусок.

```text
CREATE WORLD INSTANCE
    ↓
CREATE CHARACTER
    ↓
MOVE
    ↓
INSPECT
    ↓
FIND INFORMATION
    ↓
CREATE EVENT
    ↓
CHANGE WORLD STATE
    ↓
SAVE
    ↓
RESTART
    ↓
LOAD
```

Пока этот цикл не работает — нельзя добавлять что-либо сверху.

Обязательный тест: два инстанса A и B, изменение A не влияет на B.

---

## 11. Стек (рекомендация)

Для MVP:

- **Язык:** Python
- **Telegram:** `aiogram`
- **База:** PostgreSQL
- **ORM:** SQLAlchemy + Alembic
- **Валидация:** Pydantic
- **Тесты:** pytest
- **Очереди/локи:** Redis (только когда реально нужно)
- **Архитектура:** modular monolith

Не использовать микросервисы на старте.

---

## 12. Структура проекта

```text
world-error/
├── AGENTS.md
├── MASTER_SPEC.md
├── CODING_RULES.md
├── README.md
├── pyproject.toml
├── alembic.ini
├── docs/
│   ├── canon/              # 6 канонических V1-документов
│   ├── design/             # 15 документов деталей
│   └── archive/            # 6 устаревших версий
├── content/                # контент мира: определения, не состояние
│   ├── manifest.json
│   ├── locations/
│   └── information/
├── migrations/
│   ├── env.py
│   └── versions/
├── src/world_error/
│   ├── domain/             # world, events, characters, locations,
│   │                       # information, knowledge, content, shared
│   ├── application/        # action_result.py, commands/, ports/, services/
│   ├── infrastructure/     # db/{tables,engine,unit_of_work,repositories/}, content/
│   ├── interfaces/         # cli/ (Telegram — отдельная фаза)
│   └── bootstrap/          # config.py, container.py
└── tests/
    ├── conftest.py
    ├── test_layering.py
    ├── unit/
    ├── integration/
    ├── invariants/
    └── scenarios/
```

Появятся позже (не создавать заранее): `domain/{npcs,factions,items,economy,investigations,consequences,time}`,
`infrastructure/{telegram,ai,scheduler,queue}`, `content/{npcs,factions,items,clues,investigations}`.

Правило слоёв: `domain/` не импортирует `telegram`, `aiogram`, `http`, `fastapi`, `sqlalchemy`,
`alembic`, `pydantic`, а также `infrastructure/`, `interfaces/`, `bootstrap/`.
Проверяется автоматически: `tests/test_layering.py`.

---

## 13. Порядок разработки

Строго по roadmap, один вертикальный срез за раз.

```text
1. Foundation (env, db, migrations, tests)
2. WORLD INSTANCE
3. WORLD STATE
4. EVENT ENGINE
5. Persistence + snapshots + recovery
6. Character
7. Locations
8. Actions
9. Information / Knowledge
10. Multiplayer
11. NPC core (без AI)
12. Relationships
13. Consequences
14. Time
15. Death
16. New character + legacy
17. Factions
18. Simple economy
19. Investigation engine + первое расследование
20. AI interpreter
21. AI NPC dialogue
22. Telegram integration (group + DM)
23. ARG prototype
24. Admin / Debug tools
25. Internal playtest
26. Fix first, expand later
27. Closed alpha
```

AI подключается **только после пункта 19** — когда World Engine уже работает самостоятельно.

---

## 14. Инварианты

Проверяются автоматически.

- Мёртвый персонаж не выполняет обычные физические действия.
- Предмет не может принадлежать двум владельцам одновременно.
- Деньги не уходят в минус без явной поддержки долга.
- NPC не может быть в двух локациях одновременно.
- Персонаж не может быть в двух локациях одновременно.
- Событие не обрабатывается дважды, если оно не повторяемое.
- Инстанс не может ссылаться на приватное состояние другого инстанса.
- Одно событие не может случайно применяться дважды.
- `Player` не равен `Character`.
- `Telegram message` не является игровым событием.

---

## 15. Стоп-сигналы для coding AI

Если AI предлагает что-то из этого списка — остановиться и объяснить конфликт с архитектурой:

- «AI сам решит, что произошло».
- «Положим игровую логику прямо в Telegram handler».
- «Сделаем один большой `GameManager`».
- «AI напрямую обновит базу данных».
- «Объединим два инстанса».
- «Сначала сделаем красивый интерфейс, потом движок».
- «Добавим микросервисы сейчас».
- «Сделаем сразу всю игру».
- «Храним состояние в сообщениях Telegram».
- «AI получает весь world state».
- «Перепишем архитектуру ради одной функции».
- «Обойдём существующую систему, чтобы быстрее».

Каждый такой случай — сигнал, что агент потерял канон. Нужно вернуть его к `AGENTS.md` и этому файлу.

---

## 16. Definition of Done

Функция считается готовой, когда:

- находится в правильном слое;
- имеет единственный source of truth;
- имеет validation;
- корректно меняет state через event;
- создаёт необходимые записи в event log;
- сохраняется в БД;
- имеет тесты;
- не ломает instance isolation;
- не даёт AI лишних полномочий;
- имеет понятный error path;
- закоммичена отдельным осмысленным коммитом.

---

## 17. Финальный принцип

> Сначала строим мир, который умеет существовать.
> Потом персонажей, которые умеют в нём действовать.
> Потом информацию, которая позволяет его понимать.
> Потом последствия, которые делают действия значимыми.
> Потом AI, который делает взаимодействие естественным.
> И только после этого начинаем строить большую вселенную.

---

**Конец MASTER_SPEC.md**
