# Фаза D — дельта-ревью спринта (release 0.2.0)

- **Дата:** 2026-10-03
- **Ревьюер:** `@oracle` (read-only, сессия `ora-8` / `ses_f019234e3ffegHe54tF3lKSrIV`)
- **HEAD на момент ревью:** `550958b`
- **Предмет:** вся дельта спринта — Фаза A (docs), Фаза B (plugin B1–B3), Фаза C (релиз 0.2.0).
- **Общий вердикт:** **GO (к C4), блокеров нет.** Функционально релиз `0.2.0` годен.

## Вердикт по пунктам

| # | Пункт | Вердикт |
|---|-------|---------|
| 1 | Состояние: `spec-status` = DONE×3, evidence root-relative, `git_head=550958b`, `tree_dirty=false`, 12 modified `verify/*.json` | **PASS** (с замечанием к механике C4) |
| 2 | Отсутствие регрессий: pytest **186**, node **27**, `docs-lint .` 0 ERROR / 4 WARN, `--spec`×3 rc=0, `check_portability config\|install\|paths` rc=0 | **PASS** |
| 3 | CI валиден, линтит все 3 спеки, `paths` блокирующий, installer-smoke есть; прогон на чистом клоне `550958b` | **PASS** |
| 4 | Installer: rc=0 `smoke: OK`, идемпотентен, без `--target` rc=2, нет `__pycache__`/`*.pyc` в target | **PASS** |
| 5 | Версия/док: `VERSION`=0.2.0, CHANGELOG `[0.2.0] — 2026-10-03`, README L3/L33 согласованы | **PASS** (дрейф инвентаря — исправлен) |
| 6 | Доктрина m8 «одобрения host-local» в README §6 + `config/AGENTS.md`, не противоречит коду | **PASS** |
| 7 | Границы мандатов: 8 файлов дельты покрыты активными `scope`; `docs/**` не трогались | **PASS** |
| 8 | Готовность к C4 (тег + push) | **блокеров нет** |

## Ключевое замечание: механика C4 (one-commit lag)

$$\text{stale} = (\text{ev\_head} \neq \text{HEAD}) \;\lor\; \text{tree\_dirty}$$

DONE — свойство **worktree** перед коммитом. Любой коммит двигает `HEAD`, поэтому после
коммита 12 `verify/*.json` состояние честно станет `VERIFY` (отставание ровно на один
чисто-evidence коммит). Это структурное свойство схемы, **не регрессия**. Порядок C4:
коммит 12 evidence → тег `0.2.0` на evidence-коммит → `git push`.

## Находка (исправлена): дрейф инвентаря README

Числа в README отстали после Фазы B (мандат B не покрывал README). Исправлено в этой же
сессии (мандат `p0-portability-sprint` → `README.md`):

| Место | Было | Стало (факт) |
|-------|------|--------------|
| `README.md:44` `spec-gate.ts` | 1283 | **1291** |
| `README.md:45` `spec-gate.test.ts` | 593 | **714** |
| `README.md:177` node | 25/25 | **27/27** |
| `README.md:166,182` `paths` note | 45 (`35` + `10`) | **48** (`34` `[doctrine]` + `4` `[code]` + `10` `[evidence-inactive]`) |

## Прочее

- Реальные `~/.local/share/opencode/audit|approvals` ревью не задело (тесты hermetic:
  env-пин `OPENCODE_SPEC_GATE_AUDIT_FILE` + tmp-фикстуры; тест 25 сторожит реальный журнал).
- Фаза B подтверждена кодом: B1 — `spec-gate.ts:57-62`; B2 — `bootWritten = true` после
  успешного `appendChained` (`:1056-1060`); B3 — `chainSeq = nextSeq` после записи (`:1075-1080`).
- Ссылки `file:line` в README §4 на ревизию `f984997` помечены как исторические — устарели,
  но это документированный дрейф (не блокер).

## Остаток после Фазы D

- **C4 (человек, последним):** коммит 12 `verify/*.json` → тег `0.2.0` → `git push`
  (гейт A+B+C1–C3 зелёные — выполнен).
- **Фаза E:** drop/defer с триггерами (HMAC/Ed25519, m6/m7, Diátaxis, `scope_sha256`, N1, M9).
- **Фаза F (человек):** ARCH-политика после 0.2.0 (нужен минимальный живой мандат), push,
  ADR для m8 в `docs/**`.
