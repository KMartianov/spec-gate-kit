# Consistency review of all plans — ora-8 (oracle, read-only)

Date: 2026-10-01. Session: ses_f0c0b0c84fferfgkjj2WfGY0Fw.
Scope reviewed: `research/**` (README, S1–S6, M1–M4, SYNTHESIS, OCLAB-REQUEST),
`.slim/spec/preflight-0.md`, `docs/` (SPEC-OpenCode-Hardening §11–13, ADR-0001,
ADR-0003, ADR-0004, guide), and the live `config/` tools.
Note: this is a review, not a contract. It lives under `.slim/spec/notes/` only
because the gate is active and no other location is writable yet.

## Verdict

**Согласовано с оговорками** — есть 4 HIGH-противоречия/блокера (ожидания по B,
политика `verify/`, правило `id` с точкой, нулевая базовая линия git), остальное
MED/LOW.

## Contradictions

| ID | sev | where (file:line) | essence | minimal fix |
|---|---|---|---|---|
| C1 | HIGH | `.slim/spec/preflight-0.md:80` vs `research/M4-review.md:47-55`, `research/SYNTHESIS.md:165-172`, `research/S4-tooling.md:61` | **B закрыт наполовину, но подаётся как «B+H5».** B в M2/M4/SYNTHESIS = фактическое ИСПОЛНЕНИЕ дедупа: stateless `wave-run` (объединение `dod`, один прогон на волну, $H=1$). W2 лишь СООБЩАЕТ о дублях (WARNING + `suggested_owner`); ни `wave-run`, ни `dod-run --changed`, ни переназначение владельца suite не исполняются. H5 (pre-lint) — да; B — только его половина-наблюдаемость | Сказать человеку: апрув preflight-0 = H5 + «видимость B», а не B. Исполнение дедупа = отдельный контракт (`wave-run`, эффект S/M). Не расширять текущий scope (другие файлы/риски/evidence) |
| C2 | HIGH | `.slim/spec/preflight-0.md:28,146` (`verify/` в `.gitignore`) + `research/SYNTHESIS.md:31` (UNTRACKED + `.gitignore`) vs `config/AGENTS.md:159-163` («which **is committed**: it is proof, not junk»), `docs/guides/spec-driven-development.md:640-646`, `docs/adr/0004-dod-evidence-artifacts.md:84-85` | **Раскол политики `verify/`; preflight-0 молча выбирает сторону.** SYNTHESIS §3a выбрал UNTRACKED + wave-log (которого нет); живая доктрина (AGENTS/guide/ADR-0004) требует коммитить `verify/`. Игнор `verify/` ⇒ доказательства теряются из git; tracked ⇒ каждая волна инвалидируется глобальным stale. §4 спеки читается двояко | Решить ДО апрува (правки scope/`.gitignore` после апрува инвалидируют апрув+evidence): либо (a) принять SYNTHESIS §3a и тогда обновить AGENTS/guide/ADR-0004 + заспечить wave-log, либо (b) убрать `verify/` из `.gitignore` в scope preflight-0 и остаться tracked |
| C3 | HIGH | `.slim/spec/preflight-0.md:74` (id содержащий `/`, `\`, `.`, `..`) vs `config/bin/dod-run:248` (`if "/" in check_id or "\\" in check_id or check_id in (".", "..")`) | **E3 строже механики и буквально неисполним.** `dod-run` запрещает только `/`, `\`, ровно `.`/`..`; точка ВНУТРИ id (`a.b`) легальна. Чтение «содержит `.`» даст ERROR на легальных id | Переписать E3 дословно по `dod-run:248`: запрещены `/`, `\`, ровно `.`/`..`, пустой; всё прочее (вкл. внутреннюю `.`) разрешено. Покрыть парой тестов `a.b`-ok / `.`-fail |
| C4 | HIGH | `git status` (весь репозиторий untracked, `HEAD` отсутствует — `fatal: Needed a single revision`) vs `.slim/spec/preflight-0.md:133,147,153-154`, `config/bin/spec_scope.py:500-501,208` (`tree_dirty` = False когда нет `HEAD`; `read_evidence` → `stale=True` когда `head is None`), `config/AGENTS.md:147-154` | **Нет базовой линии ⇒ `DONE` сейчас недостижим ни для preflight-0, ни для чего угодно.** `spec-status` всегда покажет stale без первого коммита; DoD-чек `preflight-0-spec-status` не сможет стать `DONE` на «чистом дереве», потому что чистого дерева с `HEAD` не существует. Порядок спеки «commit → approve → implement → dod-run» предполагает существующий коммит | Человек: `git add` + первый базовый коммит ДО `dod-run` (решить, что входит: весь `config/`, `docs/`, `research/`, черновик `.slim/spec/preflight-0.md`). Только затем approve → implement → коммит кода → `dod-run`. Без этого вся цепочка §6 заблокирована |
| C5 | MED | `.slim/spec/preflight-0.md:42,70-72` (отсутствие `scope` → ERROR `preflight-scope`, «ERROR = DONE-impossibility») vs `config/bin/docs-lint:369-379` (нет фенса → WARNING), `docs/guides/spec-driven-development.md:700-702`, `config/AGENTS.md:164-166`, `docs/guides/spec-driven-development.md:588-591` (без `scope` → апрув с предупреждением, мандата нет) | **Неверная классификация.** Отсутствие `scope` блокирует *запись* (fail-closed мандат), а не DONE: контракт без `scope` может получить апрув + зелёный `dod` + `DONE`. Ранг ERROR в отчёте preflight вводит в заблуждение и расходится с WARNING-нормой линта | Переименовать: отсутствующий/пустой `scope` → WARNING `preflight-scope` (write-impossibility, не DONE-impossibility). ERROR оставить только для сломанной ФОРМЫ (невалидный JSON/типы/unsafe — тоже нет мандата, но это дефект формы, который ловит `docs-lint` как ERROR). Поправить интро §3.2: ERROR = «DONE-impossibility», WARNING = «write-impossibility/waste» |
| C6 | MED | `research/OCLAB-REQUEST.md:52` (R1: `root_override` + `root_hash_override`, acceptance через `== /h/P/x` ИЛИ `sha256(real_root)==record.root_hash`) vs `docs/adr/0003-derived-lifecycle-state.md:23-43`, `research/M1-model-design.md:33` | **R1 вводит вторую истину о корне — анти-паттерн, о котором предупреждают M4/SYNTHESIS.** Две дизъюнкции acceptance = два источника истины; `approvalDir=rootHash` (`config/plugins/spec-gate.ts:231-237`) расходится host/env при override. Черновик честен (`OCLAB-REQUEST.md:109`), но R1 сохраняет оба варианта | Норма: `bind_abs` (тот же абс. путь, одна истина). `root_hash_override` — только как явное исключение с пином хэша + audit-маркером, либо удалить. Та же оговорка нужна для снапшота approvals R4 (`OCLAB-REQUEST.md:55`: устаревший апрув внутри env без механизма/триггера обновления) |
| C7 | MED | `.slim/spec/preflight-0.md:92-94` (`canon_command` срезает `nice/taskset/ionice`, ENV-префиксы, `python3 -m`→`python -m`) vs семантика дедупа | **Срезание ENV склеивает различимые команды.** `OMP_NUM_THREADS=1 pytest` и `OMP_NUM_THREADS=8 pytest` после нормализации выглядят дублями → ложные группы W2 и неверный `suggested_owner`. Это лишь WARNING, но спека не перечисляет точный набор срезаемых ENV | Зафиксировать исчерпывающий список нормализации (throttling-обёртки + `OMP_*/OPENBLAS/MKL/NUMEXPR/PYTHONDONTWRITEBYTECODE` из `config/AGENTS.md:361-363`) и правило: неизвестный `VAR=` не срезается, а БЛОКИРУЕТ группировку. Тест: `OMP=1` и `OMP=8` — разные canon |
| C8 | MED | `.slim/spec/preflight-0.md:1,52-55` (slug `preflight-0`, CLI `spec-preflight`) vs `research/S4-tooling.md:29,62` (`bin/preflight`: env/ports B9, пишет `.slim/preflight.json`), `research/SYNTHESIS.md:49` (P0-7 `bin/preflight` + dispatch-fact) vs `research/SYNTHESIS.md:51` (P0-9 `spec-preflight`) | **Имя обещает больше, чем scope; dispatch-fact молча выпал.** S4/SYNTHESIS различают ДВА инструмента: `preflight` (env/ports, B9) и `spec-preflight` (консенсус, F1). Спека делает только второй, но называется `preflight-0`, а §3.1 «writes nothing» отменяет `S4-tooling.md:62` (`.slim/preflight.json` как dispatch-fact) без объяснения. Человек подумает, что B9 закрыт | (a) Переименовать slug/заголовок в `spec-preflight-0` ИЛИ явно добавить в §1.3 non-goals: «env/port-preflight (B9, `S4-tooling.md:62`) — не делаем, остаётся открытым». (b) Одна строка, оправдывающая read-only отход от `.slim/preflight.json`: вторая истина запрещена `ADR-0003`; факты передаются через `--json` stdout + `spec-status --json`, а не файлом |
| C9 | LOW | `.slim/spec/preflight-0.md:76` (межконтрактный дубль `id` → постоянный ERROR) vs `research/SYNTHESIS.md:27` (после namespaced-миграции меж-`id` → advisory + ERROR только при коллизии flat-пути), `research/SYNTHESIS.md:31,54` (P1-10) | **E4 закостенеет при миграции evidence.** Сегодня ERROR верен (плоский `verify/<id>.json`: `config/bin/dod-run:319-320`, `config/bin/docs-lint:29-33`). После P1-10 меж-`id` ERROR станет ложным | Добавить в E4 строку-закат: «до namespaced-миграции (P1-10) — ERROR; после — advisory, ERROR только при коллизии flat-пути». Без кода, одно предложение |
| C10 | LOW | `.slim/spec/preflight-0.md:78` (`report.owners`: только когда $\ge 1$) vs масштаб (`config/bin/spec_scope.py:517-522` `tracked_files` — тысячи путей) | **Отчёт раздуется.** Карта путь→контракты для ВСЕХ покрытых файлов, а не только конфликтов, — шум в `--json` и в человеческом блоке на большом репозитории | Ограничить `owners` перекрытиями ($\ge 2$ контракта); покрытие $\ge 1$ держать за опциональным флагом или убрать (сам чек W1 всё равно бежит по полному множеству) |
| C11 | LOW | `research/S6-economics.md:42` («owner-scoped DoD + wave parallelism 2–3»), `research/M2-simulation.md:150-153` (§5.3) vs `research/M4-review.md:47-55`, `research/SYNTHESIS.md:167-170` | **Остаточный оптимизм H=2 в старых текстах.** S6/M2 старше M4; их формулировки формально перекрыты. Живые планы корректно цитируют M4, но любой новый текст, цитирующий M2 §5 как авторитет вместо SYNTHESIS Ф3, воскрешает опровергнутое утверждение | Не править S6/M2 (история). Правило: ранжирование цитировать только через `SYNTHESIS.md:165-172` + `M4-review.md:45-55`. В roadmap P1-11/12 добавить квалификаторы «C — платная опция», «no H=2» |
| C12 | LOW | `research/OCLAB-REQUEST.md:99` (S1: «zero oclab changes» + «`dod-run`-in-headless dry-run») | **Мягкая S1-циркулярность.** Headless dry-run предполагает существующий env/рантайм, которого S1 якобы не касается | Уточнить: dry-run использует хостовый `dod-run` с эмулированными env-переменными, ЛИБО перенести пункт в S2. Одна строка |
| C13 | LOW | проектный `docs-lint` (без `--spec`) vs `.slim/spec/preflight-0.md:144,146` («no ERROR») | **Проектный линт красный независимо от спеки.** В `docs/` только `adr/ guides/ notes/ SPEC-*` — нет `docs/tutorials how-to reference explanation` (`config/bin/docs-lint:387-397` требует все 5 → ERROR `diataxis-dirs`). Режим `--spec` (§6 DoD) не зовёт `lint_dirs` и зелёный, но полный прогон — нет | Информация, не блокер: self-hosting DoD сформулирован через `--spec` и исполним. Но зафиксировать, что проектный `docs-lint` будет красным, пока не появятся квадранты Diátaxis |

## What NOT to change (genuinely consistent)

- H5-ядро и числа ($19.3\to5.9$, $622\to233$, 3 круга инвалидации) идентичны в
  `M2-simulation.md:118-124`, `M4-review.md:51`, `SYNTHESIS.md:161,174`,
  `preflight-0.md:15`; батч `--all/--changed` не тронут (human-only) — верно.
- Имя/интерфейс/проверки `spec-preflight` (`config/bin/spec-preflight`,
  `[--spec] --json` + `[<path>] [--quiet] [--help]`, exit 0/1/2, E1–E4/W1–W3) —
  надмножество `S4-tooling.md:68` и `SYNTHESIS.md:51` без дрейфа.
- Слои и non-goals oclab («плагин советует, ядро запрещает», без парсинга `bash`,
  без uid-split/microVM/CoW/`keyctl`/ARM сейчас) совпадают с `ADR-0001:69-77,83-86`
  и SPEC §11-13.
- Механика фенсов/evidence (`scope` ≡ в `config/AGENTS.md:82-88`,
  `spec_scope.py:305-374`, `spec-gate.ts:414-483`; first-fence-wins; fail-closed;
  `deny` побеждает; классы GOV-6/7; тройка evidence v2 снимается один раз до
  первого чека `dod-run:396-398`; коммит до `dod-run`; flat-store E4-ERROR
  `docs-lint:212-281`; docs-lint только контракты; `dod-run` отказывает
  index/undeclared/archive) — preflight-0 не противоречит ничему, кроме деталей C3/C5.
- H7 соблюдён: `$` нигде не критерий ранжирования. C-как-опция и H=2-отложен
  соблюдены: preflight-0 не трогает сертификацию staleness (`DONE` остаётся
  глобальным `stale_cert`). Рефакторинг `docs-lint` → общий `dod_check_ids`
  семантически равен локальной копии `docs-lint:175-201` (толерантный парсер,
  `[]` при отсутствии); третий парсер `has_dod_block:149-172` законно остаётся.

## Open questions to the human

1. **Инкремент.** Апрувить preflight-0 как «H5 + видимость B» и открыть отдельный
   контракт `wave-run` для исполнения B — или расширить текущий scope?
   (Oracle рекомендует первое.)
2. **`verify/` tracked vs untracked.** Выбрать ДО апрува. Выбор решает, патчить ли
   AGENTS/guide/ADR-0004 или заспечить wave-log.
3. **R1.** Зафиксировать `bind_abs` нормой и понизить `root_hash_override` до
   исключения (или удалить) + механизм обновления снапшота approvals (окно R4).
4. **Базовая линия.** Что именно войдёт в первый `git add` (весь untracked
   `config/ docs/ research/ README.md .slim/`?) и кто его делает — до апрува
   preflight-0.
5. **oclab S1.** Кто пишет S1-контракт(ы) (эмиттер манифеста, argv-preview,
   обёртка doctor, audit-merge, dry-run) — следующий спек после preflight-0.
6. **Мелкие формулировки preflight-0.** (a) E3 — дословно по `dod-run:248`;
   (b) отсутствие `scope` → WARNING; (c) точный список срезаемых ENV в
   `canon_command`; (d) slug/§1.3: отделить от B9-`preflight` + закат E4 +
   `owners` только $\ge 2$.
