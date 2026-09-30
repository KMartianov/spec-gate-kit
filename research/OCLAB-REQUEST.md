# Feature Request к oclab: HARD-субстрат под spec-gate-kit (Zero-Code Gate)

> Черновик. Status: draft (ожидает утверждения человеком перед отправкой в oclab).
> Автор: oracle (M-series, Ф3). Grounded в `spec-gate-kit` и `opencode-lab` @ 2026-10-01.

## 1. Резюме

`spec-gate-kit` — проектная фабрика с мягким userspace Zero-Code Gate: перехват `tool.execute.before`, per-spec мандат `scope`, неизменяемость `docs/**` (GOV-2), выводимое состояние $INTAKE \rightarrow SPEC\_DESIGN \rightarrow APPROVED \rightarrow VERIFY \rightarrow DONE$, доказательства `verify/<id>.json` v2. Честно признано: это не граница безопасности (`spec-gate-kit/docs/adr/0001-gate-as-soft-guardrail.md:51-53`, `spec-gate-kit/docs/SPEC-OpenCode-Hardening.md:363-367`).

Просим у `oclab` то, что kit не может дать себе сам: **kernel-enforced HARD-субстрат снизу** — bubblewrap `EROFS`, seccomp, Landlock, memfd-окружение, net-изоляцию — при сохранении spec-gate сверху как слоя мандата/UX/аудита. Доктрина kit уже фиксирует эту точку: `oclab` — будущий execution/isolation-слой (`spec-gate-kit/docs/SPEC-OpenCode-Hardening.md:230-235`), возврат по триггерам `:236-241`, блокеры `:243-248`. Настоящий документ — минимальный контракт стыка. Считаем, что перечисленное ниже **будет реализовано**; здесь фиксируем что и где.

Инварианты стыка в формулах. Валидность одобрения:

$$ \mathrm{valid}(S) \iff \operatorname{sha256}(\mathrm{bytes}(S)) = \mathrm{record.spec\_sha256} $$

Мандат области:

$$ \operatorname{allow}(r) = \left(\exists a \in A : \operatorname{match}(r,a)\right) \land \neg\left(\exists d \in D : \operatorname{match}(r,d)\right) $$

Привязка approval к корню:

$$ r_{16} = \operatorname{sha256}(\mathrm{root})[0:16], \qquad \mathrm{dir} = \mathrm{approvals}/r_{16}/ $$

Нарушение любого из трёх равенств обязано давать отказ, а не деградацию.

## 2. Контекст и текущая архитектура стыка

Сегодня kit перехватывает только вызовы инструментов с путями в аргументах: read-only allowlist, извлечение целей, fail-closed для неразбираемых писателей (`spec-gate-kit/config/plugins/spec-gate.ts:63-86,103,614-657,809-813`), порядок `spec-dir → docs → serena-cache → GATE-OFF → mandate` (`:676-708`), exemptions хоста (`:180-187`), аудит без влияния на решение (`:788-795,863-873`). Обходы признаны открыто: `bash`/`python -m *` мимо гейта (`spec-gate-kit/docs/adr/0001-gate-as-soft-guardrail.md:52-53,71,76-77`; `spec-gate-kit/docs/SPEC-OpenCode-Hardening.md:365-366,379-381`), `relative_path` от серверного корня Serena (`spec-gate-kit/docs/guides/spec-driven-development.md:820-822`), shell-пути `spec-new`/`dod-run` вне хука (`spec-gate-kit/docs/SPEC-OpenCode-Hardening.md:379-381`).

`oclab` уже имеет всё нужное как механизм, но не как контракт под kit: argv builder с `hardening` флагом (`opencode-lab/src/oclab/sandbox/bwrap.py:154-179`), единственная RW-точка `$HOME/work` (`:303-313`), per-env `.opencode` RO (`:316-321`), per-env данные/кэши RW (`:323-336`), пользовательские `read_only`/`read_write` (`:353-369`), memfd-канал + `--seccomp FD` до маски рантайма (`:397-400`), безусловная маска рантайма (`:402-405`), `--clearenv` + фиксированный `PATH` (`:408-412`, `:437-443`), запуск `opencode --standalone` с `hardening=True` (`opencode-lab/src/oclab/cmd_env.py:797-808,851-854`), лимиты через transient scope (`:856-860`), `pass_fds` (`:865-871`), композиция strict (`:873-879`, `opencode-lab/src/oclab/sandbox/strict.py:1-15`), генерация `.opencode` из реестра (`opencode-lab/src/oclab/config_builder.py:492-512`, `...:431-435`, `opencode-lab/src/oclab/tools.py:523-553`). Более того, oclab уже вызывает хостовые `bin/*` и approvals/audit kit-стиля (`opencode-lab/tools/gov/governance_check.py:43,53,387-392`, `opencode-lab/tools/gov/gate_scope_check.mjs:35,50`). Не хватает только явного проектного режима.

Схема слоёв (нормативная):

```text
+-------------------------------+  SOFT+HARD(userspace): мандат, UX, аудит
| OpenCode + spec-gate plugin   |  scope allow/deny, docs-immutable,
| scope/approvals/audit (host)  |  GATE-OFF, fail-closed writers
+---------------+---------------+
                | allow = scope-решение (совет)
+---------------v---------------+  HARD(kernel): исполнение, EROFS
| oclab env: bwrap/seccomp/     |  RO/RW mounts, Landlock, memfd,
| Landlock/memfd/strict/systemd |  netns, лимиты, doctor-gate
+-------------------------------+
```

Правило: плагин советует, ядро запрещает. Ни один слой не парсит `bash`.

## 3. Требования

| ID | Что нужно | Зачем kit'у | Точка в oclab (менять там) | P | Acceptance (проверяемо) | Риск если не сделать |
|---|---|---|---|---|---|---|
| R1 | `work` по исходному абс. пути проекта или `root_override` + `root_hash_override`: внутри env рабочий корень виден по тому же абс. пути, approval-хэш `r16` считается от хост-корня | Иначе `findRoot` (`spec-gate.ts:194-206`) и `approvalDir=rootHash` (`spec-gate.ts:231-237`) расходятся: одобрение на хосте не узнаётся внутри | `src/oclab/sandbox/bwrap.py:305-313` (всегда `$HOME/work`), `:393` guard-ветка; `src/core/task_argv.cpp:632,1339`, `src/core/task_argv.hpp:46-47` (`work_read_only` уже есть — расширить до `work_target_abs`) | P0 | Given проект `/h/P/x` с `r16`, when env поднят с `root_override`, then `realpath($OCLAB_WORK)==/h/P/x` или `sha256(real_root)==record.root_hash`, `spec-status --json` внутри видит `APPROVED`; `ctest -R argv_parity` зелен | Тихий split-brain: одобрено снаружи, заблокировано внутри (или наоборот); S2 невозможен |
| R2 | Инъекция kit-артефактов в генерируемый `.opencode/`: `spec-gate.ts` (плагин), `bin/{spec-status,dod-run,docs-lint,spec-approve,spec-revoke,gate-off,gate-on,spec_scope.py}`, подтверждение имени каталога `plugin` vs `plugins` под OpenCode v2.0.15 | Per-env конфиг RO (`bwrap.py:316-321`), хост `~/.config/opencode` никогда не монтируется (`docs/reference/file-layout.md:189-196`); без вендоринга внутри нет гейта вообще | `src/oclab/config_builder.py:492-512` (создаёт `agents,skills,command,plugin` `:495-496`, пишет `opencode.json` `:500-507`), `src/oclab/sandbox/bwrap.py:316-321` (RO-биндинг) | P0 | Given env с `kit: {plugin_src, bin_src}`, when `materialize_opencode_dir`, then `.opencode/plugin/spec-gate.ts` байт-в-байт равен источнику, `opencode.json: plugin[]` указывает на существующий путь, `opencode --standalone` стартует без `plugin load error`; e2e пишет без approval → `[SPEC-GATE BLOCKED]` | Внутри env нет гейта: ядро одно без мандата (см. отклонённую замену O3); silent open |
| R3 | Доставка `bin/*`+`spec_scope.py` в `PATH` либо документированный абс. вызов (`$OCLAB_KIT_BIN/spec-status`) | `PATH` внутри фиксирован и не переопределяем (`bwrap.py:437-443`, `schema.py:33-51` `RESERVED/UNOVERRIDABLE_ENV_KEYS`); агент не должен гадать где CLI | `src/oclab/sandbox/bwrap.py:437-443` (`PATH`), `src/oclab/schema.py:33-51` | P0 | Given env поднят, when `which spec-status` или `echo $OCLAB_KIT_BIN`, then вызов `spec-status --json` работает из `$HOME/work` без абс. хаков; `dod-run` пишет `verify/<id>.json` v2 | Агент вызывает не тот `dod-run`/не находит CLI; доказательства не пишутся, `DONE` недостижим |
| R4 | Approvals: RO-снапшот внутрь env; human `spec-approve` остаётся на хосте и никогда не исполняется внутри | Сегодня approvals exempt+RW на хосте (`spec-gate.ts:180-187`); внутри тот же путь обязан быть RO, иначе агент допишет себе одобрение | `src/oclab/sandbox/bwrap.py:353-369` (custom `read_only`), `src/oclab/config_builder.py:492-512` (материализация снапшота при создании env) | P0 | Given валидная запись `approvals/<r16>/<slug>.json`, when env стартует, then внутри тот же файл видим RO, `approvalScan` (`spec-gate.ts:502-546`) даёт `APPROVED`, попытка `write` в approvals внутри → `EROFS`; правка спеки снаружи → снапшот протухает до рематериализации | Агент самоодобряется; вся GOV-цепочка обесценивается |
| R5 | Audit: RW-фрагмент per-env (`$HOME/.local/share/opencode/audit/` уже RW per-env `bwrap.py:323-325`, кэши `...:327-336`), merge наружу при выходе/по команде с сохранением порядка и без потерь | Аудит-решения гейта (`spec-gate.ts:834-859`) внутри обязаны пережить env и сойтись с хост-журналом для разбора | `src/oclab/sandbox/bwrap.py:323-325`, `src/oclab/sandbox/launcher.py:47-96` (точка merge после `run_headless`/`launch_interactive`) | P0 | Given сессия с N gated-решениями, when env завершён, then хост-журнал вырос ровно на N строк, `ts` монотонны, `sessionID/root/reason/spec` intact; потеря 0 при kill (`--die-with-parent`, `bwrap.py:194`) проверена | Разбор обходов невозможен; gate превращается в трение без следа |
| R6 | Per-env H-токен сериализации тяжёлых прогонов и/или лимиты: одновременно не более одного `cmake --build -j2` / `ctest -j1` / полного `pytest` на 6-ядерном laptop (load 26.68), обёртка `nice/taskset/ionice`, `OMP_*=1` | Ноутбучная политика kit: тяжёлые шаги троттлятся и сериализуются; два параллельных env убивают хост | `src/oclab/cmd_env.py:856-860` (`wrap_with_systemd_run`, ADR-0005), `src/oclab/sandbox/launcher.py:47-96`, лимиты манифеста | P1 | Given два env, when оба запускают DoD-тяжёлый чек, then второй ждёт H-токен или респектит `CPUQuota=150%`, `loadavg < 8`, оба `verify/*.json` валидны; `dod-run` под троттлингом задокументирован | Взаимный OOM/thrash, ложные красные DoD, убитый хост |
| R7 | Doctor: fail-closed проверки `plugin_present+loadable`, `Landlock ABI`, `seccomp filter bytes==C++ twin`, `guard executable`, `strict-init/nft/pasta/userns` | Сегодня doctor покрывает binaries/systemd/userns/DNS/mounts/secrets (`src/oclab/doctor.py:91,121,144,163,193,252,366,383,985-1037`), но не слои принуждения — деградация молчаливая (`docs/adr/0018:112-116` требует проверки) | `src/oclab/doctor.py:985-1082` (`run_doctor_checks`, `_check_strict_egress:1014`, `_check_kernel_version:1037`), `src/oclab/sandbox/seccomp.py:1-14` (паритет), `src/oclab/sandbox/hardening.py:148-163` | P0 | Given ядро без Landlock или нет guard/seccomp, when `doctor`, then `FAIL` (не `WARN`) + запрет `env open --hardening`; Given паритет Python/C++ нарушен, then `sbx_seccomp` чек красный | Тихая деградация в голый bwrap; заявление `EROFS` ложно |
| R8 | Порты `19280/19281`: per-env offset или unix-socket broker | Фиксированные порты (`src/oclab/network.py:20-21`, `src/core/common.hpp:25-28`, `src/oclab/config_builder.py:28-32`) коллидируют при параллельных env | `src/oclab/network.py:20-21`, `src/oclab/config_builder.py:28-32,122-123`, `src/oclab/doctor.py:668` | P1 | Given два env параллельно, when оба поднимают broker/egress-proxy, then оба `open` успешны, `doctor` без `EADDRINUSE`, `strict` `http_proxy` указывает на свой инстанс (`bwrap.py:469-473`) | Второй env не стартует или ходит в чужой broker — кросс-проектная утечка токенов |
| R9 | Исправить блокеры §11 (`docs/SPEC-OpenCode-Hardening.md:243-248`): (a) symlink `/etc/resolv.conf` через tmpfs родителя+bind файла (`docs/reference/file-layout.md:202-203`, `bwrap.py:293-295`); (b) `permissions` (plural) → `permission` (singular) в генераторе (`config_builder.py:441-444` ставит оба — подтвердить канон v2.0.15); (c) явный запрет/подтверждение профиля `host` (`--dev-bind / /`, `bwrap.py:219-253`); (d) задокументировать что `dns-only` делит host netns/loopback (`isolation-model.md:94-103,238-245`) | Без этого kit-env либо без DNS, либо без гейта (конфиг не читается), либо с ложным чувством изоляции | Те же файлы + `docs/SPEC-OpenCode-Hardening.md:230-249` | P0 для (a)(b), P1 для (c)(d) | (a) env стартует на хосте с symlink resolv.conf, DNS внутри работает; (b) сгенерированный `opencode.json` валидируется живой v2.0.15 без варнингов; (c) `host` требует интерактивного подтверждения и запрещён для root (`bwrap.py:180-181`); (d) `egress.md`-нота в `env open --help` | Повторение уже диагностированных падений S1 |
| R10 | x86_64-ограничение seccomp: явный гейт + диагностика (arch-kill, hardcoded numbers) | Фильтр байт-в-байт с C++ (`seccomp.py:1-14`) собран под одну arch; на другой — либо дыра, либо смерть | `src/oclab/sandbox/seccomp.py:37-125`, `src/oclab/sandbox/hardening.py:250-255`, `src/oclab/doctor.py:1037` (`_check_kernel_version`) | P1 | Given `uname -m != x86_64`, when `env open --hardening`, then понятный отказ до `exec` + `doctor` `FAIL` с объяснением; Given x86_64, then `argv_preview --dump-seccomp` совпадает побайтово | Неявный отказ/ложная защита на ARM |
| R11 | MCP/loopback-контракт: stdio MCP внутри песочницы, service MCP только через loopback в `dns-only`, local MCP (serena/jupyter/memory) — явная матрица проброса сокета/бинаря; `.opencode` RO означает MCP привозит реестр, а не хост | Сегодня MCP материализуется из реестра (`tools.py:523-553` → `config_builder.py:431-435`), хост-конфиг не шарится (`isolation-model.md:123-126`); kit-агенты без serena неработоспособны | `src/oclab/tools.py:523-553`, `src/oclab/config_builder.py:431-435,450-464`, `src/oclab/cmd_env.py:808` (`materialize_opencode_dir`) | P1 | Given env с `tools=[serena]`, when сессия стартует, then `mcp.serena` резолвится внутри, `relative_path` записи покрыты гейтом; Given `strict`, then service MCP идёт через `10.0.2.2`, не через host-loopback | Агент без инструментов или с доступом к хостовым loopback-сервисам (токен-брокер) в `dns-only` |

## 4. Минимальный manifest-контракт (предложение)

```yaml
# oclab env для spec-gate-kit проекта. Один env == один project_root.
apiVersion: oclab/v1
kind: env
name: spec-kit-pilot
project:
  root_host: /home/u/Projects/demo
  root_hash_override: "01a008314dd39430"  # r16 хост-корня; R1
  work_mode: bind_abs             # bind исходного абс. пути, не копия
  work_read_only_when: "no-approval"  # RO до APPROVED, затем scoped-RW
kit:
  plugin_src: /home/u/Projects/spec-gate-kit/config/plugins/spec-gate.ts
  bin_src: /home/u/Projects/spec-gate-kit/config/bin
  scope_lib: spec_scope.py
  plugin_dir_name: plugin         # подтвердить под v2.0.15; R2
  kit_bin_env: OCLAB_KIT_BIN      # + PATH fallback; R3
approvals:
  snapshot_host_dir: ~/.local/share/opencode/approvals/<r16>
  mount: ro                       # R4; запись только хостом
audit:
  fragment: $HOME/.local/share/opencode/audit/spec-gate.jsonl  # RW; R5
  merge_on: [exit, env-close]
sandbox:
  hardening: true                 # seccomp+Landlock+memfd+guard; R7 гейтит
  egress: dns-only                # strict только в S3
  limits: { cpu: "150%", mem: 4G }  # + H-token сериализация; R6
  broker_port: auto               # offset/unix-socket; R8
```

Поведение монтирования: `work` — `bind`/`ro-bind` по `work_read_only_when` (`bwrap.py:305-313`, `task_argv.cpp:1339`); `.opencode` — всегда RO (`bwrap.py:316-321`); данные/аудит/кэши — RW per-env (`:323-336`); кастомные пути только через `read_only`/`read_write` (`:353-369`); `PATH` и охраняемые ключи не переопределяются (`bwrap.py:437-443`, `schema.py:33-51`).

## 5. План внедрения S1/S2/S3 с триггерами

**S1 — kit-only (нулевые изменения oclab; всё внутри `spec-gate-kit/`).** Эмиттер манифеста из `scope`+approval (`root`, `r16`, `allow/deny`, `plugin_src/bin_src`), `argv-preview` сверка с каноном bwrap, префлайт `doctor`-обёртка (guard/seccomp/Landlock/`plugin`-имя/`permission`-singular), аудит-merge спецификация (порядок, идемпотентность, HMAC-заготовка), `dod-run`-в-headless dry-run. Триггер S2: S1 `DONE` по evidence v2 ($\forall c: exit\_code=0 \land spec\_sha256\ match \land tree\_dirty=false$) + человек одобрил + oclab HEAD собирает guard и проходит новый `doctor`.

**S2 — один пилотный проект в hardened env (адаптация oclab: R1–R5,R7,R9ab).** `root_override` + RO-снапшот approvals + RW-фрагмент аудита с merge + вендоринг плагина/`bin` + `PATH`/`OCLAB_KIT_BIN` + fail-closed doctor + фиксы resolv.conf/`permission`. Режим `dns-only`, профиль не-`host`. Триггер S3: пилот показывает ноль случайных вне-`scope` записей через обход `bash`/`python -c` (попытка → `EROFS`), ноль потерь аудита при kill, `19280/19281` разведены.

**S3 — strict + сериализация + цепочка.** `strict` egress без деградации (`strict.py:13-15`), H-токен/лимиты (R6), порты (R8), x86_64-гейт (R10), MCP-матрица (R11), HMAC/audit-chain поверх merge. Триггер: стабильный S2 на двух параллельных env + зелёный расширенный `doctor`.

## 6. Открытые вопросы к мейнтейнерам oclab

1. Каноническое имя каталога плагинов: `plugin` vs `plugins` в генерируемом `.opencode/` под OpenCode v2.0.15? Генератор создаёт `plugin` (`config_builder.py:495-496`); SPEC kit §11 подозревает mismatch (`SPEC-OpenCode-Hardening.md:243-248`). Подтвердите живым стартом и зафиксируйте в схеме.
2. Канон `permission` vs `permissions`: генератор ставит оба (`config_builder.py:441-444`); что читает бинарь v2.0.15 — singular, plural, merge? Нужен один источник истины, иначе R9b недоказуем.
3. Готовы ли принять `root_override`/`work_target_abs` (R1) или предпочитаете жёстко `$HOME/work`-копию + ремаппинг `r16` на стороне kit? Второй вариант держит ядро чистым, но вводит вторую истину о корне.
4. Merge аудита (R5): хук в `launcher.py:47-96` достаточен или нужен демон-side `StartTransientUnit` хук? Требование — ноль потерь при `--die-with-parent`.
5. Брокер (R8): offset портов или unix-socket по умолчанию? Что дешевле при сохранении `STRICT_BROKER_BASE_URL=http://10.0.2.2:19280/v1` (`config_builder.py:28-32`)?
6. Serena-внутри (R11): бинарь+сокет пробрасываем как `read_only` бинд или пересобираем MCP из реестра внутри (`tools.py:523-553`)? Как закрываете `relative_path` рассинхрон (`spec-driven-development.md:820-822`)?
7. `host`-профиль (`bwrap.py:219-253`): вводим интерактивное подтверждение + неизменяемый audit-маркер, или kit просто запрещает `host` в своём эмиттере?

## 7. Non-goals (kit явно НЕ просит)

- **uid-split / DynamicUser сейчас.** Признан отдельной линией (`docs/adr/0018:128-130`, `isolation-model.md:210-213`); состав остаётся same-UID typo-guard, не adversary boundary.
- **microVM / rootful systemd / `pivot_root`/`chroot`.** Последние seccomp-заблокированы по дизайну; kit просит только существующую композицию bwrap→seccomp→Landlock→netns.
- **CoW-btrfs бэкенд + qgroup + GC в S1/S2.** Дизайн-only (ADR-0017/19); пилоту достаточно `bind`/`ro-bind` (R1).
- **Парсинг `bash` в гейте.** Отклонён как гонка вооружений (`0001:76-77,83-86`); ядро закрывает последствие (`EROFS`), не строку.
- **Per-agent allowlist в хуке, шифрованный `keyctl`-бэкенд секретов, глобальный cgroup-бюджет, ARM-порт seccomp.** Все — отдельные волны; S1/S2 их не требуют.
- **Замена плагина ядром.** Плагин остаётся источником мандата/UX/аудита; ядро — источником запрета. Любая оптимизация, убивающая `scope`/`docs-immutable`/`GATE-OFF`/audit-различимость, — отказ по дизайну.
