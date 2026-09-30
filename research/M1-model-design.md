# M1 — Модель конвейера и пространство политик (DES для M2)

> Контекст: `research/README.md:42-50` — Ф3 моделирует организацию **при HARD-субстрате oclab**; `research/SYNTHESIS.md:5` — keep+harden + 3 примитива; допущение задачи — bwrap/Landlock/seccomp, work по исходному пути, плагин+`bin/` внутрь, approvals RO-in, audit merge-out, systemd-scope лимиты, multi-env. Субстрат: `docs/explanation/isolation-model.md:136-161` (opencode-lab), `docs/adr/0018-sandbox-enforcement-layers.md:47-73`, `docs/adr/0005-resource-limits-systemd-run.md:18-21`, `src/oclab/sandbox/bwrap.py:194` (`--die-with-parent`).

## 1. Формальная модель (дискретно-событийная)

**Состояние** в момент $t$ (единственный источник правды — выводимое состояние + git + evidence; ср. `README.md:81-86`, `docs/adr/0003-derived-lifecycle-state.md`):

$$X(t)=\left(G(t),\,d(t),\,\{s_i,h_i,a_i,E_i\}_{i\in C},\,Q(t),\,H(t),\,L(t),\,A(t),\,w(t),\,H_n(t),\,C_{\$}(t)\right)$$

- $C=\{1..N\}$ — контракты волны; $G=(C,E_{dep})$ — DAG зависимостей.
- $G(t)=\text{HEAD}$, $d(t)\in\{0,1\}$ — `tree_dirty`.
- $s_i\in\{\text{INTAKE},\text{SPEC\_DESIGN},\text{APPROVED},\text{VERIFY},\text{DONE},\text{FAILED},\text{BLOCKED}\}$ — выводится `spec-status` (`config/bin/spec-status`), не хранится.
- $h_i=\operatorname{sha256}(\text{spec}_i)$; $a_i\in\{0,1\}$ — валидный approval ($h_i=\text{record.spec\_sha256}$).
- $E_i=\{(e_{ij},x_{ij},\hat{h}_{ij},\hat{G}_{ij},\hat{d}_{ij},\tau_{ij})\}_j$ — evidence чека $j$: exit, sha-совпадение, head, dirty, длительность.
- $Q=(Q_{recon},Q_{write},Q_{heavy},Q_{verify})$ — очереди (`research/S2-scheduling.md:73`).
- $H(t)\in\{0..H_{max}\}$ — свободные тяжёлые токены ($H_{max}=1$ laptop; $>1$ при multi-env); $L(t)$ — лёгкие слоты ($N=2$, `config/oh-my-opencode-slim.json:17-25`).
- $A(t)$ — очередь к человеку (approvals); $w(t)$ — id волны; $H_n(t)$ — голова hash-цепи аудита ($H_n=\operatorname{sha256}(H_{n-1}\Vert\mathrm{canon}(entry_n))$, `research/SYNTHESIS.md:34`); $C_{\$}(t)$ — накопленная стоимость.

**Генерация работы:** запрос $\to$ $N$ контрактов, $N\sim \text{Empir}(\approx 6\text{--}16)$; ребро зависимости с вероятностью $p_{dep}$ (типы: interface/data/migration, `research/S2-scheduling.md:21`). Гранулярность: 1–8 путей в `scope.allow`, один владелец (`research/S2-scheduling.md:24-26`).

**События и динамика** (симулятор M2 реализует как очередь событий с приоритетами):

1. `draft(i)`: $\tau\sim \text{LogN}(\mu_{draft})$; затем `lint`: pre-approval кросс-спек проверка (`scope`, канон, уник. `dod.id`, writer-map; `research/S2-scheduling.md:19`).
2. `approve_request(B)$: батч $B$; человек — сервер с $S_a\sim \text{Exp}(\lambda_a^{-1})$ + фиксированная полоса; `--all/--changed` = сервис только для $\Delta B$ (`docs/notes/2026-09-28-orchestrator-improvement-report.md:198-199`).
3. `dispatch(i)$: $i$ is READY $\iff a_i=1 \wedge \forall j\to i: s_j=\text{DONE} \wedge \text{writer-map}(i)\cap \text{busy}=\emptyset$.
4. `heavy\_acquire/release`: любой `cmake/ctest/pytest-full/e2e/ASan` держит 1 токен $H$ эксклюзивно; лёгкое (recon/lint/`spec-status --json`/draft) — слот $L$ (`research/S2-scheduling.md:57-61`).
5. `dod(i)$: $k_i$ чеков, длительности $\tau_{ij}$; дедуп: уникальная доля $u\approx 0.20$–$0.25$ (`research/S6-economics.md:42`):
$$T_{wave}\approx \frac{1}{H}\sum_{c\in heavy}T_c+\max_{l\in light}T_l,\quad T'_{wave}\approx u\,T_{wave}+T_{tail}.$$
6. **Staleness (два яруса, `research/SYNTHESIS.md:32`):** сертификация $\text{stale}_{cert}=(\hat{G}_{ij}\neq G(t))\lor d(t)$ (`README.md:85`); планирование $\text{stale}_{scope}(i)=(\text{scope.allow}(i)\cap \Delta F\neq\emptyset)\lor(\text{dod-inputs}(i)\cap\Delta F\neq\emptyset)$. Политика B/C решает, что реранить; DONE всегда по $\text{stale}_{cert}$.
7. **Retries/R6:** на чек $\le 3$ попыток, задержка $d_k=\min(d_{max},d_0 2^k)+U(0,j)$ (`research/S2-scheduling.md:42-46`); 4-е подряд падение одного чека / противоречие спек / риск потери / env-критика $\Rightarrow$ `BLOCKED` + стоп-волна (R6 — policy line, счёт из audit-журнала).
8. **Rework-раунды:** после сдачи батча с вероятностью $q$ (канон/scope/id-дефект) $\to$ правка спеки $\to$ инвалидация $a_i$ и $E_i$ (hash-правило, `README.md:75-77`) $\to$ новый раунд. Число раундов $R\sim \text{Geom}(1-q)$; наблюдалось $R=3$ (`research/S2-scheduling.md:7`).
9. **oclab-проекция:** каждый write-лейн $i$ живёт в своём env $e(i)$: свой CoW-work (`isolation-model.md:167-185`), свои кэши per-env (`isolation-model.md:70-72`), RW только $\text{scope.allow}(i)$ (Landlock RW `<sandbox>/**`, ADR-0018), лимиты через transient scope systemd, approvals/audit — RO-in / merge-out. Конфликт файлов/портов внутри env невозможен по построению; кросс-env — только через git-merge + `wave_id` в evidence (`research/S5-reliability.md:21`).

Инвариант сертификации (проверяется симулятором каждый шаг):

$$\text{DONE}_i \iff a_i=1 \wedge \forall j: (e_{ij}=0 \wedge \hat{h}_{ij}=h_i \wedge \hat{G}_{ij}=G(t) \wedge \hat{d}_{ij}=0).$$

## 2. Параметры + калибровка

| Параметр | Значение / prior | Источник |
|---|---|---|
| $N$ (контрактов/волна) | 6 (батч), 16 (волна) | `orchestrator-improvement-report.md:48,172`, `README.md:155-166` |
| $T_{wave}$ full | $\approx 14$ мин / 16 контрактов | `README.md:155-166` |
| Дедуп $u$ | $0.20$–$0.25$ уникального; 155 чеков/волна: `pytest` 14×, `ruff` 15×, `ctest` 3–5× | `README.md:159-166`, `S6-economics.md:42` |
| $H_{max},L$ laptop | $H=1$, $N_{light}=2$; `cmake -j2`, `ctest -j1`, `nice/taskset/ionice`, loadavg 26.68 | `config/AGENTS.md:Known Caveats`, `S2-scheduling.md:50-55` |
| $H_{max}$ oclab | $H=E$ (#env), лимит пула (демон не стартует сверх остатка) | `adr/0005-resource-limits-systemd-run.md:18-21`, `isolation-model.md:90-92` |
| Стоимость | Subagents $\approx\$1.00$/18 сессий; 6 draft $\approx\$0.70$ ($\approx 70\%$); оркестратор $\approx\$0.17$ ($N_{in}=448396$, $N_c=4.7M$) | `orchestrator-improvement-report.md:87-97`, `S6-economics.md:27-34` |
| $r=N_c/N_{in}$ | $\approx 13.7$ (60.4M/4.4M) | `S6-economics.md:30-32` |
| Контекст | 200–290k input/draft, 50–70k reasoning, 0 `compress`/18 сессий | `orchestrator-improvement-report.md:87-97` |
| Approvals | $\ge 12$/сессия, $R=3$ раунда инвалидации | `orchestrator-improvement-report.md:48,198-199` |
| $p_{dup-id}$ (flat-store) | 6 общих id $\to$ 2 спеки никогда не DONE одновременно | `dod-run-flat-store-collision.md:8-15,27-34` |
| Stale | глобальное: любой commit инвалидирует всё | `README.md:81-86`, `S5-reliability.md:20` |
| Цены (маршрутизация) | deepseek-flash in \$0.15–0.30/M, cache \$0.003–0.006; council architect glm-5.3 \$1.40/M, cap \$15/220 req | `S6-economics.md:11-23` (по [opencode.ai/docs/go](https://opencode.ai/docs/go/), [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/)) |
| Flake/надёжность | нет данных $P(\text{false DONE})$; denylist-театр; harness врёт зелёным | `repo-audit-2026-09-29.md:112-122,89-102` |
| Внешние эффекты (priors) | fan-out +90.2% research, ~15× токенов ([Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)); ReWOO 5× экономия ([arXiv:2305.18323](https://arxiv.org/abs/2305.18323)); PBT ловит реальные баги ([Anthropic PBT](https://www.anthropic.com/research/property-based-testing)); attestation SLSA/Sigstore ([slsa.dev](https://slsa.dev/spec/v1.2/faq)); durable-исполнение ([Temporal](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution)) | `research/S1-paradigms.md:13-27` |

M3 должен заменить priors замерами `verify/*.json` + `spec-gate.jsonl` (распределения $\tau_{ij}$, $q$, $S_a$, flake-перезапуски).

## 3. Пространство политик

- **A — status quo.** Per-contract полный DoD, глобальный re-wave после каждого commit, flat-store + конвенция префиксов (`dod-run-flat-store-collision.md:48-56`). База для сравнения. Цена: $T_{wave}\approx 14$ мин, повтор 75–80%; риск: коллизия при забытом префиксе.
- **B — дедуп + stateless `wave-run`.** Один владелец полного сьюта, остальные — своя поверхность; union `dod`, один прогон на волну, $H=1$ throttle, port/build-локи (`README.md:162-166`, `SYNTHESIS.md:19`). Эффект: $14\to\approx 4$–$5$ мин. Цена: батч-правка `dod`-фенсов + 1 re-approve; риск: владелец сьюта — SPOF волны.
- **C — scope-shallow staleness + `dod-run --changed`.** Перезапуск только при $\text{stale}_{scope}=1$; DONE по-прежнему по $\text{stale}_{cert}$ (`SYNTHESIS.md:32`). Эффект: инкрементальные коммиты дёшево. Цена: нужен `scope_sha256` + учёт dod-inputs/toolchain; риск: пропуск инвалидации (ложный fresh) — главный объект проверки M4.
- **D — параллельные oclab-env ($H>1$, single-writer).** $E$ env-ов, в каждом RW только свой `scope.allow` (Landlock), work смонтирован по тому же абсолютному пути (убирает класс "у меня другой путь"), approvals RO, audit merge по $w(t)$, лимиты systemd-scope. Эффект: линейный рост throughput по независимым контрактам. Цена: диск/память на env, GC сабволюмов (ADR-0019); риск: конкуренция за CPU/IO на 6 ядрах, merge-конфликты work-копий.
- **E — risk-weighted / verification-sampling.** Полный сьют один раз на волну (владелец B); остальные контракты — свой scope-сьют + сэмпл общих чеков с вероятностью $s$ (стратификация по риску: touched-ядро/seccomp/изоляция — всегда полно). Эффект: −$(1-s)$ стоимости верификации. Цена/риск: рост $P(\text{false DONE})$; требует модели flake (нет данных — M3) и карантина flaky-id (`S5-reliability.md:16`).
- **Комбинации:** **B+C** — инкрементальный дедуп-раннер (фаворит P1, `SYNTHESIS.md:54-61`); **B+C+D** — целевая "фабрика" (дедуп + shallow + $E$ env); **B+C+E$_{cons}$** — консервативный сэмплинг ($s=1$ для ядра/границ доверия, $s<1$ для док/шаблонов); **D+E$_{aggr}$** запрещена до M4 (параллелизм × сэмплинг скрывает источник зелености).

## 4. Метрики (все — из существующих стоков, `S6-economics.md:67-84`)

$T_{\text{DONE}}$ (wall-clock запрос$\to$все DONE); $C_{\$}$/сессия и /волна ($C=p_{in}N_{in}+p_cN_c+p_{out}(N_{out}+N_{reason})$); число human-approvals (цель 12+$\to$1–2); rework-раунды $R$; $P(\text{false DONE})$ (симуляция впрыскивает flake $f$ и пропуск shallow-инвалидации $m$); throughput (DONE/час); tail $p95$ волны; approvals-churn; first-pass DoD rate; wave-staleness (чек/коммит); lane-discipline (ходы/лейн, abort); качественный флаг **verification theater** (доля зелёных волн при $m>0\lor f>0$ без карантина — детектор самообмана E).

## 5. Фальсифицируемые гипотезы

- $H_1$ (дедуп): B даёт $T'_{wave}\le 0.4\,T_{wave}$ при том же множестве дефектов. Опровергнута, если $u>0.5$ на реальных `verify/*.json`.
- $H_2$ (shallow soundness): C сокращает число реранов $\ge 2\times$ при $\Delta P(\text{false DONE})\approx 0$. Опровергнута, если хоть один случай $\text{stale}_{scope}=0\wedge\text{stale}_{cert}=1$ с пойманным дефектом (M4-контрпример).
- $H_3$ (параллелизм): D с $E=2$–$3$ и single-writer даёт $\ge 1.5\times$ throughput без роста flake. Опровергнута, если flake-rate или $p95$ растёт $>20\%$ vs $H=1$.
- $H_4$ (сэмплинг): E с $s=0.3$ вне ядра держит $P(\text{false DONE})\le 10^{-3}$ при −50% стоимости verify. Опровергнута симуляцией при откалиброванном $f$ из M3.
- $H_5$ (pre-lint): кросс-спек lint + `--changed` снижает approvals $12\to\le 3$ и $R:3\to 1$. Опровергнута, если доминирует человеческая правка содержания (не формы).
- $H_6$ (изоляция): в oclab кросс-env интерференция $=0$ (порты/кэши/файлы), и work-по-абс-пути убирает класс path-дрейфа. Опровергнута первым зафиксированным кросс-env инцидентом.
- $H_7$ (экономика): draft-стоимость падает $\ge 30\%$ от брифинг-контракта + шаблона (не от модели). Опровергнута A/B: тот же бриф на том же tier без изменения $C$.

## 6. Проверки на артефакт (M2 обязан вшить, M4 — перепроверить)

1. $\text{DONE}\Rightarrow$ все чеки green+свежие+sha-match (ассерт каждый шаг; тест на данных `dod-run-flat-store-collision.md:19-34` обязан показать stuck-VERIFY до неймспейса).
2. Состояние целиком выводимо из (спеки, approvals, `verify/`, git HEAD/dirty) — запрет второго truth-файла; property-тест: удалить весь scheduler-state $\Rightarrow$ тот же `spec-status --json`.
3. Монотонность: commit без изменения scope $\Rightarrow$ $\text{stale}_{cert}=1$, $\text{stale}_{scope}=0$ (различение ярусов обязано наблюдаться).
4. Границы: $N=1$ (волна = контракт); $p_{dep}=0/1$ (параллель/цепочка); $H\to\infty$ (нижняя грань = критпуть DAG); задержка человека $0/\infty$ (асимптоты $T_{\text{DONE}}$); $f=0/1$, $m=0/1$ (калибровка шкалы theater).
5. Консервация: сумма $C_{\$}$ по лейнам = $C_{\$}$ волны; union чеков B = multiset чеков A минус дубли (diff-отчёт).
6. Детерминизм: фиксированный seed $\Rightarrow$ бит-в-бит одинаковые траектории и метрики (M2 хранит seeds в логе прогона).

## 7. Открытые вопросы (в M3/M4)

1. Входят ли dod-inputs/toolchain/фикстуры в $\text{stale}_{scope}$, и кто версионирует `scope_sha256`?
2. Неймспейс `verify/<slug>/<id>.json`: flat-fallback навсегда или однократная миграция с batch re-approve?
3. Где живёт токен $H$ при multi-env — декорреляция в `wave-run --lock` или демон/пул oclab (ADR-0004/0005)?
4. Порог сэмплирования E: какие классы чеков никогда не сэмплируются, какие $n$ подряд-зелёных для flaky?
5. Как writer-map переживает merge $E$ work-копий (кто резолвит пересечение `scope.allow`)?
6. Метрика $P(\text{false DONE})$: откуда взять $f$ (flake-база из M3 достаточна или нужен отдельный fault-injection стенд)?
7. Человеческая полоса: измеряемая $S_a$ и эффект `--all` — масштабируется ли approve-батчинг на $N>20$ или нужна coarsening-гранулярность?

**Передача в M2:** DES-события §1 + параметры §2 как priors с seed-логом; сравнить A/B/C/D/E/B+C/B+C+D по метрикам §4; принимать только при прохождении проверок §6; вход калибровки — реальные `verify/*.json`, `spec-gate.jsonl` (M3), инвариант DONE — нерушим.
