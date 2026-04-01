"""1D-CNN for chart pattern detection on raw price sequences.

Detects classical chart patterns from raw price data using Conv1d layers:
- Double top / double bottom
- Head and shoulders / inverse H&S
- Ascending / descending triangles
- Bull / bear flags
- Rising / falling wedges

NOT image-based; operates directly on 1D price + volume sequences.
"""

import os
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

import copy

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from src.utils.types import Signal, Direction

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Recognized chart patterns."""
    DOUBLE_TOP = "double_top"
    DOUBLE_BOTTOM = "double_bottom"
    HEAD_SHOULDERS = "head_and_shoulders"
    INV_HEAD_SHOULDERS = "inverse_head_and_shoulders"
    ASC_TRIANGLE = "ascending_triangle"
    DESC_TRIANGLE = "descending_triangle"
    BULL_FLAG = "bull_flag"
    BEAR_FLAG = "bear_flag"
    RISING_WEDGE = "rising_wedge"
    FALLING_WEDGE = "falling_wedge"
    NO_PATTERN = "no_pattern"


# Map pattern to expected direction: 1 = bullish, -1 = bearish, 0 = neutral
PATTERN_DIRECTION = {
    PatternType.DOUBLE_TOP: -1,
    PatternType.DOUBLE_BOTTOM: 1,
    PatternType.HEAD_SHOULDERS: -1,
    PatternType.INV_HEAD_SHOULDERS: 1,
    PatternType.ASC_TRIANGLE: 1,
    PatternType.DESC_TRIANGLE: -1,
    PatternType.BULL_FLAG: 1,
    PatternType.BEAR_FLAG: -1,
    PatternType.RISING_WEDGE: -1,
    PatternType.FALLING_WEDGE: 1,
    PatternType.NO_PATTERN: 0,
}

NUM_PATTERNS = len(PatternType)


class PatternCNNNetwork(nn.Module):
    """1D-CNN for multi-label pattern classification."""

    def __init__(
        self,
        input_channels: int = 5,  # OHLCV
        seq_length: int = 60,
        dropout: float = 0.2,
    ):
        super().__init__()

        # Multi-scale convolutions (different kernel sizes catch different pattern scales)
        self.conv_small = nn.Sequential(
            nn.Conv1d(input_channels, 32, kernel_size=3, padding=1),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),
        )

        self.conv_medium = nn.Sequential(
            nn.Conv1d(input_channels, 32, kernel_size=7, padding=3),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=7, padding=3),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),
        )

        self.conv_large = nn.Sequential(
            nn.Conv1d(input_channels, 32, kernel_size=15, padding=7),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Conv1d(32, 64, kernel_size=15, padding=7),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(2),
        )

        # Merge multi-scale features
        merged_channels = 64 * 3  # 3 scales
        pooled_len = seq_length // 2

        self.merge_conv = nn.Sequential(
            nn.Conv1d(merged_channels, 128, kernel_size=3, padding=1),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.AdaptiveAvgPool1d(1),
        )

        # Pattern classification (multi-label via sigmoid)
        self.pattern_head = nn.Sequential(
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, NUM_PATTERNS),
        )

        # Direction head (binary: up/down)
        self.direction_head = nn.Sequential(
            nn.Linear(128, 32),
            nn.ReLU(),
            nn.Linear(32, 2),
        )

        # Confidence head
        self.confidence_head = nn.Sequential(
            nn.Linear(128, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(
        self, x: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Args:
            x: (batch, input_channels, seq_length) — channels-first

        Returns:
            pattern_logits: (batch, NUM_PATTERNS)
            direction_logits: (batch, 2)
            confidence: (batch, 1)
        """
        # Multi-scale convolutions
        s = self.conv_small(x)
        m = self.conv_medium(x)
        l = self.conv_large(x)

        # Concatenate along channel dimension
        merged = torch.cat([s, m, l], dim=1)  # (batch, 192, pooled_len)
        features = self.merge_conv(merged).squeeze(-1)  # (batch, 128)

        pattern_logits = self.pattern_head(features)
        direction_logits = self.direction_head(features)
        confidence = self.confidence_head(features)

        return pattern_logits, direction_logits, confidence


class _EarlyStopping:
    """Stop training when validation loss stops improving.

    Saves the best model weights (by validation loss) and restores them
    when patience is exhausted or training completes.
    """

    def __init__(self, patience: int = 7, min_delta: float = 0.0):
        self.patience = patience
        self.min_delta = min_delta
        self.best_loss: Optional[float] = None
        self.best_weights: Optional[dict] = None
        self.counter = 0
        self.stopped_epoch = 0

    def step(self, val_loss: float, model: nn.Module, epoch: int) -> bool:
        """Return True if training should stop."""
        if self.best_loss is None or val_loss < self.best_loss - self.min_delta:
            self.best_loss = val_loss
            self.best_weights = copy.deepcopy(model.state_dict())
            self.counter = 0
            return False
        self.counter += 1
        if self.counter >= self.patience:
            self.stopped_epoch = epoch
            return True
        return False

    def restore_best(self, model: nn.Module) -> None:
        """Load the best weights back into the model."""
        if self.best_weights is not None:
            model.load_state_dict(self.best_weights)


class PatternCNN:
    """Train/predict interface for the pattern detection CNN."""

    def __init__(
        self,
        input_channels: int = 5,
        seq_length: int = 60,
        dropout: float = 0.2,
        learning_rate: float = 0.001,
        epochs: int = 100,
        batch_size: int = 64,
        device: Optional[str] = None,
        val_split: float = 0.2,
        early_stopping_patience: int = 7,
    ):
        self.input_channels = input_channels
        self.seq_length = seq_length
        self.dropout = dropout
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.batch_size = batch_size
        self.val_split = val_split
        self.early_stopping_patience = early_stopping_patience

        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.model = PatternCNNNetwork(
            input_channels=input_channels,
            seq_length=seq_length,
            dropout=dropout,
        ).to(self.device)

        self.optimizer = torch.optim.Adam(
            self.model.parameters(), lr=learning_rate, weight_decay=1e-5
        )
        self.pattern_criterion = nn.BCEWithLogitsLoss()
        self.direction_criterion = nn.CrossEntropyLoss()

        self.train_losses: list = []
        self.val_losses: list = []
        self.is_trained = False

    def prepare_input(self, df_ohlcv: np.ndarray) -> np.ndarray:
        """Prepare OHLCV data for CNN input.

        Normalizes each sequence independently by dividing by the first close
        price and subtracting 1 (relative changes).

        Args:
            df_ohlcv: Raw OHLCV array (n_samples, seq_length, 5)
                      where channels are [open, high, low, close, volume].

        Returns:
            Normalized array (n_samples, 5, seq_length) — channels first.
        """
        X = df_ohlcv.copy().astype(np.float32)

        # Normalize price channels by first close of each sequence
        for i in range(X.shape[0]):
            ref_price = X[i, 0, 3]  # First bar's close
            if ref_price > 0:
                X[i, :, :4] = X[i, :, :4] / ref_price - 1  # Relative changes

            # Normalize volume separately (ratio to mean)
            vol_mean = X[i, :, 4].mean()
            if vol_mean > 0:
                X[i, :, 4] = X[i, :, 4] / vol_mean - 1
            else:
                X[i, :, 4] = 0

        # Transpose to channels-first: (batch, channels, seq_len)
        X = np.transpose(X, (0, 2, 1))
        return X

    def train(
        self,
        X: np.ndarray,
        y_patterns: np.ndarray,
        y_direction: np.ndarray,
        epochs: Optional[int] = None,
    ) -> Dict[str, list]:
        """Train the pattern CNN with validation split and early stopping.

        Uses a time-based split (last ``val_split`` fraction of samples as
        validation) which is more appropriate for financial time-series than
        a random split — it prevents future data from leaking into training.

        Best model weights (by validation loss) are restored at the end.

        Args:
            X: Input (n_samples, channels, seq_length).
            y_patterns: Multi-hot pattern labels (n_samples, NUM_PATTERNS).
            y_direction: Direction labels (n_samples,) — 0=down, 1=up.
            epochs: Override default.

        Returns:
            Training history with train_loss and val_loss.
        """
        if epochs is None:
            epochs = self.epochs

        # --- Time-based train / validation split (no shuffle across split) ---
        n_samples = X.shape[0]
        n_val = max(1, int(n_samples * self.val_split))
        n_train = n_samples - n_val

        X_train = torch.FloatTensor(X[:n_train]).to(self.device)
        yp_train = torch.FloatTensor(y_patterns[:n_train]).to(self.device)
        yd_train = torch.LongTensor(y_direction[:n_train]).to(self.device)

        X_val = torch.FloatTensor(X[n_train:]).to(self.device)
        yp_val = torch.FloatTensor(y_patterns[n_train:]).to(self.device)
        yd_val = torch.LongTensor(y_direction[n_train:]).to(self.device)

        train_dataset = TensorDataset(X_train, yp_train, yd_train)
        train_loader = DataLoader(train_dataset, batch_size=self.batch_size, shuffle=True)

        val_dataset = TensorDataset(X_val, yp_val, yd_val)
        val_loader = DataLoader(val_dataset, batch_size=self.batch_size, shuffle=False)

        self.train_losses = []
        self.val_losses = []

        early_stopper = _EarlyStopping(patience=self.early_stopping_patience)

        logger.info(
            "PatternCNN training: %d train / %d val samples, max %d epochs, "
            "early-stop patience=%d",
            n_train, n_val, epochs, self.early_stopping_patience,
        )

        for epoch in range(epochs):
            # --- Training pass ---
            self.model.train()
            epoch_loss = 0.0
            n_batches = 0

            for X_b, yp_b, yd_b in train_loader:
                self.optimizer.zero_grad()
                pat_logits, dir_logits, _ = self.model(X_b)

                loss_pattern = self.pattern_criterion(pat_logits, yp_b)
                loss_direction = self.direction_criterion(dir_logits, yd_b)
                loss = loss_pattern + loss_direction

                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
                self.optimizer.step()
                epoch_loss += loss.item()
                n_batches += 1

            avg_train_loss = epoch_loss / max(n_batches, 1)
            self.train_losses.append(avg_train_loss)

            # --- Validation pass ---
            self.model.eval()
            val_loss = 0.0
            val_batches = 0
            with torch.no_grad():
                for X_b, yp_b, yd_b in val_loader:
                    pat_logits, dir_logits, _ = self.model(X_b)
                    loss_pattern = self.pattern_criterion(pat_logits, yp_b)
                    loss_direction = self.direction_criterion(dir_logits, yd_b)
                    val_loss += (loss_pattern + loss_direction).item()
                    val_batches += 1

            avg_val_loss = val_loss / max(val_batches, 1)
            self.val_losses.append(avg_val_loss)

            if (epoch + 1) % 10 == 0 or epoch == 0:
                logger.info(
                    "PatternCNN epoch %d/%d: train_loss=%.4f  val_loss=%.4f",
                    epoch + 1, epochs, avg_train_loss, avg_val_loss,
                )

            # --- Early stopping check ---
            if early_stopper.step(avg_val_loss, self.model, epoch):
                logger.info(
                    "PatternCNN early stopping at epoch %d (best val_loss=%.4f at epoch %d)",
                    epoch + 1, early_stopper.best_loss,
                    epoch + 1 - early_stopper.patience,
                )
                break

        # Restore the best model weights (lowest validation loss)
        early_stopper.restore_best(self.model)
        self.model.eval()
        self.is_trained = True

        logger.info(
            "PatternCNN training complete: best val_loss=%.4f, %d epochs run",
            early_stopper.best_loss or self.val_losses[-1],
            len(self.train_losses),
        )

        return {"train_loss": self.train_losses, "val_loss": self.val_losses}

    def predict(
        self, X: np.ndarray, asset: str = "", timeframe: str = "1h"
    ) -> Signal:
        """Detect patterns and predict direction from a single sequence.

        Args:
            X: (1, channels, seq_length) or (channels, seq_length).
            asset: Asset identifier.
            timeframe: Timeframe string.

        Returns:
            Signal with detected patterns in metadata.
        """
        if not self.is_trained:
            return Signal(
                asset=asset,
                direction=Direction.HOLD,
                confidence=0.0,
                source="pattern_cnn",
                timeframe=timeframe,
            )

        if X.ndim == 2:
            X = X[np.newaxis, :]

        self.model.eval()
        with torch.no_grad():
            X_t = torch.FloatTensor(X).to(self.device)
            pat_logits, dir_logits, confidence = self.model(X_t)

            pat_probs = torch.sigmoid(pat_logits).cpu().numpy()[0]
            dir_probs = torch.softmax(dir_logits, dim=1).cpu().numpy()[0]
            conf_val = confidence.cpu().numpy()[0, 0]

        # Detected patterns (threshold > 0.5)
        patterns = list(PatternType)
        detected = []
        net_direction = 0.0
        for i, pattern in enumerate(patterns):
            if pat_probs[i] > 0.5:
                detected.append({
                    "pattern": pattern.value,
                    "confidence": float(pat_probs[i]),
                    "direction": PATTERN_DIRECTION[pattern],
                })
                net_direction += PATTERN_DIRECTION[pattern] * pat_probs[i]

        # Direction from direction head
        prob_up = dir_probs[1] if len(dir_probs) > 1 else 0.5
        combined_confidence = float(conf_val * 100)

        # Combine pattern direction with direction head
        if net_direction > 0.5:
            direction = Direction.BUY
        elif net_direction < -0.5:
            direction = Direction.SELL
        elif prob_up > 0.6:
            direction = Direction.BUY
        elif prob_up < 0.4:
            direction = Direction.SELL
        else:
            direction = Direction.HOLD

        return Signal(
            asset=asset,
            direction=direction,
            confidence=combined_confidence,
            source="pattern_cnn",
            timeframe=timeframe,
            metadata={
                "detected_patterns": detected,
                "pattern_direction": float(net_direction),
                "prob_up": float(prob_up),
                "raw_confidence": float(conf_val),
            },
        )

    def predict_batch(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Batch prediction for ensemble integration.

        Args:
            X: (n_samples, channels, seq_length)

        Returns:
            (direction_probs [n, 2], confidence [n])
        """
        if not self.is_trained:
            n = X.shape[0]
            return np.full((n, 2), 0.5), np.zeros(n)

        self.model.eval()
        with torch.no_grad():
            X_t = torch.FloatTensor(X).to(self.device)
            _, dir_logits, confidence = self.model(X_t)
            probs = torch.softmax(dir_logits, dim=1).cpu().numpy()
            conf = confidence.cpu().numpy().squeeze()

        return probs, conf

    def save(self, path: str) -> None:
        """Save model checkpoint."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        torch.save(
            {
                "model_state": self.model.state_dict(),
                "input_channels": self.input_channels,
                "seq_length": self.seq_length,
                "dropout": self.dropout,
                "is_trained": self.is_trained,
                "timestamp": datetime.utcnow().isoformat(),
            },
            path,
        )
        logger.info(f"PatternCNN saved to {path}")

    def load(self, path: str) -> None:
        """Load model checkpoint."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)

        self.model = PatternCNNNetwork(
            input_channels=checkpoint["input_channels"],
            seq_length=checkpoint["seq_length"],
            dropout=checkpoint["dropout"],
        ).to(self.device)

        self.model.load_state_dict(checkpoint["model_state"])
        self.model.eval()
        self.is_trained = checkpoint.get("is_trained", True)
        logger.info(f"PatternCNN loaded from {path}")


def generate_pattern_labels(
    df_ohlcv: np.ndarray,
    future_returns: np.ndarray,
    seq_length: int = 60,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate pattern labels using heuristic detection for training data.

    This provides weak supervision for the CNN. The model learns to refine
    these heuristic labels through training.

    Args:
        df_ohlcv: OHLCV sequences (n_samples, seq_length, 5).
        future_returns: Future returns for each sample (n_samples,).
        seq_length: Length of each sequence.

    Returns:
        (pattern_labels [n, NUM_PATTERNS], direction_labels [n])
    """
    n = len(df_ohlcv)
    patterns = np.zeros((n, NUM_PATTERNS), dtype=np.float32)
    directions = np.zeros(n, dtype=np.int64)

    for i in range(n):
        seq = df_ohlcv[i]  # (seq_length, 5)
        close = seq[:, 3]  # Close prices
        high = seq[:, 1]
        low = seq[:, 2]

        # Direction label from future returns
        directions[i] = 1 if future_returns[i] > 0 else 0

        # Heuristic pattern detection
        detected = _detect_patterns_heuristic(close, high, low)
        for pat_idx in detected:
            patterns[i, pat_idx] = 1.0

    return patterns, directions


def _detect_patterns_heuristic(
    close: np.ndarray, high: np.ndarray, low: np.ndarray
) -> List[int]:
    """Simple heuristic pattern detection for label generation."""
    detected = []
    n = len(close)
    if n < 20:
        return detected

    # Find local peaks and troughs
    peaks = []
    troughs = []
    for i in range(2, n - 2):
        if high[i] > high[i - 1] and high[i] > high[i - 2] and high[i] > high[i + 1] and high[i] > high[i + 2]:
            peaks.append((i, high[i]))
        if low[i] < low[i - 1] and low[i] < low[i - 2] and low[i] < low[i + 1] and low[i] < low[i + 2]:
            troughs.append((i, low[i]))

    # Double top: two peaks at similar levels with trough between
    if len(peaks) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        if abs(p1[1] - p2[1]) / p1[1] < 0.01 and p2[0] - p1[0] > 5:
            detected.append(list(PatternType).index(PatternType.DOUBLE_TOP))

    # Double bottom: two troughs at similar levels
    if len(troughs) >= 2:
        t1, t2 = troughs[-2], troughs[-1]
        if abs(t1[1] - t2[1]) / t1[1] < 0.01 and t2[0] - t1[0] > 5:
            detected.append(list(PatternType).index(PatternType.DOUBLE_BOTTOM))

    # Head and shoulders: three peaks, middle higher
    if len(peaks) >= 3:
        p1, p2, p3 = peaks[-3], peaks[-2], peaks[-1]
        if p2[1] > p1[1] and p2[1] > p3[1] and abs(p1[1] - p3[1]) / p1[1] < 0.015:
            detected.append(list(PatternType).index(PatternType.HEAD_SHOULDERS))

    # Inverse H&S
    if len(troughs) >= 3:
        t1, t2, t3 = troughs[-3], troughs[-2], troughs[-1]
        if t2[1] < t1[1] and t2[1] < t3[1] and abs(t1[1] - t3[1]) / t1[1] < 0.015:
            detected.append(list(PatternType).index(PatternType.INV_HEAD_SHOULDERS))

    # Ascending triangle: flat resistance, rising support
    if len(peaks) >= 2 and len(troughs) >= 2:
        peak_levels = [p[1] for p in peaks[-3:]]
        trough_levels = [t[1] for t in troughs[-3:]]
        if len(peak_levels) >= 2:
            peak_range = (max(peak_levels) - min(peak_levels)) / max(peak_levels)
            trough_slope = (trough_levels[-1] - trough_levels[0]) / max(abs(trough_levels[0]), 1e-8)
            if peak_range < 0.005 and trough_slope > 0.005:
                detected.append(list(PatternType).index(PatternType.ASC_TRIANGLE))
            if peak_range < 0.005 and trough_slope < -0.005:
                detected.append(list(PatternType).index(PatternType.DESC_TRIANGLE))

    # Bull/Bear flag: strong move followed by tight consolidation
    half = n // 2
    first_half_ret = (close[half] - close[0]) / close[0]
    second_half_range = (high[half:].max() - low[half:].min()) / close[half]
    if first_half_ret > 0.02 and second_half_range < 0.01:
        detected.append(list(PatternType).index(PatternType.BULL_FLAG))
    if first_half_ret < -0.02 and second_half_range < 0.01:
        detected.append(list(PatternType).index(PatternType.BEAR_FLAG))

    # If nothing detected, mark as no_pattern
    if not detected:
        detected.append(list(PatternType).index(PatternType.NO_PATTERN))

    return detected
