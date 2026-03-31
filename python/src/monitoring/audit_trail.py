"""Append-only audit trail for trading decisions.

Every trade decision is logged with full context in JSONL format.
Files rotate daily: audit_YYYY-MM-DD.jsonl
Hash chain: each record includes SHA-256 hash of previous record for tamper detection.
"""

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditRecord:
    record_id: str = ""
    timestamp: str = ""
    record_type: str = ""  # trade_decision, position_closed, safety_triggered, system_event
    symbol: str = ""
    action: str = ""  # BUY, SELL, HOLD, REJECTED, SKIPPED, CLOSE
    technical_signal: Optional[Dict] = None
    sentiment_signal: Optional[Dict] = None
    fused_signal: Optional[Dict] = None
    meta_reasoning: Optional[Dict] = None
    risk_state: Optional[Dict] = None
    trade_details: Optional[Dict] = None
    outcome: Optional[Dict] = None
    degradation_level: Optional[str] = None
    circuit_breaker: Optional[Dict] = None
    previous_hash: str = ""
    record_hash: str = ""


class AuditTrail:
    """Append-only, hash-chained audit trail."""

    def __init__(self, config: Dict[str, Any]):
        audit_cfg = config.get("audit", {})
        self._enabled = audit_cfg.get("enabled", True)
        self._dir = Path(audit_cfg.get("directory", "data/audit"))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._last_hash = ""
        self._current_file = None
        self._current_date: Optional[date] = None
        self._record_count = 0
        self._restore_last_hash()

    def _get_file_path(self, d: Optional[date] = None) -> Path:
        d = d or date.today()
        return self._dir / f"audit_{d.isoformat()}.jsonl"

    def _ensure_file(self) -> None:
        today = date.today()
        if self._current_date != today or self._current_file is None:
            if self._current_file:
                self._current_file.close()
            path = self._get_file_path(today)
            self._current_file = open(path, "a")
            self._current_date = today

    def _compute_hash(self, data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _restore_last_hash(self) -> None:
        files = sorted(self._dir.glob("audit_*.jsonl"), reverse=True)
        for f in files:
            try:
                with open(f, "r") as fh:
                    lines = fh.readlines()
                    if lines:
                        last = json.loads(lines[-1])
                        self._last_hash = last.get("record_hash", "")
                        return
            except Exception:
                continue

    def _write_record(self, record: AuditRecord) -> None:
        if not self._enabled:
            return
        record.record_id = str(uuid.uuid4())[:12]
        record.timestamp = datetime.utcnow().isoformat()
        record.previous_hash = self._last_hash

        record_dict = asdict(record)
        record_dict.pop("record_hash", None)
        content = json.dumps(record_dict, sort_keys=True, default=str)
        record.record_hash = self._compute_hash(content)
        self._last_hash = record.record_hash

        self._ensure_file()
        line = json.dumps(asdict(record), default=str)
        self._current_file.write(line + "\n")
        self._current_file.flush()
        self._record_count += 1

    def log_decision(self, symbol: str, action: str, **kwargs) -> None:
        self._write_record(AuditRecord(
            record_type="trade_decision", symbol=symbol, action=action,
            technical_signal=kwargs.get("technical_signal"),
            sentiment_signal=kwargs.get("sentiment_signal"),
            fused_signal=kwargs.get("fused_signal"),
            meta_reasoning=kwargs.get("meta_reasoning"),
            risk_state=kwargs.get("risk_state"),
            trade_details=kwargs.get("trade_details"),
            degradation_level=kwargs.get("degradation_level"),
            circuit_breaker=kwargs.get("circuit_breaker"),
        ))

    def log_position_closed(self, symbol: str, entry_price: float,
                            exit_price: float, pnl: float, reason: str,
                            duration_hours: float = 0, **kwargs) -> None:
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
        self._write_record(AuditRecord(
            record_type="position_closed", symbol=symbol, action="CLOSE",
            outcome={"entry_price": entry_price, "exit_price": exit_price,
                     "pnl": pnl, "pnl_pct": pnl_pct, "reason": reason,
                     "duration_hours": duration_hours},
            risk_state=kwargs.get("risk_state"),
        ))

    def log_safety_event(self, event_type: str, details: Dict) -> None:
        self._write_record(AuditRecord(
            record_type="safety_triggered", symbol="", action=event_type,
            risk_state=details,
        ))

    def log_system_event(self, event: str, details: Optional[Dict] = None) -> None:
        self._write_record(AuditRecord(
            record_type="system_event", symbol="", action=event,
            risk_state=details or {},
        ))

    def get_recent(self, limit: int = 50, record_type: Optional[str] = None) -> List[Dict]:
        records: List[Dict] = []
        files = sorted(self._dir.glob("audit_*.jsonl"), reverse=True)
        for f in files:
            try:
                with open(f, "r") as fh:
                    for line in reversed(fh.readlines()):
                        if line.strip():
                            rec = json.loads(line)
                            if record_type is None or rec.get("record_type") == record_type:
                                records.append(rec)
                            if len(records) >= limit:
                                return records
            except Exception:
                continue
        return records

    def verify_chain(self, date_str: Optional[str] = None) -> bool:
        d = date.fromisoformat(date_str) if date_str else date.today()
        path = self._get_file_path(d)
        if not path.exists():
            return True
        prev_hash = ""
        with open(path, "r") as f:
            for i, line in enumerate(f):
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("previous_hash", "") != prev_hash:
                    logger.error("Chain broken at record %d", i)
                    return False
                stored_hash = rec.pop("record_hash", "")
                content = json.dumps(rec, sort_keys=True, default=str)
                computed = self._compute_hash(content)
                if computed != stored_hash:
                    logger.error("Hash mismatch at record %d", i)
                    return False
                prev_hash = stored_hash
        logger.info("Audit chain verified for %s", d.isoformat())
        return True

    def close(self) -> None:
        if self._current_file:
            self._current_file.close()
            self._current_file = None

    @property
    def status(self) -> Dict[str, Any]:
        files = sorted(self._dir.glob("audit_*.jsonl"))
        total = 0
        for f in files:
            try:
                with open(f) as fh:
                    total += sum(1 for _ in fh)
            except Exception:
                pass
        return {
            "enabled": self._enabled,
            "directory": str(self._dir),
            "files": len(files),
            "total_records": total,
            "session_records": self._record_count,
            "last_hash": self._last_hash,
        }
