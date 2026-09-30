# Отчёт по аудиту репозитория `~/.config/opencode`

> **Дата:** 2026-09-29
> **Метод:** два параллельных read-only аудита `@oracle` (лейн «конфигурация и агенты» + лейн
> «исполняемая часть и тулинг»); ключевые находки дополнительно перепроверены вручную по коду.
> **Объект:** user-config OpenCode (`~/.config/opencode`). Это **не** git-репозиторий; путь полностью
> exempt от `spec-gate` (`~/.config/opencode/**`).

---

## 0. Вердикты

| Лейн | Вердикт |
|---|---|
| Конфигурация и агенты | Модельная таблица `AGENTS.md` **полностью синхронна** с `oh-my-opencode-slim.json` (старый `qwen3.7-max`-баг закрыт), но есть **1 orphan-секрет**, **2 недокументированных wiring** и дрейф `SPEC-OpenCode-Hardening.md §8/§10` относительно фактического конфига. |
| Исполняемая часть и тулинг | Честно спроектировано (fail-closed по мандату, flip-before-hash, выводимое состояние), но **тест-харнес гейта протух**, часть защит — театр, доки уже дрейфуют от кода. |

**Итог:** CRITICAL — 3, MAJOR — 10, MINOR — 15, NIT — ~10. Ни одна из находок не отменяет архитектуру;
речь о рассинхронизации артефактов, устаревших тестах и переоценённых гарантиях.

---

## 1. Находки — конфигурация и агенты (ora-2)

### CRITICAL

**1. `service.json:2` — orphan-пароль в открытом виде.**
Файл содержит `{"password": "-Lx71kwre…"}`. На него **нет ни одной ссылки** ни в одном
`.json/.ts/.md` конфига (grep по всему каталогу, кроме `node_modules`), а `.gitignore:1-5` его
**не исключает** — при `git init` + публикации пароль уедет в репозиторий.
*Исправление:* выяснить владельца секрета; если не нужен — удалить; иначе — перенести в `{env:...}`
и добавить `service.json` в `.gitignore`. Подтверждение: `service.json:2` vs `.gitignore:1-5`.

### MAJOR

**2. `oh-my-opencode-slim.json:84-85` — `librarian.mcps` ссылается на отсутствующие `context7`/`gh_grep`.**
В `opencode.json` объявлены только `serena/jupyter/hf/arxiv/memory` (5), а пресет (и `big-pickle`,
и `opencode-zen-free:148-151`) требует 7 имён. `AGENTS.md:265` называет их «remote (built-in)», но
объявления или проверяемого источника этого свойства в файлах нет — из репозитория неразрешимо,
заведён ли backend. *Исправление:* либо добавить `context7`/`gh_grep` в `opencode.json → mcp`, либо
в `AGENTS.md:265` дать проверяемый источник «built-in».

**3. `SPEC-OpenCode-Hardening.md:183-194 (§8)` — матрица per-agent permissions не реализована.**
Таблица обещает path-scoped разрешения (`fixer/cpp/python/ml-expert → allow только ~/Projects/**`,
`orchestrator → ask`, `oracle → bash deny`). Фактически (`oh-my-opencode-slim.json:63-73,97-99,217-220,239-242,276-279`):
у `fixer` блока `permission` нет; у `cpp/python/ml-expert` — blanket `"edit":"allow","bash":"allow"`;
у `orchestrator` блока нет; у `oracle` только `edit:deny` (bash наследует глобальный `ask`, не `deny`).
Path-scoped per-agent разрешений как механизма **не существует**. *Исправление:* переписать §8 как
целевой/аспирационный либо снять отметку «реализовано» в §12.

**4. `SPEC-OpenCode-Hardening.md:216-224 (§10)` — stale относительно JSON.**
§10 рекомендует `librarian → Muse Spark 1.3`, `orchestrator → GLM-5.3-Flash`; фактически
(`oh-my-opencode-slim.json:30,75`) — `orchestrator → deepseek-v4.1-flash`, `librarian → glm-5.3-flash`
(совпадает со `Список моделей.md:287`, но не с §10). §12-шаг 5 при этом утверждает «сверено с JSON».
*Исправление:* обновить §10 под факт и снять/перепроверить отметку шага 5.

### MINOR

- **5. Провайдер `opencode-go` нигде не объявлен.** Все 10+1 моделей — `opencode-go/*`, а в
  `provider`-секции `opencode.json:47-318` его нет. `AGENTS.md:362-364` утверждает «working default».
  *Исправление:* одна строка об источнике резолва (подписка/Zen-auth вне файлов).
- **6. `opencode.json:374-381` — `agent.explore/general: disable` недокументировано.** `AGENTS.md:204`
  упоминает только `disabled_agents: designer/observer`. *Исправление:* добавить строку.
- **7. Расхождение agent-may-run списков.** `AGENTS.md:119-131` разрешает `spec-new/spec-status/dod-run/docs-lint`;
  `orchestrator_append.md:48-51` — только первые три; `bin/oc-usage` не упомянут нигде.
- **8. `AGENTS.md:336-342` — таблица Configuration Files без `dcp.jsonc` и `service.json`.**
  `dcp.jsonc` почти пуст (только `$schema`), поэтому DCP-конфиг = дефолты, и это нигде не сказано.
- **9. `AGENTS.md:188` — висячая ссылка «Doc-Driven spec §7».** Вероятный референт — `guides/spec-driven-development.md`.
- **10. `Список моделей.md:16,284-295,313-321` — stale, но подан как актуальный.** TL;DR/§8 о
  `qwen3.7-max`-баге и колонка «Сейчас» §7.1 описывают конфиг до миграции. *Исправление:* freshness-banner.
- **11. `AGENTS.md:274-283,356-361` — `tools/jupyter_up.sh` не существует в этом каталоге** (внешний проект Diplom).
- **12. `AGENTS.md:325-333` — таблица Subagents перечисляет лишь 4 кастомных**, молча пропуская 6 пресетных.

### NIT

- `opencode.json:150-152` — единственный литеральный ключ `"apiKey": "zai-proxy"` + `http://127.0.0.1:36019`
  (остальные — `{env:...}`); риск низкий (localhost).
- `.gitignore:2,5` — игнорируются `package.json` (пин `@opencode-ai/plugin 1.18.29`) и сам `.gitignore`.
- `memory.jsonl:1` — ASCII-математика (`q^T R_{n-m} k`) при обязательном LaTeX.
- 9 из 10 `*_append.md` — чистые LaTeX-стабы по 11 строк; `AGENTS.md:35-37` подаёт их как «enforcement».
- RU/EN-микс в `AGENTS.md` (EN-каркас + RU-блоки) без строки о конвенции.

---

## 2. Находки — исполняемая часть и тулинг (ora-3)

### CRITICAL

**1. Харнес гейта не соответствует реализации и пачкает реальное хранилище.**
`plugins/__tests__/spec-gate.test.ts:46-51` — `approve()` ждёт, что CLI напечатает путь `*.json`
(`out.endsWith(".json")`), и вызывает CLI без `--approvals-dir`; текущий `bin/spec-approve:452-455`
печатает `approved <spec> (sha256…)` + `gate: …`, `.json` не печатает. Тот же харнес `test.ts:116-119`
ждёт `allowed` после одобрения спеки **без** `scope`-ограды (`makeProject` `test.ts:31-41` ограды не создаёт),
а `plugins/spec-gate.ts:689-707` при `scope === null` даёт `no-mandate` (блок).
*Исправление:* переписать `approve()` на `--approvals-dir <tmp>`, парсить новую выдачу, добавить
`scope`-ограду в фикстуру.

**2. Тесты одобряют в реальный store.**
`test.ts:46-51` не передаёт `--approvals-dir` (в отличие от `bin/tests/test_spec_approve.py:60-66`).
Прогон `node --test` пишет в `~/.local/share/opencode/approvals`; `after()` чистит лишь `approvalDirs`,
спарсенные из **несуществующего** вывода. *Исправление:* прокинуть изолированный `approvals-dir`
через env `OPENCODE_APPROVALS_DIR` или аргумент и чистить его.

### MAJOR

**3. `tools/gov/scope_vectors.json` отсутствует — паритет TS↔Python не проверен.**
`bin/spec_scope.py:7` объявляет его «single source of truth», но файла нет (`ls tools/gov → No such file`).
`plugins/spec-gate.ts:414-466` и `bin/spec_scope.py:306-364` — два независимых транслятора
glob→regex без общего вектора. *Исправление:* создать векторы (`*`, `?`, `**`, `**/`, `a/**`, классы,
deny-wins, `..`/абсолютные) и гонять обе реализации в CI.

**4. Denylist `dod-run` — театр.**
`bin/dod-run:68-78` блокирует подстроки (`sudo`, `dd if=`, `rm -rf /`, `:(){`, `chmod -r 777`),
но пропускает `dd of=/dev/sda`, `rm -rf /*`, `rm -rf $HOME`, `rm -rf .`, `chmod 777 -R`, `: () {`,
`python -c 'os.system("rm…")'`, env-обфускацию. Угрозу снижает лишь то, что команды из
human-approved спеки. *Исправление:* либо честно задокументировать «denylist — только от опечаток»,
либо добавить `of=`, `/*`, `$HOME`, `.` формы.

**5. `dod-run` пишет evidence неатомарно.**
`bin/dod-run:319-325` — `mkdir` + `write_text`, тогда как `bin/spec_scope.py:133-149` уже даёт
`atomic_write` (same-dir temp + `os.replace`). Гонка двух `dod-run` или kill в середине = рваный JSON
→ `spec-status:189-192` сочтёт доказательство отсутствующим. *Исправление:* писать через `spec_scope.atomic_write`.

**6. `spec-revoke` не возвращает голый `approved` в `draft`.**
`bin/spec-revoke:81-82` — `STATUS_APPROVED_RE` матчит только `` `approved` `` в бэктиках. Спека с
bare-токеном `approved` (который `spec-approve` сам умеет флипать, `bin/spec-approve:233-242`)
после revoke остаётся с токеном `approved`, но без записи: строка врёт, гейт блокирует.
*Исправление:* матчить ту же `STATUS_RE`-семантику + `declared_token`.

**7. Дрейф «APPROVED vs VERIFY» после переодобрения.**
`bin/spec-status:216-227`: при непустых checks и всех `present == false` (чужие `spec_sha256`)
возвращается `APPROVED`; `guides/spec-driven-development.md:364-369` обещает в этом месте `VERIFY`.
По коду stale-by-revision ≡ нет доказательств, т.е. **чинить надо гайд**.
*Исправление:* в гайде (§6, §18) — `APPROVED`; либо менять `derive_state` и фиксировать тестом.

**8. TS `approvalScan` ломается на симлинкнутом root, Python — нет.**
`plugins/spec-gate.ts:523-529` сравнивает `path.dirname(canonicalize(record.spec, root)) !== path.join(root, SPEC_REL)`
(левая часть realpath'нута, правая — нет); `bin/spec_scope.py:438-441` резолвит обе стороны.
На macOS (`/tmp → /private/tmp`) валидный аппрув в TS не найдётся (fail-closed блок).
*Исправление:* каноникализировать `specDir` тем же `canonicalize`.

**9. Нет тестов там, где риск.**
`bin/tests/` покрывает `spec-approve`, `spec-revoke`, часть `docs-lint`; нет ничего для `dod-run`
(таймаут/denylist/атомарность/`--only`), `spec-status` (stale/DONE), `spec_scope.glob_match/scope_report`,
`spec-new`, `gate-off/on`, `oc-usage`.

**10. ADR отстали от кода.**
`docs/adr/0002:27` — запись `<slug>.json`, код `bin/spec-approve:197` — `<hash>-<slug>.json`;
`docs/adr/0004:43` — схема evidence v1 без $\text{git\_head},\ \text{tree\_dirty},\ \text{scope\_sha256}$,
код `bin/dod-run:301-315` — v2; DONE-формула `0004:57-59` без свежести
$\text{git\_head} = \text{HEAD} \wedge \text{tree\_dirty} = \text{false}$, которую требует
`bin/spec-status:206-212`; `docs/adr/0001:50` — аудит `{"ts",…,"decision"}`, код `spec-gate.ts:773-782`
пишет ещё `reason, spec, targets, root`.

### MINOR

- **11. Третий парсер фенсов.** `bin/docs-lint:149-172` (`has_dod_block`) дублирует `spec_scope.parse_fences`
  и `spec-gate.ts:272-300`; сейчас эквивалентны, дрейф гарантирован.
- **12. `find_root` скопирован в 4 CLI** (`spec-status:93-104`, `dod-run:104-114`, `docs-lint:88-98`,
  `gate-off:38-48`, `gate-on:35-46`) вместо `spec_scope.find_root`.
- **13. Кейс-чувствительность слагов разная** (`lower()` в `spec-status/dod-run` vs точное `Path.exists()`
  в `approve/revoke`).
- **14. `scope`-пример в шаблоне не рендерится.** `templates/spec-template.md:90` — `tools/<task>/**`,
  а `bin/spec-new:143-153` подставляет только `<task_slug>`; скаффолд уезжает с буквальным `<task>`
  (валидный, но ничего не покрывающий glob). *Исправление:* `tools/<task_slug>/**`.
- **15. `patternError` слишком широк к `~` и врёт на незакрытом `[`.** `spec-gate.ts:330-346`,
  `spec_scope.py:213-237`: `includes("~")` бракует легитимный `src/~backup/**`; `/`-в-классе
  не учитывает незакрытый `[`. Оба — в безопасную сторону.

### NIT

`command/spec-approve.md:15` vs `bin/spec-approve:601-603` (каталог только с ровно одним `.md`);
`bin/spec-new:234-240` — `git init -q` без `--initial-branch`; `bin/spec-new:163-182` — захардкожен
`/home/asdcxfrt/ml_base/.venv`; `bin/spec_scope.py:528-537` — рваный LaTeX; `bin/oc-usage:65-96` —
квоты/модели захардкожены; `spec-gate.ts:817-858` — при мультитаргете через два корня аудит `allowed`
пишет только первый root.

---

## 3. Подтверждено вручную (evidence)

Проверено лично по коду, не со слов аудиторов:

- ✓ **`service.json`**: права `0600`, содержимое ровно `{"password": …}`, **0 ссылок** в конфиге,
  `.gitignore` не исключает; сам `.gitignore` игнорирует `package.json` и `.gitignore` (строки 2 и 5).
- ✓ **`context7`/`gh_grep`**: присутствуют в `AGENTS.md:265` и `oh-my-opencode-slim.json:84-85,149-150`,
  но `opencode.json → mcp` = `['serena','jupyter','hf','arxiv','memory']`.
- ✓ **`derive_state`** (`bin/spec-status:216-227`): `present ≡ hash_matches`, где
  $\text{hash\_matches} = \big(\text{record.spec\_sha256} = \operatorname{sha256}(\text{spec\_bytes})\big)$.
  Поэтому evidence с чужим хешем не считается present, и после переодобрения состояние = **`APPROVED`**;
  `VERIFY` даёт только present-но-несвежее evidence, т.е.
  $\text{git\_head} \ne \text{HEAD} \lor \text{tree\_dirty} = \text{true}$. Строка docstring `:34-35`
  («legacy evidence → VERIFY») описывает случай **совпавшего** хеша со stale-ревизией.
  ⟹ Мой прошлый вывод «переодобрение без `dod-run` → `VERIFY`» **неверен** — правка гайда на `APPROVED`.
- ✓ **`spec-revoke:81-82`**: `STATUS_APPROVED_RE` матчит только `` `approved` `` (бэктики).
- ✓ **`dod-run`**: `DENYLIST = (sudo, mkfs, "dd if=", "rm -rf /", "rm -rf ~", ":(){", shutdown, reboot, "chmod -r 777")`;
  запись evidence — `out_dir.mkdir` + `write_text` (неатомарно).
- ✓ **`tools/gov/`** отсутствует; `plugins/__tests__/spec-gate.test.ts:46-51` зовёт CLI без
  `--approvals-dir` и ассертит `out.endsWith(".json")`.

---

## 4. План исправлений и улучшений

### Приоритет 0 — безопасность и достоверность

- **P0-1. Секрет в репозитории.** Выбранное решение: **добавить `service.json` в `.gitignore`**
  (файл не удаляем). Опционально — выяснить владельца пароля и перенести в `{env:...}`.
  Также вернуть в отслеживание `package.json` (пин `@opencode-ai/plugin 1.18.29`) и сам `.gitignore`.
- **P0-2. Починить `plugins/__tests__`.** Изоляция `approvals-dir` (tmp + чистка), `scope`-ограда в
  фикстуру, парсинг новой выдачи. Иначе зелёные тесты врут и пачкают реальный store.
  *Владелец:* @fixer (TS). *Приёмка:* `node --test` не пишет в `~/.local/share/opencode/approvals`;
  есть позитив/негатив по `scope`.

### Приоритет 1 — корректность

- **P1-1 (Lane D).** `tools/gov/scope_vectors.json` + кросстест TS↔Python; каноникализация `specDir`
  в `approvalScan`; `~` запрещать только как ведущий `~/`. *Владелец:* @fixer/@cpp-expert.
- **P1-2 (Lane C).** `dod-run`: `atomic_write` для `verify/*.json`; честный docstring про denylist +
  формы `of=`, `/*`, `$HOME`, `.`; `spec-revoke` — bare-токен тем же путём, что `mark_approved`;
  дедуп `find_root`/`has_dod_block` в `spec_scope`. *Владелец:* @python-expert.
- **P1-3 (Lane E).** Синхронизация доков: ADR 0001/0002/0004; гайд §6/§18 → `APPROVED`;
  `templates/spec-template.md` `tools/<task_slug>/**`; `AGENTS.md` (источник `opencode-go`,
  `explore/general`, agent-may-run + `oc-usage`, `dcp.jsonc`/`service.json`, ссылка на §7,
  оговорка про `tools/jupyter_up.sh`, «Custom subagents»); `SPEC-OpenCode-Hardening.md §8/§10`;
  freshness-banner на `Список моделей.md`; решение по `context7`/`gh_grep`. *Владелец:* @fixer.
  *Примечание:* `docs/**` здесь writable — репозиторий целиком exempt, спеки `.slim` нет.

### Приоритет 2 — покрытие и мелкий харднинг

- **P2-1 (Lane F).** Тесты: `dod-run` (`--list/--only/timeout/denylist/атомарность`), `spec-status`
  (fresh/stale/legacy/dirty), `spec_scope.glob_match`, `spec-new --force`, `gate-off/on`. *Владелец:* @python-expert.
- **P2-2.** Унификация slug-резолва; `git init --initial-branch=main`; убрать хардкод venv из README-скаффолда;
  3-й парсер фенсов → общий.

### Зависимости

```
P0-1 ──┐
P0-2 ──┤ независимы
P1-1 ──┤
P1-2 ──┴──► P2-1 (тесты после харднинга)
P1-3 ────── независим
```

### Quick wins (< 15 мин)

1. `.gitignore`: убрать `package.json`/`.gitignore`, добавить `service.json`.
2. Гайд §6/§18: `VERIFY` → `APPROVED`.
3. Шаблон `scope`: `<task>` → `<task_slug>`.
4. `AGENTS.md`: +2 строки (источник `opencode-go`; `explore/general: disable`).

---

## 5. Что сделано хорошо (по обоим аудитам)

- Модельная таблица `AGENTS.md:191-202` ↔ `oh-my-opencode-slim.json` (`big-pickle` + `council.balanced`):
  все 10 агентов и 3 councillor совпадают по model/variant/$T$; все `variant` валидны против каталога
  `Список моделей.md:87-121`.
- Детект по путям, а не по именам + exhaustive read-only allowlist + fail-closed на непарсящемся писателе
  (`spec-gate.ts:63-104,597-600,808-813`) — дыра Serena закрыта по-настоящему.
- Терминальный порядок `spec-dir → docs (всегда) → serena → GATE-OFF → мандат`; `docs/**` не открывает
  даже `GATE-OFF` (`spec-gate.ts:676-708`).
- Единая ментальная модель инвалидации:
  $\text{valid} \iff \operatorname{sha256}(\text{spec\_bytes}) = \text{record.spec\_sha256}$,
  flip-before-hash (`spec-approve:341-374`), выводимое состояние вместо `state.json`,
  evidence v2 с $\text{git\_head} = \text{HEAD} \wedge \text{tree\_dirty} = \text{false}$.
- `deny` побеждает любой `allow` across-контрактов; `archive/**` неактивен в обоих языках;
  `atomic_write` + readback в approve; защита `id` от traversal (`dod-run:248`); аудит fail-open
  с fail-closed обёрткой (`spec-gate.ts:788-874`).
- MCP-раздача и skills по агентам совпадают с JSON; все 16 `skills/*/SKILL.md` и 9 `bin/`-CLI на месте;
  `bin/tests` изолированы (`--approvals-dir`, tmpdir, снепшоты) — образец для чинки TS-харнеса.

---

*Источники: `AGENTS.md`, `opencode.json`, `oh-my-opencode-slim.json`, `cli.json`, `tui.json`, `dcp.jsonc`,*
*`.oh-my-opencode-slim/skills-manifest.json`, `oh-my-opencode-slim/*_append.md`, `skills/*/SKILL.md`,*
*`command/*.md`, `plugins/spec-gate.ts`, `plugins/__tests__/spec-gate.test.ts`, `bin/*`, `bin/tests/*`,*
*`templates/*.md`, `docs/adr/*.md`, `guides/spec-driven-development.md`, `SPEC-OpenCode-Hardening.md`,*
*`Список моделей.md`, `memory.jsonl`, `.gitignore`, `service.json`.*
