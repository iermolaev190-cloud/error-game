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

HEAD: 7545f15 — feat(ai): add NPC dialogue layer (коммит 13, Phase 22), завершён.
Тесты: 472 passed, exit 0.
Коммит 13 завершён; обновление PROJECT_STATE.md будет отдельным chore(state).

Следующий этап — AI NPC dialogue (Phase 22).

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

Миграции: 0001-0010.

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

## TODO

- MASTER_SPEC §13: проверить и исправить устаревшую нумерацию ссылки на правила/границы AI.
- Уточнить для INSPECT различие FACT vs CLAIM и привести реализацию/документацию к единому правилу.
- Сверить ссылки на фазу AI NPC dialogue: в `19_MVP_V1_FOR_AI.txt` §21 описывает AI interface flow, §22 — Telegram; в `20_TECH_ARCHITECTURE_V1_FOR_AI.txt` §§40–43 не являются разделами AI gateway (AI provider/interpreter/generator находятся в §§17–19).
- `NpcDefinition.goals` пока не имеет маркировки public/hidden; не передавать цели NPC в AI context до отдельной модели видимости.
- AI-generated dialogue не проверяется на hallucination; разработать grounding/validation отдельной фазой.

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