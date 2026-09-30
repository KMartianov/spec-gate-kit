# `dod-run` / `spec-status`: коллизия плоского хранилища доказательств

- **Дата:** 2026-09-28
- **Автор:** orchestrator (сессия `ses_f1c4749d6ffe2kjYDXq9X9h3ee`)
- **Область:** глобальный инструментарий `oh-my-opencode-slim` — `bin/dod-run`, `bin/spec-status`, `plugins/spec-gate.ts`
- **Проект-источник:** `/home/asdcxfrt/Projects/opencode-lab` (три утверждённые спеки)

## Симптом

Когда в одном проекте **две и более** утверждённых спецификации содержат проверки с
**одинаковым `id`**, они пишут в один и тот же файл `verify/<id>.json` и перетирают
друг друга. `spec-status` при этом сверяет `spec_sha256`, поэтому файл «принадлежит»
ровно одной спеке; вторая навсегда остаётся в состоянии `VERIFY`, а повторный прогон
лишь переключает состояние обратно (симметрично). **Две спеки с общим `id` не могут
одновременно стать `DONE`.**

## Наблюдение (opencode-lab, HEAD + три спеки)

`verify/` содержал 34 файла, все `exit_code: 0`. Распределение по `spec_sha256`:

| спека | sha256 (префикс) | файлов |
|---|---|---|
| `oclab-egress-hardening.md` | `ddc23395807b…` | 11 |
| `oclab-sandbox-builder.md` | `f386c0d91a60…` | 14 |
| `oclab-ipc-trust.md` | `fcf273b2ac64…` | **9** (было 15) |

Шесть `id` встречались у `oclab-egress-hardening` **и** `oclab-ipc-trust`:

```
configure, build, ctest, werror, asan, docs_untouched
```

Их команды были **побайтово одинаковыми** в обеих спеках, однако для второй спеки
`spec-status` показывал `hash: no` → ipc-trust застревал в `VERIFY` (9 hash-yes из 15).

## Корневая причина

`dod-run` исполняет fence той спеки, что задана `--spec`, но **пишет результат всегда
в `<root>/verify/<id>.json`** — без неймспейса по спеке. `--spec` выбирает лишь
*какой fence исполнять*, а не *куда писать*. Соответственно пространство имён
доказательств плоское и не может различить двух владельцев одного `id`.

Фреймворк-контракт (`docs/adr/0003-derived-lifecycle-state.md`) закрепляет именно
путь `verify/<id>.json`, поэтому проблема структурная, а не случайная.

## Временная мера (применена в opencode-lab)

**Конвенция: `id` проверки обязан быть уникален в пределах проекта → префиксовать
слагом спеки.** Применено к двум перекрывающимся спекам:

- `configure→egress_configure`, `build→egress_build`, `ctest→egress_ctest`,
  `werror→egress_werror`, `asan→egress_asan`, `docs_untouched→egress_docs_untouched`;
- то же с префиксом `ipc_` в `oclab-ipc-trust.md`.

После правки: 40 проверок, 40 уникальных `id`, 0 дублей. Осиротевшие
`verify/{configure,build,ctest,werror,asan,docs_untouched}.json` удалены (34→28 файлов).

⚠️ Правка спеки **инвалидирует** её approval и доказательства (тот же `sha256`-правило) →
потребовался повторный `spec-approve` человеком и повторный `dod-run`.

Ограничение меры: она не устраняет причину — любой будущий автор спеки, забывший
префикс, снова получит коллизию.

## Рекомендуемое настоящее исправление (владельцу инструмента / ADR фреймворка)

1. **Неймспейс пути доказательств по спеке:** писать `verify/<spec-slug>/<id>.json`
   (или `verify/<sha256(root)[:16]>/<slug>/<id>.json`); `spec-status` читает тот же
   layout. Обратная совместимость — фолбэк на `verify/<id>.json`, если неймспейсного
   файла нет.
2. **Fail-loud вместо тихого перетирания:** если `verify/<id>.json` существует и его
   `spec_sha256` (или `spec`) принадлежит **другой** спеке — `dod-run` обязан
   отказаться писать и вернуть ошибку, а не молча затирать чужое доказательство.
3. Опционально: `bin/docs-lint` предупреждает о дублирующихся `id` **между** спеками
   проекта (сейчас проверяется только уникальность/валидность fence внутри файла).

## Ссылки

- `~/.config/opencode/bin/dod-run`, `~/.config/opencode/bin/spec-status`
- `~/.config/opencode/plugins/spec-gate.ts`
- `~/.config/opencode/docs/adr/0003-derived-lifecycle-state.md`
- Проект: `.slim/spec/oclab-{egress-hardening,ipc-trust,sandbox-builder}.md`
