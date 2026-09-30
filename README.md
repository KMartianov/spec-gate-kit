# spec-gate-kit — переносимый комплект управления спецификациями для OpenCode

**Что это.** Самодостаточный набор механики «запрета кода без одобренной спецификации» для
агентных сессий OpenCode: плагин Zero-Code Gate, CLI жизненного цикла спек, человеческие
одобрения, DoD-доказательства, шаблоны и доктрина.

**Зачем.** Вся эта механика разрабатывалась «на месте», внутри `~/.config/opencode`, вперемешку
с машинно-зависимой конфигурацией (провайдеры, MCP, абсолютные пути). Из-за этого её нельзя было
ни перенести на другую машину, ни тестировать в изоляции, ни версионировать отдельно. Этот репозиторий
выделяет **переносимое ядро** в один каталог, который разворачивается поверх целевой конфигурации
как drop-in и развивается как обычный проект.

**Статус.** Снимок рабочей конфигурации на **2026-09-30** (копии `cp -a`, байт-в-байт).
Никаких новых файлов, кроме этого README, здесь намеренно не создано — структура и копии.

---

## 1. Состав (`config/` = drop-in-зеркало `~/.config/opencode/`)

| Путь | Что это |
|---|---|
| `config/plugins/spec-gate.ts` | Сам гейт (993 строки): перехват `tool.execute.before`, решение allow/block, аудит-JSONL |
| `config/plugins/__tests__/spec-gate.test.ts` | Тесты гейта (в т.ч. fail-closed-ветки разбора путей) |
| `config/bin/spec-approve` | Одобрение контракта человеком: флип статуса → штамп → запись с `sha256` содержимого |
| `config/bin/spec-revoke` | Отзыв одобрения (ревертит статус, удаляет записи только отозванных спек) |
| `config/bin/spec-status` | Производное состояние (`INTAKE → SPEC_DESIGN → APPROVED → VERIFY → DONE`), read-only, multi-spec, `--json` |
| `config/bin/spec-new` | Скаффолд проекта: спека из шаблона, Diátaxis-дерево, `docs/adr/`, `README`, `.gitignore`, `git init` |
| `config/bin/dod-run` | Исполнение `dod`-чеков → `verify/<id>.json` (evidence v2: `spec_sha256`, `git_head`, `tree_dirty`, `tail`) |
| `config/bin/docs-lint` | Линт контрактов: статус, ссылки на ADR/`docs/**`, валидность `scope`, коллизии `id` чеков |
| `config/bin/gate-off`, `config/bin/gate-on` | Локальный escape hatch (`<root>/.slim/GATE-OFF`) — только человеку |
| `config/bin/spec_scope.py` | Общий разбор `scope`-фенса и glob-матчинг (импортируется CLI) |
| `config/bin/tests/*.py` | Тесты `spec-approve`/`spec-revoke`/`docs-lint` (pytest) |
| `config/templates/{spec-template,adr-template}.md` | Шаблон контракта и шаблон ADR (Nygard) |
| `config/command/spec-approve.md` | Слэш-команда TUI `/spec-approve` (единственно легитимный путь одобрения из сессии) |
| `config/oh-my-opencode-slim/*_append.md` | Append-промпты 10 ролей (в т.ч. обязательная LaTeX-нотация формул) |
| `config/skills/{verification-planning,oh-my-opencode-slim}/SKILL.md` | Скилл планирования доказательств и скилл работы с самим плагином |
| `config/AGENTS.md` | Доктрина: гейт, классы файлов, состояние, троттлинг, каветы |
| `config/opencode.json` | Снапшот: `permission` (bash/external_directory), реестр плагинов, MCP |
| `config/oh-my-opencode-slim.json` | Снапшот: пресет, модели/варианты агентов, их `permission`-карты, council, фоновые задания |
| `config/cli.json`, `config/tui.json`, `config/dcp.jsonc` | Снапшоты CLI/TUI-настроек |

`docs/` — копии существующей доктрины и заметок разработки:

| Путь | Что это |
|---|---|
| `docs/SPEC-OpenCode-Hardening.md` | Спека харденинга самой конфигурации (аудит поверхности доверия) |
| `docs/guides/spec-driven-development.md` | Как вести разработку по спекам (человекочитаемое руководство) |
| `docs/guides/repo-audit-2026-09-29.md` | Аудит репозитория-примера по этой методологии |
| `docs/notes/2026-09-28-orchestrator-improvement-report.md` | Отчёт по улучшению оркестратора |
| `docs/notes/2026-09-28-spec-approve-hardening-plan.md` | План харденинга `spec-approve` |
| `docs/notes/dod-run-flat-store-collision.md` | Заметка о коллизиях в плоском сторе `verify/<id>.json` |
| `docs/adr/0001…0004` | ADR самой механики: гейт как soft guardrail; внешние записи одобрений; производное состояние; артефакты-доказательства |

`examples/` — пусто, место под примеры (минимальный контракт, индекс-`ROADMAP`, архивная спека,
образцы `verify/*.json`).

---

## 2. Как это работает (сжато)

- **Когда включается.** Гейт активен, если вверх по дереву от целевого пути есть `.slim/spec/`
  (остановка на `.git` или `$HOME`). Проект без `.slim/spec` гейт не трогает.
- **Порядок решения** (`tool.execute.before`, каждый шаг терминален): kill switch
  `OPENCODE_SPEC_GATE=off` → read-only allowlist (`read`, `grep`, `glob`, `task`, `question`, …)
  → извлечение целей (writer без разбираемых путей блокируется fail-closed) → exempt
  (`~/.config/opencode/**`, `~/.local/share/opencode/{approvals,audit}/**`, `/tmp/opencode/**`)
  → `.slim/spec/**` всегда доступно для записи → **`docs/**` всегда запрещено** → `.serena/**`
  → `.slim/GATE-OFF` → мандат: цель покрыта `allow`-паттерном и не покрыта `deny`-паттерном
  активного одобренного контракта, иначе `[SPEC-GATE BLOCKED]`.
- **`scope`-фенс — единственный мандат.** JSON `{"allow": [...], "deny": [...]}`; globs `*`, `?`,
  `[a-z]`, `**` как целый компонент. Пустой/битый фенс не даёт ничего (fail-closed).
- **Классы файлов в `.slim/spec/`.** Токен статуса `roadmap`/`index` ⇒ портфельный индекс (не
  контракт, мандата не даёт); иной токен ⇒ контракт; нет статус-строки ⇒ `undeclared`.
  `archive/**` — неактивная зона (retire без удаления), гейт/`spec-status`/`docs-lint` её игнорируют.
- **Одобрение — только человек.** `spec-approve` флипает статусную строку в `approved`, ставит штамп
  и хэширует **пост-флип** байты в `~/.local/share/opencode/approvals/<sha256(root)[:16]>/<slug>.json`.
  Любая правка спеки меняет хэш и **аннулирует** одобрение. Из сессии — только `/spec-approve`.
- **DoD.** Фенс `dod` с `{"checks":[{"id","cmd"}]}`; `dod-run` выполняет чеки (destructive-команды
  отклоняются до запуска, таймаут по умолчанию 900 с ⇒ `exit_code 124`) и пишет
  `verify/<id>.json` со `spec_sha256`, `git_head`, `tree_dirty`, `tail`, `duration_s`.
- **Состояние выводится, не хранится.** `INTAKE → SPEC_DESIGN → APPROVED → VERIFY → DONE`; `DONE`
  требует по каждому чеку одновременно: `exit_code == 0`, совпадение `spec_sha256`, `git_head == HEAD`,
  `tree_dirty == false`. Отсюда правило устаревания:

  $$\text{stale} \;=\; \bigl(\text{ev\_head} \neq \text{HEAD}\bigr) \;\lor\; \text{tree\_dirty}$$

- **Кто что может.** Агентам: `spec-new`, `spec-status`, `dod-run`, `docs-lint`. Только человеку:
  `spec-approve`, `spec-revoke`, `gate-off`/`gate-on` и `/spec-approve` в TUI.
- **Рабочий цикл.** `spec-new` → правка `draft`-спеки → человеческое `spec-approve` → реализация
  (агенты/лейны) → `dod-run` (под троттлингом) → `spec-status` → `DONE`; `verify/**` коммитится
  или нет — отдельное решение политики (см. §5 п.7).

---

## 3. Установка / восстановление

```bash
cd /home/asdcxfrt/Projects/spec-gate-kit
cp -a config/. ~/.config/opencode/     # drop-in поверх целевой конфигурации
# ОБЯЗАТЕЛЕН рестарт OpenCode: plugins/*.ts и MCP-серверы читаются на старте процесса
```

После рестарта проверить:

```bash
python3 -m pytest ~/.config/opencode/bin/tests -q          # тесты CLI (pytest)
# тесты плагина — раннером, настроенным в вашем окружении (файл plugins/__tests__/spec-gate.test.ts)
~/.config/opencode/bin/spec-status <любой-проект-с-.slim/spec>   # read-only; ничего не пишет
```

Смоук-проверка «в одну минуту» (временный каталог, ничего не коммитится):

```bash
T=$(mktemp -d); cd "$T"; mkdir -p .slim/spec; git init -q
~/.config/opencode/bin/spec-new demo --base "$(pwd)"   # или скопировать templates/spec-template.md
~/.config/opencode/bin/spec-status .                   # ожидаем SPEC_DESIGN (draft)
# любая запись вне .slim/spec/** должна получить [SPEC-GATE BLOCKED]
```

---

## 4. Что обязательно поправить при переносе (машинно-зависимое)

| Файл | Что заменить |
|---|---|
| `config/command/spec-approve.md` | Абсолютный путь в `!`-строке (`/home/asdcxfrt/.config/opencode/bin/spec-approve`) — на путь целевой машины |
| `config/AGENTS.md` | Пути `/home/asdcxfrt/...`, таблица моделей `opencode-go/*`, счётчики, ссылки на локальные проекты |
| `config/opencode.json` | `permission.external_directory` (`~/Projects/**`, `/home/asdcxfrt/ml_base/**`, `~/.conda/**`, `/tmp/**`, `~/.local/share/opencode/**`); MCP `jupyter` (`JUPYTER_URL`, `JUPYTER_TOKEN`), `serena` (`--project-from-cwd`), `memory` (`MEMORY_FILE_PATH`); провайдеры (рабочий ключ — только `OPENROUTER_API_KEY`) |
| `config/oh-my-opencode-slim.json` | Имена/варианты моделей, `permission`-карты агентов (объектные `bash`-карты + общий deny-слой), `backgroundJobs` |
| `config/plugins/spec-gate.ts` | Пути `~/.config/opencode`, `~/.local/share/opencode/{approvals,audit}`, `/tmp/opencode` |
| `config/bin/*` | Shebang `#!/usr/bin/env python3` предполагает Python ≥ 3.11 без внешних зависимостей |

---

## 5. Требуемые улучшения (приоритеты)

**P0 — границы доверия.**

1. **Гейт — soft guardrail, а не граница безопасности.** `bash` находится вне гейта (у shell нет
   file-targets, heredoc/`python -c` пишут в обход), а агент имеет запись к артефактам, которые его
   же ограничивают: конфиг, исходник плагина, `approvals/`, `audit/`, таблица `permission` в
   `opencode.db` (сохранённые «always allow» перекрывают будущие config-`deny`). Минимум: убрать
   `~/.config/opencode/**` и `~/.local/share/opencode/**` из `external_directory`; не выдавать
   агентам `edit: {"*": "allow"}`; **никогда** не писать `bash: "allow"` строкой (строковая форма
   разворачивается в `{"*":"allow"}` и обнуляет глобальные `deny`) — только объектные карты;
   для устойчивости к противнику (prompt-injection) — ОС-изоляция (`bwrap`, uid-split), а не соглашение.
2. **Одобрения подделываемы по построению.** Проверяется лишь совпадение `sha256` байтов спеки;
   `approved_by: "human"` — непроверяемая строка, имя файла записи не значимо. Варианты: подпись
   (GPG/HMAC ключом вне досягаемости агента) либо перенос записи одобрения в процесс с UID-разделением.
3. **`docs/**` защищён только от файловых инструментов.** Задокументировать residual и, если
   неизменяемость действительно важна, закрывать на уровне ОС (ro-mount) — плагин этого не обеспечит.

**P1 — стоимость и качество.**

4. **Глобальная staleness.** Любой коммит делает недействительными **все** evidence ⇒ полная волна
   (~14 мин на 16 контрактов, замер 2026-09-30). Предложение: поверхностная staleness — evidence
   недействительно, только если изменились файлы из `scope.allow` контракта; плюс `dod-run --changed`.
   Полная волна — для финальной сертификации.
5. **Дублирование в DoD (главный пожиратель времени).** Замер: 155 чеков на волну, из них идентичные
   команды повторяются — полный `pytest tests --ignore=tests/e2e` **14×**, `ruff check src/ tests/`
   **15×**, `pytest tests/e2e -m contract` **4–6×**, `ctest` **3–5×** ⇒ ≈75–80 % времени волны —
   повтор. Предложения: (а) ограниченный параллелизм волны (2–3 контракта, лок на порты для
   e2e/ctest-стендов, разведение по ядрам) ≈2× без роста пиковой нагрузки; (б) сузить команды —
   «весь сьют» и «весь ctest-стенд» за одним владельцем, остальные контракты проверяют свою
   поверхность (нужен батч правок `dod`-фенсов + одно человеческое одобрение) ⇒ ~4–5 мин и более
   точный сигнал; (в) `--fail-fast`, разовый `compileall`, опционально `pytest-xdist -n 2`.
6. **Плоский стор `verify/<id>.json`.** Коллизия `id` между контрактами молча перезаписывает файл и
   лишает один из контрактов шанса на `DONE` (`docs-lint` это ловит — проверку сохранить).
   Рассмотреть пространство имён `<slug>/<id>`.
7. **Политика `verify/**` не решена.** Три варианта: untracked + `.gitignore` (воспроизводимо),
   tracked + перепрогон волны после каждого коммита (дорого из-за п.4), либо evidence в
   артефакт-хранилище, а в репозитории — лог волны. Выбор влияет на всё остальное.
8. **Аудит-журнал не tamper-evident.** Добавить цепочку хэшей (`prev_hash`) и/или вынос в append-only
   хранилище.

**P2 — инженерия самого кита.**

9. Нет версионирования и упаковки: `VERSION`, CHANGELOG, `install.sh` (проверка Python, бэкап
   существующего конфига, drop-in, смоук-тест, `--target DIR`).
10. Нет CI для кита: `bin/tests/*.py`, `plugins/__tests__/spec-gate.test.ts` и смоук-прогон
    `INTAKE → DONE` в временном каталоге.
11. Нет `.gitignore` (намеренно не создавался): нужны `__pycache__/`, `*.py[cod]`, `.venv/`, `verify/`.
12. `examples/` пуст: положить минимальный контракт с `scope`+`dod`, индекс-`ROADMAP.md`, архивную
    спеку и образец `verify/*.json`.
13. Синхронизация снапшота: `config/` — точка во времени; при изменениях рабочей конфигурации её
    нужно пересинхронизировать (пока вручную) либо заменить снапшоты на генератор с шаблонами путей.

---

## 6. Честные ограничения

- Гейт даёт **трение и аудит-след**, не безопасность (см. P0). Его собственная документация это
  признаёт: «soft guardrail with real value, not a security boundary».
- `DONE` зарабатывается артефактами (`verify/<id>.json`), а не заявлением; состояние никогда не
  хранится файлом — только выводится.
- Снапшот `config/` не является «настройкой по умолчанию»: это рабочая конфигурация конкретной
  машины, требующая ревизии перед переносом (§4).
