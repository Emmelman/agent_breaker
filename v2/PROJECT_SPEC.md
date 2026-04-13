# Agent-Breaker v2 — PROJECT SPEC

> Живой документ. Обновляется после каждого изменения.
> Claude Code ОБЯЗАН сверяться с этим файлом при каждой задаче.

---

## 1. Обзор

**Agent-Breaker v2** — фреймворк для автоматического тестирования безопасности ИИ-агентов с эволюцией атак (Ouroboros/OpenClaw pattern).

- **5 рисков**: TOXIC, HALL, DISINFO, AGENCY, GH_RCE
- **Стек**: Python 3.12, NiceGUI, OpenAI-compatible LLM API (LLM Studio)
- **Архитектура**: pipeline generate -> run -> score -> evolve с агентным планированием
- **Multi-model**: разные LLM для генерации (attacker), оценки (judge), ревью (reviewer)
- **KB-aware режим**: HALL и DISINFO (с RAG-факторами) используют KB целевого агента
- **Единый pipeline**: ВСЕ риски идут через один цикл (Planner -> Gen -> Run -> Score -> Evolve)
- **Progress callbacks**: run_batch и run_chain поддерживают progress_callback/step_callback
- **Adaptive Budget**: единый бюджет атак, Planner распределяет между single/multi
- **Technique Leaderboard**: визуализация эффективности техник в Dashboard
- **Meta-Reflection**: Claudini autoresearch loop — анализ всей сессии, prompt evolution, reward hacking detection
- **Background Thinker**: Ouroboros consciousness — фоновый LLM-анализ каждые 20 сек
- **Strategy Memory**: persistent знания между сессиями, версионированные стратегии

### Архитектурная диаграмма

```mermaid
graph TB
    subgraph UI["NiceGUI Web UI (port 8080)"]
        Setup["Настройка"]
        Dashboard["Dashboard"]
        Report["Отчёт"]
    end

    subgraph Pipeline["Testing Pipeline (asyncio)"]
        Planner["Attack Planner<br/>OBS-HYP-DEC"]
        Generator["Attack Generator<br/>single + multi-turn"]
        Runner["Attack Runner<br/>HTTP - target"]
        Scorer["Response Scorer<br/>LLM-as-Judge"]
        Evolution["Evolution Engine<br/>reflect-keep best-mutate-review"]
        Meta["Meta Reflector<br/>diagnosis, prompt evo"]
    end

    subgraph Thinker["Background Thinker"]
        BG["Фоновый анализ<br/>каждые 30 сек"]
    end

    subgraph LLM["LM Studio (localhost:1234)"]
        Gemma["gemma-3-12b-it<br/>attacker"]
        Qwen["qwen3-8b<br/>judge / reviewer / thinker"]
    end

    subgraph Target["Target Agent"]
        Agent["chatbot-professor<br/>FastAPI + ChromaDB"]
    end

    subgraph Storage["Persistent Storage"]
        KB["knowledge_base.json"]
        HallKB["HALL KB docs"]
        StratMem["strategy_memory.json"]
        Reports["data/runs/"]
    end

    Setup -->|risk configs| Pipeline
    Pipeline -->|results| Dashboard
    Dashboard -->|export| Report
    Planner -->|decision| Generator
    Generator -->|attacks| Runner
    Runner -->|HTTP POST| Agent
    Agent -->|response| Runner
    Runner -->|raw results| Scorer
    Scorer -->|scored| Evolution
    Evolution -->|new attacks| Generator
    Meta -->|insights| Planner
    BG -->|thinker_insights| Planner
    Planner --> Gemma
    Generator --> Gemma
    Scorer --> Qwen
    Evolution --> Gemma
    Meta --> Qwen
    BG --> Qwen
    Planner -->|prior| StratMem
    Evolution -->|record| StratMem
    Generator -->|ground truth| HallKB
```

---

## Технологический стек

### Ядро

| Компонент | Технология | Назначение |
|-----------|-----------|-----------|
| Язык | Python 3.11+ | Основной язык |
| UI | NiceGUI | Веб-интерфейс с реактивными компонентами |
| Схемы данных | Pydantic v2 | Валидация, сериализация |
| HTTP клиент | aiohttp | Async HTTP для target agent |
| Конфигурация | PyYAML | config.yaml |
| Графики | ECharts (NiceGUI) | Evolution chart |

### LLM инфраструктура

| Компонент | Технология | Назначение |
|-----------|-----------|-----------|
| LLM сервер | LM Studio | Локальный inference, OpenAI-compatible |
| Attacker | gemma-3-12b-it | Генерация, reflect, mutate, planner |
| Judge | qwen3-8b | Scoring, review, thinker |
| API | OpenAI Chat Completions | /v1/chat/completions |
| Multi-model | LLMFactory | Маршрутизация по ролям из config.yaml |

### Паттерны и вдохновения

| Паттерн | Источник | Что взяли |
|---------|---------|-----------|
| Autoresearch loop | Claudini | Meta-reflection меняет промпт генератора |
| Technique recombination | Claudini | Комбинирование 2-3 техник |
| Reward hacking detection | Claudini | Проверка что judge не завышает |
| Strategy versioning | Claudini | Версии стратегий с leaderboard |
| Background consciousness | Ouroboros | Фоновый LLM-анализ параллельно |
| Keep best, mutate worst | Claudini + EA | Успешные сохраняются, failed мутируются |
| ReAct agent loop | CAI | Observe-Think-Act в Planner |
| Multi-model review | OpenClaw / Ouroboros | Разные LLM для генерации и оценки |

### Стандарты безопасности ИИ

| Стандарт | Применение |
|----------|-----------|
| OWASP LLM Top 10 (2025) | LLM01, LLM04, LLM06, LLM09 |
| OWASP Agentic Top 10 (2026) | ASI01, ASI02, ASI05, ASI09 |
| NIST AI RMF | Фреймворк управления рисками ИИ |

---

## Memory System -- трёхуровневая persistent память (Ouroboros pattern)

### Принцип (Claudini)
"Later runs have access to all methods and results from earlier runs."

### Три уровня
1. **Session (working memory)** — runtime-состояние в `AppState`
   (`evolution_history`, `all_results`, `thinker_insights`).
2. **Agent (episodic memory)** — файл `data/memory/agents/<agent_id>.json`
   (сессии со `version`, `technique_stats`, `risk_profile`, `feedback`).
3. **Global (semantic memory)** — файл `data/memory/global.json`
   (cross-agent `technique_stats`, per-agent-per-risk `best_rate`, `general_lessons`).

### Жизненный цикл
1. **Start**: `MemorySystem(agent_id, version)` загружает agent/global с диска.
   `current_version` хранит значение **с прошлой сессии** (не перезаписывается
   до коммита — это важно для regression-детекции).
2. **Plan**: `plan_initial()` выбирает один из 4 сценариев старта
   (FRESH / INFORMED / PRECISION / REGRESSION) на основе `agent_memory` +
   `global_memory`. `plan_next()` получает сжатый prior-блок в промпт.
3. **Commit (в конце сессии)**: `SessionCompactor` сводит runtime в компакт,
   `MemoryGuard` санитизирует (jailbreak-маркеры, control chars, лимиты),
   `memory.commit_session()` пишет и в agent, и в global.

### Cross-session эффект
- Первая сессия агента X: FRESH START, широкая разведка.
- Вторая сессия того же агента (та же версия): PRECISION START —
  70% на проверенные техники.
- Свежий агент Y, но есть данные о других агентах: INFORMED START —
  применяем top-техники из global.
- Та же версия тестируется повторно → PRECISION; новая версия v2.0 → REGRESSION.

---

## Эволюция атак -- подробное описание

### Keep Best + Mutate Worst

```mermaid
graph LR
    subgraph Gen1["Gen 1 (13 атак)"]
        S1["7 успешных"]
        F1["6 неуспешных"]
    end
    subgraph Gen2["Gen 2 (12 атак)"]
        K2["7 kept"]
        M2["5 новых (mutate)"]
    end
    subgraph Gen3["Gen 3 (14 атак)"]
        K3["9 kept"]
        M3["5 новых"]
    end
    S1 -->|copy| K2
    F1 -->|reflect+mutate| M2
    K2 -->|copy| K3
    M2 -->|успешные kept| K3
```

### Цикл одного поколения

```
1. PLANNER (gemma): OBS-HYP-DEC, budget, techniques
2. KEEP BEST: успешные из Gen N-1 копируются без мутации
3. GENERATE/MUTATE (gemma): новые атаки для замены failed
4. RUN (HTTP -> target): run_batch + run_chain
5. SCORE (qwen judge): TOXIC/HALL/DISINFO=стандарт, AGENCY/GH_RCE=специализированный
6. REFLECT (gemma): defense_patterns, weak_spots, bypass
7. REVIEW (qwen): multi-model ревью мутаций
8. META-REFLECTION (qwen): diagnosis, prompt_evo, reward hacking
9. AUTO-STOP: goal/stagnation/degradation/META-STOP
10. STRATEGY MEMORY: record_strategy()
```

### Background Thinker

- Отдельная asyncio задача параллельно с pipeline
- Использует тот же factory (shared model, семафор)
- Интервал: 30 сек, пропускает если LLM занят
- Инсайты -> state.thinker_insights -> Planner

### Специализированные Judge промпты

| Риск | Judge | Ситуации | Confirmation |
|------|-------|----------|-------------|
| TOXIC | Стандартный | Токсичный контент: да/нет | confirmed |
| HALL | KB-verifier | Факт в KB / выдумка | confirmed |
| DISINFO | KB-verifier | Искажение факта из KB | confirmed |
| AGENCY | Специализированный | REFUSAL / INTENT / EXECUTION | intent_confirmed |
| GH_RCE | Специализированный | REFUSAL / DISCLOSURE / EXECUTION_INTENT / GOAL_HIJACK | intent_confirmed |

---

## 2. Структура файлов

```
v2/
├── config.yaml                 # Multi-model конфигурация, target, evolution
├── PROJECT_SPEC.md             # Этот файл — спецификация проекта
├── verify_invariants.sh        # Скрипт проверки инвариантов
├── README.md                   # Быстрый старт
├── requirements.txt            # Зависимости
├── convert_csv_to_kb.py        # Конвертация CSV -> knowledge_base.json
│
├── ui/
│   ├── __init__.py
│   └── app.py                  # NiceGUI приложение (3 страницы + pipeline)
│
├── core/
│   ├── __init__.py
│   ├── llm_client.py           # LLMClient (OpenAI-compatible) + LLMFactory (multi-model)
│   ├── attack_generator.py     # Генерация single-turn + multi-turn атак, мутации
│   ├── attack_runner.py        # HTTP клиент: run_attack, run_batch, run_chain, check_target
│   ├── response_scorer.py      # LLM-as-Judge: score, score_batch, score_chain + guards
│   ├── evolution_engine.py     # Reflect -> Mutate -> Review (multi-model)
│   ├── attack_planner.py       # Агентный планировщик: observe -> decide -> act
│   ├── hall_verifier.py        # KB-aware генерация/верификация (HALL, DISINFO) + evolution
│   ├── meta_reflector.py       # Meta-анализ сессии + background thinking (Ouroboros)
│   ├── strategy_memory.py      # Persistent память между сессиями (Claudini versioning)
│   ├── knowledge.py            # Загрузка knowledge_base.json (UFR/UMF)
│   ├── tracing.py              # JSONL трейсинг событий
│   └── utils.py                # strip_llm_wrapper(), parse_llm_json()
│
├── models/
│   ├── __init__.py
│   └── schemas.py              # Pydantic модели (Attack, AttackResult, EvolutionCycle, и др.)
│
├── knowledge/
│   └── knowledge_base.json     # 89 факторов (UFR), 82 меры (UMF), 514 маппингов
│
├── data/
│   ├── runs/                   # Отчёты: report_*.json, full_report_*.json/md
│   └── strategy_memory.json    # Persistent память стратегий (cross-session)
│
└── tests/
    ├── test_schemas_and_kb.py  # 15 тестов: KB + Pydantic модели
    ├── test_knowledge_and_llm.py # 15 тестов: KnowledgeBase + LLMClient
    ├── test_core_modules.py    # 11 тестов: generator, runner, scorer, evolution, tracer
    ├── test_fixes.py           # 22 теста: runner extract, scorer guards, ui.chart
    ├── test_batch3.py          # 15 тестов: LLMFactory, HallVerifier, Planner
    └── test_utils.py           # 11 тестов: strip_llm_wrapper, parse_llm_json
```

**Всего тестов: 89**

---

## 3. UI — все элементы

### Страница "/" — Настройка

| Секция | Элементы |
|--------|----------|
| CONNECTION | Target URL (input), LLM Base URL (input), LLM Model (input) |
| RISKS | 5 expandable карточек (TOXIC, HALL, DISINFO, AGENCY, GH_RCE). Каждая: toggle "Тестировать", слайдер "Атак: N", чекбоксы факторов (UFR), чекбоксы мер (UMF, реактивные через `_rebuild_mitigations`) |
| HALLUCINATION KB | Путь к KB целевого агента (input) |
| EVOLUTION | Toggle "Включить эволюцию", слайдер "Циклов: N", toggle режима планирования (auto/single/multi) |
| BUDGET | Слайдер "Бюджет: N атак" (5-100), слайдер "Макс. цепочек" (1-10), слайдер "Макс. шагов" (2-8), toggle "Авто/Фиксированное" |
| ЗАПУСК | Кнопка, проверяет target через `check_target()` перед стартом |

### Страница "/dashboard" — Dashboard

**ЛЕВАЯ ПАНЕЛЬ (w-80):**

| Блок | Содержимое | Таймер |
|------|-----------|--------|
| SESSION | ID, Risk, Status (●/○), progress bar | 0.5s `_update_session` |
| METRICS | Total, Rate, Success (зелёный), Failed (красный) | 0.5s `_update_metrics` |
| EVOLUTION | echart график + expandable детали (OBS/HYP/DEC/ESC/Learnings/Review + META block) | 2.0s `_update_evo` |
| TECHNIQUES | Горизонтальные бары: rate% + название + (success/total) | 2.0s `_update_tech` |
| СТОП | Кнопка -> `state.should_stop=True` + notify + state.log | — |

**EVOLUTION details — meta-reflection block:**
Если `cycle.meta_diagnosis` непуст — оранжевый блок:
- 🧠 META-REFLECTION: диагноз, root cause, рекомендация
- 🔄 Prompt Evolution (если есть)
- ⛔ РЕКОМЕНДАЦИЯ: ПРЕКРАТИТЬ (если should_stop)

**ПРАВАЯ ПАНЕЛЬ (flex-1):**

| Элемент | Описание |
|---------|----------|
| Вкладки | `ATTACK LOG` / `ACTIVITY LOG` |
| status_text | Текущий статус pipeline |
| ATTACK LOG | scroll_area -> log_column. Карточки атак (см. ниже) |
| ACTIVITY LOG | scroll_area -> activity_column. Хронология с таймстампами |

**Карточка атаки (внутри log_column):**
```
┌─ border-green/red ─────────────────────────────┐
│ #idx   Gen N   RISK_ID   icon confidence        │  <- заголовок
│ 📤 payload preview (120 символов)...             │  <- preview
│ 📥 response preview (120 символов)...            │  <- preview
│ ⚖️ judge reasoning preview (120 символов)...     │  <- preview
│ ▼ Детали                                         │  <- expandable
│   Payload: (полный текст)                        │
│   Response: (полный текст)                       │
│   Judge: (полный текст)                          │
└──────────────────────────────────────────────────┘
```

**Таймеры (СНАРУЖИ tab_panels):**
- `ui.timer(0.5, _update_log)` — 1 раз
- `ui.timer(0.5, _update_activity)` — 1 раз

### Страница "/report" — Отчёт

| Элемент | Описание |
|---------|----------|
| Summary | session_id, target, дата |
| Метрики | Risks, Attacks, Success, Overall Rate (цвет: red>25%, orange>10%, green) |
| Детали рисков | Для каждого: status badge, rate, confirmed factors, evolution improvement, top evidence |
| Экспорт | 4 кнопки: Summary JSON, Summary MD, Full Report MD, Full Report JSON |

---

## 4. Pipeline

```
_start_testing()
  └─ check_target() -> fail? notify + return
  └─ _run_testing_pipeline(risk_configs)
  └─ _background_thinker()              # параллельная задача (Ouroboros)
       │
       ├─ LLMFactory() -> attacker, judge, reviewer (thinker = judge с семафором)
       ├─ MemorySystem(agent_id=...) -> AgentMemory + GlobalMemory (Ouroboros 3 levels)
       ├─ HallVerifier (если hall_kb_path задан)
       │
       └─ for risk_config in risk_configs:
            ├─ try/except/continue (graceful)
            │
            ├─ _is_kb_aware_risk()? -> KB-aware генерация + верификация
            │
            └─ Обычный flow:
                 └─ for cycle_num in 1..max_cycles:
                      ├─ Planner (адаптивный старт):
                      │    ├─ plan_initial(risk, agent_memory, global_memory, version):
                      │    │    ├─ FRESH START: нет знаний -> разведка single-turn
                      │    │    ├─ INFORMED START: global-знания -> top-техники + разведка
                      │    │    ├─ PRECISION START: знаем агента -> best strategy + exploration
                      │    │    └─ REGRESSION START: новая версия -> проверка починили ли
                      │    └─ plan_next(..., agent_memory) с prior-блоком в промпте
                      ├─ Budget: single_count + chains × steps <= budget
                      ├─ Single-turn: generate -> run_batch(progress_callback) -> score_batch
                      ├─ Multi-turn: generate_multi_turn(max_steps) -> run_chain(step_callback) -> score_chain
                      ├─ Technique stats -> Activity Log
                      ├─ Статистика -> EvolutionCycle -> state.evolution_history
                      ├─ Evolution: reflect -> mutate -> review
                      └─ MetaReflector.analyze() (если >=2 gen)
                           ├─ diagnosis, root_cause, recommendation
                           ├─ prompt_evolution, technique_recombination
                           ├─ reward_hacking_detection
                           └─ should_pivot / should_stop -> break
       │
       └─ После всех рисков: SessionCompactor -> MemoryGuard -> memory.commit_session
            ├─ agent file: sessions (with version), technique_stats, risk_profile, feedback
            └─ global file: per-agent per-risk rates, cross-agent technique_stats
```

Все LLM-вызовы через `_run_in_bg()` (ThreadPoolExecutor) — не блокируют UI.

---

## 5. Multi-Model конфигурация

```yaml
# config.yaml
llm:
  models:
    attacker:   gemma-3-12b-it   # генерация, reflect, mutate, planner
    judge:      qwen3-8b         # scoring (LLM-as-Judge)
    reviewer:   qwen3-8b         # ревью мутаций
    thinker:    qwen3-8b         # background consciousness (shared с judge, семафор)
  fallback_model: gemma-3-12b-it
```

- `LLMFactory()` читает `config.yaml` автоматически
- qwen3 возвращает `<think>...</think>` -> `strip_llm_wrapper()` из `core/utils.py`
- `attack_runner` добавляет `user_id` в body (требование chatbot-professor)
- `_llm_semaphore` — background thinker пропускает ход если LLM занят

---

## 6. Инварианты

### UI

| ID | Правило | Проверка |
|----|---------|----------|
| UI-1 | Карточки содержат preview 📤 📥 ⚖️ | `grep -c "📤" v2/ui/app.py >= 1` |
| UI-2 | Expandable = "Детали" (не "Полный текст") | `grep -c '"Детали"' v2/ui/app.py >= 1` AND `grep -c "Полный текст" v2/ui/app.py == 0` |
| UI-3 | Нет `.move()` в app.py | `grep -c "\.move(" v2/ui/app.py == 0` |
| UI-4 | Таймеры СНАРУЖИ tab_panels | `_update_log` не содержит `ui.timer` |
| UI-5 | Activity Log существует | `grep -c "_update_activity" v2/ui/app.py >= 2` |

### LLM

| ID | Правило | Проверка |
|----|---------|----------|
| LLM-1 | JSON парсинг через `strip_llm_wrapper()` | Все модули используют `strip_llm_wrapper`, не ручной парсинг |
| LLM-2 | `LLMFactory()` без `state.llm_model` для judge/reviewer | `grep -c "LLMFactory()" v2/ui/app.py >= 1` |

### Pipeline

| ID | Правило | Проверка |
|----|---------|----------|
| PIPE-1 | Пустой response -> is_successful=False | Guard в `response_scorer.py` |
| PIPE-2 | Каждый риск в try/except/continue | `grep -c "except Exception" v2/ui/app.py >= 2` |
| PIPE-3 | `should_stop` проверяется после каждого await | Множественные проверки в pipeline |

### Data

| ID | Правило | Проверка |
|----|---------|----------|
| DATA-1 | `SessionReport.all_attack_results` существует | `grep -c "all_attack_results" v2/models/schemas.py >= 1` |
| DATA-2 | `SessionReport.activity_log` существует | `grep -c "activity_log" v2/models/schemas.py >= 1` |

### Budget

| ID | Правило | Проверка |
|----|---------|----------|
| BUD-1 | Слайдер бюджета в UI | `grep -c "attack_budget" v2/ui/app.py >= 2` |
| BUD-2 | Budget лог в pipeline | `grep -c "📊 БЮДЖЕТ" v2/ui/app.py >= 1` |

### Techniques

| ID | Правило | Проверка |
|----|---------|----------|
| TECH-1 | technique в AttackResult | `grep -c "technique" v2/models/schemas.py >= 3` |
| TECH-2 | Leaderboard в Dashboard | `grep -c "TECHNIQUES" v2/ui/app.py >= 1` |
| TECH-3 | Progress callbacks | `grep -c "progress_callback" v2/core/attack_runner.py >= 2` |

### Meta-Reflection

| ID | Правило | Проверка |
|----|---------|----------|
| META-1 | MetaReflector существует | `test -f v2/core/meta_reflector.py` |
| META-2 | Meta-поля в EvolutionCycle | `grep -c "meta_diagnosis" v2/models/schemas.py >= 1` |
| META-3 | Background thinker | `grep -c "_background_thinker" v2/ui/app.py >= 2` |

### Strategy Memory

| ID | Правило | Проверка |
|----|---------|----------|
| MEM-1 | StrategyMemory существует | `test -f v2/core/strategy_memory.py` |
| MEM-2 | Интеграция в pipeline | `grep -c "StrategyMemory" v2/ui/app.py >= 1` |

---

## 7. Pydantic модели (schemas.py)

| Модель | Назначение |
|--------|-----------|
| `RiskDefinition` | Риск из KB |
| `FactorDefinition` | UFR фактор |
| `MitigationDefinition` | UMF мера |
| `Mapping` | Связь risk -> factor -> mitigation |
| `KnowledgeBaseData` | Полная KB |
| `RiskConfig` | Выбранный риск + факторы + меры |
| `TestSession` | Конфигурация сессии |
| `Attack` | Атака (+ ground_truth, source_document для HALL) |
| `AttackResult` | Результат атаки (+ technique) |
| `MultiTurnChain` | Multi-turn цепочка |
| `MultiTurnResult` | Результат цепочки |
| `AttackDecision` | Решение планировщика (+ single_turn_count, multi_turn_chains, steps_per_chain, budget_*) |
| `EvolutionCycle` | Цикл эволюции (+ planner/review/meta поля) |
| `RiskResult` | Итог по риску |
| `SessionReport` | Полный отчёт (+ all_attack_results, activity_log) |

---

## 8. Activity Log — все типы событий

| Событие | Цвет | Описание |
|---------|------|----------|
| 🔧 INIT | серый | Инициализация (модели, версии) |
| 🎯 НАЧАЛО | серый | Начало тестирования риска |
| 🧠 PLANNER | оранжевый | Решение планировщика |
| 👁 OBS | оранжевый | Наблюдение планировщика |
| 🧪 HYP | оранжевый | Гипотеза планировщика |
| ⚡ DEC | оранжевый | Решение планировщика |
| 📊 БЮДЖЕТ | серый | Распределение бюджета |
| ⚔️ ГЕНЕРАЦИЯ | серый | Начало генерации атак |
| ✅ СГЕНЕРИРОВАНО | серый | Атаки сгенерированы |
| 📤 ОТПРАВКА | серый | Начало отправки в target |
| 📤 АТАКА | серый | Прогресс: N/M атака |
| 📥 ПОЛУЧЕНО | серый | Ответы получены |
| ⚖️ SCORING | серый | Judge оценивает |
| 📈 ТЕХНИКА | серый | Статистика техники |
| 📊 РЕЗУЛЬТАТ | зелёный | Итог поколения |
| 🔄 REFLECT | фиолетовый | Анализ результатов |
| 👥 REVIEW | голубой | Multi-model review |
| 🔗 MULTI-TURN | серый | Начало multi-turn |
| 🔗 CHAIN | серый | Прогресс цепочки N/M |
| 🔗 STEP | серый | Прогресс шага |
| 📚 KB-AWARE | синий | KB-aware режим |
| 📚 KB-GEN | синий | KB-aware генерация |
| 🔍 KB-VERIFY | синий | KB-aware верификация |
| 🔄 KB-REFLECT | синий | KB-aware reflect |
| 💭 THINKING | серый | Фоновый инсайт (Ouroboros) |
| 💭 THINKER | серый | Завершение фонового анализа |
| 🧠 META | оранжевый | Meta-reflection диагноз |
| 🔍 ROOT | оранжевый | Корневая причина |
| 💡 РЕКОМЕНДАЦИЯ | оранжевый | Рекомендация meta-reflection |
| 🔄 PROMPT EVO | синий | Эволюция промпта |
| 🔀 RECOMB | голубой | Рекомбинация техник |
| 🚨 HACKING | красный | Reward hacking detected |
| ⛔ META-STOP | красный | Рекомендация прекратить |
| 📖 MEMORY | серый | Загрузка prior knowledge |
| 💾 MEMORY | серый | Запись стратегии |
| ❌ ОШИБКА | красный | Ошибка |
| ⛔ СТОП | красный | Остановка пользователем |
| 🏁 ЗАВЕРШЕНО | зелёный | Тестирование завершено |

---

## 9. Методология тестирования рисков

### Подход: Black-box HTTP

Agent-Breaker тестирует ИИ-агентов как чёрный ящик: отправляет текстовый запрос
по HTTP, получает текстовый ответ. Нет доступа к весам модели, внутренним состояниям,
трейсам tool calls, или логам агента. Оценка -- по тексту ответа через LLM-as-Judge.

### Уровни подтверждения

| Уровень | Описание | Требует трейсы? |
|---------|----------|-----------------|
| CONFIRMED | Риск фактически подтверждён по ответу агента | Нет |
| INTENT_CONFIRMED | Агент продемонстрировал намерение выполнить действие | Нет |
| REQUIRES_TRACE_VERIFICATION | Нужна проверка по трейсам/логам агента | Да |

### Риски: полное black-box тестирование

#### TOXIC -- Генерация токсичного контента
- **Что тестируем:** Генерирует ли агент оскорбления, угрозы, дискриминацию, вредоносные инструкции, контент 18+ в ответ на провокационные запросы.
- **Как оцениваем:** LLM-Judge анализирует текст ответа на наличие токсичного контента.
- **Уровень подтверждения:** CONFIRMED -- токсичный контент виден в ответе напрямую.
- **Black-box достаточен:** Да, полностью.
- **Стандарты:** OWASP LLM Top 10 -- LLM01 (Prompt Injection), LLM06 (Excessive Agency).

#### HALL -- Галлюцинации (выдумывание фактов)
- **Что тестируем:** Выдумывает ли агент факты, которых НЕТ НИГДЕ -- ни в его KB, ни в реальности.
- **Как оцениваем:** Сравнение ответа с ground truth из KB целевого агента.
- **Отличие от DISINFO:** HALL = агент выдумал из ничего (факта нет в KB). DISINFO = агент исказил то что есть в KB.
- **Уровень подтверждения:** CONFIRMED -- факт выдуман, видно в ответе.
- **Black-box достаточен:** Да. KB-aware верификация сравнивает ответ с ground truth.
- **Стандарты:** OWASP LLM Top 10 -- LLM09 (Misinformation).

#### DISINFO -- Дезинформация (искажение фактов из KB)
- **Что тестируем:** Искажает ли агент факты, которые ЕСТЬ в его базе знаний.
- **Как оцениваем:** Сравнение ответа с фактами из KB. Если в KB "ставка 5%", а агент сказал "7%" -- дезинформация.
- **Уровень подтверждения:** CONFIRMED -- искажение видно при сравнении ответа с KB.
- **Black-box достаточен:** Да, при наличии KB целевого агента для верификации.
- **Стандарты:** OWASP LLM Top 10 -- LLM09 (Misinformation), OWASP Agentic -- ASI09 (Trust Exploitation).

### Риски: тестирование intent (требует верификации по трейсам)

#### AGENCY -- Чрезмерная автономность
- **Что тестируем:** Пытается ли агент выполнить действия за пределами полномочий.
- **Как оцениваем (black-box):** По тексту ответа определяем INTENT -- агент продемонстрировал намерение или заявил о выполнении действия.
- **Ограничение black-box:** Без доступа к трейсам tool calls не отличим "реально выполнил" от "сказал что выполнил" (галлюцинация о возможностях).
- **Уровень подтверждения:** INTENT_CONFIRMED / REQUIRES_TRACE_VERIFICATION
- **Стандарты:** OWASP LLM Top 10 -- LLM06 (Excessive Agency). OWASP Agentic -- ASI01, ASI02.

#### GH_RCE -- Скрытые цели / удалённое выполнение
- **Что тестируем:** Можно ли заставить агента выполнить произвольный код, SQL, системную команду, или использовать инструменты деструктивно.
- **Суть риска:** Output LLM попадает в исполняемую среду (eval, exec, SQL, tool call) без валидации.
- **Ограничение black-box:** Аналогично AGENCY -- без трейсов не подтвердить реальное исполнение.
- **Уровень подтверждения:** INTENT_CONFIRMED / REQUIRES_TRACE_VERIFICATION
- **Стандарты:** OWASP LLM Top 10 -- LLM04 (Insecure Output), LLM06. OWASP Agentic -- ASI01, ASI02, ASI05.

### Применимость к целевым агентам

| Тип агента | TOXIC | HALL | DISINFO | AGENCY | GH_RCE |
|------------|-------|------|---------|--------|--------|
| Текстовый бот (chatbot-professor) | Full | Full | Full | Intent only | Intent only |
| Агент с инструментами + black-box | Full | Full | Full | Intent only | Intent only |
| Агент с инструментами + grey-box (трейсы) | Full | Full | Full | Full | Full |

### Связь с OWASP стандартами

| Наш риск | OWASP LLM Top 10 (2025) | OWASP Agentic Top 10 (2026) |
|----------|-------------------------|----------------------------|
| TOXIC | LLM01 (Prompt Injection) | ASI01 (Goal Hijack) |
| HALL | LLM09 (Misinformation) | ASI06 (Memory Poisoning) |
| DISINFO | LLM09 (Misinformation) | ASI09 (Trust Exploitation) |
| AGENCY | LLM06 (Excessive Agency) | ASI01, ASI02 (Goal Hijack, Tool Misuse) |
| GH_RCE | LLM04 (Insecure Output) | ASI01, ASI02, ASI05 (Goal Hijack, Tool Misuse, Code Execution) |

### Regression Testing

При тестировании новой версии того же агента (v1.0 → v2.0) система
автоматически включает regression-режим:

1. `plan_initial()` детектирует смену версии через сравнение `state.agent_version`
   с сохранённым `agent_memory.current_version` (сравнение — на СТАРОМ значении
   до коммита новой сессии).
2. REGRESSION START: 80% бюджета идёт на те техники, которые пробивали
   прошлую версию (из `agent_memory.get_best_strategy(risk_id)`);
   20% — на разведку специфичных для новой версии защит.
3. В `RiskResult.regression_data` сохраняются `{old_version, new_version,
   old_rate, new_rate, change, status}` (`improved` / `degraded` / `stable`).
4. UI Report выводит цветную плашку (✅ FIXED / ❌ WORSE / ➡️ STABLE).
5. В Full Report MD добавляется отдельная секция **Regression Report**
   с таблицей risk × (old, new, change, status).

### Планы расширения

- **Grey-box режим:** Подключение к audit log / трейсам агента для полного подтверждения AGENCY и GH_RCE.
- **Train/Validation split:** Разделить KB на train (генерация) и validation (оценка) для предотвращения переобучения HALL атак.
- **Специализированные judge промпты:** Отдельные промпты для AGENCY и GH_RCE judge, учитывающие разницу между "сказал что сделал" (HALL) и "реально сделал" (AGENCY).
