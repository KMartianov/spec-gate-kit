# Спецификация: Надёжный OpenCode — spec-first + автономность

| | |
|---|---|
| **Версия** | 1.0 |
| **Дата** | 2026-09-27 |
| **Автор** | orchestrator (сессия `ses_f20cba006ffeVn1l3rLZRbSHbq`) |
| **Статус** | draft → ожидает утверждения |
| **Тип** | спецификация системы (инфраструктура + workflow) |
| **Статус реализации** | Шаги 0–1, 3–16 выполнены и проверены вживую; Шаг 2 отложен осознанно; oclab — отдельный этап (§11) |

> Этот документ — входная спецификация того, что мы строим. Он сам является примером артефакта, который система должна требовать и утверждать до начала работы.

---

## 1. Назначение и цель

Сделать OpenCode **управляемым исполнителем**:

1. **Spec-first.** Любая нетривиальная работа начинается с письменной спецификации, которую пользователь явно утверждает.
2. **Автономность после утверждения.** С момента `status: approved` агент выполняет фазы без остановок (кроме исключений), доводя работу до Definition of Done.
3. **Дисциплина места.** Агент не выходит за пределы разрешённых директорий и не правит чужие файлы/конфиги.
4. **Полноценный проект вместо мелких правок.** Новая функциональность → новый проект в `~/Projects/<name>/`, а не набор in-place изменений.
5. **Контроль ресурсов.** Работа в пределах подписки OpenCode Go (\$10/мес).

### 1.1. Non-goals (вне рамок этой спецификации)

- Полная kernel-level изоляция (bubblewrap/namespaces) — это **oclab**, см. §11.
- Замена OpenCode другим агентом.
- Обучение/дообучение моделей.

---

## 2. Проблемы «как есть» (as-is)

| ID | Проблема | Наблюдение |
|---|---|---|
| P1 | **Выход из папки** | агент пишет/читает вне designated-зоны; распространяется и на конфиг |
| P2 | **Нет спецификации и утверждения** | сразу правит файлы, «задача завершена» без согласованного плана |
| P3 | **Мелкая правка вместо проекта** | новая функциональность делается набором in-place изменений |
| P4 | **Нет Definition of Done** | завершение объявляется без тестов/сборки/документации |
| P5 | **Неконтролируемый расход** | дорогие модели на рутинных задачах |

---

## 3. Целевая модель (to-be)

Двухслойный контроль:

| Слой | Механизм | Гарантия |
|---|---|---|
| **HARD** | `permission` (opencode.json + per-agent) | жёсткий отказ платформы |
| **HARD** | plugin `tool.execute.before` → `throw` | spec-gate |
| **SOFT** | `orchestratorPrompt`, `*_append.md`, skills | намерение модели |

Инвариант: **всё, что должно соблюдаться безусловно, обязано быть HARD**. SOFT-механизмы — только для эвристик и порядка.

---

## 4. Архитектура

```
                    ┌──────────────────────────────┐
   запрос  ───────▶ │  orchestrator (primary)      │
                    │  INTAKE → SKELETON → SPEC…   │
                    └───────────────┬──────────────┘
                                    │
                   ┌────────────────┼─────────────────┐
                   ▼                ▼                 ▼
            ┌────────────┐   ┌────────────┐   ┌────────────┐
            │ explorer   │   │ oracle     │   │ fixer /    │
            │ (recon)    │   │ (design)   │   │ experts    │
            └────────────┘   └────────────┘   └────────────┘
                   │                │                 │
                   └────────────────┼─────────────────┘
                                    ▼
                    ┌───────────────────────────────────┐
   HARD-слой  ────▶ │ opencode permission + spec-gate   │
                    │ plugin (tool.execute.before)      │
                    └───────────────────────────────────┘
                                    │
                    ┌───────────────▼───────────────────┐
   будущее ───────▶ │ oclab (bubblewrap isolation)      │
                    └───────────────────────────────────┘
```

Компоненты: **оркестратор** (спецификация + делегирование), **субагенты** (lузкие лэйны), **HARD-слой** (permission + плагин), **артефакты** (`.slim/spec/`, отчёты), **oclab** (позже — изоляция).

---

## 5. State machine «Spec → Approve → Autonomous»

$$S \in \{\text{INTAKE},\ \text{SKELETON},\ \text{SPEC\_DRAFT},\ \text{APPROVED},\ \text{EXECUTING},\ \text{VERIFYING},\ \text{DONE}\}$$

| Состояние | Артефакт | Переход | Утверждает | Гейт |
|---|---|---|---|---|
| INTAKE | запрос | → SKELETON / SPEC_DRAFT | — | — |
| SKELETON | `~/Projects/<name>/` + `README.md`, `.gitignore` | → SPEC_DRAFT | авто | SOFT |
| SPEC_DRAFT | `.slim/spec/<task>.md` со `status: draft` | → APPROVED | **пользователь** | **HARD** |
| APPROVED | `status: approved` в файле | → EXECUTING | авто | **HARD** (разблокирует edit) |
| EXECUTING | фазы + чекпоинты | → VERIFYING | авто + @oracle на фазу | SOFT |
| VERIFYING | тесты / сборка / метрики | → DONE | авто | SOFT |
| DONE | финальный отчёт + commit | — | — | — |

**Разблокировка автономности:** запись `status: approved` (после ответа пользователя через `question`). До этого правки запрещены хуком; после — фазы идут без остановок, кроме исключений (см. R6).

---

## 6. Требования

### 6.1. HARD

| ID | Требование | Механизм | Приёмка |
|---|---|---|---|
| **R1** | Файловые операции только в разрешённых зонах | `permission.external_directory` (`*` deny + allow-список) | `read/grep/edit` вне зон → `permission.rejected` |
| **R2** | Read-only агенты не пишут | per-agent `permission.edit` | `explorer`/`librarian`/`oracle`/`math-verifier` не могут `edit` |
| **R3** | Опасные команды запрещены | `permission.bash` deny-список | `sudo*`, `rm -rf /*`, `sh -c`, `eval` → `rejected` |
| **R4** | Прочие команды — только с подтверждением | `permission.bash` `"*": "ask"` | запрос появляется в TUI |
| **R5** | **Правки запрещены до утверждённой спецификации** | plugin `tool.execute.before` → `throw` | до approved `edit/write/patch` → жёсткий отказ |

Разрешённые зоны (baseline): `~/Projects/**`, `~/.config/opencode/**`, `/tmp/opencode/**`, `~/ml_base/**`.

### 6.2. SOFT (обязательны к соблюдению, но не гарантируются платформой)

| ID | Требование |
|---|---|
| R6 | Останавливаться и спрашивать при: неоднозначности, разрушительных операциях, выходе за spec, ≥3 неудачных попытках на один баг |
| R7 | Правило «новый проект vs in-place» (§9) |
| R8 | Definition of Done перед DONE (§9) |
| R9 | Порядок фаз: recon → design → implement → verify → review |
| R10 | Математика/формулы — в LaTeX |

---

## 7. Spec-gate: артефакт и механика

### 7.1. Артефакт `.slim/spec/<task>.md`

```markdown
# Спецификация: <название>
**Статус:** draft | approved
**Создано:** <дата> · **Автор:** orchestrator

## Цель
## Ограничения
## Definition of Done
- [ ] тесты проходят (pytest / ctest)
- [ ] сборка чистая; C++ → ASan/UBSan без ошибок
- [ ] документация/README обновлены
- [ ] commit с осмысленным message
## Фазы
1. анализ → 2. дизайн → 3. реализация → 4. верификация → 5. review
## Риски
```

### 7.2. Поведение плагина

- триггер: инструмент ∈ `edit`/`write`/`patch`;
- если путь внутри `.slim/spec/**` — пропуск;
- иначе найти корень проекта (вверх до `.slim/`);
- если `.slim/spec/` существует и нет файла со `status: approved` → `throw`.

> ✅ **O1 — ЗАКРЫТ (верифицировано 2026-09-27 по бинарнику `opencode` v2.0.15 и dist `oh-my-opencode-slim`).**
> Актуальный контракт — **v2**: `export default { id, setup }`; внутри `setup` →
> `await ctx.tool.hook("execute.before", handler)`. Локальные типы
> `@opencode-ai/plugin@1.18.29` описывают устаревший v1 (`"tool.execute.before"`)
> — полагаться на них нельзя. `throw` внутри хука **отклоняет** вызов; форма
> события — `{ tool, sessionID, id, input }`; патч-инструмент называется
> `apply_patch`; `toolNameToV1` — identity, кроме `subagent`↔`task`.

> ✅ **O2 — ЗАКРЫТ.** Утверждение хранится **вне проекта**:
> `~/.local/share/opencode/approvals/<sha256(root)[:16]>/<slug>.json` со схемой
> `{root, spec, spec_sha256, task, approved_by:"human", approved_at}`. Файл
> создаёт только человек через `bin/spec-approve`; валидность = совпадение
> `sha256` текущего содержимого спеки с `spec_sha256`, поэтому любая правка
> спеки **автоматически аннулирует** утверждение. Самоприсвоение
> `status: approved` агентом разблокировки больше не даёт.

---

## 8. Матрица permission (baseline)

| Агент | `edit` | `bash` |
|---|---|---|
| orchestrator | `ask` (spec/README allow) | как глобально |
| explorer | deny | deny (+ read-only allowlist) |
| fixer | `~/Projects/**` allow, иначе deny | как глобально |
| librarian | deny | deny |
| oracle | deny | deny |
| council | deny | как глобально |
| cpp-expert | `~/Projects/**` allow, иначе deny | allow: cmake/make/ctest/valgrind |
| python-expert | `~/Projects/**` allow, иначе deny | allow: python/uv/pytest |
| math-verifier | deny (+ `/tmp/opencode/**`) | allow: python |
| ml-expert | `~/Projects/**` allow, иначе deny | allow: python/pytest |

Глобально: `external_directory` — deny + 4 зоны; `bash` — `ask` + safe allowlist + destructive deny (см. §12, Шаг 1 — реализовано).

---

## 9. Workflow и правила

### 9.1. Новый проект vs in-place

$$\text{Decision}=\begin{cases}\text{новый проект в } \texttt{\sim/Projects/}, & |\text{files}|>3 \ \lor\ \text{new\_repo}\ \lor\ \text{явный запрос}\\[2pt]\text{in-place (с предупреждением)}, & \text{иначе}\end{cases}$$

### 9.2. Definition of Done

Задача не завершена, пока: тесты проходят; сборка чистая (C++ → ASan/UBSan); документация обновлена; commit осмысленный; факты проверены независимо (где применимо — @math-verifier/@oracle).

---

## 10. Модельная карта (бюджет \$10/мес)

Лимиты: подписка \$10/мес, помодельные крышки \$15/\$30/\$60, окна 5ч=20 % / нед=50 % / мес=100 %. Главный драйвер — orchestrator (видит весь контекст).

| Агент | Рекомендация | \$/M in/out |
|---|---|---|
| orchestrator | GLM-5.3-Flash (альт. DeepSeek V4.1 Flash) | 0.15/0.50 |
| explorer / fixer | DeepSeek V4.1 Flash | 0.15/0.60 |
| librarian | Muse Spark 1.3 (альт. DeepSeek V4.1 Flash) | 0.10/0.20 |
| oracle | GLM-5.3 (альт. Muse Spark 1.3) | 1.40/4.40 |
| council.architect / reviewer / pragmatist | GLM-5.3 / MiMo-V2.6-Pro / Hy3 | 1.40/4.40 · 0.435/0.87 · 0.14/0.58 |
| cpp-expert / python-expert / ml-expert | DeepSeek V4.1 Flash | 0.15/0.60 |
| math-verifier | Muse Spark 1.3 (альт. GLM-5.3) | 0.10/0.20 |

Дорогие closed-max (\$6–\$15/M) — только oracle/council и только на сложных задачах. Детали и метрики — в `Список моделей.md`.

---

## 11. oclab: точка интеграции (позже)

**Решение пользователя:** пока жёсткую изоляцию не делаем, OpenCode работает без oclab.

**Роль oclab:** будущий **execution/isolation-слой**, заменяющий `permission` + плагин (kernel-level bubblewrap), без изменения workflow. spec-gate остаётся на уровне OpenCode.

**Точка возврата:** после готовности spec-gate (Шаг 3) и стабилизации spec-first workflow.

**Триггеры вернуться:**
1. остались обходы, которые `permission`/плагин не закрывают;
2. нужна автономность с недоверенными агентами / без присмотра;
3. spec-first стабилен → можно перенести workspace внутрь oclab-env.

**Блокеры oclab к устранению (диагностированы):**
- баг symlink `/etc/resolv.conf` в `src/oclab/sandbox/bwrap.py` (фикс протестирован на уровне bwrap);
- `config_builder.py:121` пишет `permissions` (plural) — OpenCode ждёт `permission` (singular);
- `.opencode` внутри env — RO ⇒ конфиги/навыки/MCP переносить в env-манифест;
- локальные MCP (serena/jupyter/memory) — нужен проброс сокета/бинаря;
- профиль `host` — подтверждение не реализовано; `dns-only` делит host-netns (broker виден).

---

## 12. Этапы внедрения

| Шаг | Что | Тип | Статус |
|---|---|---|---|
| **0** | Бэкап + гигиена (AGENTS.md: serena 1.7.0 = MIT) | — | ✅ выполнено |
| **1** | Закрыть bash-обход: `"*": "ask"` + safe allowlist + destructive deny | HARD | ✅ выполнено, проверено |
| **2** | Разделить workspace и конфиг (агент не правит свой конфиг) | HARD | ⏸ отложено осознанно: конфиг намеренно **exempt** в spec-gate, иначе агент не сможет сопровождать собственную конфигурацию |
| **3** | Spec-gate: верификация Plugin API + плагин | HARD | ✅ выполнено, проверено вживую (§16) |
| **4** | Workflow/DoD: `orchestrator_append.md` + `templates/` + AGENTS.md | SOFT | ✅ выполнено |
| **5** | Модельная карта + температуры (§10) | конфиг | ✅ выполнено, сверено с JSON |
| **6** | Приёмка и метрики | — | ✅ приёмка spec-gate пройдена; метрики — ongoing |
| **7** | P0-1: единый источник истины — `spec-approve` флипает статус **до** хеша; `spec-revoke` | HARD | ✅ выполнено, проверено (§16.4) |
| **8** | P0-2: закрыть дыру MCP-писателей (read-only allowlist + гейт по путям в args) | HARD | ✅ выполнено; 17/17 тестов |
| **9** | P0-3: тривиальный путь — маркер `.slim/GATE-OFF` + `gate-off`/`gate-on` | SOFT | ✅ выполнено |
| **10** | P1-1: аудит решений гейта → `audit/spec-gate.jsonl` | SOFT | ✅ выполнено (пишется в `before`, `after` — no-op) |
| **11** | P1-2: проверка, применяется ли `variant` | — | ✅ проверено вживую (§16.5) |
| **12** | P1-3: документация под фактическое поведение | SOFT | ✅ выполнено (§16) |
| **13** | A: каркас Diátaxis + ADR в `spec-new`, линт `bin/docs-lint` | SOFT | ✅ выполнено |
| **14** | B→пересмотр: состояние **выводится** (derive-on-read); `state.json` и счётчик R6 удалены; ADR 0003 | HARD | ✅ выполнено, проверено вживую (§16.6) |
| **15** | C: метрики квот §7 — `bin/oc-usage` (read-only, `opencode.db`); баг `question` | — | ✅ выполнено; `question` закрыт как «диалог отклонён человеком» |
| **16** | E: DoD-доказательства — блок `dod`, `bin/dod-run`, `verify/<id>.json`, read-only `spec-status`; ADR 0004 | HARD | ✅ сквозная приёмка (§16.6) |

**Порядок:** 3 → 4 → 5 → 7–16 (выполнено). Шаг 2 отложен; oclab (§11) — следующий крупный этап.

---

## 13. Критерии приёмки и метрики

| Метрика | Цель |
|---|---|
| Правки вне разрешённых зон (`edit`) | **0** |
| Опасные команды выполнены | **0** |
| Задачи с approved-спецификацией до первого edit | **100 %** |
| Доля новых функциональностей, начатых как проект в `~/Projects/` | **≥ 90 %** |
| Расход/мес | **≤ \$10** |
| Доля задач, закрытых с выполненным DoD | **100 %** |
| Обходы через bash (записи вне зон, одобренные вручную) | минимизировать; → 0 после oclab |

---

## 14. Риски и открытые вопросы

| ID | Риск / вопрос | Митигация |
|---|---|---|
| O1 | Точная форма Plugin API (экспорт/регистрация) | ✅ закрыт: контракт v2 (`export default {id, setup}` + `ctx.tool.hook`), см. §7.2 |
| O2 | Агент сам вписывает `status: approved` | ✅ закрыт: внешний approval-файл с проверкой `sha256(spec)`, см. §7.2 |
| O3 | `ask` — подтверждение, а не запрет | частично: spec-gate (Шаги 3, 8) закрывает `edit`/`write` **и MCP-писателей**; полную изоляцию даёт oclab |
| O4 | `ls *` allow → `ls /etc` без вопроса | убрать `ls *` при необходимости |
| O5 | Workspace == конфиг → self-edit | отложено (Шаг 2); конфиг намеренно exempt в гейте |
| O6 | Glob-семантика (relative/`~`/порядок) | уже подтверждена (last-match-wins; catch-all первым) |
| O7 | Бюджет: реальный объём токенов orchestrator | ✅ источник данных найден: таблица `session_message` в `~/.local/share/opencode/opencode.db` (`json_extract(data,'$.model')`); регулярная приборка метрик не делалась |
| O8 | SOFT-требования могут нарушаться | ✅ частично закрыт: журнал `audit/spec-gate.jsonl` фиксирует каждое решение гейта |
| O9 | `variant` у оркестратора не применяется | ✅ объяснено (§16.5): для оркестратора omos не задаёт модель, вариант следует за сессией; у субагентов работает |

---

## 15. Глоссарий и файлы

| Термин / файл | Значение |
|---|---|
| `~/projects` vs `~/Projects` | в этом документе — `~/Projects/**` (фактическая зона allow) |
| `opencode.json` | глобальный конфиг: permission, MCP, plugin |
| `oh-my-opencode-slim.json` | пресеты, агенты, модели, per-agent permission |
| `AGENTS.md` | правила/инструкции, nearest-wins |
| `.slim/spec/<task>.md` | артефакт спецификации (источник истины гейта) |
| HARD / SOFT | платформенная гарантия / намерение модели |
| oclab | внешний проект (bubblewrap-изоляция), будущий execution-слой |

---

## 16. Реализовано: артефакты и приёмка (2026-09-27)

### 16.1. Артефакты

| Путь | Роль |
|---|---|
| `plugins/spec-gate.ts` | HARD-хук `tool.execute.before`: read-only allowlist + гейт **по путям в args** (перехватывает и MCP-писателей serena), fail-closed, `.slim/GATE-OFF`, `.serena/**`, аудит |
| `bin/spec-approve` | CLI человеческого утверждения: флип статуса → штамп `Утверждено` → хеш **post-flip** → внешний approval-файл |
| `bin/spec-revoke` | обратный ход: удаляет approval-записи, возвращает `draft`, снимает штамп |
| `bin/gate-off` / `bin/gate-on` | создают/снимают маркер `<root>/.slim/GATE-OFF` (человеческий opt-out) |
| `bin/spec-new` | скаффолд проекта: `.slim/spec/<slug>.md`, дерево Diátaxis, `docs/adr/{README,0000-template,0001-<slug>}`, `README.md`, `.gitignore`, `git init` (без `.slim/state.json`) |
| `plugins/__tests__/spec-gate.test.ts` | 17 тестов `node:test` — 17/17 pass (часть гоняет реальный `spec-approve` через `execFileSync`) |
| `command/spec-approve.md` | слэш-команда TUI `/spec-approve` (шелл-блок исполняет клиент, а не агент) |
| `templates/spec-template.md`, `templates/adr-template.md` | контракт спеки (§7.1) и скелет ADR по Найгарду |
| `oh-my-opencode-slim/orchestrator_append.md` | derive-on-read вместо state machine, Zero-Code Gate + механика гейта, R6 как policy-line, Diátaxis, `dod`/`verify/`, состав CLI |
| `AGENTS.md` | раздел «Doc-Driven Development (Zero-Code Gate)» + модельная таблица + семантика `variant` |
| `bin/spec-status` | read-only отчёт: выведенное состояние из спеки + approval + `verify/*.json` (не пишет ничего) |
| `bin/dod-run` | исполняет блок `dod` из спеки → `verify/<id>.json` (единственный писатель доказательств); destructive-команды отклоняются |
| `bin/docs-lint` | линт документации: строка статуса, ссылка на реальный ADR, существование `docs/…`, WARN при отсутствии `dod` |
| `bin/oc-usage` | read-only метрики §7: запросы за окно (по умолчанию 5 ч) и all-time по агентам из `opencode.db`, флаг `DRIFT` |
| `docs/adr/0001–0004` | решения лаборатории: гейт как soft-guardrail; внешние approval-записи; выводимое состояние; DoD-доказательства |

Kill switch: `OPENCODE_SPEC_GATE=off`. Exempt-зоны: `~/.config/opencode/**`,
`~/.local/share/opencode/approvals/**`, `~/.local/share/opencode/audit/**`,
`/tmp/opencode/**`. Журнал решений: `~/.local/share/opencode/audit/spec-gate.jsonl`.

### 16.2. Приёмка (вживую, с активным гейтом)

Проект `~/Projects/gate-smoke` с `.slim/spec/demo.md`:

| # | Действие | Ожидание | Результат |
|---|---|---|---|
| 1 | `write src/a.ts` без утверждения | отказ | ✅ `[SPEC-GATE BLOCKED]`, каталог `src/` не создан |
| 2 | `bin/spec-approve .slim/spec/demo.md` | запись approval | ✅ `approvals/01a008314dd39430/demo.json`, `approved_by: human` |
| 3 | повтор `write src/a.ts` | разрешено | ✅ файл создан |
| 4 | правка `demo.md` → `write src/b.ts` | отказ (hash mismatch) | ✅ снова `[SPEC-GATE BLOCKED]` |
| 5 | `write ~/.config/opencode/.gate-selfcheck.tmp` | разрешено (exempt) | ✅ нет self-lockout |

Затем smoke-проект, approval-запись и тестовый файл удалены; `~/Projects/` и
`approvals/` пусты.

### 16.3. Известные ограничения (честно)

1. **Это soft-guardrail, а не граница безопасности.** `permission.bash`
   разрешает `python -m *`, поэтому запись возможна в обход `edit`/`write`.
   Роль гейта — трение + след в аудите, а не изоляция.
2. Утверждённая спека разблокирует **весь проект** до следующей правки спеки
   (per-file allowlist не делался — в v1 это было бы «театром поверх театра»).
3. Субагенты гейтятся так же, как оркестратор (идентичность агента в хук не
   передаётся).
4. Строка `- **Статус спецификации:**` обязательна: и `spec-approve`, и
   `spec-revoke` отказываются работать со спекой без неё (лучше явная ошибка,
   чем approval, чей статус человек не видит в документе).
5. `relative_path` (форма serena) резолвится относительно `directory` хука:
   собственный project-root serena из хука не наблюдаем. Это остаточный риск.
6. Kernel-level барьер (`EROFS`), сетевые профили и cgroups даёт только oclab
   (§11) — там же патчи `cmd_env.py` / `bwrap.py` из §8 исходной спецификации DDD.
7. `spec-new` и `dod-run` исполняются как shell-команды, поэтому гейт их не
   видит: агент может скаффолдить проект или записать `verify/` без approval.
   Гейт перехватывает только вызовы инструментов с путями в аргументах.
8. Отдельного хранилища состояния (`state.json`) и счётчика R6 нет намеренно:
   второй источник истины уже однажды разошёлся с approval-записью (P0-1).

### 16.4. P0: закрытые дефекты (проверено вживую)

| # | Дефект | Исправление | Проверка |
|---|---|---|---|
| P0-1 | approval-запись существовала, а спека в документе оставалась `draft` → агент, читая спеку, отказывался работать | `spec-approve` флипает статус и штампует `Утверждено` **до** хеширования; `spec-revoke` возвращает `draft` | на scratch-проекте: `approved` в спеке, комментарий сохранён, `sha256(spec) == record.spec_sha256`; повторный запуск идемпотентен |
| P0-2 | 7 пишущих инструментов serena (`replace_content`, `replace_in_files`, `replace_symbol_body`, `insert_before_symbol`, `insert_after_symbol`, `rename_symbol`, `safe_delete_symbol`) обходили гейт | инверсия в read-only allowlist + извлечение путей из args; fail-closed для писателя без разбираемых путей | тесты 2, 4, 5, 13 (17/17 pass) |
| P0-3 | тривиальная правка требовала полной церемонии | маркер `<root>/.slim/GATE-OFF` + CLI `gate-off`/`gate-on`; маркер лежит **вне** `.slim/spec/**`, поэтому агент не может сам себе его выписать | тест 9; `gate-off`/`gate-on` прогнаны на scratch-проекте |

### 16.5. P1-2: применяется ли `variant`? — вердикт

**`variant` применяется** (OpenCode v2 трактует его как reasoning-effort:
`settings.reasoningEffort`). Доказательство прямым зондом: `@python-expert`
(в конфиге `variant: "max"`) выполнил тривиальный запрос, и в
`session_message` появилась запись
`{"id":"deepseek-v4.1-flash","providerID":"opencode-go","variant":"max"}`.

| Агент | В конфиге | Фактически (последняя запись) | Итог |
|---|---|---|---|
| `python-expert` | `max` | `max` | ✅ |
| `fixer` | `high` | `high` | ✅ |
| `explorer` | `high` | `high` | ✅ |
| `librarian` | `high` | `high` (`glm-5.3-flash`) | ✅ |
| `oracle` | `xhigh` | `xhigh` | ✅ |
| `orchestrator` | `max` | `high` | ⚠️ см. ниже |

**Единственная аномалия — оркестратор.** omos намеренно оставляет
`agent.config.model = undefined` для оркестратора, чтобы победил выбор
`/model` в сессии (`dist/index.js:21334`), и копирует вариант из пресета только
для **не**-оркестратора (`:21336`). Поэтому фактический вариант оркестратора
следует за моделью сессии, а не за `variant: "max"` из пресета. Подтверждение:
за всю историю `session_message` у оркестратора **ни разу** не встречается `max`
(распределение: `default` 766, `high` 1097, `xhigh` 58 — `xhigh` появлялся, когда
моделью сессии был `muse-spark-1.3-contributor`). `temperature` при этом
применяется ко всем агентам, включая оркестратора (`:21344`).

**Вывод для §10/§7:** колонка `variant` для оркестратора декоративна; чтобы
реально получить `max`, нужно выбрать вариант модели в TUI (`/model`) либо
патчить omos. У всех субагентов матрица работает как заявлено. Старые записи
БД (`math-verifier` = `deepseek-v4-pro`, `cpp-expert` = `default`) —
исторические, до смены конфига, и не являются признаком поломки.

### 16.6. Сквозная приёмка: выводимое состояние + DoD-доказательства (E)

Прогон на scratch-проекте `~/Projects/ddd-e2e` (скаффолд `bin/spec-new`, затем
`bin/spec-status --json` как источник истины; после прогона проект удалён):

| # | Ситуация | Выведенное состояние |
|---|---|---|
| 1 | скаффолд, approval нет | `SPEC_DESIGN` |
| 2 | `dod` сужен до тривиальных проверок, approval нет | `SPEC_DESIGN` |
| 3 | `verify/*.json` записаны **без** approval | `SPEC_DESIGN` |
| 4 | после `bin/spec-approve` (доказательства устарели) | `APPROVED` |
| 5 | `bin/dod-run` на утверждённой спеке | **`DONE`** |
| 6 | спека отредактирована после утверждения | `SPEC_DESIGN` |

Ключевые инварианты подтверждены: (3) доказательства сами по себе не двигают
состояние; (4) approval инвалидирует ранее записанные доказательства
(несовпадение `spec_sha256`); (5) `DONE` требует $\forall\,c \in \text{DoD}:$
`verify/c.json` с `exit_code == 0` и совпадающим `spec_sha256`; (6) правка спеки
обнуляет и approval, и доказательства — при этом текстовая строка статуса
остаётся `approved`, то есть выведенное состояние авторитетнее объявленной метки.

Дополнительно проверено: denylist `dod-run` (`sudo rm -rf /` → отказ, файл
доказательства не создан), `docs-lint` даёт WARN без `dod`-блока, `spec-status`
не содержит ни одной операции записи, все CLI компилируются.

Архитектурные решения зафиксированы в ADR лаборатории:
`docs/adr/0001-gate-as-soft-guardrail.md`,
`0002-external-approval-records.md`,
`0003-derived-lifecycle-state.md`,
`0004-dod-evidence-artifacts.md`.

**Откат:** `rm ~/.config/opencode/plugins/spec-gate.ts` + рестарт; либо запуск
с `OPENCODE_SPEC_GATE=off`; для CLIs — `git`-истории нет, файлы удаляются
вручную (`bin/spec-{new,approve,revoke,status,dod-run,docs-lint,oc-usage}`,
`bin/gate-{off,on}`, `command/spec-approve.md`).

---

*Спецификация подготовлена как входной документ работы. Шаги 0–1 и 3–16 реализованы и проверены; Шаг 2 отложен сознательно; oclab (§11) — следующий крупный этап.*
