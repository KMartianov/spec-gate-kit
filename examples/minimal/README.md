# `minimal` — один сквозной контракт

`examples/minimal/spec/example-task.md` — **эталонный файл**, который принимающий
проект копирует к себе как `<project>/.slim/spec/example-task.md`. Он демонстрирует
две машиночитаемые ограды:

- **`scope`** — `{"allow": [...], "deny": [...]}`: единственный мандат записи;
  битый/пустой `scope` не даёт ничего (fail-closed).
- **`dod`** — `{"checks": [{"id", "cmd"}]}`: `id` **префиксны slug-ом**
  (`example-task-*`), чтобы не коллизировать в плоском сторе `verify/<id>.json`
  (коллизию ловит `docs-lint` — ERROR `dod-duplicate`).

В ките файл остаётся `draft` и никогда не одобряется. Поэтому он лежит в
`examples/minimal/spec/`, а **не** в `examples/minimal/.slim/spec/`: вложенный
`.slim/spec/` сделал бы `examples/minimal` отдельным gated-корнем, и любая правка
файлов примера агентом блокировалась бы `[SPEC-GATE BLOCKED] / no-approval`.

## Сквозной рецепт (все команды — из корня репозитория кита)

```bash
# 1. поставить кит во временный проект (создаёт $tmp/.slim/spec/, smoke OK)
tmp=$(mktemp -d)
bash install.sh --target "$tmp"

# 2. скопировать эталонный контракт в spec-зону проекта
mkdir -p "$tmp/.slim/spec"
cp examples/minimal/spec/example-task.md "$tmp/.slim/spec/"

# 3. целостность контракта: статус, scope-фенс, отсутствие коллизий id → rc=0
python3 config/bin/docs-lint --spec "$tmp/.slim/spec/example-task.md"

# 4. производное состояние, read-only → rc=0, SPEC_DESIGN (draft, не одобрен)
python3 config/bin/spec-status "$tmp/.slim/spec/example-task.md"
```

Фактический вывод шага 4 (сокращён):

```
Derived state (read-only, no store): SPEC_DESIGN
spec       : .../example-task.md (role=spec, active=yes, slug=example-task)
approval   : —
declared   : draft (display only, never authoritative)
```

## Read-only проверка самого образца

Образец линтуется и «на месте», из корня кита (ADR-ссылка резолвится в `docs/adr/`
кита):

```bash
python3 config/bin/docs-lint --spec examples/minimal/spec/example-task.md   # rc=0
```

`spec-status` для файла **вне** `<root>/.slim/spec` намеренно не работает
(`not a spec under …`): состояние контракта производно от spec-зоны проекта.
Поэтому для `spec-status` образец сначала копируется в `<project>/.slim/spec/`
(шаг 2 рецепта). Сам файл в ките — вне чьей-либо spec-зоны, и это правильно.

## Состав

```
examples/minimal/
├── README.md              # этот файл
└── spec/
    └── example-task.md    # эталонный контракт (draft); копируется в <project>/.slim/spec/
```

Пример намеренно не содержит `verify/*.json` и не требует прогона: его чеки —
заглушки (`true`), цель примера — форма контракта, а не вычисление.
