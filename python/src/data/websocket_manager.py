"""WebSocket manager for real-time market data streaming.

Uses ccxt.pro (bundled in ccxt v4+) for unified WebSocket access across exchanges.
Falls back to REST polling if WebSocket is unavailable.
Implements multi-tier reconnection following OctoBot patterns:
  - Tier 1: 0.5s quick retry (transient disconnect)
  - Tier 2: 5s extended retry (exchange issue)
  - Tier 3: Force reconnect after 2min of failures
  - Tier 4: Dead connection detection after 4min with no messages
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set

import pandas as pd

logger = logging.getLogger(__name__)

# Default reconnection tier delays (seconds)
DEFAULT_RECONNECT_TIERS = [0.5, 5.0, 30.0]
DEFAULT_DEAD_CONNECTION_TIMEOUT = 240  # 4 minutes
DEFAULT_HEALTH_CHECK_INTERVAL = 30  # seconds
DEFAULT_REST_FALLBACK_INTERVAL = 10  # seconds


class WebSocketManager:
    """Manages WebSocket connections to exchanges for real-time data.

    Features:
    - Subscribe to ticker updates for multiple symbols
    - Subscribe to OHLCV candle updates
    - Subscribe to order book updates (L2)
    - Multi-tier reconnection with exponential backoff
    - Automatic fallback to REST polling if WS unavailable
    - Thread-safe price cache accessible by position monitor
    - Callback system for price updates
    """

    def __init__(self, exchange_id: str = "binance", config: Optional[dict] = None):
        self._exchange_id = exchange_id
        self._config = config or {}
        self._exchange = None  # ccxt.pro exchange instance
        self._running = False
        self._stop_event = asyncio.Event()

        # Price cache: symbol -> {price, bid, ask, timestamp, volume}
        self._prices: Dict[str, Dict[str, Any]] = {}

        # OHLCV cache: (symbol, timeframe) -> list of candle lists
        self._candles: Dict[str, Dict[str, list]] = {}

        # Subscriptions
        self._ticker_symbols: Set[str] = set()
        self._candle_subscriptions: Dict[str, str] = {}  # symbol -> timeframe

        # Callbacks: (symbol, price, timestamp) for price; (symbol, timeframe, candles) for candle
        self._on_price_update: List[Callable] = []
        self._on_candle_update: List[Callable] = []

        # Reconnection state
        self._last_message_time: float = 0
        self._consecutive_failures: int = 0
        self._reconnect_tier: int = 0

        # Configurable thresholds
        ws_cfg = self._config.get("websocket", {})
        tiers = ws_cfg.get("reconnect_tiers", DEFAULT_RECONNECT_TIERS)
        self._tier_delays: List[float] = list(tiers)
        self._dead_connection_timeout: float = ws_cfg.get(
            "dead_connection_timeout", DEFAULT_DEAD_CONNECTION_TIMEOUT
        )
        self._health_check_interval: float = ws_cfg.get(
            "health_check_interval", DEFAULT_HEALTH_CHECK_INTERVAL
        )
        self._rest_poll_interval: float = ws_cfg.get(
            "rest_fallback_interval", DEFAULT_REST_FALLBACK_INTERVAL
        )

        # Fallback REST polling
        self._rest_fallback_active = False

        # Tasks managed by start()
        self._tasks: List[asyncio.Task] = []

        # Whether ccxt.pro is available
        self._ws_supported = True

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Initialize the ccxt.pro exchange instance.

        Tries ccxt.pro first (WebSocket support). If ccxt.pro is not installed
        or the exchange does not support watch methods, falls back to
        ccxt.async_support for REST-only usage.
        """
        exchange_config: Dict[str, Any] = {
            "enableRateLimit": True,
            "timeout": 30000,
        }

        # Merge API keys and extra params from config
        api_key = self._config.get("api_key") or self._config.get("apiKey")
        api_secret = self._config.get("api_secret") or self._config.get("secret")
        if api_key:
            exchange_config["apiKey"] = api_key
        if api_secret:
            exchange_config["secret"] = api_secret

        # Merge any extra exchange params
        extra = self._config.get("exchange_params", {})
        exchange_config.update(extra)

        # Close existing connection if any
        if self._exchange is not None:
            try:
                await self._exchange.close()
            except Exception:
                pass
            self._exchange = None

        # Try ccxt.pro first
        try:
            import ccxt.pro as ccxtpro

            exchange_class = getattr(ccxtpro, self._exchange_id, None)
            if exchange_class is None:
                raise AttributeError(
                    f"Exchange '{self._exchange_id}' not found in ccxt.pro"
                )
            self._exchange = exchange_class(exchange_config)
            self._ws_supported = True
            logger.info(
                "WebSocket connection initialized via ccxt.pro for %s",
                self._exchange_id,
            )
        except (ImportError, AttributeError) as e:
            logger.warning(
                "ccxt.pro not available for %s (%s), falling back to async REST",
                self._exchange_id,
                e,
            )
            import ccxt.async_support as ccxt_async

            exchange_class = getattr(ccxt_async, self._exchange_id, None)
            if exchange_class is None:
                raise ValueError(
                    f"Exchange '{self._exchange_id}' not found in ccxt"
                )
            self._exchange = exchange_class(exchange_config)
            self._ws_supported = False
            self._rest_fallback_active = True

        # Enable sandbox if configured
        if self._config.get("sandbox", False):
            self._exchange.set_sandbox_mode(True)
            logger.info("Sandbox mode enabled for %s", self._exchange_id)

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    async def subscribe_tickers(self, symbols: List[str]) -> None:
        """Subscribe to real-time ticker updates for symbols.

        Can be called before or after start(). If called after start(),
        the ticker loop will pick up the new symbols on its next iteration.
        """
        added = set(symbols) - self._ticker_symbols
        self._ticker_symbols.update(symbols)
        if added:
            logger.info("Subscribed to tickers: %s", sorted(added))

    async def subscribe_candles(
        self, symbol: str, timeframe: str = "1h"
    ) -> None:
        """Subscribe to OHLCV candle updates for a symbol/timeframe."""
        self._candle_subscriptions[symbol] = timeframe
        logger.info("Subscribed to candles: %s (%s)", symbol, timeframe)

    def on_price_update(self, callback: Callable) -> None:
        """Register a callback for price updates.

        Callback signature: ``callback(symbol: str, price: float, timestamp: int)``
        """
        self._on_price_update.append(callback)

    def on_candle_update(self, callback: Callable) -> None:
        """Register a callback for candle updates.

        Callback signature: ``callback(symbol: str, timeframe: str, candles: list)``
        """
        self._on_candle_update.append(callback)

    # ------------------------------------------------------------------
    # Price cache (synchronous access)
    # ------------------------------------------------------------------

    def get_price(self, symbol: str) -> Optional[float]:
        """Get latest cached price for a symbol. Thread-safe for sync callers."""
        data = self._prices.get(symbol)
        if data is None:
            return None
        return data.get("price")

    def get_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get full ticker data (bid/ask/last/volume/timestamp)."""
        return self._prices.get(symbol)

    def get_all_prices(self) -> Dict[str, float]:
        """Return a snapshot of all cached prices: {symbol: last_price}."""
        return {
            sym: data["price"]
            for sym, data in self._prices.items()
            if data.get("price") is not None
        }

    def get_cached_candles(
        self, symbol: str, timeframe: str
    ) -> Optional[pd.DataFrame]:
        """Return cached OHLCV candles as a DataFrame, or None."""
        key = f"{symbol}|{timeframe}"
        raw = self._candles.get(key)
        if not raw:
            return None
        df = pd.DataFrame(
            raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        return df

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start all WebSocket subscription loops.

        This coroutine blocks until ``stop()`` is called.
        """
        if self._exchange is None:
            await self.connect()

        self._running = True
        self._stop_event.clear()
        self._tasks.clear()

        # If WebSocket is not supported, go straight to REST fallback
        if not self._ws_supported:
            logger.info(
                "WebSocket not supported for %s, using REST polling",
                self._exchange_id,
            )
            self._rest_fallback_active = True
            self._tasks.append(asyncio.create_task(self._rest_polling_loop()))
        else:
            # WebSocket loops
            if self._ticker_symbols:
                self._tasks.append(asyncio.create_task(self._ticker_loop()))
            for symbol, tf in self._candle_subscriptions.items():
                self._tasks.append(
                    asyncio.create_task(self._candle_loop(symbol, tf))
                )

        # Health monitor always runs
        self._tasks.append(asyncio.create_task(self._health_monitor()))

        logger.info(
            "WebSocketManager started for %s with %d ticker symbol(s), "
            "%d candle subscription(s)",
            self._exchange_id,
            len(self._ticker_symbols),
            len(self._candle_subscriptions),
        )

        # Wait until stop is requested
        await self._stop_event.wait()

        # Cancel all tasks
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        logger.info("WebSocketManager stopped for %s", self._exchange_id)

    async def stop(self) -> None:
        """Stop all WebSocket connections gracefully."""
        logger.info("Stopping WebSocketManager for %s ...", self._exchange_id)
        self._running = False
        self._stop_event.set()
        if self._exchange is not None:
            try:
                await self._exchange.close()
            except Exception as e:
                logger.warning("Error closing exchange connection: %s", e)
            self._exchange = None

    # ------------------------------------------------------------------
    # Internal loops
    # ------------------------------------------------------------------

    async def _ticker_loop(self) -> None:
        """Main loop watching tickers via WebSocket."""
        logger.info(
            "Ticker WebSocket loop started for %d symbol(s)",
            len(self._ticker_symbols),
        )
        while self._running:
            try:
                symbols = list(self._ticker_symbols)
                if not symbols:
                    await asyncio.sleep(1)
                    continue

                # watch_tickers is the batch method; some exchanges only support
                # watch_ticker (singular). Try batch first.
                try:
                    tickers = await self._exchange.watch_tickers(symbols)
                except (AttributeError, NotImplementedError):
                    # Fallback: watch one at a time using the first symbol
                    # (less efficient, but compatible)
                    ticker = await self._exchange.watch_ticker(symbols[0])
                    tickers = {symbols[0]: ticker}

                self._last_message_time = time.time()
                self._consecutive_failures = 0
                self._reconnect_tier = 0

                for symbol, ticker in tickers.items():
                    price_data = {
                        "price": ticker.get("last") or ticker.get("close", 0),
                        "bid": ticker.get("bid", 0),
                        "ask": ticker.get("ask", 0),
                        "volume": ticker.get("baseVolume", 0),
                        "timestamp": ticker.get(
                            "timestamp", int(time.time() * 1000)
                        ),
                    }
                    self._prices[symbol] = price_data

                    logger.debug(
                        "WS ticker %s: %.8g (bid=%.8g ask=%.8g)",
                        symbol,
                        price_data["price"],
                        price_data["bid"],
                        price_data["ask"],
                    )

                    # Fire callbacks
                    for cb in self._on_price_update:
                        try:
                            result = cb(
                                symbol,
                                price_data["price"],
                                price_data["timestamp"],
                            )
                            # Support both sync and async callbacks
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.warning(
                                "Price update callback error for %s: %s", symbol, e
                            )

                # If we had been on REST fallback, switch back to WS
                if self._rest_fallback_active:
                    logger.info("WebSocket recovered, disabling REST fallback")
                    self._rest_fallback_active = False

            except asyncio.CancelledError:
                raise
            except Exception as e:
                await self._handle_disconnect(e, "ticker")

    async def _candle_loop(self, symbol: str, timeframe: str) -> None:
        """Watch OHLCV candles for a single symbol/timeframe."""
        logger.info("Candle WebSocket loop started for %s (%s)", symbol, timeframe)
        cache_key = f"{symbol}|{timeframe}"

        while self._running:
            try:
                candles = await self._exchange.watch_ohlcv(symbol, timeframe)
                self._last_message_time = time.time()
                self._consecutive_failures = 0

                # Store raw candle data
                self._candles[cache_key] = candles

                logger.debug(
                    "WS candle %s (%s): %d candles, latest close=%.8g",
                    symbol,
                    timeframe,
                    len(candles),
                    candles[-1][4] if candles else 0,
                )

                # Also update price cache from the latest candle close
                if candles:
                    latest = candles[-1]
                    # candle format: [timestamp, open, high, low, close, volume]
                    if symbol not in self._prices:
                        self._prices[symbol] = {}
                    self._prices[symbol].update(
                        {
                            "price": latest[4],  # close
                            "timestamp": latest[0],
                        }
                    )

                # Fire candle callbacks
                for cb in self._on_candle_update:
                    try:
                        result = cb(symbol, timeframe, candles)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        logger.warning(
                            "Candle update callback error for %s: %s", symbol, e
                        )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                await self._handle_disconnect(e, f"candle:{symbol}")

    async def _health_monitor(self) -> None:
        """Monitor connection health, detect dead connections."""
        logger.debug("Health monitor started (interval=%ds)", self._health_check_interval)
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)
            except asyncio.CancelledError:
                raise

            now = time.time()
            if self._last_message_time > 0:
                silence = now - self._last_message_time

                if silence > self._dead_connection_timeout:
                    logger.error(
                        "Dead WebSocket connection detected (%.0fs silence), "
                        "forcing reconnect",
                        silence,
                    )
                    await self._force_reconnect()
                elif silence > self._dead_connection_timeout / 2:
                    logger.warning(
                        "WebSocket silent for %.0fs, may need reconnect", silence
                    )

    # ------------------------------------------------------------------
    # Reconnection logic
    # ------------------------------------------------------------------

    async def _handle_disconnect(self, error: Exception, context: str = "") -> None:
        """Multi-tier reconnection logic.

        Tier 1 (attempts 1-3):   quick retry at tier_delays[0] (default 0.5s)
        Tier 2 (attempts 4-10):  extended retry at tier_delays[1] (default 5s)
        Tier 3 (attempts 11+):   force reconnect at tier_delays[2] (default 30s)
        After 20 failures:       fall back to REST polling
        """
        self._consecutive_failures += 1

        if self._consecutive_failures <= 3:
            delay = self._tier_delays[0] if self._tier_delays else 0.5
            self._reconnect_tier = 1
        elif self._consecutive_failures <= 10:
            delay = self._tier_delays[1] if len(self._tier_delays) > 1 else 5.0
            self._reconnect_tier = 2
        else:
            delay = self._tier_delays[2] if len(self._tier_delays) > 2 else 30.0
            self._reconnect_tier = 3
            await self._force_reconnect()

        logger.warning(
            "WebSocket error [%s] (tier %d, attempt %d): %s. Retrying in %.1fs",
            context,
            self._reconnect_tier,
            self._consecutive_failures,
            error,
            delay,
        )

        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise

        # After too many failures, fall back to REST
        if self._consecutive_failures > 20 and not self._rest_fallback_active:
            logger.error(
                "WebSocket failed %d times, falling back to REST polling",
                self._consecutive_failures,
            )
            self._rest_fallback_active = True
            self._tasks.append(asyncio.create_task(self._rest_polling_loop()))

    async def _force_reconnect(self) -> None:
        """Close and re-establish the exchange connection."""
        logger.info("Force-reconnecting to %s ...", self._exchange_id)
        try:
            if self._exchange is not None:
                await self._exchange.close()
                self._exchange = None
            await self.connect()
            self._consecutive_failures = 0
            logger.info("Force-reconnect to %s succeeded", self._exchange_id)
        except Exception as e:
            logger.error("Force reconnect to %s failed: %s", self._exchange_id, e)

    async def _rest_polling_loop(self) -> None:
        """Fallback REST polling when WebSocket is down.

        Polls tickers for all subscribed symbols at a fixed interval.
        Automatically stops when WebSocket recovers.
        """
        logger.info(
            "REST fallback polling started (interval=%ds, symbols=%d)",
            self._rest_poll_interval,
            len(self._ticker_symbols),
        )
        while self._running and self._rest_fallback_active:
            for symbol in list(self._ticker_symbols):
                try:
                    ticker = await self._exchange.fetch_ticker(symbol)
                    price_data = {
                        "price": ticker.get("last") or ticker.get("close", 0),
                        "bid": ticker.get("bid", 0),
                        "ask": ticker.get("ask", 0),
                        "volume": ticker.get("baseVolume", 0),
                        "timestamp": ticker.get(
                            "timestamp", int(time.time() * 1000)
                        ),
                    }
                    self._prices[symbol] = price_data
                    self._last_message_time = time.time()

                    logger.debug(
                        "REST fallback %s: %.8g", symbol, price_data["price"]
                    )

                    # Fire callbacks even in REST mode
                    for cb in self._on_price_update:
                        try:
                            result = cb(
                                symbol,
                                price_data["price"],
                                price_data["timestamp"],
                            )
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception as e:
                            logger.warning(
                                "REST fallback callback error for %s: %s",
                                symbol,
                                e,
                            )
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("REST fallback error for %s: %s", symbol, e)

            try:
                await asyncio.sleep(self._rest_poll_interval)
            except asyncio.CancelledError:
                raise

        logger.info("REST fallback polling stopped")

    # ------------------------------------------------------------------
    # Status / diagnostics
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether the manager is actively running."""
        return self._running

    @property
    def is_websocket_active(self) -> bool:
        """Whether the WebSocket connection is active (vs REST fallback)."""
        return self._ws_supported and not self._rest_fallback_active

    @property
    def subscribed_symbols(self) -> Set[str]:
        """Set of symbols currently subscribed for ticker updates."""
        return set(self._ticker_symbols)

    def status(self) -> Dict[str, Any]:
        """Return a diagnostic status dict."""
        now = time.time()
        silence = (
            now - self._last_message_time if self._last_message_time > 0 else None
        )
        return {
            "exchange": self._exchange_id,
            "running": self._running,
            "ws_supported": self._ws_supported,
            "rest_fallback_active": self._rest_fallback_active,
            "ticker_symbols": sorted(self._ticker_symbols),
            "candle_subscriptions": dict(self._candle_subscriptions),
            "cached_prices": len(self._prices),
            "consecutive_failures": self._consecutive_failures,
            "reconnect_tier": self._reconnect_tier,
            "last_message_age_seconds": round(silence, 1) if silence else None,
        }
