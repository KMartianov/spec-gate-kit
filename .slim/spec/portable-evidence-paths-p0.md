# Portable evidence paths & host-local approvals — `portable-evidence-paths-p0`

- **Статус спецификации:** `approved`   <!-- draft | approved — перевод в approved делает ТОЛЬКО человек -->
- **Утверждено:** 2026-10-02T16:51:17.716421+00:00 (human)
- **Дата создания:** 2026-10-02
- **Автор:** orchestrator
- **Целевая ветка / worktree:** `master` (HEAD `0001176`)
- **Task slug:** `portable-evidence-paths-p0`  (имя файла: `.slim/spec/portable-evidence-paths-p0.md`)

> **Zero-Code Gate.** Пока статус `draft`, разрешена запись только в `.slim/spec/**`.
> Мандат записи — ограждение `scope` (§3), а не факт одобрения; `docs/**` закрыт
> безусловно (GOV-2). Правка спеки после одобрения инвалидирует approval.

---

## Раздел 1. Цели и границы (Scope)

### Цели
Закрыть **m8** (аудит 2026-10-02): абсолютные машино-специфичные пути в артефактах
`verify/*.json` и в привязке одобрений делают доказательства непереносимыми при
клоне/переносе репозитория. Контракт переводит записываемый путь спеки в
**относительный от корня проекта**, вводит **dual-accept** чтение (легаси-абсолютный
и новый относительный) и фиксирует доктрину: **одобрения — host-local**.

Три разделяемых вреда (уточнены `@oracle`):
1. `dod-run::ensure_overwritable` — абсолютный путь как tie-breaker (гигиена, не
   корректность: digest-плечо и так принимает байт-идентичный клон).
2. **Привязка одобрений** — `root_hash` каталога и имя файла записи выводятся из
   абсолютного пути (`spec_scope.py:80-82`, `spec-approve:195-197`): клон/перенос →
   одобрения невидны → `SPEC_DESIGN`. **Это реальный критический разрыв.**
3. Закоммиченные `verify/*.json` с `/home/...` — непереносимая документация + утечка
   имени пользователя.

### Non-goals (категорически запрещено менять)
- **Никаких** изменений ключевания одобрений (`root_hash`) и их местоположения:
  одобрения остаются host-local по построению (доктрина ниже).
- Файл `config/plugins/spec-gate.ts` и порядок принятия решения гейтом.
- `docs/**` (GOV-2), `config/command/**`, реальный `~/.config/opencode`, `research/**`.
- Правила `docs-lint`, `spec-revoke`, фенсы `scope`/`dod`, формула `DONE` в
  `spec-status` (staleness не трогаем).
- Сетевое взаимодействие, внешние якоря, подписи (P1), namespaced evidence
  `verify/<slug>/<id>.json` (P1-10).

---

## Раздел 2. Архитектурное решение (Mini-ADR)

- **Контекст и проблема:** `spec`-поле evidence и привязка одобрений завязаны на
  абсолютный путь проекта; при клоне на другую машину/в другой каталог доказательства
  теряют провенанс, а одобрения становятся невидимыми.
- **Принятое решение:**
  - **evidence — портируемый артефакт:** `spec` пишется корне-относительным POSIX-путём
    (`.slim/spec/<name>.md`), чтение — dual-accept (легаси-абсолютный ∪ относительный);
  - **одобрения — host-local:** это внешнее, машино-локальное, human-only хранилище
    (ADR-0002); после клона штатным восстановлением является `spec-approve --all`
    (дёшево и уже существует). Портируемым делается **доказательство**, не одобрение;
  - **честная деградация:** никакой схемы не меняем без dual-accept — иначе мгновенно
    инвалидируются 4 живые записи в `~/.local/share/opencode/approvals/bef96c3328c64cc1/`.
- **Отвергнутые альтернативы:**
  - Альтернатива A — сделать `root_hash`/имя записи корне-относительными: ломает
    существующее хранилище и требует миграции всех машин; ставит лабораторную
    портируемость выше простоты human-only хранилища. Отвергнута (YAGNI; см. доктрину).
  - Альтернатива B — оставить всё как есть и лишь документировать: не закрывает m8,
    оставляет утечку пути и «ложную» непереносимость коммитов. Отвергнута.
  - Альтернатива C — namespaced evidence `verify/<slug>/<id>.json` вместе с этим:
    смешивает два предмета, правит `docs-lint`/`spec-status`, тянет ADR. Отложено (P1-10).
- **Последствия:**
  - Позитивные: клон воспроизводит provенанс evidence без машино-специфичных путей;
    `check_portability.py paths` становится зелёным; снимается утечка имени пользователя.
  - Негативные / риски: после клона всё равно нужен `spec-approve --all` (заявлено
    честно, это доктрина, а не дефект); нужен dual-accept, чтобы не убить легаси-записи.

---

## Раздел 3. Спецификация контрактов и интерфейсов (Reference)

> Нормативно. Реализация пишется строго по этому разделу.

### 3.1 Текущее поведение (что меняем)

| Место | Сейчас | Станет |
|---|---|---|
| `config/bin/dod-run:396` и `:529` | `record["spec"] = str(spec)` (абсолютный) | `record["spec"] = spec_rel(root, spec)` (корне-относительный POSIX) |
| `config/bin/dod-run::guard_existing_evidence` (`:285-328`) | digest-first; при расхождении `Path(recorded).resolve() == spec.resolve()` | digest-first сохраняется; fallback → `spec_matches(root, recorded, spec)` (dual-accept) |
| `config/bin/spec_scope.py:592-634` `find_valid_approval` | `Path(record["spec"]).resolve() != spec.resolve()` (`:627-630`) | `norm_spec_path(root, record["spec"]) != spec.resolve()` (dual-accept) |
| `config/tools/gov/check_portability.py` (`paths`) | сканирует `config/**`, `README.md`, `install.sh`, `VERSION` | дополнительно сканирует `verify/**/*.json` поле `spec` на абсолютный домашний путь |

`root_hash` (`spec_scope.py:80-82`) и имя записи (`spec-approve:195-197`)
**не меняются** — это host-local по доктрине.

### 3.2 Публичные интерфейсы (Python)

```python
# config/bin/spec_scope.py
def norm_spec_path(root: Path, recorded: str) -> Path:
    """Принять и легаси-абсолютный, и новый корне-относительный записанный путь спеки."""

def spec_rel(root: Path, spec: Path) -> str:
    """Вернуть корне-относительный POSIX-путь спеки (напр. '.slim/spec/<name>.md')."""
```

```python
# config/bin/dod-run
def spec_matches(root: Path, recorded: object, spec: Path) -> bool:
    """True, если записанный путь (abs|rel) указывает на ту же спеку относительно root."""
```

### 3.3 Математические выражения и инварианты (строго LaTeX)

Относительный путь в evidence:

$$\text{spec\_field} = \operatorname{posix}\!\left(\operatorname{relpath}(\text{spec},\ \text{root})\right)$$

Dual-accept предикат совпадения записи со спекой:

$$
M(\text{rec}, \text{spec}) \;=\;
\begin{cases}
\texttt{true}, & \operatorname{resolve}(\text{abs}(\text{rec})) = \operatorname{resolve}(\text{spec})\\
\texttt{true}, & \operatorname{resolve}(\text{root} \parallel \text{rec}) = \operatorname{resolve}(\text{spec})\\
\texttt{false}, & \text{иначе (чужой артефакт или путь отсутствует} \to \text{exit 3)}.
\end{cases}
$$

$M$ вызывается **только** когда $\text{recorded}.\text{spec\_sha256} \neq \operatorname{sha256}(\text{spec bytes})$.

Первичная идентичность evidence остаётся по хешу: $same = (\text{recorded}.\text{spec\_sha256} = \text{sha256}(\text{spec bytes}))$; путь — только tie-breaker при расхождении хешей.

### 3.4 Ограждение `scope` — машинный мандат записи (GOV-1)

```scope
{
  "allow": [
    "config/bin/dod-run",
    "config/bin/spec_scope.py",
    "config/bin/spec-approve",
    "config/bin/spec-status",
    "config/bin/tests/test_portable_paths.py",
    "config/tools/gov/check_portability.py"
  ],
  "deny": ["docs/**", "config/command/**", "**/approvals/**", "**/audit/**", "**/*.db"]
}
```

---

## Раздел 4. Evidence Path (план доказательства корректности)

- **Стратегия:** `verification-planning`.
- **Юнит-тесты (изолированные):** `config/bin/tests/test_portable_paths.py` — на tmp-копии:
  (i) запись evidence даёт корне-относительный `spec`; (ii) легаси-абсолютная запись
  принимается dual-accept; (iii) чужой `spec_sha256` + чужой путь → exit 3, файл цел;
  (iv) `norm_spec_path` корректен для abs/rel/отсутствия.
- **Проверка переносимости:** на relocated tmp-клоне `python3 config/tools/gov/check_portability.py paths` → rc=0
  (включая `verify/**`); на непропатченном клоне — rc=1 (контроль).
- **Dual-accept легаси:** чтение текущих `verify/*.json` (абсолютный `spec`) не меняет вердикт.
- **Миграция:** реализация → регенерация затронутого evidence из **чистого** дерева
  (`dod-run`) → `paths` зелёный. Не коммитить evidence после `dod-run` в том же акте,
  который двигает HEAD (staleness по `git_head`).
- **Тяжёлый прогон:** владелец — этот контракт; команды каноничны и не дублируют иные контракты.

---

## Раздел 5. Definition of Done (чек-лист)

- [ ] `scope` покрывает все изменяемые файлы (без него мандата нет)
- [ ] `spec` в новых evidence-записях — корне-относительный POSIX-путь
- [ ] Dual-accept: легаси-абсолютные записи и перенос репозитория не меняют вердикт
- [ ] `check_portability.py paths` сканирует `verify/**` и зелёный на чистом дереве
- [ ] `pytest config/bin/tests` — rc=0
- [ ] `docs-lint --spec portable-evidence-paths-p0` — rc=0
- [ ] Доктрина host-local одобрений зафиксирована в шапке §2 (и вынесена человеком в `docs/**`/`README` отдельно)

```dod
{
  "checks": [
    {"id": "portable-evidence-paths-p0-pytest", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 -m pytest config/bin/tests -q"},
    {"id": "portable-evidence-paths-p0-paths", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 config/tools/gov/check_portability.py paths"},
    {"id": "portable-evidence-paths-p0-docs-lint", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 config/bin/docs-lint --spec portable-evidence-paths-p0"}
  ]
}
```

---

## Раздел 6. Фазы автономного исполнения

| # | Фаза | Субагент | Ожидаемый результат |
|---|------|----------|---------------------|
| 1 | Относительные пути + dual-accept + тесты | `@python-expert` | `dod-run`/`spec_scope.py` правки, `test_portable_paths.py` |
| 2 | Расширение `check_portability.py` | `@fixer` | `paths` сканирует `verify/**` |
| 3 | Независимое ревью | `@oracle` | read-only проверка инвариантов dual-accept |
| 4 | Регенерация evidence + DoD | orchestrator | `dod-run` → `spec-status` DONE |

---

## Approval (одобряет только человек)

`~/.config/opencode/bin/spec-approve portable-evidence-paths-p0` либо `/spec-approve portable-evidence-paths-p0`.
Агент не пишет артефакт одобрения сам. Правка спеки после одобрения инвалидирует approval.

<!-- Связано: `.slim/spec/audit-chain-p0.md` (журнал, отдельный предмет),
     `.slim/spec/p0-portability-sprint.md` (упаковка/переносимость кита),
     аудит `.slim/spec/notes/full-audit-2026-10-02.md` (m8),
     решения `.slim/spec/notes/decisions-2026-10-02.md`. -->
