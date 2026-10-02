# Changelog

Все заметные изменения этого проекта документируются здесь.

Формат — [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/);
версионирование — [Semantic Versioning](https://semver.org/lang/ru/).

## [0.2.0] — 2026-10-03

### Added
- Tamper-evident audit chain (`prev_hash` / `entry_hash` / `pid` / `seq` / `plugin`)
  в `config/plugins/spec-gate.ts`, boot-canary (в т.ч. под `OPENCODE_SPEC_GATE=off`),
  read-only `config/bin/audit-verify`, кросс-языковые векторы
  `config/tools/gov/audit_vectors.json` (`audit-chain-p0`).

### Changed
- `verify/*.json`: поле `spec` теперь root-relative + dual-accept чтение;
  `check_portability.py paths` сканирует `spec`-поле `verify/**/*.json`
  (active → hard-fail, archived → note) (`portable-evidence-paths-p0`).

### Docs
- Граница тампер-эвиденс и релизная политика; доктрина m8 «одобрения host-local».

## [0.1.0] — 2026-10-02

Первый «portable» срез кита в рамках контракта `p0-portability-sprint`
(строки дерева — на ревизии `f984997`, working tree).

### Added
- `config/tools/gov/check_portability.py` — исполняемый чекер портируемости с тремя
  режимами (`paths`, `config`, `install`), только stdlib; `config/tools/gov/scope_vectors.json`
  как вектор-кейсы glob-семантики `scope`.
- Поведенческие тесты `config/bin/tests/**` на `spec-status` (все переходы + stale),
  `spec-new`, `gate-off`/`gate-on`, `wave-run --execute` на реальном `dod-run`.
- `VERSION` (`0.1.0`), `CHANGELOG.md`, `install.sh --target DIR`, `.github/workflows/ci.yml`.
- `examples/` — сквозной пример `examples/minimal/` (валидные `scope` и `dod` со
  slug-префиксными `id`).

### Changed
- **F1 / D1 — изоляция:** тесты CLI и TS-харнесс резолвят пути от собственного файла;
  ни один файл под `config/**` больше не содержит абсолютный домашний путь автора
  (исключение — human-owned `config/command/spec-approve.md:9`, зона `deny`).
- **F2 / D3 — харденинг отгружаемого снапшота:** из `permission.external_directory`
  (`config/opencode.json`) убраны каталоги живой конфигурации OpenCode; `bash`-разрешения
  всех агентов (`config/oh-my-opencode-slim.json`) переведены из строковой формы в
  объектные карты без human-only CLI.
- **F3 / D4 — README** переписан по фактам дерева: актуальный инвентарь с LOC, реальный
  состав тестов, чек-лист подстановок `файл:line`, маркер `SYNCED`.
- **F12 / D6 — шаблон:** `config/templates/spec-template.md` — `scope.allow` с
  `<task_slug>`, `dod.id` со slug-префиксом (защита от коллизий в плоском
  `verify/<id>.json`).
- **F19 / D7 — дерево:** удалён `.pytest_cache/`.

### Removed
- `.pytest_cache/` и пик-кэши из рабочего дерева (артефакты, не исходники).

### Not in this release
- **F8:** политика `verify/**` (tracked vs untracked) — решение человека.
- **P1:** HMAC-подпись одобрений, namespaced `verify/<slug>/<id>.json`, wave-дедуп, `oc-usage`.
- Tamper-evident аудит-журнал (`prev_hash`-цепочка).
