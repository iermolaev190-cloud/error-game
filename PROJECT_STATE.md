# PROJECT_STATE.md — WORLD//ERROR

Это единственная точка входа для нового coding AI.
Читать первым, до всего остального.

## Что за проект

WORLD//ERROR — persistent multiplayer world engine для Telegram.
Не телеграм-бот с квестами. Движок мира, где Telegram — интерфейс.
Один групповой чат = один WORLD INSTANCE.
DM — канал внутри активного INSTANCE, не создаёт мир.
AI — интерфейс, не источник истины.
Telegram не содержит игровой логики.

## Стек

- Python 3.12
- SQLAlchemy 2.x, Alembic, pydantic, pytest
- SQLite локально (прод-цель PostgreSQL)
- .venv/ в корне

## Состояние

HEAD: 9009740 — fix(core): process due events before player actions.
Тесты: 575 passed, exit 0 (`pytest -q`).
Коммиты 14a, 14b, 14c, 14d, ARG links, Telegram UX fixes, Telegram command mention fix, Admin/Debug и Registration завершены.

## Порядок чтения для нового AI

1. PROJECT_STATE.md (этот файл)
2. AGENTS.md
3. MASTER_SPEC.md (§3, §9, §13)
4. CODING_RULES.md
5. docs/canon/19_MVP_V1_FOR_AI.txt (§15 первая investigation)
6. docs/canon/20_TECH_ARCHITECTURE_V1_FOR_AI.txt
7. docs/canon/11_WORLD_STATE_V1.txt (§35 source of truth)
8. docs/design/09_CLUES_AND_DOCUMENTS.txt (для коммита 11)

## Что уже сделано

Все коммиты в git log. Кратко:

- b452f87 baseline документов
- 77febae restructure docs
- e0ce558 коммит 1 — фундамент (WorldInstance, Event, WorldState, persistence)
- 9af8ec5 коммит 2 — Character, Location, MOVE, INSPECT, Information, Knowledge
- 397f726 канон-коммит
- 6c8e75c нормализация Status
- 7642b1b коммит 3a — CLAIM/RUMOR/THEORY/BELIEF, KNOWLEDGE_SHARED
- 777974d коммит 3b — LocationView, CAS по state_version
- b3038a5 коммит 4 — NPC core без AI
- 880bc7c коммит 5 — асимметричные отношения, значимые действия
- 2fe30fa коммит 6 — последствия
- 859a1e7 коммит 7 — scheduled events, cancel/transform
- 337a68d коммит 8 — death, action cost, legacy document
- e5e9c8e коммит 9 — Factions (Phase 18)
- d027945 фикс F2 CLI test
- 68acef9 коммит 10 — Simple economy (Phase 19)
- коммит 11 — Investigation engine (Phase 20)
- e6fe130 коммит 12 — AI intent interpreter (Phase 21)
- 7545f15 коммит 13 — AI NPC dialogue (Phase 22)
- bf21218 коммит 14a — Telegram group adapter, chat bindings
- c81e098 коммит 14b — Telegram DM channel
- 194213f коммит 14c — Telegram slash command interface
- 6c41075 fix — регистрация Telegram DM handler
- 18edf5f коммит 16a — curated information links (ARG)
- 0e453fe коммит 14d — GIVE, SHARE, TRADE и fallback command templates
- 750b92e fix — дружелюбные player-facing сообщения об ошибках Telegram
- 27883dc fix — strip `@BotUsername` from Telegram slash commands
- df282f5 feat — Telegram Admin tools, Phase 26
- faee5a0 chore — PROJECT_STATE после Admin tools
- ae8dbbd feat — DM character registration, Phase 27a
- 9009740 fix — scheduled events before player actions, Unicode names, CAS regression

Миграции: 0001-0013.

## Ключевые архитектурные решения

- Один групповой чат = один INSTANCE. DM — не INSTANCE.
- AI не источник истины. Только интерфейс.
- Telegram не содержит логики.
- Все значимые изменения идут через EVENTS.
- domain/ не импортирует инфраструктуру (test_layering).
- relationships: holder_*/subject_*, не source_*/target_*.
- relationships: INCREASE/DECREASE, не IMPROVE/WORSEN.
- TRUST + SUSPICION. Лестницы с базами NEUTRAL и NONE.
- HELPED, BETRAYED, LIED_TO как значимые действия.
- NPC материализуются из content/npcs/*.json при создании INSTANCE.
- Consequence: source_event_id обязателен, 3 типа, 3 триггера.
- Насосы без демонов: ConsequenceEngine.pump + ScheduledEventEngine.
- Общий лимит каскада 16 на оба насоса.
- Death: cause_event_id обязателен. Мёртвый не действует.
- Новый персонаж не наследует знание/отношения/инвентарь.
- LegacyDocument через INSPECT, не через аккаунт.
- INACTIVE не убивает по таймеру.
- CostTicks=N: world_tick += N, один ACTION_COST_TICK_CONSUMED.
- CHARACTER_ARRIVAL валидируется при срабатывании.

Решения коммита 9 (Factions, Phase 18):
- FactionDefinition (контент, immutable) vs Faction (instance-state).
- FactionStatus без DISSOLVED (8 состояний).
- RelationshipKind.STANDING: ALLIED←COOPERATE←NEUTRAL→COMPETITIVE→HOSTILE→AT_WAR, база NEUTRAL.
- RelationshipKind.MEMBERSHIP: OUTSIDER→SYMPATHISER→MEMBER→OFFICER, база OUTSIDER.
- MEMBERSHIP только CHARACTER↔FACTION, не NPC.
- visibility в relationships (PUBLIC|SECRET), default PUBLIC.
- visibility меняется тем же change_relationship через payload RELATIONSHIP_CHANGED.
- hidden_goal только в FactionDefinition, не в Faction и не в FactionView.
- faction_locations как child-таблица с composite FK.
- Одно событие FACTION_STATUS_CHANGED.
- Три теста коммита 5 переписаны, не удалены.

Решения коммита 10 (Simple economy, Phase 19):
- ItemDefinition (контент, immutable) vs Item (instance).
- Inventory = запрос по Item.owner, отдельной таблицы нет.
- credits — stackable Item с key="credits", quantity=integer (не float).
- owner_type ∈ {CHARACTER, LOCATION, NONE}. NPC вне среза.
- ItemOwnerType — отдельный enum, не SubjectType.
- unique=True = один экземпляр этого key на instance (частичный UNIQUE-индекс).
- Partial transfer и stack merge разрешены для stackable.
- Одно событие ITEM_TRANSFERRED на операцию, даже при partial + merge.
- MONEY_TRANSFERRED отдельным событием не вводится.
- TRADE — одностороннее действие с co-location, без propose/accept.
- GIVE — односторонняя передача.
- Items мёртвого остаются у мёртвого, новый персонаж не наследует.
- LegacyDocument не превращается в Item.
- Transaction сущность не вводится, атомарность через UoW.
- Всё материализуется из контента, никаких хардкодов.
- dev CLI без auth, identity не проверяется.
- LocationView показывает items локации (name + key), без owner.
- SECRET items не видны в LocationView.

## Коммит 11: Investigation engine (Phase 20)

- CaseDefinition — глобальный content; Case и все результаты расследования — instance-scoped.
- При создании INSTANCE материализуются Case и начальные evidence links из контента.
- Evidence связывает Information с Knowledge конкретного Character; первый claim заполняет authorial link.
- Теории начинаются в ACTIVE; подтверждение без resolution criteria запрещено.
- Case notes append-only: PRIVATE видны автору, CASE_SHARED — другим участникам.
- Вопросы Case append-only и обновляют текущий вопрос.
- Закрытие Case требует заданных content criteria, включая evidence, theory, quorum contributors и actions.
- Suspects могут ссылаться на Character, NPC и Faction; исторический Character-author допустим после смерти, новые действия мёртвого запрещены.
- Case/evidence/theory/note/question/relation операции проверены на event persistence, idempotency, restart и A/B isolation.
- Integration: F1 обнаруживает утечку при удалённом viewer-filter; F2 обнаруживает подтверждение теории без guard.
- Полный набор: 436 passed.

## Коммит 12: AI intent interpreter (Phase 21)

- Добавлен `application/ai/`: Intent, IntentInterpreter, provider-интерфейсы и mock/stub реализации, CommandIntentParser и реестр player intents.
- `Intent` описывает только действие игрока; `world_instance_id` не включён.
- `INTENT_HANDLERS` содержит ровно 18 player intents; системные/world-controlled методы не доступны через реестр.
- `WorldEngine.handle_intent` — тонкий диспетчер через `resolve_handler` и `getattr`; не импортирует `IntentType` и не содержит логики действий.
- CLI получил отдельную подкоманду `interpret`; существующие команды действий сохранены.
- `ai_provider` настраивается как `stub` или `mock`; реального LLM-провайдера нет.
- Container собирает interpreter с command-parser fallback.
- F1/F2/F3 проверены фальсификациями; полный набор: 455 passed.

## Коммит 13: AI NPC dialogue (Phase 22)

- Добавлены `NpcDialogueContext` и builder со scoped knowledge только выбранного NPC; `world_instance_id`, цели без visibility metadata и чужое знание в контекст не передаются.
- Добавлен `NpcDialogueProvider` с stub/mock/template реализациями; template fallback отвечает нейтрально и без фактов.
- `WorldEngine.talk_to_npc` проверяет активность Character/NPC и совпадение локаций, возвращает реплику через `ActionResult`; world state, knowledge, tick и events не меняются.
- `TALK` добавлен как 19-й player intent; CLI получил подкоманду `talk`.
- `NPC_TALKED` не вводится: диалог read-only и не является изменением мира.
- F1–F4 подтверждены; полный набор: 472 passed.

## Коммиты 14a–14c: Telegram integration (Phase 23)

### Коммит 14a — group adapter

- `chat_bindings` связывает Telegram group chat ID с WORLD INSTANCE ID; эти ID не смешиваются.
- Group adapter остаётся транспортным слоем и передаёт действия в `WorldEngine.handle_intent`.
- Первое сообщение в группе выполняет bootstrap: создаёт INSTANCE и binding; это не player action и не создаёт игровых событий.
- Group formatter использует whitelist публичных полей.

### Коммит 14b — DM channel

- `player_telegram_state` хранит `last_group_chat_id`; он обновляется на каждом сообщении пользователя в группе.
- DM выбирает INSTANCE по последней группе, с fallback к единственному активному character.
- DM никогда не создаёт INSTANCE и не выполняет group bootstrap.
- Group и DM используют раздельные formatter whitelists; приватные inventory и knowledge доступны только в DM.

### Коммит 14c — slash command interface

- Добавлены `CommandRouter`, `RoutedCommand` и instance-scoped `key_resolver`.
- Slash actions: `/move`, `/inspect`, `/take`, `/drop`; публичные queries: `/look`, `/npcs`, `/help`.
- Только для DM: `/inventory`, `/knowledge`, `/character`, `/talk`; приватные queries в группе отклоняются до query execution.
- `LocationView` дополнен публичными выходами (exits).
- Query отделён от Intent; игровые actions по-прежнему выполняются через WorldEngine.

### Fix — регистрация Telegram DM handler

- Aiogram router регистрирует private callback наряду с group/supergroup callback.
- Реальные Dispatcher-level тесты проверяют маршрутизацию private и group updates; invariant проверяет оба тонких callback.
- F1/F2 подтверждены; полный набор: 528 passed.

### Коммит 16a — curated information links (ARG)

- `InformationDefinition` поддерживает необязательный `external_url`.
- `inspect_information` возвращает `external_url` в payload при наличии ссылки.
- Formatter выводит ссылку как `Ссылка: ...`; group allowlist разрешает только это поле из payload.
- `content/information/damaged_radio.json` содержит заглушку `https://example.com/archive-17`; заменить реальным URL позже.

### Коммит 14d — GIVE, SHARE, TRADE и command fallback

- Slash-команды `/give <character> <item>`, `/share <character> <information>` и `/trade <character> <offered> <requested>` доступны в группе и DM.
- `InstanceKeyResolver` находит information только в knowledge выбранного персонажа и выбранного INSTANCE; для TRADE requested item разрешается из inventory counterparty.
- `CommandIntentParser` поддерживает `take <item>`, `drop <item>`, `talk to <npc>`, `give <item> to <character>`, `share <information> with <character>` и `trade <offered> to <character> for <requested>`.
- `TelegramCommandExecutor` разрешает цели и предметы, затем вызывает существующие WorldEngine операции GIVE, SHARE и TRADE.
- Fallback-команды для TAKE, DROP, TALK, GIVE, SHARE и TRADE также проходят через resolver/executor; для этого минимально изменены `adapter.py` и `dm_handler.py`.
- Получатель GIVE/SHARE/TRADE должен быть активным персонажем в той же локации; NPC и персонажи из других локаций или INSTANCE отвергаются.
- SHARE передаёт только knowledge/claim отправителя, не truth. GIVE/TRADE используют существующее событие `ITEM_TRANSFERRED`; SHARE — `KNOWLEDGE_SHARED`.
- F1–F4 подтверждены; полный набор: 543 passed.

### Fix — дружелюбные Telegram error messages

- Улучшены player-facing сообщения ошибок без изменения проверок, отказов, событий или state.
- TAKE различает предмет, уже находящийся у персонажа, и предмет, отсутствующий в текущей локации; DROP объясняет, что предмета нет в inventory.
- TALK в группе сообщает, что диалог доступен только в DM, и подсказывает `/talk <npc>`.
- GIVE/SHARE/TRADE с NPC сообщают, что NPC — не игрок; недоступного получателя предлагают проверить по имени и локации.
- Ошибки SHARE, связанные с отсутствием знания, подсказывают проверить `/knowledge` в DM.
- Ошибки выбора INSTANCE и отсутствующего персонажа локализованы; нераспознанный ввод подсказывает `/help`.
- Обновлены только player-facing тексты и тесты этих текстов; полный набор: 546 passed.

### Fix — Telegram command mentions

- `CommandRouter` снимает `@BotUsername` с имени slash-команды, не меняя аргументы и fallback-текст.
- `/give@BotUsername`, `/move@BotUsername` и `/look@BotUsername` маршрутизируются штатно.
- Инвариант подтверждает отсутствие мутации world state при маршрутизации.
- Полный набор перед Admin: 547 passed.

### Admin/Debug — Phase 26 initial Telegram tools

- `WORLD_ERROR_ADMIN_CHAT_ID` задаёт отдельный admin-чат; он обрабатывается раньше game-group resolver и не создаёт WORLD INSTANCE.
- Доступ выдаётся только активным Telegram user IDs из глобальной таблицы `admin_users`; членство в чате не предоставляет права.
- Миграция `0013_admin_users`; первый админ добавляется глобально через `python -m world_error admin add-user --telegram-id X --name Y` (bootstrap `added_by_telegram_id=0` означает system/CLI).
- В admin-чате доступны `/admin`, `worlds`, `instance`, `events`, `character`, `npc`, `location`, `admins`; активный админ может выполнять `/add-admin` и `/remove-admin`.
- Admin queries scoped по указанному `world_id`, не меняют игровой state/events/knowledge. Admin-команды в игровых группах отклоняются до создания/разрешения INSTANCE; в DM отклоняются до DM resolver.
- Фальсификации F1–F4 подтверждены; полный набор: 561 passed.

### Registration — Phase 27a

- `/start` в DM запускает регистрацию через aiogram FSM: подтверждение, ввод имени, завершение; storage — встроенный `MemoryStorage`.
- Активный INSTANCE разрешается через существующий `GroupInstanceResolver`; DM не создаёт INSTANCE.
- Повторный `/start` при существующем character показывает приветствие и локацию; существующий character не дублируется.
- Создание проходит через `WorldEngine.create_character(..., actor="system")`, создаёт штатный `CHARACTER_CREATED` event.
- В группе `/start` отказывает, а игрок без character получает подсказку зарегистрироваться в DM; DM без character направляется к `/start`.
- Добавлены unit, integration и invariant-тесты; фальсификации F1–F3 подтверждены; полный набор: 571 passed.

### Fix — scheduled events, Unicode names, and CAS regression

- Обработчики с насосом мира применяют уже наступившие scheduled events и consequences до следующего действия игрока; cascade limit по-прежнему блокирует действие при достижении лимита.
- Command router, parser и key resolver поддерживают кириллические имена персонажей.
- CAS integration test запускает конкурирующую запись после чтения версии именно тестируемым обработчиком, не полагаясь на число внутренних чтений насоса.
- Полный набор: 575 passed; `compileall` и `git diff --check` прошли.

## TODO

- MASTER_SPEC §13: нумерация фаз устарела; проверить и исправить.
- INSPECT выдаёт `FACT` от одного наблюдения; сверить с `07_KNOWLEDGE §6.1` и согласовать реализацию/канон.
- Сверить ссылки на фазу AI NPC dialogue: в `19_MVP_V1_FOR_AI.txt` §21 описывает AI interface flow, §22 — Telegram; в `20_TECH_ARCHITECTURE_V1_FOR_AI.txt` §§40–43 не являются разделами AI gateway (AI provider/interpreter/generator находятся в §§17–19).
- `NpcDefinition.goals` пока не имеет маркировки public/hidden; не передавать цели NPC в AI context до отдельной модели видимости.
- AI-generated dialogue не проверяется на hallucination; разработать grounding/validation отдельной фазой.
- `/talk <npc>` не содержит message; сейчас передаётся фиксированная реплика по умолчанию.
- `ItemPresence` не содержит `item_id`; key resolver получает ID через instance-scoped repository.
- Нет инварианта регистрации всех интерфейсных handlers (Telegram, CLI, AI); добавить проверку регистрации interface entrypoints.
- Первый срез Admin/Debug не включает все элементы roadmap Phase 26: inspect event by ID, knowledge, pending events/timeline/errors и списки players; определить scope для дальнейшего среза.

## Правила работы

1. Перед большой задачей — сначала план, потом код. Не начинать код без подтверждения.
2. Один коммит = одна закрытая единица.
3. Мелкие фиксы внутри одной фичи — через git commit --amend, не отдельным коммитом.
4. После каждого коммита: pytest -q зелёный, старые тесты не сломаны.
5. Фальсификации на ключевые проверки: показать падает/зелёный.
6. Фальсификации после git add -A, чтобы git checkout -- работал.
7. Временные файлы (_smoke*, .pytest_last.txt, .vscode/tasks.json) удалять до коммита.
8. Если конфликт с архитектурой — остановиться и объяснить, не обходить.
9. pytest долгий (4-5 минут из-за subprocess restart и alembic). Не перезапускать, ждать сводку.
12. После коммита с миграцией — локально выполнить `alembic upgrade head`.
13. План → явный `go` → код. Один `go` разрешает один шаг. После каждого шага показать `git status --short` и `git diff --stat`; без `go` остановиться.
14. После задачи предоставить подробный отчёт: что сделано, тесты, фальсификации, отклонения от плана, аномалии и что не сделано.

## Стоп-сигналы

Никогда:

- удалять или ослаблять старые тесты;
- смешивать данные разных INSTANCE;
- restart-тест без subprocess;
- AI или Telegram раньше фазы;
- God Object / GameManager;
- логика в Telegram handler;
- AI как источник истины;
- NPC как квестодатель;
- отношение как одно число;
- consequence без cause;
- самопричинение каскада;
- смерть от таймера;
- grindy cooldown;
- скрытые часы персонажей без причины;
- расписание в публичном выводе;
- HIDDEN_GOAL фракции в публичном выводе;
- бесконечная эмиссия денег;
- inventory как одно число;
- дублирование ownership;
- неатомарный trade;
- рынки / shops / производство / налоги / кредиты / макроэкономика;
- trade без события;
- раскрытие чужого/private inventory через публичные проекции.

## Как проверять

```powershell
git log -3 --oneline
git status --short
.venv\Scripts\python.exe -m pytest -q