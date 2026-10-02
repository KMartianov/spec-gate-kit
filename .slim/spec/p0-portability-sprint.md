# P0 Portability Sprint — тесты, харденинг, README, упаковка

- **Статус спецификации:** `approved`
- **Утверждено:** 2026-10-01T20:49:42.160722+00:00 (human)
- **Дата создания:** 2026-10-02
- **Автор:** orchestrator (по отчёту `.slim/spec/notes/readiness-audit-2026-10-02.md`: F1, F2, F3, F4, F10-minimal, F12, F19)
- **Целевая ветка / worktree:** текущая ветка репозитория `spec-gate-kit` (без отдельного worktree)
- **Task slug:** `p0-portability-sprint` (файл `.slim/spec/p0-portability-sprint.md`)

> **Zero-Code Gate.** Пока статус `draft`, разрешена запись только в `.slim/spec/**`.
> Мандат записи даёт **`scope`**, а не сам факт одобрения.

## Раздел 1. Цели и границы (Scope)

### 1.1 Зачем

Отчёт о готовности (`.slim/spec/notes/readiness-audit-2026-10-02.md`) вынес вердикт: ядро принуждения корректно, но кит **не переносим**. Три BLOCKER и упаковочный MAJOR:

1. **F1 — тесты хардкодят живой путь автора.** `config/bin/tests/test_spec_approve.py:16` и `config/bin/tests/test_docs_lint.py:18-20,250` указывают на `/home/asdcxfrt/.config/opencode/bin/**`. Документированная процедура проверки после установки тестирует **живую конфигурацию автора**, а не кит. Любое зелёное свидетельство обнуляется для чужой машины.
2. **F2 — Stage-1 харденинг доверия не реализован в отгружаемом JSON.** `config/opencode.json:8` держит `~/.config/opencode/**` в `external_directory`, а строковая форма `"bash":"allow"` (`config/oh-my-opencode-slim.json:218-219,240-241,277-279`) разворачивается в `{"*":"allow"}` и стирает глобальные `deny`.
3. **F3 — README ложен на несущих фактах:** «новых файлов нет» (`README.md:13`) при 7 тест-файлах и новом `scope_vectors.json`; «`.gitignore` намеренно не создан» (`:182`) при существующем `.gitignore` (388 B); «993 строки» (`:22`) при 997; §1 не упоминает `spec-preflight`, `wave-run`, `research/`, `verify/`, `.slim/spec/`, `tests/`.
4. **F10 — нет упаковки:** нет `VERSION`, `CHANGELOG`, `install.sh`, CI; TS-харнесс требует Node ≥ 22 (нативное исполнение `.ts`), но требование нигде не зафиксировано.

Без закрытия F1–F3 и упаковочного минимума метка «portable v0.1» будет нечестной.

### 1.2 Границы (что делаем)

- **D1 (F1)** — все тесты `config/bin/tests/**` и TS-харнесс резолвят пути **от собственного файла**, а не от живой машины; ни один файл под `config/**` не содержит `/home/asdcxfrt`.
- **D2 (F4)** — добавить поведенческие тесты на `spec-status` (все переходы `INTAKE → SPEC_DESIGN → APPROVED → VERIFY → DONE` и stale-ветки), `spec-new` (скаффолд в tmp), `gate-off`/`gate-on` (маркер + взаимодействие с гейтом) и `wave-run --execute` на **реальном** `dod-run`.
- **D3 (F2)** — Stage-1 в отгружаемом снапшоте: убрать `~/.config/opencode/**` и `~/.local/share/opencode/**` из `external_directory`; перевести `bash`-разрешения трёх агентов в объектную форму, исключив из неё человеческие CLI (`spec-approve`, `spec-revoke`, `gate-off`, `gate-on`).
- **D4 (F3)** — переписать `README.md` по фактам §1.1 и пометить `SYNCED: <rev>`.
- **D5 (F10-minimal)** — `VERSION` (semver), `install.sh --target DIR` (идемпотентная установка с проверкой Python ≥ 3.11 / Node ≥ 22, бэкапом существующего конфига и смоуком), `CHANGELOG.md`, CI-workflow.
- **D6 (F12)** — исправить шаблон: `scope.allow` = `["tools/<task_slug>/**"]`, примеры `dod.id` — со slug-префиксом.
- **D7 (F19)** — наполнить `examples/` хотя бы одним сквозным примером; убрать `.pytest_cache/` из дерева.

### 1.3 Не-цели

- **Никаких изменений семантики гейта:** порядок решения, exempt-список, read-only allowlist, безусловный отказ `docs/**`, fail-closed на неразбираемых путях, glob-семантика — не меняются. D3 правит **отгружаемый конфиг-снапшот**, не рантайм-логику `spec-gate.ts`.
- **`docs/**` не трогаем.** Это immutable-зона (GOV-2): даже `GATE-OFF` её не открывает. Синхронизация ADR (F20) и создание Diátaxis-квадрантов — **задача человека в редакторе**, не агента.
- **F8 (политика `verify/**`) не входит.** Рассогласование tracked-proof / untracked+wave-log — отдельное решение человека; контракт его не предрешает.
- **F16 (сплошной dedup резолверов) не входит.** Дублирование `find_root`/`resolve_target`/`spec_rel` остаётся; допускается вынести в `spec_scope.py` только то, что реально нужно D1/D2, и это не должно менять поведение.
- **F9 (граница `findRoot` TS/Python), F13, F18 — не входят** (отдельный follow-up).
- **Никаких правок реального `~/.config/opencode/**`** и реального `~/.local/share/opencode/**`.
- Никаких P1-элементов: HMAC-подпись, namespaced `verify/<slug>/<id>.json`, wave-дедуп, `oc-usage`.
- Никаких новых рантайм-зависимостей: Python — только stdlib; TS — только встроенные модули Node; `package.json`/lockfile **не вводится**.
- Архив завершённых контрактов (`gate-parity-p0`, `evidence-atomic-p0`) — **действие человека** (GOV-6), не агента.

## Раздел 2. Архитектурное решение (Mini-ADR)

- **Контекст и проблема:** кит проверяет себя на живой машине автора (F1) и поставляет конфиг, который сам себе противоречит (F2): доктрина провозглашает Stage-1 харденинг, а снапшот держит `~/.config/opencode/**` доступным агенту и допускает строковый `bash`-allow, стирающий `deny`. Титульный README описывает состояние, которого нет (F3). Три дефекта образуют один корень: **артефакт, который нельзя установить и проверить на чистой машине, не является deliverable.**
- **Принятое решение:**
  - **сначала изоляция, потом всё остальное:** пока тесты не резолвят пути от себя, ни один другой результат не является свидетельством;
  - харденинг — **в данных** (конфиг-снапшот), а не в прозе доктрины: то, что нельзя проверить скриптом, не считается сделанным;
  - переносимость проверяется **исполняемым чекером**, а не ревью: отдельный `config/tools/gov/check_portability.py` с тремя режимами (`paths`, `config`, `install`) — это DoD-чек, а не пожелание;
  - README — производная от фактов; расхождение с деревом = дефект.
  - Базовый ADR: `docs/adr/0001-gate-as-soft-guardrail.md`
- **Отвергнутые альтернативы:**
  - A — оставить хардкод путей и «задокументировать», что тесты нужно править после установки: переносит дефект на владельца, обесценивает проверку.
  - B — включить в спринт F16 (сплошной dedup): расширяет диффузию риска по всем CLI ради читаемости, увеличивает шанс не дойти до `DONE`; вынесено отдельно.
  - C — решить F8 внутри спринта: политика хранилища — продуктовое решение, а не механическая правка; предрешать её в портирующем контракте нельзя.
  - D — сделать README «по мотивам» без чек-листа подстановок `file:line`: оставляет владельца один на один с машинно-связанными путями.
- **Последствия:**
  - Позитивные: кит становится устанавливаемым и проверяемым на чистой машине; проверка перестаёт быть театром; доктрина и снапшот конфига сходятся.
  - Негативные / риски: README-переписывание устаревает быстро (митигация — маркер `SYNCED: <rev>`); D3 правит файлы, влияющие на безопасность самой платформы (митигация — независимое ревью `@oracle` и исполняемый чекер `config`).

**Связанные ADR.** `docs/adr/0001-gate-as-soft-guardrail.md` — почему мягкий гейт обязан быть точным, и почему «честная граница доверия» — это требование, а не пожелание.

## Раздел 3. Спецификация контрактов и интерфейсов (Reference)

> Нормативно. Реализация пишется строго по этому разделу.

### 3.1 Изоляция тестов (D1)

- Все тест-файлы `config/bin/tests/*.py` определяют CLI-пути **от собственного расположения**, например:
  `BIN = Path(__file__).resolve().parents[1]` (`config/bin`), `CLI = BIN / "spec-approve"`.
  Образец — `config/bin/tests/test_scope_parity.py:31-34`.
- Ни один файл под `config/**` не содержит подстроку `/home/asdcxfrt`.
- TS-харнесс независим от `cwd` (`import.meta.dirname` / `fileURLToPath`) и не создаёт записей в реальном хранилище одобрений (инвариант сохраняется).

### 3.2 `config/tools/gov/check_portability.py` — новый чекер

CLI: `python3 config/tools/gov/check_portability.py {paths|config|install}`; выход `0` = чисто, `1` = нарушение (печатает найденные пути/факты). Только stdlib.

- **`paths`** — сканирует `config/**`, `README.md`, `install.sh`, `VERSION`; падает, если найден литерал `/home/asdcxfrt` или `~/.config/opencode` вне доктринального пояснения.
- **`config`** — читает отгружаемые JSON и проверяет:
  1. `config/opencode.json` → `permission.external_directory` **не** содержит `~/.config/opencode/**` и `~/.local/share/opencode/**`;
  2. `config/oh-my-opencode-slim.json` → ни у одного агента `bash` не задан строкой `"allow"`/`"deny"`; форма — объектная карта;
  3. в этой карте отсутствуют `spec-approve`, `spec-revoke`, `gate-off`, `gate-on`.
- **`install`** — исполняет `bash install.sh --target <mktemp -d>` и проверяет, что в цели появились `config/`, `README.md`, `VERSION`, `.slim/spec/`, а `VERSION` совпадает с `python3 -c "print(open('VERSION').read().strip())"`.

### 3.3 Отгружаемый конфиг (D3) — нормативные факты

- `config/opencode.json`: `permission.external_directory` **не** включает каталоги живой конфигурации OpenCode.
- `config/oh-my-opencode-slim.json`: `bash` каждого агента — объектная карта; человеческие CLI (`spec-approve`, `spec-revoke`, `gate-off`, `gate-on`) в неё не входят.

### 3.4 `install.sh --target DIR` (D5) — нормативная семантика

- Идемпотентен: повторный запуск не ломает уже установленное.
- Проверяет окружение: Python ≥ 3.11, Node ≥ 22 (для нативного `.ts`).
- Бэкапит существующие конфликтующие файлы цели (`*.bak`), не перезаписывая молча.
- `--force` — перезапись без бэкапа; `--help` — справка; по умолчанию печатает план и требует явную цель.
- `VERSION` — semver, на старте спринта `0.1.0`.

### 3.5 Шаблон (D6)

- `config/templates/spec-template.md`: `scope.allow` = `["tools/<task_slug>/**"]`; примеры `dod.id` — с slug-префиксом (`<task_slug>-build`, `<task_slug>-test`).

### 3.6 Инварианты (строго LaTeX)

$$\forall\,f\in\{\text{test-файлы}\}:\ \operatorname{cli}(f)=\operatorname{parent}(\operatorname{dir}(f))+1 \quad\text{(никакого } /home/\ast\text{)}$$

$$\operatorname{permissions}(\text{agent})[\texttt{bash}]\ \text{— объектная карта}\ \land\ \text{human-CLI}\notin\operatorname{keys}$$

$$\operatorname{install}(T)\ \text{идемпотентен}:\ \operatorname{install}(\operatorname{install}(T))=T_{\text{valid}}$$

### Ограждение `scope` — машинный мандат записи

```scope
{
  "allow": [
    "config/**",
    "README.md",
    "VERSION",
    "CHANGELOG.md",
    "install.sh",
    "examples/**",
    ".gitignore",
    ".github/workflows/**"
  ],
  "deny": ["docs/**", "config/command/**", "**/approvals/**", "**/audit/**", "**/*.db"]
}
```

## Раздел 4. Evidence Path (план доказательства корректности)

- **Стратегия:** `verification-planning`.
- **Юнит (Python):** `python3 -m pytest config/bin/tests -q` — весь сьют, из чистого `$HOME`; включает новые тесты D2 и изолированные D1.
- **Юнит (TS):** `node --test config/plugins/__tests__/spec-gate.test.ts` — мандатный путь и изоляция хранилища.
- **Линт контракта:** `python3 config/bin/docs-lint --spec p0-portability-sprint` — целостность фенсов этой спеки и отсутствие коллизий `dod.id`.
- **Портируемость (исполняемо):** `check_portability.py paths|config|install` — три независимых свидетельства (нет живучих путей; снапшот харденизирован; установка в чистый каталог работает).
- **Чего в DoD нет и почему:** `spec-status --spec p0-portability-sprint` не включён — состояние выводится из самого evidence, такой чек тавтологичен (класс «театра верификации», `research/S5-reliability.md`).
- **Владение тяжёлым прогоном:** все чеки лёгкие; запуск под троттлингом (`nice -n 19 taskset -c 0,1 ionice -c3`), одна тяжёлая команда за раз.
- **Порядок доказательства:** коммит всего, кроме `.slim/spec/**` и `verify/**` → `dod-run` → `spec-status --spec p0-portability-sprint` = `DONE`.

## Раздел 5. Definition of Done (чек-лист)

- [ ] Ни один файл под `config/**` не содержит `/home/asdcxfrt`; тесты резолвят CLI от `__file__`.
- [ ] Добавлены тесты на `spec-status` (все переходы + stale), `spec-new`, `gate-off`/`gate-on`, `wave-run --execute`.
- [ ] `config/opencode.json` и `config/oh-my-opencode-slim.json` харденизированы по §3.3.
- [ ] `README.md` соответствует дереву, содержит чек-лист подстановок `file:line` и маркер `SYNCED: <rev>`.
- [ ] `VERSION`, `CHANGELOG.md`, `install.sh --target`, CI-workflow созданы; установка идемпотентна.
- [ ] `config/templates/spec-template.md` исправлен по §3.5.
- [ ] `examples/` содержит минимум один сквозной пример.
- [ ] `config/tools/gov/check_portability.py` реализован в трёх режимах.
- [ ] Ограждение `scope` покрывает все изменённые файлы (без него мандата нет).
- [ ] Независимое ревью (`@oracle`, read-only) не нашло необъяснённых расхождений.

```dod
{
  "checks": [
    {"id": "p0-portability-sprint-pytest", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 -m pytest config/bin/tests -q"},
    {"id": "p0-portability-sprint-ts", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 node --test config/plugins/__tests__/spec-gate.test.ts"},
    {"id": "p0-portability-sprint-docs-lint", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 config/bin/docs-lint --spec p0-portability-sprint"},
    {"id": "p0-portability-sprint-paths", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 config/tools/gov/check_portability.py paths"},
    {"id": "p0-portability-sprint-config", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 config/tools/gov/check_portability.py config"},
    {"id": "p0-portability-sprint-install", "cmd": "nice -n 19 taskset -c 0,1 ionice -c3 python3 config/tools/gov/check_portability.py install"}
  ]
}
```

## Раздел 6. Фазы автономного исполнения

| # | Фаза | Субагент | Ожидаемый результат |
|---|------|----------|---------------------|
| 1 | Изоляция тестов (D1) + новые тесты (D2) + чекер `paths` | `@python-expert` | правка `config/bin/tests/**`, `check_portability.py paths` зелёный |
| 2 | Харденинг снапшота (D3) + шаблон (D6) | `@fixer` | правка `config/opencode.json`, `config/oh-my-opencode-slim.json`, `config/templates/spec-template.md` |
| 3 | README (D4) + упаковка (D5) + `examples/` (D7) | `@fixer` → orchestrator ревью копирайта | `README.md`, `VERSION`, `CHANGELOG.md`, `install.sh`, `.github/workflows/**`, `examples/**` |
| 4 | Чекер `config`/`install` + прогон трёх режимов | `@python-expert` | `check_portability.py` полностью зелёный |
| 5 | Независимое ревью (read-only) | `@oracle` | вердикт: изоляция настоящая, снапшот не даёт агенту лишнего, README не лжёт |
| 6 | Доказательство | orchestrator | коммит → `dod-run --spec p0-portability-sprint` → `spec-status --spec p0-portability-sprint` = `DONE` |

R6: после трёх подряд неудач на одном чеке — останов и вопрос человеку.

## Approval (одобряет только человек)

Одобрение — исключительно человеческое действие: `~/.config/opencode/bin/spec-approve p0-portability-sprint`
либо `/spec-approve p0-portability-sprint` в TUI. Агент не пишет артефакт одобрения и не меняет статусную строку.
Правка спеки после одобрения меняет хеш и **инвалидирует** approval и всё evidence.
