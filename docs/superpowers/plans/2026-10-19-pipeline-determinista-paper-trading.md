# AutoHedge: pipeline determinista + paper trading — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir AutoHedge en un sistema medible: datos de mercado reales calculados en código, orden fijo Director → Quant → Riesgo → Ejecución, veto de riesgo en código (no en un LLM), solo paper trading, y un registro de cada recomendación que se puede evaluar contra lo que pasó después en el mercado.

**Architecture:** Los LLM hacen solo dos cosas, y siempre devuelven JSON validado con pydantic: el Director propone tesis y el Quant interpreta un snapshot de indicadores que se calcularon en Python a partir de datos de Yahoo Finance. El riesgo, el tamaño de la posición, el stop, el take-profit y la orden son funciones puras y deterministas. Cada corrida agrega filas a un ledger JSONL. `autohedge evaluate` mide cada recomendación contra las velas posteriores y la compara con buy-and-hold.

**Tech Stack:** Python ≥3.10, pydantic v2, yfinance, swarms (`Agent`, vía litellm), rich, pytest.

**Spec:** Sección "Requisitos" de este documento. Salen de la auditoría del 2026-10-19 en la conversación, que encontró cuatro problemas: el Quant no recibe datos, el orden de los agentes lo decide el LLM, el riesgo no puede vetar, y no hay forma de medir resultados.

## Requisitos

1. El Quant trabaja sobre datos reales. Los indicadores se calculan en código y el LLM no inventa números.
2. Las etapas Director → Quant → Riesgo → Ejecución corren en ese orden, fijado en código.
3. El riesgo es una regla determinista con poder de veto. Si veta, no se genera orden.
4. El modo por defecto, y el único disponible, es paper. Ejecutar en vivo queda bloqueado con un error explícito.
5. Toda recomendación, aprobada o vetada, queda registrada con sus razones.
6. Hay un comando que mide los aciertos de las recomendaciones (win rate, expectancy y comparación con buy-and-hold) antes de considerar capital real.

## Global Constraints

- Rama de trabajo: `feat/pipeline-determinista`. Repo local clonado; no hay permisos de push al upstream.
- Estilo: `line-length = 70` (ruff/black, ya en `pyproject.toml`), `loguru` para logs, docstrings estilo numpy como en `autohedge/tools/`.
- Ningún módulo nuevo importa `autohedge.tools.ultra_tools` (firma y ejecuta transacciones).
- `AUTOHEDGE_MODE` default `"paper"`; cualquier otro valor → `ConfigError("live trading is not implemented; only AUTOHEDGE_MODE=paper is supported")`.
- Modelo LLM: `AUTOHEDGE_MODEL`, default `"gpt-4.1"` (litellm acepta también `claude-*` si se usa `ANTHROPIC_API_KEY`).
- Defaults de `RiskPolicy` (todos sobreescribibles por env `AUTOHEDGE_<CAMPO_EN_MAYÚSCULAS>`): `equity_usd=10_000`, `min_conviction=0.6`, `min_probability_up=0.55`, `max_position_pct=0.05`, `risk_per_trade_pct=0.01`, `stop_atr_mult=2.0`, `take_profit_r=2.0`, `max_annual_vol=1.20`.
- Costo asumido en evaluación: `FEE_ROUND_TRIP_PCT = 0.30` (en %).
- Mínimo de historia para indicadores: 60 velas diarias.
- Ledger por defecto: `outputs/ledger.jsonl`.
- Símbolos en formato Yahoo (`NVDA`, `SOL-USD`).
- Tests sin red: yfinance y LLM siempre se reemplazan con fakes/monkeypatch.

## Review Focus

1. **Ticker sin datos** (inventado por el Director, deslistado, o Yahoo con rate-limit que devuelve vacío). Lo esperado: la recomendación queda vetada con `reasons=["no_market_data"]`, el resto del lote sigue y no hay crash. Test en Task 5.
2. **El LLM responde JSON envuelto en ```json``` o con texto alrededor, o JSON inválido.** Lo esperado: se extrae el JSON si se puede. Si no se puede, la recomendación queda vetada con `"invalid_llm_output"`. Si falla el Director, se registra una sola fila vetada para la tarea. Tests en Task 4 y Task 5.
3. **Historia corta (menos de 60 velas, como un token recién listado) o velas con NaN.** Lo esperado: veto `"insufficient_history"` y nunca una división por cero o un NaN en la orden. Tests en Task 2 y Task 5.
4. **Evaluar recomendaciones cuyo horizonte todavía no venció, o cuya orden límite nunca se llenó.** Lo esperado: cuentan como `pending` o `unfilled` y no entran en el win rate. Test en Task 6.
5. **Vela que toca el stop y el take-profit el mismo día.** Lo esperado: se cuenta como pérdida (supuesto conservador). Test en Task 6.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `autohedge/schemas.py` (nuevo) | Modelos pydantic compartidos + `ConfigError` |
| `autohedge/config.py` (nuevo) | `RiskPolicy.from_env()`, `get_mode()`, `get_model_name()` |
| `autohedge/market_data.py` (nuevo) | Descarga de velas (yfinance) e indicadores puros |
| `autohedge/risk_gate.py` (nuevo) | Veto, sizing, stop/TP y `OrderProposal` |
| `autohedge/llm_io.py` (nuevo) | Extraer y validar JSON de respuestas LLM |
| `autohedge/ledger.py` (nuevo) | Append/lectura de `ledger.jsonl` |
| `autohedge/pipeline.py` (nuevo) | Orquestación fija con dependencias inyectables |
| `autohedge/evaluation.py` (nuevo) | Scoring de recomendaciones y reporte |
| `autohedge/workers.py` (reescribir) | Fábrica de los dos LLM (Director, Quant) |
| `autohedge/prompts.py` (modificar) | Agregar `DIRECTOR_JSON_PROMPT`, `QUANT_JSON_PROMPT` |
| `autohedge/main.py` (modificar) | `AutoHedge.run` delega en `run_pipeline` |
| `autohedge/cli.py` (modificar) | Subcomandos `run` y `evaluate`; REPL usa el pipeline |
| `.env.example`, `README.md`, `pyproject.toml` | Variables correctas, docs, pytest |
| `tests/` (nuevo) | Un archivo de test por módulo |

---

### Task 1: Esquemas y configuración

**Files:**
- Create: `autohedge/schemas.py`, `autohedge/config.py`, `tests/__init__.py`, `tests/test_config.py`
- Modify: `pyproject.toml` (agregar grupo `[tool.poetry.group.dev.dependencies]` con `pytest = "*"`), `.env.example`

**Interfaces:**
- Produces (en `autohedge/schemas.py`):
  - `class ConfigError(Exception)`
  - `Bar(date: datetime.date, open: float, high: float, low: float, close: float, volume: float)`
  - `MarketSnapshot(ticker: str, as_of: date, last_close: float, sma_20: float, sma_50: float, rsi_14: float, atr_14: float, vol_20d_annual: float, return_20d_pct: float, return_60d_pct: float, high_52w: float, low_52w: float, n_bars: int)`
  - `Thesis(ticker: str, direction: Literal["long","flat"], conviction: float [0,1], horizon_days: int [1,90], rationale: str)`
  - `DirectorOutput(theses: list[Thesis])` (min 1, max 5)
  - `QuantView(probability_up: float [0,1], expected_move_pct: float, summary: str)`
  - `OrderProposal(ticker: str, side: Literal["buy"], order_type: Literal["limit"], entry_price: float, quantity: float, stop_loss: float, take_profit: float, notional_usd: float, expires_after_days: int)`
  - `RiskDecision(approved: bool, reasons: list[str], order: OrderProposal | None)`
  - `Recommendation(id: str, created_at: datetime (UTC), task: str, ticker: str | None, mode: Literal["paper"], approved: bool, reasons: list[str], thesis: Thesis | None, quant: QuantView | None, snapshot: MarketSnapshot | None, order: OrderProposal | None)`
  - Los rangos `[a,b]` se implementan con `Field(ge=a, le=b)`.
- Produces (en `autohedge/config.py`):
  - `@dataclass(frozen=True) class RiskPolicy` con los 8 campos y defaults de Global Constraints; `@classmethod from_env(cls) -> RiskPolicy`
  - `get_mode() -> Literal["paper"]` (lanza `ConfigError`)
  - `get_model_name() -> str`

- [ ] **Step 1: Write the failing tests** en `tests/test_config.py`

```python
def test_mode_defaults_to_paper(monkeypatch):
    monkeypatch.delenv("AUTOHEDGE_MODE", raising=False)
    assert get_mode() == "paper"

def test_live_mode_is_blocked(monkeypatch):
    monkeypatch.setenv("AUTOHEDGE_MODE", "live")
    with pytest.raises(ConfigError, match="live trading is not implemented"):
        get_mode()

def test_policy_defaults(monkeypatch):
    for k in list(os.environ):
        if k.startswith("AUTOHEDGE_"):
            monkeypatch.delenv(k)
    p = RiskPolicy.from_env()
    assert (p.equity_usd, p.max_position_pct, p.risk_per_trade_pct) == (10_000, 0.05, 0.01)

def test_policy_env_override(monkeypatch):
    monkeypatch.setenv("AUTOHEDGE_EQUITY_USD", "2500")
    assert RiskPolicy.from_env().equity_usd == 2500.0

def test_thesis_rejects_out_of_range_conviction():
    with pytest.raises(ValidationError):
        Thesis(ticker="NVDA", direction="long", conviction=1.5, horizon_days=10, rationale="x")
```

- [ ] **Step 2: Run** `pytest tests/test_config.py -v` → FAIL (`ModuleNotFoundError: autohedge.config`)
- [ ] **Step 3: Implement** `schemas.py` y `config.py` según Interfaces. En `from_env`, un valor de env no numérico → `ConfigError` con el nombre de la variable.
- [ ] **Step 4: Update `.env.example`**: renombrar `WALLET_PRIVATE_KEY` → `SOLANA_PRIVATE_KEY` con comentario `# NOT used in paper mode. Never put your main wallet here.`; agregar `EXA_API_KEY=`, `AUTOHEDGE_MODE=paper`, `AUTOHEDGE_MODEL=gpt-4.1`, `AUTOHEDGE_EQUITY_USD=10000`.
- [ ] **Step 5: Run** `pip install pytest && pytest tests/test_config.py -v` → 5 passed
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: add shared schemas, risk policy config and paper-only mode guard"`

---

### Task 2: Datos de mercado e indicadores

**Files:**
- Create: `autohedge/market_data.py`, `tests/test_market_data.py`

**Interfaces:**
- Consumes: `Bar`, `MarketSnapshot` (Task 1)
- Produces:
  - `class MarketDataError(Exception)`; `class InsufficientHistoryError(MarketDataError)`
  - `fetch_bars(ticker: str, period: str = "1y") -> list[Bar]`: `yf.Ticker(ticker).history(period=period, interval="1d")`. Descarta filas con NaN en OHLC. Si queda vacío → `MarketDataError`.
  - `build_snapshot(ticker: str, bars: list[Bar]) -> MarketSnapshot`: si hay menos de 60 barras → `InsufficientHistoryError`.
  - `MIN_BARS = 60`

Definiciones exactas (el implementador no debe elegir otras):
- `sma_n`: media de los últimos n cierres.
- `rsi_14`: Wilder. Semilla = media simple de ganancias y pérdidas de los primeros 14 cambios; luego `avg = (avg*13 + x)/14`. Si `avg_loss == 0` y `avg_gain == 0` → 50; si solo `avg_loss == 0` → 100.
- `atr_14`: media simple del true range `max(h-l, |h-prev_c|, |l-prev_c|)` de las últimas 14 barras.
- `vol_20d_annual`: `stdev(ln(c_t/c_{t-1}) últimos 20, ddof=1) * sqrt(252)`.
- `return_Nd_pct`: `(c_last / c_{last-N} - 1) * 100`.
- `high_52w`/`low_52w`: máx de `high` / mín de `low` en las últimas `min(252, n)` barras.

- [ ] **Step 1: Write the failing tests**

```python
def _bars(closes):  # helper: open=high=low=close salvo que se indique
    ...

def test_snapshot_linear_series():
    s = build_snapshot("TEST", _bars([float(i) for i in range(1, 101)]))
    assert s.last_close == 100 and s.sma_20 == 90.5 and s.sma_50 == 75.5
    assert s.rsi_14 == 100
    assert s.return_20d_pct == pytest.approx((100 / 80 - 1) * 100)
    assert s.n_bars == 100

def test_flat_series_rsi_50_and_zero_vol():
    s = build_snapshot("TEST", _bars([10.0] * 60))
    assert s.rsi_14 == 50 and s.vol_20d_annual == 0 and s.atr_14 == 0

def test_atr_uses_true_range():
    # 60 barras con high=c+1, low=c-1, close constante → TR = 2
    assert build_snapshot("T", bars_hl).atr_14 == pytest.approx(2.0)

def test_insufficient_history():
    with pytest.raises(InsufficientHistoryError):
        build_snapshot("NEW", _bars([1.0] * 59))

def test_fetch_bars_empty_raises(monkeypatch):
    # monkeypatch yf.Ticker → objeto cuyo .history() devuelve pd.DataFrame()
    with pytest.raises(MarketDataError):
        fetch_bars("ZZZZ")

def test_fetch_bars_drops_nan_rows(monkeypatch):
    # DataFrame de 3 filas, la del medio con Close=NaN → 2 Bars
    assert len(fetch_bars("X")) == 2
```

- [ ] **Step 2: Run** `pytest tests/test_market_data.py -v` → FAIL (módulo inexistente)
- [ ] **Step 3: Implement** con `statistics`/`math` de la stdlib (sin pandas fuera de `fetch_bars`).
- [ ] **Step 4: Run** → 6 passed
- [ ] **Step 5: Commit** `git commit -am "feat: compute market indicators from real price history"` (agregar archivos nuevos con `git add`)

---

### Task 3: Gate de riesgo y orden

**Files:**
- Create: `autohedge/risk_gate.py`, `tests/test_risk_gate.py`

**Interfaces:**
- Consumes: `Thesis`, `QuantView`, `MarketSnapshot`, `OrderProposal`, `RiskDecision` (Task 1), `RiskPolicy` (Task 1)
- Produces: `evaluate_risk(thesis: Thesis, quant: QuantView, snapshot: MarketSnapshot, policy: RiskPolicy) -> RiskDecision`

Reglas. Se evalúan **todas** y se acumulan las razones. Si hay al menos una razón → `approved=False, order=None`.

| Condición | Razón |
|---|---|
| `thesis.direction == "flat"` | `"no_trade"` |
| `thesis.conviction < min_conviction` | `"low_conviction"` |
| `quant.probability_up < min_probability_up` | `"low_probability"` |
| `snapshot.vol_20d_annual > max_annual_vol` | `"volatility_too_high"` |
| `snapshot.atr_14 <= 0` o `stop_loss <= 0` | `"invalid_stop"` |

Cálculo de la orden: `entry = last_close`; `stop = entry - stop_atr_mult*atr_14`; `tp = entry + take_profit_r*(entry - stop)`; `stop_dist = (entry - stop)/entry`; `notional = min(max_position_pct*equity, risk_per_trade_pct*equity/stop_dist)`; `quantity = notional/entry`; `expires_after_days = thesis.horizon_days`. Redondeo: precios a 6 decimales, cantidad a 8.

- [ ] **Step 1: Write the failing tests**

```python
# fixture: snapshot con last_close=100, atr_14=2.5, vol_20d_annual=0.4
# thesis long conviction=0.8 horizon=20; quant probability_up=0.6; RiskPolicy() default

def test_approved_order_sizing():
    d = evaluate_risk(thesis, quant, snap, RiskPolicy())
    assert d.approved and d.reasons == []
    o = d.order
    assert (o.entry_price, o.stop_loss, o.take_profit) == (100, 95, 110)
    assert o.notional_usd == 500 and o.quantity == 5 and o.expires_after_days == 20

def test_risk_budget_caps_position_when_stop_is_wide():
    # atr_14=10 → stop=80, stop_dist=0.2 → risk cap 100/0.2=500; pos cap 500 → 500
    # atr_14=25 → stop=50, stop_dist=0.5 → risk cap 200 < 500
    assert evaluate_risk(thesis, quant, snap_atr25, RiskPolicy()).order.notional_usd == 200

def test_multiple_vetoes_accumulate():
    d = evaluate_risk(thesis_conv_0_3, quant_p_0_4, snap_vol_2, RiskPolicy())
    assert not d.approved and d.order is None
    assert set(d.reasons) == {"low_conviction", "low_probability", "volatility_too_high"}

def test_flat_is_no_trade():
    assert evaluate_risk(thesis_flat, quant, snap, RiskPolicy()).reasons == ["no_trade"]

def test_stop_below_zero_is_vetoed():
    # last_close=1, atr_14=0.6 → stop=-0.2
    assert "invalid_stop" in evaluate_risk(thesis, quant, snap_penny, RiskPolicy()).reasons
```

- [ ] **Step 2: Run** `pytest tests/test_risk_gate.py -v` → FAIL
- [ ] **Step 3: Implement** `evaluate_risk` como función pura (sin I/O ni logs obligatorios).
- [ ] **Step 4: Run** → 5 passed
- [ ] **Step 5: Commit** `git commit -m "feat: deterministic risk gate with veto and position sizing"`

---

### Task 4: Parseo de salidas LLM

**Files:**
- Create: `autohedge/llm_io.py`, `tests/test_llm_io.py`

**Interfaces:**
- Produces:
  - `class LLMOutputError(Exception)`
  - `parse_llm_json(text: str, model: type[T]) -> T` (`T` ligado a `pydantic.BaseModel`). Orden: 1) si hay bloque ```` ```json ... ``` ```` o ```` ``` ... ``` ````, usar su contenido; 2) si no, la subcadena desde el primer `{` hasta el último `}`; 3) `model.model_validate_json`. Cualquier fallo → `LLMOutputError` con el texto truncado a 200 chars.

- [ ] **Step 1: Write the failing tests**

```python
def test_plain_json(): assert parse_llm_json('{"probability_up":0.7,"expected_move_pct":3,"summary":"s"}', QuantView).probability_up == 0.7
def test_fenced_json(): assert parse_llm_json('Here:\n```json\n{"probability_up":0.7,"expected_move_pct":3,"summary":"s"}\n```', QuantView)
def test_text_around_json(): assert parse_llm_json('Sure! {"probability_up":0.7,"expected_move_pct":3,"summary":"s"} hope it helps', QuantView)
def test_garbage_raises():
    with pytest.raises(LLMOutputError): parse_llm_json("I cannot help", QuantView)
def test_schema_violation_raises():
    with pytest.raises(LLMOutputError): parse_llm_json('{"probability_up":7,"expected_move_pct":3,"summary":"s"}', QuantView)
```

- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → 5 passed
- [ ] **Step 5: Commit** `git commit -m "feat: robust JSON extraction and validation for LLM outputs"`

---

### Task 5: Ledger y pipeline determinista

**Files:**
- Create: `autohedge/ledger.py`, `autohedge/pipeline.py`, `tests/test_ledger.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces:
  - `append_recommendations(path: Path, recs: list[Recommendation]) -> None` (crea directorio padre; una línea `model_dump_json()` por rec)
  - `read_recommendations(path: Path) -> list[Recommendation]` (archivo inexistente → `[]`; línea corrupta → se omite con `logger.warning`)
  - `LLM = Callable[[str], str]`; `BarsFetcher = Callable[[str], list[Bar]]`
  - `run_pipeline(task: str, *, director: LLM, quant: LLM, fetch: BarsFetcher = fetch_bars, policy: RiskPolicy | None = None, ledger_path: Path = Path("outputs/ledger.jsonl"), now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> list[Recommendation]`

Flujo fijo:
1. `get_mode()`. Si lanza error, se propaga.
2. `director(task)` → `parse_llm_json(..., DirectorOutput)`. Si falla, devuelve y registra una sola rec con `ticker=None, reasons=["invalid_llm_output"]`.
3. Por cada tesis:
   1. `fetch(ticker)` → `build_snapshot`. `MarketDataError` → `"no_market_data"`; `InsufficientHistoryError` → `"insufficient_history"`. Este `except` va antes que el de `MarketDataError`, porque es su subclase.
   2. `quant(prompt)`. El prompt incluye la tesis y `snapshot.model_dump_json()`. Se parsea con `QuantView`; si falla → `"invalid_llm_output"`.
   3. `evaluate_risk`.
   4. Se arma la `Recommendation`.
4. `append_recommendations` una sola vez con el lote, y se devuelve.

El pipeline nunca llama al LLM de Quant si no hay snapshot.

- [ ] **Step 1: Write the failing tests** (fakes: `director=lambda t: DIRECTOR_JSON`, `quant=lambda p: QUANT_JSON`, `fetch` que devuelve barras sintéticas o lanza)

```python
def test_happy_path_writes_ledger(tmp_path):
    recs = run_pipeline("Analyze NVDA", director=..., quant=..., fetch=fake_ok, ledger_path=tmp_path/"l.jsonl")
    assert len(recs) == 1 and recs[0].approved and recs[0].order is not None
    assert read_recommendations(tmp_path/"l.jsonl")[0].id == recs[0].id

def test_quant_receives_real_snapshot(tmp_path):
    seen = []
    run_pipeline(..., quant=lambda p: seen.append(p) or QUANT_JSON, ...)
    assert '"last_close"' in seen[0] and '"rsi_14"' in seen[0]

def test_unknown_ticker_does_not_stop_batch(tmp_path):
    # director devuelve [ZZZZ, NVDA]; fetch lanza MarketDataError para ZZZZ
    recs = run_pipeline(...)
    assert recs[0].reasons == ["no_market_data"] and recs[1].approved

def test_short_history_is_vetoed(tmp_path):
    assert run_pipeline(..., fetch=lambda t: bars_59, ...)[0].reasons == ["insufficient_history"]

def test_invalid_director_output_logged(tmp_path):
    recs = run_pipeline("x", director=lambda t: "sorry", quant=boom, ...)
    assert len(recs) == 1 and recs[0].reasons == ["invalid_llm_output"] and recs[0].ticker is None

def test_quant_not_called_without_data(tmp_path):
    run_pipeline(..., fetch=raises_market_data_error, quant=boom, ...)  # boom lanza AssertionError si se llama

def test_live_mode_blocks_pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTOHEDGE_MODE", "live")
    with pytest.raises(ConfigError): run_pipeline(...)

def test_pipeline_never_loads_signing_code():
    # subprocess: python -c "import autohedge.pipeline, sys; assert 'autohedge.tools.ultra_tools' not in sys.modules"
    assert subprocess.run([sys.executable, "-c", CODE]).returncode == 0
```

Además en `tests/test_ledger.py`: roundtrip de 2 recs, archivo inexistente → `[]`, línea corrupta omitida.

- [ ] **Step 2: Run** `pytest tests/test_pipeline.py tests/test_ledger.py -v` → FAIL
- [ ] **Step 3: Implement** `ledger.py`, después `pipeline.py`. Si `test_pipeline_never_loads_signing_code` falla porque `autohedge/__init__.py` o `autohedge/tools/__init__.py` importan `ultra_tools`, hay que mover ese import dentro de `get_tools()` en `tools_registry.py` y quitarlo de `tools/__init__.py`.
- [ ] **Step 4: Run** → todos pasan
- [ ] **Step 5: Commit** `git commit -m "feat: fixed-order pipeline with recommendation ledger"`

---

### Task 6: Evaluación de aciertos

**Files:**
- Create: `autohedge/evaluation.py`, `tests/test_evaluation.py`

**Interfaces:**
- Consumes: `Recommendation`, `Bar`, `fetch_bars`, `read_recommendations`
- Produces:
  - `FEE_ROUND_TRIP_PCT = 0.30`
  - `Outcome(rec_id: str, ticker: str, status: Literal["win","loss","expired","unfilled","pending"], return_pct: float | None, benchmark_return_pct: float | None)`
  - `score_recommendation(rec: Recommendation, bars_after: list[Bar], today: date) -> Outcome`
  - `EvalReport(n_total: int, n_resolved: int, n_pending: int, n_unfilled: int, win_rate: float | None, avg_return_pct: float | None, avg_benchmark_return_pct: float | None, expectancy_pct: float | None)`
  - `summarize(outcomes: list[Outcome]) -> EvalReport`
  - `evaluate_ledger(path: Path, fetch: BarsFetcher = fetch_bars, today: date | None = None) -> tuple[list[Outcome], EvalReport]` (solo recs `approved`; `bars_after` = barras con `date > rec.created_at.date()`, máx `expires_after_days`)

Algoritmo de `score_recommendation`. Solo aplica a long; `entry`, `stop` y `tp` salen de `rec.order`.
1. **Fill:** se busca la primera barra con `low <= entry`. Si no hay ninguna y `today < created + expires_after_days` → `pending`. Si no hay ninguna y el plazo venció → `unfilled`.
2. **Salida:** desde la barra del fill, inclusive, en orden:
   - `low <= stop` → `loss`, con salida en `stop`. Va primero porque es el supuesto conservador.
   - `high >= tp` → `win`, con salida en `tp`.
3. **Sin salida y con el plazo vencido** → `expired`, con salida en el `close` de la última barra del horizonte. **Sin salida y con el plazo vigente** → `pending`.
4. `return_pct = (exit/entry - 1)*100 - FEE_ROUND_TRIP_PCT`.
5. `benchmark_return_pct = (close_última_barra_evaluada / entry - 1)*100`, que es buy-and-hold sin fees en la misma ventana.
6. Resueltas = `win`, `loss` y `expired`. `win_rate` es la fracción de las resueltas con `return_pct > 0`. `expectancy_pct` es la media de `return_pct` de las resueltas.

- [ ] **Step 1: Write the failing tests** (entry=100, stop=95, tp=110, horizon=5)

```python
def test_take_profit_hit(): assert score(bars=[b(l=99,h=101), b(l=100,h=111)]).status == "win" and o.return_pct == pytest.approx(9.7)
def test_stop_hit(): assert score(bars=[b(l=94,h=101)]).return_pct == pytest.approx(-5.3)
def test_same_bar_stop_and_tp_counts_as_loss(): assert score(bars=[b(l=94,h=111)]).status == "loss"
def test_never_filled_after_horizon(): assert score(bars=[b(l=101,h=103)]*5, today=after).status == "unfilled"
def test_horizon_not_elapsed_is_pending(): assert score(bars=[b(l=99,h=101)], today=day2).status == "pending"
def test_expired_exits_at_last_close(): # 5 barras sin tocar stop/tp, último close 103 → return 2.7
def test_summary_excludes_pending_and_unfilled():
    r = summarize([win, loss, pending, unfilled])
    assert (r.n_resolved, r.n_pending, r.n_unfilled, r.win_rate) == (2, 1, 1, 0.5)
def test_summary_empty(): assert summarize([]).win_rate is None
```

- [ ] **Step 2: Run** → FAIL · **Step 3: Implement** · **Step 4: Run** → todos pasan
- [ ] **Step 5: Commit** `git commit -m "feat: score paper recommendations against realized prices"`

---

### Task 7: Conectar LLMs, CLI y documentación

**Files:**
- Modify: `autohedge/prompts.py` (agregar al final), `autohedge/workers.py` (reescribir), `autohedge/main.py:33-63`, `autohedge/cli.py:144-230`, `README.md` (sección nueva "Paper trading y evaluación" y diagrama real)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `run_pipeline`, `evaluate_ledger`, `get_model_name`
- Produces:
  - `DIRECTOR_JSON_PROMPT: str`: pide **solo** JSON con forma `DirectorOutput`, de 1 a 5 tesis, símbolos Yahoo (`SOL-USD` para cripto), `direction` igual a `"long"` o `"flat"` (spot, sin cortos) y que no incluya precios. Se incluye un ejemplo literal del JSON.
  - `QUANT_JSON_PROMPT: str`: recibe tesis + snapshot y devuelve **solo** JSON `QuantView`. Debe usar exclusivamente los números del snapshot y no inventar ninguno.
  - `make_director() -> LLM` y `make_quant() -> LLM` en `workers.py`. Envuelven `swarms.Agent(agent_name=..., system_prompt=..., model_name=get_model_name(), max_loops=1, output_type="str")` y devuelven `lambda text: str(agent.run(text))`. Los agentes se crean al llamar estas funciones, no al importar el módulo. Se eliminan `sentiment_agent`, `risk_agent`, `execution_agent` y `handoffs`. Los prompts viejos siguen en `prompts.py`.
  - `AutoHedge.run(task) -> list[Recommendation]`, que llama a `run_pipeline(task, director=make_director(), quant=make_quant(), ledger_path=self.output_dir / "ledger.jsonl")`.
  - CLI:
    - `autohedge`: REPL igual que hoy. El resultado se muestra con `render_recommendations(recs) -> None`, una tabla rich con columnas `ticker`, `approved`, `reasons`, `entry`, `stop`, `tp`, `notional`.
    - `autohedge run "<task>"`: no interactivo, imprime la tabla y sale con código 0.
    - `autohedge evaluate [--ledger PATH]`: imprime la tabla de outcomes y el `EvalReport`. Default `outputs/ledger.jsonl`.
    - Se mantienen `autohedge help`, `--help` y `--version`.

- [ ] **Step 1: Write the failing tests** en `tests/test_cli.py`

```python
def test_run_subcommand_uses_pipeline(monkeypatch, capsys):
    monkeypatch.setattr("autohedge.cli._run_task", lambda task: [fake_rec])  # helper que construye AutoHedge
    monkeypatch.setattr(sys, "argv", ["autohedge", "run", "Analyze NVDA"])
    with pytest.raises(SystemExit) as e: main()
    assert e.value.code == 0 and "NVDA" in capsys.readouterr().out

def test_evaluate_subcommand_on_empty_ledger(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["autohedge", "evaluate", "--ledger", str(tmp_path/"none.jsonl")])
    with pytest.raises(SystemExit) as e: main()
    assert e.value.code == 0 and "0" in capsys.readouterr().out

def test_workers_import_has_no_side_effects():
    import autohedge.workers as w
    assert not hasattr(w, "director_agent")
```

- [ ] **Step 2: Run** `pytest tests/test_cli.py -v` → FAIL
- [ ] **Step 3: Implement** prompts, workers, main y CLI. En la CLI, `_run_task(task: str) -> list[Recommendation]` encapsula `AutoHedge().run(task)` para poder hacer el monkeypatch.
- [ ] **Step 4: Run** `pytest -v` (suite completa) → todo pasa; `ruff check autohedge tests` → sin errores
- [ ] **Step 5: Update README**: reemplazar el diagrama `A→B→C→D→E` por el flujo real; documentar `run`, `evaluate`, variables de entorno y el criterio de pase a capital real (abajo).
- [ ] **Step 6: Commit** `git commit -am "feat: wire JSON agents into fixed pipeline; add run/evaluate CLI"`

---

### Task 8: Validación con datos y LLM reales (manual, requiere `OPENAI_API_KEY`)

- [ ] **Step 1:** `pip install -e .` y verificar que `python -c "import autohedge, sys; print(autohedge.__file__)"` apunte a `/home/user/AutoHedge/autohedge/`
- [ ] **Step 2:** `autohedge run "Analyze NVDA and SOL-USD for a 3-week swing trade"` → tabla con 2 filas. `outputs/ledger.jsonl` tiene 2 líneas con `snapshot.last_close` igual al último cierre de Yahoo (verificar a mano con `python -c "import yfinance as yf; print(yf.Ticker('NVDA').history(period='5d').Close.iloc[-1])"`).
- [ ] **Step 3:** Repetir la misma tarea 3 veces. Revisar si las direcciones y convicciones son consistentes y anotarlo. Si se contradicen en más de 1 de cada 3 corridas, se registra como hallazgo antes de seguir.
- [ ] **Step 4:** `autohedge evaluate` → todas las recomendaciones salen `pending` (no venció el horizonte) y no hay crash.
- [ ] **Step 5:** `autohedge run "Analyze ZZZZQ"` → fila vetada con `no_market_data`.

---

## Criterio de pase a capital real (decisión de negocio, no código)

No se escribe una sola línea de ejecución en vivo hasta que `autohedge evaluate` muestre todo esto:

- **≥ 30 recomendaciones aprobadas y resueltas.** Con menos, el resultado es ruido.
- **`expectancy_pct > 0` neto de fees.**
- **`avg_return_pct > avg_benchmark_return_pct`.** Si no le gana a comprar y mantener los mismos activos, el sistema no agrega valor.
- **Mayor pérdida individual ≤ `risk_per_trade_pct`** del equity simulado. Así se confirma que el stop funciona.

Si se cumple, la ejecución en vivo es un plan aparte, con wallet dedicada, límites diarios y kill-switch.
