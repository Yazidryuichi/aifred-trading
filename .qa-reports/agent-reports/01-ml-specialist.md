# ML/PyTorch Specialist Review Report

**Reviewer**: ML/PyTorch Specialist (Agent 01)
**Date**: 2026-04-01
**Scope**: All ML/AI model implementations in `python/src/analysis/`

---

## 1. PyTorch Models

### 1.1 LSTM Model (`python/src/analysis/technical/lstm_model.py`)

**Status**: PASS

- **Architecture**: 3-layer stacked LSTM with additive attention, classifier head, confidence head, and magnitude head. Well-structured multi-output design.
- **Forward pass**: Correct. LSTM output -> attention -> dropout -> three heads (logits, confidence, magnitude).
- **Training**: Proper early stopping (patience=10), gradient clipping (max_norm=1.0), LR scheduling (ReduceLROnPlateau), best-state restoration. All correct.
- **Predict**: Handles untrained model gracefully (returns HOLD with 0 confidence). Correct 2D->3D input expansion.
- **Save/Load**: Full checkpoint with hyperparams for reconstruction. Correct `map_location` usage for device portability.

**Minor concern**: `weights_only=False` in `torch.load()` (line 373) allows arbitrary code execution if checkpoint files are tampered with. Low risk if checkpoints are self-generated, but worth noting for Railway deployment where filesystem access patterns may differ.

### 1.2 Transformer Model (`python/src/analysis/technical/transformer_model.py`)

**Status**: PASS with WARN

- **Architecture**: Input projection -> sinusoidal positional encoding -> TransformerEncoder (4 layers, 8 heads) -> learnable aggregation query via cross-attention -> classifier/confidence/magnitude heads. Solid design.
- **Positional Encoding**: Uses `batch_first=True` throughout (good consistency). Cosine term uses `div_term[: d_model // 2]` which correctly handles the case where d_model is even.
- **Training**: CosineAnnealingLR scheduler, early stopping (patience=15), gradient clipping. Correct.
- **Predict/Save/Load**: Same quality as LSTM. Correct.

**WARN** (line 44): Positional encoding bug when `d_model` is odd.
```python
pe[:, 1::2] = torch.cos(position * div_term[: d_model // 2])
```
If `d_model` is odd, the cosine positions slice (`1::2`) has `d_model // 2` elements, matching `div_term[: d_model // 2]`. This is actually correct. However, the sine positions slice (`0::2`) has `(d_model + 1) // 2` elements while `div_term` has `d_model // 2` elements (from `torch.arange(0, d_model, 2)`), which means line 43 `pe[:, 0::2] = torch.sin(position * div_term)` would fail with a shape mismatch if `d_model` is odd. In practice, `d_model=128` (even) is the default, so this is low risk but would crash with odd d_model values.

### 1.3 Pattern CNN (`python/src/analysis/technical/pattern_cnn.py`)

**Status**: PASS

- **Architecture**: Multi-scale 1D CNN (kernel sizes 3, 7, 15) -> merge -> adaptive pool -> pattern classification (multi-label via sigmoid) + direction head + confidence head. Well-designed for multi-scale pattern detection.
- **Input preparation** (`prepare_input`): Correctly normalizes prices relative to first close, normalizes volume separately, transposes to channels-first. Correct.
- **Training**: Time-based validation split (not random -- correct for financial data), `_EarlyStopping` helper with deep-copy of best weights. Multi-task loss (pattern BCE + direction CE). All correct.
- **Pattern labels**: Heuristic-based weak supervision (`_detect_patterns_heuristic`) for generating training labels. Reasonable approach -- the CNN learns to refine these.

**Note**: The `pooled_len` variable on line 108 is computed but never used. Harmless dead code since `AdaptiveAvgPool1d(1)` makes the length irrelevant.

### 1.4 Ensemble Meta-Learner (`python/src/analysis/technical/ensemble.py`)

**Status**: PASS

- **Architecture**: XGBoost meta-learner (stacking) combining LSTM, Transformer, CNN, and rule signals. Feature vector includes sub-model outputs, agreement metrics, EMA accuracy, drawdown state, and indicator features.
- **Dynamic weighting**: EMA-based with softmax temperature smoothing. Walk-forward validated weight updates. Correct.
- **Signal gating**: Multi-layer: conflict resolution -> ensemble agreement (80% threshold) -> quality tiering (A+/A/B/C) -> drawdown-aware confidence scaling. Robust.
- **Train**: XGBoost with proper regularization (subsample, colsample, L1/L2, min_child_weight). Early stopping with eval set.
- **Fallback**: When meta-model is not trained, falls back to weighted average of sub-model directions. Correct.

**Note**: `build_meta_features` produces a variable-length feature vector depending on whether `indicator_features` is provided. If the number of indicator keys changes between training and inference, the scaler and XGBoost model will crash due to feature count mismatch. This is mitigated by `signals.py` always passing the same 5 indicator keys, but it is fragile.

---

## 2. NLP Models

### 2.1 FinBERT (`python/src/analysis/sentiment/finbert_model.py`)

**Status**: PASS

- **Model loading**: Lazy-load via HuggingFace pipeline with proper device selection (CUDA > MPS > CPU). Warm-up inference on load. Correct.
- **Confidence calibration**: Platt-scaling style calibration (`_calibrate_confidence`) to correct FinBERT's known overconfidence on neutral. Good practice.
- **Source quality weighting**: Institutional > news > analyst > social. Multiplied into effective confidence. Correct.
- **Multi-timeframe decay**: Exponential decay with half-lives per timeframe. Noise filtering via entropy threshold. Correct.
- **Batch inference**: Adaptive batch sizing based on GPU memory. Fallback to single-item on batch failure. Robust.
- **Sentiment velocity**: Linear regression over rolling history for rate-of-change computation. Correct.

**Note**: FinBERT model download (`ProsusAI/finbert`) requires internet access on first use. On Railway, this will work but adds cold-start latency (~2-5 minutes for first load). Consider pre-downloading the model in the Docker image.

### 2.2 LLM Analyzer (`python/src/analysis/sentiment/llm_analyzer.py`)

**Status**: PASS

- **Chain-of-thought prompting**: Structured 6-step reasoning pipeline. Dual-speed (deep/fast) based on urgency. Well-designed.
- **Fallback**: Gracefully falls back to FinBERT when API key is missing or API call fails. Correct.
- **Response parsing**: Robust 3-tier parsing: direct JSON -> brace-matching extraction -> regex fallback. Handles markdown fences, partial JSON. Correct.
- **Rate limiting**: Simple `time.sleep` based rate limiter. Adequate for single-threaded use.
- **Cache**: 5-minute TTL cache keyed on `asset:hash(text)`. Correct.

**WARN**: `analyze_async` (line 380-385) uses `asyncio.get_event_loop()` which is deprecated in Python 3.10+ and will raise `DeprecationWarning`. Should use `asyncio.get_running_loop()` instead. May fail entirely in Python 3.12+ if no loop is running.

**WARN**: Model name `claude-sonnet-4-5-20250929` (line 163) -- verify this model ID is still valid/optimal for production.

---

## 3. Technical Agent Integration (`python/src/analysis/technical/signals.py`)

**Status**: PASS

### 3.1 `_ML_AVAILABLE` guard (lines 29-53)

Correctly wraps all ML imports in a try/except block. On `ImportError`, all model classes are set to `None` and `_ML_AVAILABLE = False`. The fallback assignments for constants (`SIGNAL_TIER_C = "C"`) are correct.

### 3.2 `_ensure_initialized()` (lines 136-145)

Properly guarded:
```python
if not _ML_AVAILABLE:
    logger.warning("ML models unavailable -- indicator-only mode active")
    self._is_initialized = True
    self._input_size = n_features
    return
```
This correctly short-circuits model initialization when ML libraries are missing, and still sets `_is_initialized = True` so the method does not re-enter.

### 3.3 Indicator-only fallback in `analyze()` (lines 245-260)

Correctly placed after `_ensure_initialized()` and before any model calls:
```python
if not _ML_AVAILABLE:
    return Signal(..., metadata={"reason": "ml_models_unavailable", "mode": "indicator_only", ...})
```
Returns HOLD with indicator context. Correct.

### 3.4 Edge cases

- **Edge case 1**: If `_ML_AVAILABLE` is True but models fail during `predict()` -- NOT handled. An exception from `self._lstm.predict()` (line 266) would propagate up. **Recommendation**: Wrap individual model predict calls in try/except to gracefully degrade.
- **Edge case 2**: `get_model_performance()` (line 413-441) accesses `self._lstm.is_trained`, `self._transformer.is_trained`, etc. without checking if these are `None`. If `_ML_AVAILABLE` is False, these attributes are never set, and `self._is_initialized` could be True from the indicator-only path. Accessing `self._lstm.is_trained` would crash with `AttributeError: 'NoneType' object has no attribute 'is_trained'`. **This is a bug** at line 419.
- **Edge case 3**: `save_models()` and `load_models()` (lines 443-477) do not check `_ML_AVAILABLE`. Will crash with `AttributeError` if called in indicator-only mode.

---

## 4. Data Flow -- Hyperliquid OHLCV Fallback (`python/src/datafeeds/market_data_provider.py`)

**Status**: PASS

### 4.1 Symbol mapping (line 385)

```python
hl_symbol = asset.replace("/USDT", "/USDC:USDC")
```

- Correctly converts `BTC/USDT` -> `BTC/USDC:USDC` (Hyperliquid perps format).
- **Edge case**: Assets with `/USDT` elsewhere in the name (unlikely but possible, e.g., `USDT/USDC`) would produce `USDC/USDC:USDC` -- malformed but would just fail the API call and be caught.
- Assets already in `/USDC` format (e.g., `ETH/USDC`) would NOT be converted, meaning Hyperliquid fallback would try `ETH/USDC` instead of `ETH/USDC:USDC`. This would likely fail silently.

### 4.2 Exception handling (lines 390-392)

Catches broad `Exception` for the Hyperliquid fallback, logs a warning. The primary exchange catches specific ccxt exceptions (`NetworkError`, `ExchangeNotAvailable`, `ExchangeError`, `BadSymbol`). Good layered approach.

### 4.3 DataFrame format preservation

Both primary and fallback paths produce the same DataFrame structure:
```python
df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
df.set_index("timestamp", inplace=True)
```
Correct -- format is identical.

### 4.4 Lazy initialization (line 381)

`self._hl_fallback` is stored as an attribute via `hasattr` check. Uses `setattr` pattern implicitly. Works but is slightly non-standard -- the attribute is not declared in `__init__`. Cosmetic issue only.

---

## 5. Model Training Pipeline

### 5.1 Walk-Forward Trainer (`python/src/analysis/technical/training.py`)

**Status**: PASS

- **Purged walk-forward**: Correctly implements a purge gap between train and test windows to prevent data leakage from overlapping labels. Configurable gap (default 20 bars).
- **Expanding/sliding window**: Both modes supported. Correct.
- **Degradation detection**: Flags models below 60% rolling accuracy. Updates ensemble weights via `update_performance()`. Correct.
- **Checkpoint saving**: Saves per-fold checkpoints with try/except. Correct.
- **MLflow integration**: Optional, guarded by `MLFLOW_AVAILABLE`. Correct.

**Note**: `_build_meta_training_data` (line 329) runs sub-model predictions on training data to generate meta-features. This is computationally expensive (O(n) forward passes). The `step = max(1, len(X_seq) // 200)` subsampling helps but could still be slow on large datasets.

### 5.2 Walk-Forward Optimizer (`python/src/optimizer/walk_forward.py`)

**Status**: PASS

- **Optuna integration**: TPE sampler with median pruner. Proper search space definition. Prunes trials with too few trades or excessive drawdown. Correct.
- **Window generation**: Rolling windows with configurable train/purge/validate/test periods. Correct.
- **Consensus parameters**: Median for numeric, mode for categorical. Good aggregation strategy.
- **Backtest integration**: Uses `BacktestExchange` for realistic simulation with fees and slippage. Correct.

**WARN**: The `objective` sync wrapper (line 425-431) creates a new event loop per trial (`asyncio.new_event_loop()`). With 50 trials per window, this creates and destroys 50 event loops. While functional, this is inefficient and may cause issues on some platforms. Consider using `asyncio.run()` (Python 3.7+) or reusing the loop.

---

## 6. Known Issues Assessment

### 6.1 Hardcoded Paths

| Path | File | Line | Railway Compatible? |
|------|------|------|---------------------|
| `"checkpoints/technical"` | signals.py | 86 | WARN -- relative path, depends on CWD |
| `"src/config/default.yaml"` | signals.py | 62 | WARN -- relative path, depends on CWD |

Both are relative paths. They will work on Railway as long as the working directory is set correctly in the Dockerfile/Procfile. **Recommendation**: Use `os.path.dirname(__file__)` based resolution or environment variables for robustness.

### 6.2 Memory Concerns -- PyTorch CPU on Railway

| Model | Estimated Memory | Risk |
|-------|-----------------|------|
| LSTM (128 hidden, 3 layers) | ~2-5 MB | LOW |
| Transformer (128 d_model, 4 layers) | ~5-10 MB | LOW |
| Pattern CNN (multi-scale) | ~3-5 MB | LOW |
| XGBoost (200 trees, depth 4) | ~1-5 MB | LOW |
| FinBERT (ProsusAI/finbert) | ~400-500 MB | HIGH |
| Training (backprop + gradients) | 3-5x inference | MEDIUM |

**FinBERT is the main concern**. At ~500 MB for model weights alone, plus tokenizer and runtime overhead, it needs at least 1 GB of headroom. Railway's default container size should handle this, but if other services share the container, OOM is possible.

**Training during production**: Walk-forward training with LSTM + Transformer + CNN simultaneously could spike memory to ~1-2 GB. Recommend scheduling retraining during low-traffic periods or on a separate Railway service.

### 6.3 GPU Requirement

All models use automatic device detection:
```python
self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
```
**No models require GPU**. All will run on CPU. Performance will be slower for training but acceptable for inference on the sequence lengths used (lookback=60).

FinBERT also has proper CPU fallback (`device=-1` in HuggingFace pipeline).

### 6.4 `torch.load(weights_only=False)` Security

Three files use `weights_only=False`:
- `lstm_model.py:373`
- `transformer_model.py:404`
- `pattern_cnn.py:520`

This is a known security risk (arbitrary code execution via crafted pickle files). Since checkpoints are self-generated, the risk is low in practice, but PyTorch 2.6+ will require `weights_only=True` by default. **Recommendation**: Migrate to `weights_only=True` with explicit safe globals, or use `safetensors` format.

---

## Summary Table

| Component | Status | Notes |
|-----------|--------|-------|
| LSTM Model | PASS | Fully functional, proper architecture |
| Transformer Model | PASS/WARN | Odd d_model positional encoding edge case |
| Pattern CNN | PASS | Multi-scale design, proper training |
| Ensemble Meta-Learner | PASS | XGBoost stacking, dynamic weights, robust gating |
| FinBERT | PASS | Calibrated, batched, multi-timeframe decay |
| LLM Analyzer | PASS/WARN | Deprecated `get_event_loop()` in async path |
| signals.py ML Guard | PASS | Correct `_ML_AVAILABLE` pattern |
| signals.py Edge Cases | FAIL | `get_model_performance()` crashes in indicator-only mode |
| Market Data Fallback | PASS | Correct format, proper exception handling |
| Walk-Forward Trainer | PASS | Purged validation, degradation detection |
| Walk-Forward Optimizer | PASS | Optuna TPE, consensus params |

---

## Errors Found

| Severity | File:Line | Description |
|----------|-----------|-------------|
| **BUG** | `signals.py:419` | `get_model_performance()` accesses `self._lstm.is_trained` without null check; crashes in indicator-only mode when `_ML_AVAILABLE=False` |
| **BUG** | `signals.py:443-477` | `save_models()` and `load_models()` don't guard against `_ML_AVAILABLE=False` |
| WARN | `transformer_model.py:43-44` | Positional encoding will crash if `d_model` is odd (not triggered with default config) |
| WARN | `llm_analyzer.py:383` | `asyncio.get_event_loop()` deprecated in Python 3.10+, may fail in 3.12+ |
| WARN | `signals.py:266-274` | Individual model `predict()` calls not wrapped in try/except; single model failure crashes entire pipeline |
| WARN | `ensemble.py:build_meta_features` | Variable-length feature vector if indicator_features keys change between train/inference |
| INFO | `market_data_provider.py:385` | `/USDC` assets won't get Hyperliquid `:USDC` suffix, fallback will fail silently |
| INFO | All `torch.load` | `weights_only=False` security risk; plan migration to `weights_only=True` |
| INFO | `signals.py:62,86` | Relative paths (`src/config/default.yaml`, `checkpoints/technical`) depend on CWD |

---

## Fix Recommendations

### Critical (Fix Before Next Deploy)

1. **signals.py:419** -- Guard `get_model_performance()`:
```python
if self._is_initialized and _ML_AVAILABLE:
    result["models"] = { ... }
```

2. **signals.py:443,456** -- Guard `save_models()` and `load_models()`:
```python
def save_models(self, prefix: str = "latest") -> None:
    if not self._is_initialized or not _ML_AVAILABLE:
        logger.warning("ML models not available, nothing to save")
        return
    ...
```

3. **signals.py:266-274** -- Wrap model predictions in try/except:
```python
try:
    lstm_signal = self._lstm.predict(latest_seq, asset=asset, timeframe=timeframe)
except Exception as e:
    logger.warning("LSTM prediction failed: %s", e)
    lstm_signal = Signal(asset=asset, direction=Direction.HOLD, confidence=0.0, source="lstm", timeframe=timeframe)
```

### Recommended (Next Sprint)

4. **llm_analyzer.py:383** -- Replace `asyncio.get_event_loop()` with `asyncio.get_running_loop()`.
5. **All torch.load calls** -- Migrate to `weights_only=True` or `safetensors`.
6. **signals.py:62,86** -- Use `Path(__file__).parent` based path resolution.
7. **market_data_provider.py:385** -- Handle `/USDC` base assets for Hyperliquid fallback.

---

## Risk Assessment

### Production Risk: LOW-MEDIUM

The ML pipeline is well-engineered. The main risks are:

1. **Indicator-only mode crash** (signals.py edge case) -- If PyTorch fails to import on Railway (e.g., memory pressure, dependency issue), `get_model_performance()` will crash. This could break health check endpoints. **Probability: Medium. Impact: Low** (system still trades in indicator-only mode, just health check breaks).

2. **FinBERT cold start on Railway** -- First invocation downloads ~500 MB model. If Railway restarts the container, this happens again. **Probability: High. Impact: Low** (just latency, not failure). **Mitigation**: Bake model into Docker image.

3. **Training memory spike** -- Walk-forward training could consume 1-2 GB. On a shared Railway container, this could trigger OOM kills. **Probability: Medium. Impact: Medium** (service restart). **Mitigation**: Run training on a separate service or schedule during low-traffic periods.

4. **Model prediction failure cascading** -- If one model throws during `predict()`, the entire `analyze()` call fails. **Probability: Low. Impact: High** (no signal generated). **Mitigation**: Apply fix #3 above.

All models are functional, non-stub implementations with proper training, inference, save/load, and graceful degradation patterns. The codebase shows strong ML engineering practices (walk-forward validation, purge gaps, early stopping, gradient clipping, drawdown-aware scaling).
