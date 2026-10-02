# Полный аудит `spec-gate-kit`: готовность, безопасность, надёжность, удобство

- **Дата:** 2026-10-02 (ред. 2 — учтены правки независимой верификации `@oracle`)
- **Ревизия:** `HEAD = f9849977557eb851571c2bee513c1b915d1b5c4a`; рабочее дерево **dirty** (поверх `f984997` наложен незакоммиченный P0-спринт `p0-portability-sprint`).
- **Метод:** кросс-проверка — три параллельных `@explorer` (исполняемое ядро; контракты+evidence; доктрина+research), независимые исполняемые прогоны оркестратора под троттлингом, затем состязательная верификация `@oracle` (read-only, полное переподтверждение базы доказательств — §8).
- **Область:** портируемое ядро Zero-Code Gate (`config/**`), контракты `.slim/spec/**`, `verify/**`, `docs/**`, `research/**`, упаковка.
- **Предыдущий отчёт:** `.slim/spec/notes/readiness-audit-2026-10-02.md` (ревизия `f984997`, до P0-спринта). Данный аудит проверяет **текущее** (post-sprint, uncommitted) состояние.

---

## 0. Вердикт (кратко)

> **Ядро корректно и стало проверяемым на чистой машине, но deliverable не выпущен; один контракт отстаёт от собственного README/CI и требует человеческого действия.**
> **Готовность: ready-with-conditions** — после (1) коммита P0-поверхности, (2) человеческого разрешения коллизии `paths` в `p0-portability-sprint` (одна правка `config/command/spec-approve.md:9` **или** амендмент спеки — см. B1), (3) решения политики `verify/**` (M8).
> **Безопасность: soft guardrail, не граница** — `bash` и Code-Mode `execute` вне гейта, evidence/approvals неподписываемы. Для устойчивости к противнику нужна ОС-изоляция.
> **Надёжность: высокая у ядра, средняя у релизного процесса** (evidence не подписано, аудит-журнал не tamper-evident, дублирование резолверов).
> **Удобство: хорошее** (выводимое состояние, `--json`, `preflight`, `wave-run --dry-run`, внятные причины блокировки), с трениями в мультиписательстве и двусмысленном `dirty=True`.

Все четыре измерения независимо подтверждены `@oracle` (§8).

---

## 1. База доказательств (что реально прогнано)

Все команды — под троттлингом (`OMP_NUM_THREADS=1 …`, `nice -n 19 taskset -c 0,1 ionice -c3`), по одной тяжёлой за раз. Python 3.14.7, Node v26.10.0. **Вся база воспроизведена независимо `@oracle` с теми же результатами.**

| # | Проверка | Команда | Результат |
|---|---|---|---|
| 1 | Python-сьют кита | `python3 -m pytest config/bin/tests -q` | **149 passed** (15.93 с) |
| 2 | TS-харнесс гейта (изолированный `HOME`/`XDG_DATA_HOME`) | `HOME=<tmp> node --test config/plugins/__tests__/spec-gate.test.ts` | **20/20 pass** (601 мс); хранилище одобрений не тронуто |
| 3 | Линт контракта спринта | `python3 config/bin/docs-lint --spec p0-portability-sprint` | **rc=0** |
| 4 | Линт доктрины кита | `python3 config/bin/docs-lint .` | **rc=1**: 4 ERROR — нет `docs/tutorials|how-to|reference|explanation` |
| 5 | Pre-approval консенсус | `python3 config/bin/spec-preflight .` | **9 WARN** мультиписательства (см. M2) |
| 6 | Портируемость — снапшот | `check_portability.py config` | **clean**, rc=0 |
| 7 | Портируемость — установка | `check_portability.py install` | **clean**, rc=0 |
| 8 | Портируемость — пути | `check_portability.py paths` | **rc=1**: ровно 1 нарушение `config/command/spec-approve.md:9` (+34 информационных note) |
| 9 | Хардкод живых путей под `config/**` | `grep -rn /home/asdcxfrt config/ …` | единственное вхождение — `config/command/spec-approve.md:9` |
| 10 | Аудит-журнал | `wc -l` + `grep -c prev_hash` `~/.local/share/opencode/audit/spec-gate.jsonl` | **2470 строк / 792 КБ**, `prev_hash` — **0** вхождений |
| 11 | Хранилище одобрений | `find ~/.local/share/opencode/approvals` | запись кита: `bef96c3328c64cc1/` (4 шт., включая архивный `preflight-0`) |
| 12 | Производное состояние | `python3 config/bin/spec-status .` | 2×`DONE`, 1×`APPROVED`, 1×`SPEC_DESIGN`; `head=f984997`, `dirty=True` |

---

## 2. Инвентарь и архитектура (сжато)

- **Гейт**: `config/plugins/spec-gate.ts` (997 L) — `tool.execute.before`, порядок решений: kill switch → read-only allowlist (22 тула) → извлечение целей (writer без разбираемых путей — fail-closed) → exempt (`~/.config/opencode/**`, approvals, audit, `/tmp/opencode/**`) → `.slim/spec/**` writable → **`docs/**` refuse безусловно** (включая serena-писателей) → `.serena/**` → `.slim/GATE-OFF` → мандат (`allow`/`deny` активных одобренных контрактов, `deny` побеждает) → иначе `[SPEC-GATE BLOCKED]`. Аудит — JSONL, fail-open.
- **CLI (11)**: `docs-lint`, `dod-run`, `gate-off`, `gate-on`, `spec-approve`, `spec-new`, `spec-preflight`, `spec-revoke`, `spec-status`, `wave-run` + библиотека `spec_scope.py` (865 L). Общий примитив `atomic_write` централизован; прочие резолверы дублируются (см. m6).
- **Контракты (`.slim/spec/*.md`, non-recursive)**: `p0-portability-sprint` (approved), `evidence-atomic-p0` (approved/DONE), `gate-parity-p0` (approved/DONE), `audit-chain-p0` (**draft**, не одобрен); архив `preflight-0` (inactive). Два `notes/*.md` — `undeclared` (не контракты).
- **Evidence** `verify/**`: 10 файлов, **все schema v2** (`git_head`, `tree_dirty`, `scope_sha256`). У двух `DONE`-контрактов хэши и `git_head` актуальны; `p0-portability-sprint` evidence не имеет.
- **Состояние выводится, не хранится**: `INTAKE → SPEC_DESIGN → APPROVED → VERIFY → DONE`, где

  $$\text{passing} = (\text{spec\_sha256}_{\text{ev}} = \text{spec\_sha256}_{\text{now}}) \;\land\; (\text{exit}=0) \;\land\; \lnot\,\text{stale},\qquad \text{stale} = (\text{ev\_head} \neq \text{HEAD}) \lor \text{evidence.tree\_dirty}$$

  (`config/bin/spec-status:206-224`). Пере-исполнения нет; `DONE` выводится только из записанных полей.

---

## 3. Оценка по измерениям

| Измерение | Оценка | Обоснование |
|---|---|---|
| **Готовность** | 🟡 ready-with-conditions | Ядро и упаковка работают и воспроизводимы, но релиз не закоммичен (B2) и контракт спринта отстаёт от README/CI в вопросе `paths` (B1). |
| **Безопасность** | 🟡 основное честно | `docs/**` закрыт безусловно, kill-switch, fail-closed пути, снапшот харденизирован (`check_portability config` clean). Но `bash` вне гейта, `execute` (Code Mode) не моделируется и **не назван** в honest-limitations (M5), evidence/approvals неподписываемы (M4), аудит не tamper-evident (M3). |
| **Надёжность** | 🟢/🟡 | 🟢: паритет TS↔Python на векторах, атомарная запись evidence + foreign-guard (exit 3), `DONE`-инвариант, `spec-revoke` bare-token fix, 149+20 зелёных изолированных тестов. 🟡: неподписанный evidence, журнал без цепи, дублирование резолверов. |
| **Удобство** | 🟢/🟡 | 🟢: производное состояние read-only + `--json`, `preflight`, `wave-run --dry-run`, точные причины блокировки, human-only approval. 🟡: 9 WARN мультиписательства, `dirty=True` без пометки об исключениях, `docs-lint` отвергает собственную `docs/`, двусмысленный маркер `SYNCED`. |
| **Документация** | 🟡 | README-ложь из прошлого аудита (F3) исправлена, но инвентарь контрактов неполон (m1), ADR-0001/0004 и `S4` устарели, `SYNTHESIS §3a` конфликтует с кодом. |

---

## 4. Реестр находок (severity-ranked, текущее дерево)

Severity уточнена после верификации `@oracle` (см. §8).

### BLOCKER

| id | Находка | Доказательство |
|---|---|---|
| **B2** | **Релиз «0.1.0» не закоммичен.** `VERSION`, `CHANGELOG.md`, `install.sh`, `.github/workflows/ci.yml`, `examples/`, `config/tools/gov/check_portability.py`, `.slim/spec/p0-portability-sprint.md`, `audit-chain-p0.md` — **untracked**. README/спека заявляют `SYNCED: f984997`, но этих артефактов в `f984997` нет; тега/коммита нет. На **чистом checkout CI отсутствует вовсе** (workflow untracked), а не «красен»; красен он лишь при частичном коммите (шаг `ci.yml:34` линтит незакоммиченную спеку). Следствие для жизненного цикла: `tree_dirty` исключает только `.slim/spec/**` и `verify/**`, поэтому незакоммиченные `README.md`/`config/**` дают `tree_dirty=true` ⇒ `p0` не достигнет `DONE`, пока поверхность не закоммичена. | `git status --porcelain` (untracked-список); `install.sh:118-124`; `ci.yml:33-45`; `spec-status` — `dirty=True`. |

### MAJOR

| id | Находка | Доказательство |
|---|---|---|
| **B1** | **`p0-portability-sprint` отстаёт от README/CI и блокирует свой `DONE` (agent-unreachable, но человеческий путь пред-авторизован).** §1.2 D1 и §5 требуют «ни один файл под `config/**` не содержит `/home/asdcxfrt`», а DoD-чек `p0-portability-sprint-paths` = `check_portability.py paths` → **rc=1**. Единственное нарушение — `config/command/spec-approve.md:9`, но **та же `scope` содержит `deny:["config/command/**"]`** ⇒ агент не вправе его исправить. README §3/§4, CHANGELOG и `ci.yml:39-45` уже трактуют это вхождение как единственное human-owned исключение, требующее подстановки под машину. **Самый дешёвый выход — человек правит одну строку `config/command/spec-approve.md:9`** (это **не** правка спеки ⇒ approval сохраняется; `paths` зеленеет, D1 истинно). Альтернатива — амендмент спеки (carve-out + правка DoD-чека), что **аннулирует approval** и требует повторного одобрения. | `p0-portability-sprint.md:28,77,147,155,164`; `:130`; `config/command/spec-approve.md:9`; прогон #8 rc=1; README §4. |
| **M3** | **Аудит-журнал не tamper-evident.** 2470 строк, **0** `prev_hash`; любая строка подменяема без следа. `audit-chain-p0` (draft) должен это закрыть, но не одобрен, а его цели (`config/bin/audit-verify`, `audit_vectors.json`) не существуют. | прогон #10; `spec-gate.ts:792-799`; `audit-chain-p0.md:196-207,230-238`. |
| **M4** | **Evidence не подписано.** `DONE` выводится из 4 записанных полей; рукописный `verify/<id>.json` с `spec_sha256`=актуальный, `exit_code=0`, `git_head=HEAD`, `tree_dirty=false` даёт `DONE` без прогона. `spec_sha256` привязывает **спеку**, не evidence. Подтверждено по коду; эксплойт сознательно не выполнялся. | `spec-status:206-224,171-213`. Признано; P1 HMAC. |
| **M5** | **Вне-гейтовые каналы записи.** `bash` — вне гейта (документировано). Code-Mode `execute` **не** входит в `READ_ONLY_TOOLS`, не матчится `WRITER_NAME_RE`, не несёт path-ключей и проходит как «не-писатель» без аудита; если он способен дёргать writer-тулы — это необозначенный обход мандата. Усиление от `@oracle`: shipped `config/AGENTS.md:185` honest-limitations называет `bash` и shell-пути, но **не называет `execute`** — пробел не задокументирован даже в честном разделе. | `spec-gate.ts:63-86,103,618-661,813-816`; `AGENTS.md:185`. |
| **M8** | **Политика `verify/**` рассогласована (F8).** `research/SYNTHESIS.md §3a` = *untracked + wave-log*; фактические `.gitignore` (запрещает игнор), `README.md:184-187`, `CHANGELOG.md:42`, `docs/adr/0004:84` = *tracked-proof*. Де-факто дерево трекает 10 файлов. Продуктовое решение человека. | `SYNTHESIS.md:31,65`; `README.md:31,184-187`. |

### MINOR / NIT

| id | Находка | Доказательство |
|---|---|---|
| **M1** | 5 `verify/*.json` изменены относительно HEAD: у закоммиченных копий `git_head=ddf3fa0d`, в рабочем дереве — `f984997`; также изменились timestamps, `duration_s`, `tail` (**не только `git_head`**). Свежий passing-набор — именно **рабочие** копии (`stale=no`), закоммиченные блобы устарели. Обычный незакоммиченный результат перепрогона, не подделка. | `git diff -- verify/`; `spec-status`. |
| **M2** | Мультиписательство (гигиена single-writer, GOV-6). `p0`-мандат `allow:["config/**"]` объединяется поверх `gate-parity-p0` и `evidence-atomic-p0` (оба `DONE`, но всё ещё active); `spec-preflight` даёт **9 WARN**. Уточнение `@oracle`: 2 из 9 WARN — про `spec-gate.ts` и его тест в связке с `audit-chain-p0`, который **не одобрен** (мандата нет); живое перекрытие — 3 одобренных контракта. Влияния на принуждение нет (`allow`-пересечение не блокирует, `deny` побеждает). Архив завершённых — действие человека. | `spec-preflight .` (#5); `p0-portability-sprint.md:46`. |
| **M6** | ADR устарели (human-owned, GOV-2, нулевого runtime-эффекта). ADR-0001 (`:48-50`) описывает схему аудита без `reason`/`spec` (код пишет 8 полей, `spec-gate.ts:777-786`); ADR-0004 (`:43,57-59`) — **evidence v1** без `git_head`/`tree_dirty`/`scope_sha256` и без staleness-конъюнкта. | `0001`, `0004` vs `spec-gate.ts:34,777-786`; `spec-status:206-224`. |
| **M7** | `docs-lint .` отвергает собственную `docs/` кита: rc=1, ровно 4 `diataxis-dirs` ERROR (`docs/tutorials|how-to|reference|explanation` отсутствуют). Контрактный линт (`--spec p0`) при этом rc=0. README подаёт `docs/` как доктрину, не отмечая этого. | прогон #4. |
| **M9** | Граница `findRoot` TS↔Python расходится (F9). TS (`:194-206`): cap `depth<32` + защита `p!==HOME` (проект с корнем ровно `$HOME` не гейтится). Python (`spec_scope.py:96-112`): cap отсутствует, SPEC-проверка до HOME-стопа (`$HOME`-корень гейтится). Оба триггера патологичны. | `spec-gate.ts:194-206` vs `spec_scope.py:96-112`. |
| **m1** | README §1 перечисляет 2 активных контракта из 4 (пропущены `evidence-atomic-p0`, `gate-parity-p0`). | `README.md:30`; `spec-status`. |
| **m2** | README §4: диапазон `config/oh-my-opencode-slim.json:28-296` выходит за EOF (файл 294 строки). | `README.md:160`. |
| **m3** | `SYNCED: f984997 (working tree)` двусмыслен: документирует артефакты, которых в `f984997` нет. | `README.md:3,145`. |
| **m4** | `research/S4-tooling.md` устарел («git log пуст — нет baseline» при 5 коммитах; 993/242 L vs 997/396; ярлык «STALE/lying» протух); `M1`/`S*` ссылаются на отсутствующие `docs/explanation/isolation-model.md`, `adr/0005/0018`, `src/oclab/*`. | `S4-tooling.md:5,11,12`. |
| **m5** | `CHANGELOG.md:36,39` заявляет удаление `.pytest_cache/`; каталог gitignored, но **пересоздаётся** любым прогоном pytest (артефакт, не нарушение). | прогон #1; `.gitignore:4`. |
| **m6** | Дублирование резолверов (F16): `find_root` ×6 (+ TS `findRoot` = 7), `resolve_target`-семейство ×8, `resolve_spec` ×3, `spec_rel` ×3, `die` ×10, парсеры `dod` — 4 формы. `spec_scope.py` — лишь частичный SSOT. | exp-1 §2. |
| **m7** | Полумёртвый код (F17): `hasValidApproval`, `pickPath` — неиспользуемы в проде, но экспортируются через `__test`; `after`-хук — пустое тело, но **зарегистрирован**; абсолютный `APPROVER` в тексте блокировки. | `spec-gate.ts:553-555,572-574,885-887,930,53,750`. |
| **m8** | Evidence вшивает абсолютный `spec`-путь (F18). Механизм (уточнён `@oracle`): перенос репозитория **не** делает evidence stale (staleness = `ev_head≠HEAD ∨ dirty`, путь не входит); ломается **привязка approval** (`find_valid_approval` сравнивает резолвнутые абсолютные пути ⇒ SPEC_DESIGN). | `verify/gate-parity-p0-ts.json:8`; `spec_scope.py:621-634`. |
| **m9** | `spec-status` печатает `dirty=True` без пометки «(excl. `.slim/spec`, `verify`)»; `scope_sha256` пишется, но в вердикте не потребляется (зарезервировано). | `spec-status:206-212,360`. |
| **N1** | (новая, `@oracle`) Процедура валидации примера в §5.7 неверна: `docs-lint examples/minimal/spec/example-task.md` резолвит корень к киту и печатает 4 diataxis ERROR кита (rc=1, об примере ни строки); `spec-status examples/minimal` — то же. У `examples/minimal/` **нет** `.slim/spec`, поэтому пример не может дать `SPEC_DESIGN` на месте — это copy-me шаблон. Содержимое (валидные фенсы) проверено прямым разбором. | exp-3 §5; `examples/minimal/README.md:36-43`. |
| **N2** | (новая, `@oracle`) Shipped `config/AGENTS.md:185` в honest-limitations называет `bash`/shell-пути, но не называет Code-Mode `execute` (см. M5). | `AGENTS.md:185`. |

---

## 5. Подтверждено как корректное (не трогать)

1. **Паритет TS↔Python** по `scope`/glob (`globSource`/`glob_regex` ↔ `glob_match`), включая «`deny` побеждает при объединении»; гоняется на `config/tools/gov/scope_vectors.json` в обоих рантаймах (внутри 20/20).
2. **Порядок решений гейта** совпадает с доктриной; **`docs/**` закрыт безусловно**, включая serena-писателей.
3. **Evidence v2 честен:** `dod-run` = atomic + readback + fail-loud на чужой `spec_sha256` (exit 3, файл не тронут); `spec-status` считает `DONE` ровно по инварианту §2.
4. **`spec-revoke` bare-token fix** на месте: отзывается и `` `approved` ``, и `approved` без обёртки.
5. **Харденинг снапшота (F2)** подтверждён: `opencode.json` `permission.external_directory = {"*":"deny","~/Projects/**","/tmp/opencode/**"}` без каталогов живой конфигурации; у всех агентов `bash` — объектные карты без human-only CLI.
6. **Изоляция тестов (F1) исправлена:** все pytest-файлы резолвят CLI от `__file__`; `/home/asdcxfrt` под `config/bin/tests/**` и `config/plugins/__tests__/**` отсутствует. TS-харнесс берёт пути от `import.meta.url`; изоляция хранилища подтверждена (тест 20 — реальные approvals не тронуты).
7. **`install.sh`** идемпотентен (двойной прогон `--target` — всё `unchanged`, `smoke: OK`, `.slim/spec/` пуст); **`examples/minimal`** содержит валидные фенсы `scope`/`dod` со slug-префиксными id (проверено разбором).
8. **Шаблон (F12)** исправлен: `scope.allow` = `tools/<task_slug>/**`, `dod.id` — со slug-префиксом.

---

## 6. Решения, требующие человека (R6-класс)

1. **B1 — разрешить коллизию `paths`.** Дешёвый путь: человек правит одну строку `config/command/spec-approve.md:9` под целевую машину (approval **сохраняется**, спека не меняется). Альтернатива: амендмент `p0-portability-sprint` (вынести файл как human-owned исключение; DoD-чек `paths` заменить) — **аннулирует approval**, нужно повторное одобрение.
2. **B2 — закоммитить P0-поверхность** (включая `p0-portability-sprint.md`, чтобы шаг `ci.yml:34` был осмыслен), затем `dod-run` из чистого дерева.
3. **M8 (F8) — политика `verify/**`:** tracked-proof (рекомендация: совпадает с кодом/`.gitignore`/README) или untracked+wave-log (как в `SYNTHESIS §3a`)? Выбор меняет README/SYNTHESIS.
4. **M2 — архивировать `gate-parity-p0`/`evidence-atomic-p0`** после `DONE` (GOV-6), чтобы `p0` стал единственным писателем.
5. **M6/M7 — синхронизация `docs/`** (ADR-0001/0004, Diátaxis-квадранты) — только человек в редакторе (GOV-2).
6. **M3/M4 — приоритет `audit-chain-p0`** (одобрить после правок F6/F7/F15) против P1-HMAC: что раньше закрывает доверие.

---

## 7. Честные ограничения этого аудита

- Всё read-only; тяжёлых стендов не запускалось (политика ноутбука). Оценки измерений — качественные, не метрики.
- Проверялось **отгружаемое** `config/**` и текущее рабочее дерево; живая `~/.config/opencode` не сверялась побайтово.
- F5/M5 подтверждён по чтению `spec-gate.ts`, а не по эксплуатации Code-Mode-рантайма; фактическая способность `execute` вызывать writer-тулы не проверена эмпирически.
- Не найденные дефекты ≠ отсутствующие: покрытие тестами неполно (например, TS-регистрация v2-хуков замокана, тест 14).

---

## 8. Независимая верификация (`@oracle`, read-only)

`@oracle` перепрогнал **всю** базу доказательств (§1) с теми же результатами и перечитал все цитируемые `file:line`; выполнил состязательные попытки фальсификации.

- **Переподтверждено:** pytest 149; node 20/20 при изолированном `HOME`; `docs-lint --spec p0` rc=0; `docs-lint .` rc=1 (4 ERROR); preflight 9 WARN; `paths` rc=1 (1 hit + 34 notes); `config`/`install` clean; журнал 2471 строк/0 `prev_hash`; `spec-status` = 2×DONE/1×APPROVED/1×SPEC_DESIGN, `dirty=True`. Плюс дополнительно подтверждена идемпотентность `install.sh` (двойной прогон).
- **Исправления, внесённые в ред. 2 (адресованы):** B1 понижен до MAJOR и переформулирован как «agent-unreachable, human path pre-authorized»; B2 остался BLOCKER, но уточнён механизм CI (на чистом checkout CI отсутствует, а не красен); M1/M2/M6/M7/M9 понижены до MINOR; у M1 исправлено «остальные поля не менялись» (timestamps/`duration_s`/`tail` менялись); m8 исправлен механизм (ломается approval-привязка, не evidence-staleness); §5.7 исправлен (команды валидации примера на месте не работают — вынесено в N1); добавлены N1/N2; M5 усилен ссылкой на `AGENTS.md:185`; §5.7 переведён в §5 п.8 на основании прямого разбора.
- **Согласие по измерениям:** все четыре вердикта (готовность/безопасность/надёжность/удобство) — `AGREE`.
- **Вердикт о пригодности отчёта:** «YES, conditionally» — отчёт точен по всем несущим фактам и не является rubber-stamp; условия канонизации (перечисленные правки) выполнены в этой редакции.
- **Общая остаточная неопределённость** (совпадает с §7): эксплуатируемость Code-Mode не тестировалась; TS-тест 14 (мок регистрации v2-хуков) принят на доверии; живая `~/.config/opencode` не диффилась. Ни один пункт не является несущим.
