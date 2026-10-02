# spec-gate-kit — переносимый комплект управления спецификациями для OpenCode

**SYNCED: `f984997` (база) + незакоммиченный P0-спринт (working tree)** · версия `0.1.0`

**Что это.** Самодостаточный набор механики «запрета кода без одобренной
спецификации» для агентных сессий OpenCode: плагин Zero-Code Gate, CLI жизненного
цикла спек, человеческие одобрения, DoD-доказательства, шаблоны, доктрина и
упаковка для установки на другую машину.

**Зачем.** Механика разрабатывалась «на месте», внутри `~/.config/opencode`,
вперемешку с машинно-зависимой конфигурацией (провайдеры, MCP, абсолютные пути).
Из-за этого её нельзя было ни перенести, ни изолированно протестировать, ни
версионировать. Этот репозиторий выделяет **переносимое ядро** в один каталог,
разворачиваемый поверх целевой конфигурации, и развивает его как обычный проект.

**Честная граница.** Гейт — **soft guardrail, а не граница безопасности**; он даёт
трение и аудит-след. Подробности — §6.

---

## 1. Инвентарь репозитория

Верхнеуровневые элементы (локации — `wc -l` на этом снимке):

| Путь | Роль | Содержимое |
|---|---|---|
| `config/` | drop-in-зеркало каталога конфигурации OpenCode | CLI, плагин, тесты, снапшоты, шаблоны, доктрина (см. ниже) |
| `docs/` | доктрина и заметки | ADR `0000…0004`, Diátaxis-квадранты (`tutorials/`, `how-to/`, `reference/`, `explanation/`), `guides/`, `notes/`, `SPEC-OpenCode-Hardening.md` — **human-owned (GOV-2)** |
| `research/` | исследовательские материалы + симуляция `research/sim/` | `M1…M4`, `S1…S6`, `SYNTHESIS.md`, `sim/` (скрипты + результаты) |
| `.slim/spec/` | контракты самого кита, `notes/`, `archive/` | активные: `p0-portability-sprint` (approved), `audit-chain-p0` (draft); архив: `preflight-0`, `evidence-atomic-p0` (DONE), `gate-parity-p0` (DONE) |
| `verify/` | DoD-evidence прогонов (`<id>.json`, schema v2) | 10 отслеживаемых файлов — **доказательство, не мусор** |
| `examples/` | сквозные примеры контрактов | `minimal/` (см. `examples/README.md`) |
| `VERSION` | semver кита | `0.1.0` |
| `CHANGELOG.md` | история изменений | Keep a Changelog |
| `install.sh` | идемпотентная установка `--target DIR` | см. §3 |
| `.github/workflows/ci.yml` | CI: pytest + `node --test` + чекеры | см. §3 |
| `.gitignore` | игнор кэшей (`__pycache__/`, `.pytest_cache/`, `.serena/`) | `verify/**` **не** игнорируется — см. §5 |
| `.serena/` | локальный кэш serena MCP | не трекается (gitignored) |

### `config/` — CLI, плагин, чекер

| Путь | LOC | Что это |
|---|---|---|
| `config/plugins/spec-gate.ts` | 997 | Сам гейт: `tool.execute.before`, allow/block, аудит-JSONL |
| `config/plugins/__tests__/spec-gate.test.ts` | 396 | Тесты гейта (`node --test`), включая fail-closed разбор путей |
| `config/bin/spec-approve` | 616 | Одобрение контракта человеком: флип статуса → штамп → `sha256` пост-флип байтов |
| `config/bin/spec-revoke` | 388 | Отзыв одобрения (ревертит статус; удаляет записи только отозванных спек) |
| `config/bin/spec-status` | 460 | Производное состояние `INTAKE → … → DONE`, read-only, multi-spec, `--json` |
| `config/bin/spec-new` | 261 | Скаффолд проекта: спека, Diátaxis-дерево, `docs/adr/`, README, `.gitignore`, `git init` |
| `config/bin/dod-run` | 551 | Исполнение `dod`-чеков → `verify/<id>.json` (evidence v2: `spec_sha256`, `git_head`, `tree_dirty`, `tail`) |
| `config/bin/docs-lint` | 474 | Линт контрактов: статус, `scope`, ADR-ссылки, коллизии `dod.id` |
| `config/bin/spec-preflight` | 473 | Read-only pre-approval линт (консенсус по `scope`/командам), ничего не пишет |
| `config/bin/wave-run` | 522 | Волна по контрактам; `--dry-run` по умолчанию, `--execute` → делегирует `dod-run` |
| `config/bin/gate-off`, `config/bin/gate-on` | 93 / 87 | Локальный escape hatch (`<root>/.slim/GATE-OFF`) — только человеку |
| `config/bin/spec_scope.py` | 865 | Общий разбор `scope`-фенса и glob-матчинг (импортируется CLI) |
| `config/tools/gov/check_portability.py` | 573 | Исполняемый чекер портируемости: `paths` / `config` / `install` (stdlib) |
| `config/tools/gov/scope_vectors.json` | 32 | Вектор-кейсы glob-семантики `scope` |

**Тесты CLI** — `config/bin/tests/*.py` (11 файлов, 3289 строк):
`test_docs_lint.py`, `test_dod_run.py`, `test_gate_marker.py`,
`test_scope_parity.py`, `test_spec_approve.py`, `test_spec_new.py`,
`test_spec_preflight.py`, `test_spec_revoke.py`, `test_spec_status.py`,
`test_wave_run.py`, `test_wave_run_real_dod.py`.

Остальное в `config/`:
`templates/{spec-template,adr-template}.md`, `command/spec-approve.md` (слэш-команда
TUI), `oh-my-opencode-slim/*_append.md` (10 ролей), `skills/{verification-planning,oh-my-opencode-slim}/SKILL.md`,
`AGENTS.md` (доктрина), снапшоты `opencode.json`, `oh-my-opencode-slim.json`,
`cli.json`, `tui.json`, `dcp.jsonc`.

---

## 2. Как это работает (сжато)

- **Когда включается.** Гейт активен, если вверх по дереву от целевого пути есть
  `.slim/spec/`. Проект без `.slim/spec` гейт не трогает.
- **Порядок решения** (`tool.execute.before`, каждый шаг терминален): kill switch
  `OPENCODE_SPEC_GATE=off` → read-only allowlist (`read`, `grep`, `glob`, `task`, …)
  → извлечение целей (writer без разбираемых путей блокируется fail-closed) → exempt
  (`~/.config/opencode/**`, approvals/audit, `/tmp/opencode/**`) → `.slim/spec/**`
  всегда writable → **`docs/**` всегда запрещено** → `.serena/**` → `.slim/GATE-OFF`
  → мандат: цель покрыта `allow` и не покрыта `deny` активного одобренного контракта,
  иначе `[SPEC-GATE BLOCKED]`.
- **`scope`-фенс — единственный мандат.** JSON `{"allow": [...], "deny": [...]}`;
  globs `*`, `?`, `[a-z]`, `**` как целый компонент. Пустой/битый фенс не даёт
  ничего (fail-closed).
- **Классы файлов в `.slim/spec/`.** Токен `roadmap`/`index` ⇒ портфельный индекс
  (мандата не даёт); иной токен ⇒ контракт; нет статус-строки ⇒ `undeclared`.
  `archive/**` — неактивная зона (retire без удаления), гейт/`spec-status`/`docs-lint`
  её игнорируют.
- **Одобрение — только человек.** `spec-approve` флипает статусную строку в
  `approved`, ставит штамп и хэширует **пост-флип** байты в
  `~/.local/share/opencode/approvals/<sha256(root)[:16]>/<slug>.json`. Любая правка
  спеки меняет хэш и **аннулирует** одобрение. Из сессии — только `/spec-approve`.
- **DoD.** Фенс `dod` с `{"checks":[{"id","cmd"}]}`; `dod-run` выполняет чеки
  (destructive-команды отклоняются до запуска, таймаут 900 с ⇒ `exit_code 124`) и
  пишет `verify/<id>.json`.
- **Состояние выводится, не хранится** (`INTAKE → SPEC_DESIGN → APPROVED → VERIFY →
  DONE`). `DONE` требует по каждому чеку `exit_code == 0`, совпадения `spec_sha256`,
  `git_head == HEAD` и `tree_dirty == false`:

  $$\text{stale} \;=\; \bigl(\text{ev\_head} \neq \text{HEAD}\bigr) \;\lor\; \text{tree\_dirty}$$

- **Кто что может.** Агентам: `spec-new`, `spec-status`, `dod-run`, `docs-lint`,
  `spec-preflight`, `wave-run`. Только человеку: `spec-approve`, `spec-revoke`,
  `gate-off`/`gate-on` и `/spec-approve` в TUI.

---

## 3. Установка

**Требования:** Python ≥ 3.11 (CLI — только stdlib), Node ≥ 22 (нативное
исполнение TypeScript для тестов гейта).

```bash
bash install.sh --help                                  # справка
bash install.sh --target ~/.config/opencode             # drop-in; конфликты → *.bak
bash install.sh --target /some/dir --force              # перезапись без бэкапа
```

- Без `--target` скрипт **печатает план и завершается с ошибкой** — цель не угадывается.
- Идемпотентен: идентичные файлы не трогаются; конфликтующие бэкапятся в `<file>.bak`
  (или перезаписываются при `--force`).
- Копирует `config/**`, `README.md`, `VERSION`; создаёт **пустой**
  `<target>/.slim/spec/`. Контракты кита **не** переносятся: их мандаты не должны
  утекать в чужой проект.
- Смоук после установки: проверка наличия `config/`, `README.md`, `VERSION`,
  `.slim/spec/` и валидности JSON-снапшотов.

После установки — **рестарт OpenCode** (плагины и MCP читаются на старте процесса):

```bash
python3 -m pytest <target>/config/bin/tests -q
node --test <target>/config/plugins/__tests__/spec-gate.test.ts
python3 <target>/config/tools/gov/check_portability.py config
```

CI (`.github/workflows/ci.yml`) на push/PR гоняет то же на Python 3.12 + Node 22.

---

## 4. Чек-лист подстановок для принимающей машины

Снимок `config/` — не «настройка по умолчанию», а рабочая конфигурация конкретной
машины. Перед переносом замените (номера строк — на ревизии `f984997`, working tree):

| `файл:line` | Что заменить |
|---|---|
| `config/command/spec-approve.md:9` | Абсолютный путь в `!`-строке TUI-команды — на путь целевой машины. **Правит только человек**: файл лежит в `deny`-зоне `config/command/**`, агент писать в него не вправе (GOV-2). |
| `config/AGENTS.md:375,377` | Пути Python-окружения (`~/ml_base/.venv`, `uv pip …`) |
| `config/AGENTS.md:379,380` | Локальные проекты/conda (`~/Projects/…`, `~/.conda/envs/…`) |
| `config/AGENTS.md:197,251` | Таблица моделей/ролей (`opencode-go/*`) и их варианты |
| `config/opencode.json:5` | `permission.external_directory` (`*` deny, `~/Projects/**`, `/tmp/opencode/**`) — под вашу машину. Каталоги живой конфигурации OpenCode сюда добавлять **нельзя**. |
| `config/opencode.json:318` | MCP `serena` (`command`) — бинарь берётся из `$PATH` |
| `config/opencode.json:329` | MCP `jupyter` (`JUPYTER_URL`, `JUPYTER_TOKEN`) |
| `config/opencode.json:342` | MCP `hf` (`url`) |
| `config/opencode.json:347` | MCP `arxiv` (`uvx arxiv-mcp-server`) |
| `config/opencode.json:355` | MCP `memory` (`MEMORY_FILE_PATH`) |
| `config/opencode.json:45` | Провайдеры и ключи (`{env:…}`); рабочий по умолчанию — `OPENROUTER_API_KEY` |
| `config/oh-my-opencode-slim.json:28-294` | 20× `opencode-go/*` (модели пресетов, council, кастомных агентов), промпты, объектные `bash`-карты |
| `config/bin/spec-new:170` | Путь venv в генерируемом `README.md` (`~/ml_base/.venv`) |
| `docs/**` | **human-owned (GOV-2)**: агент не трогает; редактирует человек в редакторе |

Проверка (read-only): `python3 config/tools/gov/check_portability.py paths`.
На чистом снимке единственное нарушение — первая строка таблицы
(`config/command/spec-approve.md:9`), поэтому чекер даёт `rc=1`; после подстановки
пути человеком он даёт `rc=0` (остальные строки — `note:`-ориентиры, живой путь не
хардкодят).

---

## 5. Состояние и честность

**Проверено.**
- `python3 -m pytest config/bin/tests -q` — **149 passed** (последний прогон
  изоляции тестов; пути CLI резолвятся от `__file__`, не от живой машины).
- `node --test config/plugins/__tests__/spec-gate.test.ts` — **20/20**.
- `python3 config/tools/gov/check_portability.py config` — снапшот харденизирован:
  в `permission.external_directory` нет каталогов живой конфигурации OpenCode;
  `bash` всех агентов — объектные карты без human-only CLI.
- `python3 config/tools/gov/check_portability.py paths` — **rc=1 до подстановки**:
  ровно одно вхождение — `config/command/spec-approve.md:9` (human-owned, зона
  `deny`); после правки человеком — `rc=0`.
- `python3 config/bin/docs-lint --spec p0-portability-sprint` — без ERROR.

**Почему `verify/**` трекается.** `.gitignore` существует и намеренно **не**
игнорирует `verify/**`: это доказательство прогонов DoD (schema v2), а не мусор.
Feedback-правило источника: editing spec invalidates approval **и** evidence, поэтому
и то, и другое коммитится.

**Не решено (честно).**
- **F8 — политика `verify/**`.** Выбор tracked / untracked + `.gitignore` / внешнее
  артефакт-хранилище — отдельное продуктовое решение человека; контракт его не
  предрешает. Аудит 2026-10-02 рекомендует **tracked** (совпадает с `.gitignore`,
  ADR-0004 и этим README); расхождение в `research/SYNTHESIS.md §3a` подлежит
  синхронизации человеком.
- **P1.** HMAC-подпись одобрений, namespaced `verify/<slug>/<id>.json`,
  wave-дедуп, `oc-usage` — вне этого среза.
- **Аудит-журнал** не tamper-evident (нет `prev_hash`-цепочки). См. полный аудит
  (готовность/безопасность/надёжность/удобство, верифицирован `@oracle`):
  `.slim/spec/notes/full-audit-2026-10-02.md`.

---

## 6. Честные ограничения

- Гейт даёт **трение и аудит-след**, не безопасность: `bash` (в т.ч. `python -m *`),
  Code-Mode `execute` и shell-пути `spec-new`/`dod-run` находятся вне гейта,
  `docs/**` защищён только от файловых инструментов, а записи одобрений
  подделываемы по построению (проверяется лишь совпадение `sha256` байтов спеки).
  Для устойчивости к противнику нужна ОС-изоляция (`bwrap`, uid-split).
- **Тампер-эвиденс, не тампер-пруф.** Цепочка `prev_hash` в журнале аудита
  (`audit-chain-p0`) обнаруживает случайные повреждения, усечение и вырезание строк
  в середине, но **не** останавливает злонамеренную полную перезапись процессом с
  тем же UID: файл принадлежит тому же пользователю, что и агент. Сопротивление
  этому делегируется хосту/ОС и релизной практике — `chattr +a` (ставится только
  root/`CAP_LINUX_IMMUTABLE`, зависит от ФС и допускает подделку **добавлением**
  корректных строк), пересылка журнала в syslog/файл-тейлер, настроенная **вне**
  хука, и фиксация хэшей в Git-релизах. Внешний якорь в самом плагине сознательно
  **не** делается (автономность, офлайн, риск дедлоков).
- **Политика (d)-lite.** `verify/**` трекается как доказательство прогонов DoD
  (schema v2): «релиз — это релиз только после `git push`». Удалённый репозиторий —
  граница доверия; локальный `.git` перезаписываем тем же пользователем.
- `DONE` зарабатывается артефактами (`verify/<id>.json`), а не заявлением;
  состояние никогда не хранится файлом — только выводится.
- Снапшот `config/` — не «настройка по умолчанию»: это рабочая конфигурация
  конкретной машины, требующая ревизии перед переносом (§4).
