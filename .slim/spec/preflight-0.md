# Preflight 0 — предполётный консенсус-линт и отчёт по дублям тяжёлых чеков

- **Статус спецификации:** `draft`
- **Дата создания:** 2026-10-01
- **Автор:** orchestrator (по результатам Ф3: M2-симуляция и M4-аудит)
- **Целевая ветка / worktree:** текущая ветка репозитория `spec-gate-kit` (без отдельного worktree)
- **Task slug:** `preflight-0` (файл `.slim/spec/preflight-0.md`)

## Раздел 1. Цели и границы (Scope)

### 1.1 Зачем

Ф3-модель (M2) и её независимый аудит (M4) дали два вывода, устойчивых ко всем свипам:

1. **H5 (pre-approval consistency + батч-одобрение) — единственный устойчивый выигрыш.** На N=16 число человеческих взаимодействий падает 19.3 → 5.9 при неизменном wall-clock; при медленном человеке (30 мин/взаимодействие) преимущество растёт 622 → 233 мин. Причина в реальности: 3 волны переделок, каждая из которых инвалидировала одобрения (нужны повторные `spec-approve`).
2. **H1 (дедуп тяжёлых DoD-чеков) — держится.** ~75–80 % команд в волне — повторы (`pytest` 14×, `ruff` 15×, `ctest` 3–5×); устранение повторов экономит ~63–65 % тяжёлого времени.

Сегодня в `config/` **нет** ни одного инструмента, который до одобрения проверяет: валидность `scope`-мандата, форму `dod`-блока, коллизии `dod.id` между контрактами, пересечение зон записи (единый писатель на файл), каноничность и дублирование тяжёлых команд. `docs-lint` покрывает часть (валидность `scope`, дубли `dod.id`), но не даёт карту владения и отчёт по дублям; он также держит **локальную** копию парсера `dod.id` вместо общей.

### 1.2 Границы (что делаем)

- Новый read-only CLI `config/bin/spec-preflight` — предполётный консенсус-линт проекта.
- Общие хелперы в `config/bin/spec_scope.py`: `dod_check_ids`, `canon_command`, `command_kind`, `is_heavy_command`.
- Рефакторинг `config/bin/docs-lint`: импортировать общий `dod_check_ids` из `spec_scope` вместо локальной копии (поведение не меняется).
- Новый тест `config/bin/tests/test_spec_preflight.py`.
- Заметка в `config/templates/spec-template.md` о владельце suite и дедупликации чеков.
- Строка доктрины в `config/AGENTS.md`: `spec-preflight` добавлен в список CLI, которые агент МОЖЕТ запускать.
- Новый корневой `.gitignore` (`__pycache__/`, `*.pyc`, `.pytest_cache/`, `verify/`).

### 1.3 Не-цели

- Никаких правок `config/plugins/spec-gate.ts` (гейт не трогаем).
- Никакой автоматизации одобрения: `spec-preflight` — только отчёт; `spec-approve` остаётся human-only CLI, `--all/--changed` уже существуют и не меняются.
- Никаких изменений в `dod-run`, `spec-status`, `spec-new`, `spec-revoke`, `gate-off/on`.
- Никаких новых зависимостей вне stdlib.
- Никакой правки реального `~/.config/opencode`.

## Раздел 2. Архитектурное решение (Mini-ADR)

**Контекст.** Одобрение человека — дорогой ресурс, а обнаружение несогласованности *после* одобрения вызывает лавину переодобрений. Знания о «что с чем столкнётся» (дубли `dod.id`, пересечение `scope`, дубли тяжёлых команд, канон команд) полностью выводимы из самих спеков ещё до одобрения.

**Решение.** Ввести отдельный read-only инструмент `spec-preflight`, который собирает три класса дефектов: (а) **ERROR** — то, что делает контракт неисполнимым/недостижимым (`DONE`-невозможность): невалидный/отсутствующий `scope`-мандат, отсутствующий/битый `dod`-блок, дубли `dod.id` внутри контракта и между контрактами; (б) **WARNING** — риск/расточительство: пересечение зон записи (нарушение «один писатель на файл»), дублирование канонизированной тяжёлой команды между контрактами, использование неканонического варианта команды; (в) служебный **отчёт** (`--json` → `report`): карта файл→контракты и группы дублей с рекомендацией владельца suite. Логика `dod.id` и формы блоков выносится в `spec_scope`, чтобы у `docs-lint` и `spec-preflight` был **один** источник разбора (устранение второй копии правды).

**Следствия.** (+) Одобрение становится «один раз и по делу»; дедуп виден до запуска волны. (+) Один парсер фенсов на два инструмента. (−) Новый инструмент — ещё один файл, который надо поддерживать; (−) эвристика пересечения `scope` может давать ложные срабатывания на широких паттернах → понижена до WARNING, никогда не блокирует одобрение.

**Отвергнутые альтернативы.** (1) Расширять `docs-lint` — смешивает «линт документа» и «предполётную согласованность проекта»; `docs-lint` вызывается на один спек, а консенсус по определению проектный. (2) Встроить проверки в `spec-approve` — он human-only и не должен обрастать логикой; проверка обязана быть агент-исполняемой. (3) Парсить `bash`-строки DoD на предмет «тяжести» через запуск — запрещено: это исполнение, а не линт.

**Связанные ADR.** `docs/adr/0001-gate-as-soft-guardrail.md` — почему мягкий гейт нуждается в предполётной согласованности (он не ловит согласованность контрактов между собой); `docs/adr/0004-dod-evidence-artifacts.md` — семантика evidence v2 (`git_head`/`tree_dirty`/`scope_sha256`), на которую опирается план доказательства в §4.

## Раздел 3. Спецификация контрактов и интерфейсов (Reference)

### 3.1 CLI `config/bin/spec-preflight`

```
spec-preflight [<path-inside-project>] [--spec <slug|path>] [--json] [--quiet] [--help]
```

- `<path-inside-project>` — опциональный путь к корню проекта/подкаталогу (по умолчанию — cwd); корень ищется подъёмом до каталога, содержащего `.slim/spec` (ограничения те же, что у `docs-lint`/`spec-status`: стоп на `.git`, `$HOME`, `/`).
- `--spec <slug|path>` — ограничить проверку одним контрактом (разрешение имён как в `docs-lint.resolve_spec`: `spec_dir/<slug>`, `spec_dir/<slug>.md`, `cwd/<slug>`, `cwd/<slug>.md`); при промахе — ненулевой код и список доступных slug'ов.
- `--json` — машиночитаемый вывод (см. 3.4).
- `--quiet` — подавлять вывод только при нуле ошибок.
- Коды возврата: `0` — нет ERROR; `1` — есть хотя бы один ERROR; `2` — ошибка использования/резолвинга.

Инструмент **ничего не пишет на диск** и **не исполняет** команды из `dod`.

### 3.2 Проверки

Пусть $C$ — множество активных контрактов (не `index`, не `undeclared`; при `--spec` — один), $T$ — множество tracked-файлов (`spec_scope.tracked_files(root)`).

**(E1) Статус-строка.** Для каждого $c\in C$: `spec_scope.classify(text) == "spec"`, иначе ERROR `preflight-status`.

**(E2) `scope`-мандат.** `spec_scope.scope_report(text)`: `present == False` → ERROR `preflight-scope` «нет `scope`-фенса: гейт не даст мандат (fail-closed)»; любые `report.errors` → ERROR `preflight-scope`. Предупреждения `report.warnings` → WARNING `preflight-scope`.

**(E3) `dod`-блок.** `spec_scope.parse_fences(text).get("dod")` отсутствует → ERROR `preflight-dod`; тело не парсится по форме `{"checks":[{"id":str,"cmd":str}]}` (та же строгость, что в `dod-run.parse_dod_checks`) → ERROR `preflight-dod`; `checks` пуст → ERROR `preflight-dod`; `id`, содержащий `/`, `\`, `.`, `..`, или пустой → ERROR `preflight-dod`.

**(E4) Дубли `dod.id`.** `spec_scope.dod_check_ids(text)` по каждому $c$; дубль внутри контракта → ERROR `preflight-dod-duplicate`; один и тот же `id` у $\ge 2$ контрактов → ERROR `preflight-dod-duplicate` с перечислением контрактов и указанием, что плоское хранилище `verify/<id>.json` перезаписывается.

**(W1) Карта владения (единый писатель).** Для каждого $f \in T$ (относительный путь) и каждого $c\in C$: `spec_scope.scope_allows(scope_c, f)`. Если $\ge 2$ контракта матчат один и тот же $f$ → WARNING `preflight-owner` с парой (файл, список контрактов) и рекомендацией «оставить одного писателя или развести `deny`». В `report.owners` включается таблица: путь → список контрактов (включительно; только при $\ge 1$).

**(W2) Дубли тяжёлых команд.** Для каждого $c$ собрать `cmd` всех его `checks`. Канонизировать `canon_command(cmd)` (см. 3.3). Сгруппировать по канонической строке; если каноническая команда `is_heavy_command(...) == True` и встречается у $\ge 2$ контрактов → WARNING `preflight-heavy-duplicate` с рекомендацией «один владелец suite» и предложенным владельцем = контракт с наименьшим slug в группе. В `report.heavy_duplicates` — группы с участниками.

**(W3) Канон команды.** Если `cmd` содержит неканоничную форму (например `uv run ` — двойственность канона) → WARNING `preflight-canon`.

Порядок вывода: сначала все ERROR, затем WARNING, внутри — по возрастанию `(file, check)`.

### 3.3 Общие хелперы в `config/bin/spec_scope.py` (добавить в `__all__`)

```python
def dod_check_ids(text: str) -> list[str]:
    """Все непустые строковые id из dod-фенса (терпимо к невалидной форме; [] если блока нет)."""

def canon_command(cmd: str) -> str:
    """Канонизация shell-строки для сравнения дублей: strip; нормализация пробелов;
    удаление обёрток `nice … taskset … ionice …`, префиксных ENV-присваиваний,
    `python3 -m`/`python -m` → `python -m`; регистр ключевых слов не меняется."""

def command_kind(cmd: str) -> str:
    """Класс команды: 'pytest' | 'ctest' | 'cmake' | 'ruff' | 'build' | 'other'."""

def is_heavy_command(cmd: str) -> bool:
    """True, если каноническая команда относится к тяжёлым (pytest/ctest/cmake build/ruff на всём проекте)."""
```

`docs-lint` переключается на импорт `dod_check_ids` из `spec_scope`; локальная копия (175-201) удаляется без изменения поведения.

### 3.4 Формат `--json`

```json
{
  "root": "<абсолютный путь>",
  "errors":   [{"file": "<spec>", "check": "<id>", "message": "<текст>"}],
  "warnings": [{"file": "<spec>", "check": "<id>", "message": "<текст>"}],
  "report": {
    "contracts": ["<slug>", "..."],
    "owners": [{"path": "<rel>", "contracts": ["<slug>", "..."]}],
    "heavy_duplicates": [{"canon": "<строка>", "kind": "<kind>", "contracts": ["<slug>"], "suggested_owner": "<slug>"}]
  }
}
```

Человекочитаемый вывод: `ERROR: <file>: [<check>] <message>` / `WARN: ...`, затем (если есть) блок «Отчёт» с картой владения и дублями.

```scope
{"allow": ["config/bin/spec-preflight", "config/bin/spec_scope.py", "config/bin/docs-lint", "config/bin/tests/test_spec_preflight.py", "config/templates/spec-template.md", "config/AGENTS.md", ".gitignore"], "deny": ["docs/**", "config/plugins/**", "**/approvals/**", "**/audit/**", "**/*.db"]}
```

## Раздел 4. Evidence Path (план доказательства корректности)

- **Юнит-эвиденция:** `config/bin/tests/test_spec_preflight.py` (pytest, stdlib-хелперы; фикстуры в `/tmp/opencode/...`, никакого доступа к реальному `~/.local/share/opencode`). Каждый ERROR/WARNING-класс покрыт случаем «сработал» и «не сработал»; отдельно проверяются `--spec`-фильтр, форма `--json` и стабильность порядка.
- **Интеграционная эвиденция:** `docs-lint` после рефакторинга даёт байт-в-байт тот же вердикт на существующих спеках (проверяется прогоном по проекту).
- **Само-эвиденция (self-hosting):** `spec-preflight` на самом репозитории возвращает `0` (эта спека — единственный контракт, пересечений и дублей нет).
- **Троттлинг:** все команды — под `nice -n 19 taskset -c 0,1 ionice -c3` и однопоточными ENV; одновременно исполняется только один тяжёлый чек (политика ноутбука).
- **Изоляция доказательства:** `dod-run` пишет `verify/<id>.json` (evidence v2: `spec_sha256`, `git_head`, `tree_dirty`, `scope_sha256`). Перед запуском весь код вне `.slim/spec/**` и `verify/**` закоммичен, иначе `tree_dirty=true` и `DONE` недостижим.

Стратегии: `verification-planning` (эта таблица), `notebook-verify` не применяется (ноутбуков нет).

## Раздел 5. Definition of Done (чек-лист)

- [ ] `config/bin/spec-preflight` существует, исполняем, поддержка кодов 0/1/2, флагов `--spec/--json/--quiet/--help`.
- [ ] Реализованы проверки E1–E4, W1–W3 и `report` (`owners`, `heavy_duplicates`).
- [ ] `spec_scope.py` экспортирует `dod_check_ids`, `canon_command`, `command_kind`, `is_heavy_command`; они в `__all__`.
- [ ] `docs-lint` использует общий `dod_check_ids`; поведение не изменилось (существующие спеки — тот же вердикт).
- [ ] `config/bin/tests/test_spec_preflight.py` — зелёный; покрыты все ERROR/WARNING-классы + `--json` + `--spec`.
- [ ] `spec-preflight` на репозитории возвращает 0; `docs-lint` на этой спеке — без ERROR.
- [ ] В `config/templates/spec-template.md` есть заметка про владельца suite / дедуп чеков; в `config/AGENTS.md` `spec-preflight` добавлен в список агент-разрешённых CLI.
- [ ] Корневой `.gitignore` игнорирует `__pycache__/`, `*.pyc`, `.pytest_cache/`, `verify/`.
- [ ] `spec-status --spec preflight-0` переходит в `DONE` на чистом дереве.

```dod
{"checks": [{"id": "preflight-0-pytest", "cmd": "OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 nice -n 19 taskset -c 0,1 ionice -c3 python3 -m pytest config/bin/tests/test_spec_preflight.py -q"}, {"id": "preflight-0-docs-lint", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 config/bin/docs-lint --spec preflight-0"}, {"id": "preflight-0-preflight", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 config/bin/spec-preflight"}, {"id": "preflight-0-spec-status", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 config/bin/spec-status --spec preflight-0"}]}
```

Примечание к evidence v2: `git_head`, `tree_dirty` и `scope_sha256` фиксируются один раз перед первым чеком. Закоммитьте всё вне `.slim/spec/**` и `verify/**` **до** `dod-run`. `verify/**` — доказательство, а не мусор.

## Раздел 6. Фазы автономного исполнения

1. **Recon (владелец: orchestrator).** Сверка точных сигнатур/констант по `exp-4`; фиксация в этой секции при расхождении. Результат: подтверждённые точки правок.
2. **Реализация ядра (владелец: `@python-expert`).** Хелперы в `spec_scope.py`; новый `config/bin/spec-preflight`; рефакторинг `docs-lint`; тест-файл. Строго в границах `scope`.
3. **Доктрина/шаблон (владелец: `@fixer`).** Заметка в `spec-template.md`, строка в `AGENTS.md`, корневой `.gitignore`.
4. **Независимая проверка (владелец: `@oracle`, read-only).** Ревью интерфейса и эвристик W1/W2: нет ли ложноположительных ERROR, не ломает ли `canon_command` легитимные команды; проверка, что `docs-lint` не изменил вердикты.
5. **Эвиденция (владелец: orchestrator).** Коммит базы → `nice -n 19 taskset -c 0,1 ionice -c3 python3 config/bin/dod-run --spec preflight-0` → `spec-status --spec preflight-0` → `DONE`.

**Владелец валидации:** orchestrator (сводит lane'ы, запускает `dod-run`, сверяет `spec-status`). **Владелец независимого ревью:** `@oracle`.
**R6:** остановиться и спросить человека после трёх подряд неудач на одном чеке, при противоречии контракта или риске необратимой потери данных.

## Approval (одобряет только человек)

Одобрение выполняется человеком вне сессии агента:

```
~/.config/opencode/bin/spec-approve preflight-0
```

или в TUI командой `/spec-approve preflight-0`. После одобрения мандат выдаёт `scope`-фенс выше; любая правка этой спеки аннулирует одобрение и эвиденцию.
