"""Train ML models (LSTM, Transformer, CNN) on historical data.

Usage:
    python train_models.py                    # Train on all assets
    python train_models.py --asset BTC/USDT   # Train on specific asset
    python train_models.py --epochs 100       # More epochs
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

import pandas as pd

# Add parent to path for src imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.analysis.technical.signals import TechnicalAnalysisAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("train_models")


def fetch_candles(symbol: str, interval: str = "1h", limit: int = 2000) -> pd.DataFrame:
    """Fetch historical candles from Hyperliquid via ccxt."""
    import ccxt

    hl = ccxt.hyperliquid()
    hl.load_markets()

    # Map symbol to Hyperliquid format
    coin = symbol.split("/")[0]
    hl_symbol = f"{coin}/USDC:USDC"
    if hl_symbol not in hl.symbols:
        hl_symbol = f"{coin}/USDC"

    logger.info("Fetching %d candles for %s (%s) from Hyperliquid...", limit, symbol, hl_symbol)

    # Fetch in batches (Hyperliquid max 500 per request)
    all_candles = []
    since = None
    batch_size = 500
    remaining = limit

    while remaining > 0:
        fetch_limit = min(batch_size, remaining)
        candles = hl.fetch_ohlcv(hl_symbol, interval, since=since, limit=fetch_limit)
        if not candles:
            break
        all_candles.extend(candles)
        since = candles[-1][0] + 1  # Next batch starts after last candle
        remaining -= len(candles)
        if len(candles) < fetch_limit:
            break  # No more data
        time.sleep(0.5)  # Rate limit

    if not all_candles:
        raise ValueError(f"No candles returned for {hl_symbol}")

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df = df.astype(float)

    # Remove duplicates
    df = df[~df.index.duplicated(keep="last")]
    df.sort_index(inplace=True)

    logger.info("Fetched %d candles for %s (range: %s to %s)",
                len(df), symbol, df.index[0], df.index[-1])
    return df


def train_asset(agent: TechnicalAnalysisAgent, symbol: str, epochs: int = 50) -> dict:
    """Train models for a single asset."""
    logger.info("=" * 60)
    logger.info("Training models for %s", symbol)
    logger.info("=" * 60)

    # Fetch historical data
    df = fetch_candles(symbol, interval="1h", limit=2000)

    if len(df) < 500:
        logger.warning("Only %d candles for %s — need at least 500 for meaningful training", len(df), symbol)
        return {"status": "skipped", "reason": "insufficient_data", "bars": len(df)}

    # Train
    t0 = time.time()
    result = agent.train(symbol, df, epochs=epochs, walk_forward=False)
    elapsed = time.time() - t0

    logger.info("Training for %s completed in %.1fs", symbol, elapsed)
    logger.info("Result: %s", {k: v for k, v in result.items() if k != "fold_details"})

    return result


def main():
    parser = argparse.ArgumentParser(description="Train AIFred ML models")
    parser.add_argument("--asset", type=str, help="Single asset to train (e.g. BTC/USDT)")
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs per model")
    parser.add_argument("--checkpoint-dir", type=str, default="checkpoints/technical",
                        help="Directory to save model checkpoints")
    args = parser.parse_args()

    assets = [args.asset] if args.asset else ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

    # Initialize agent
    agent = TechnicalAnalysisAgent(checkpoint_dir=args.checkpoint_dir)

    logger.info("Starting model training for %d assets", len(assets))
    logger.info("Epochs: %d, Checkpoint dir: %s", args.epochs, args.checkpoint_dir)

    results = {}
    for symbol in assets:
        try:
            result = train_asset(agent, symbol, epochs=args.epochs)
            results[symbol] = result
        except Exception as e:
            logger.error("Training failed for %s: %s", symbol, e, exc_info=True)
            results[symbol] = {"status": "error", "error": str(e)}

    # Summary
    logger.info("=" * 60)
    logger.info("TRAINING SUMMARY")
    logger.info("=" * 60)
    for symbol, result in results.items():
        status = result.get("status", "unknown")
        if status == "error":
            logger.info("  %s: FAILED — %s", symbol, result.get("error", ""))
        elif status == "skipped":
            logger.info("  %s: SKIPPED — %s", symbol, result.get("reason", ""))
        else:
            metrics = result.get("metrics", {})
            logger.info("  %s: OK — accuracy=%.1f%%, sharpe=%.2f",
                        symbol,
                        metrics.get("accuracy", 0) * 100,
                        metrics.get("sharpe", 0))

    # Check if checkpoints were created
    ckpt_dir = args.checkpoint_dir
    if os.path.exists(ckpt_dir):
        files = os.listdir(ckpt_dir)
        logger.info("Checkpoints saved: %d files in %s", len(files), ckpt_dir)
        for f in files:
            size = os.path.getsize(os.path.join(ckpt_dir, f))
            logger.info("  %s (%.1f KB)", f, size / 1024)
    else:
        logger.warning("No checkpoint directory created at %s", ckpt_dir)


if __name__ == "__main__":
    main()
