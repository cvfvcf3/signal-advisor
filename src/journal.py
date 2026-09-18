"""
journal.py
----------
Every signal the advisor issues gets written here, along with the full
breakdown of why. Later, once enough time/candles have passed, the advisor
checks what price actually did and marks the signal correct/incorrect --
building a real, self-reported accuracy track record instead of just
trusting the confidence number blindly.
"""

import sqlite3
import json
import os
from datetime import datetime, timezone
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "signal_journal.db")


class Journal:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    action TEXT NOT NULL,             -- BUY | SELL
                    confidence REAL,
                    price_at_signal REAL,
                    buy_score REAL,
                    sell_score REAL,
                    technical_notes TEXT,
                    mtf_notes TEXT,
                    orderbook_notes TEXT,
                    market_structure_notes TEXT,
                    created_at TEXT NOT NULL,
                    eval_at_candle INTEGER,           -- candle index the signal should be evaluated at
                    status TEXT DEFAULT 'pending',     -- pending | correct | incorrect
                    price_at_eval REAL,
                    pct_move REAL,
                    evaluated_at TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT,
                    message TEXT
                )
            """)

    # ---- signals -----------------------------------------------------------
    def record_signal(self, symbol, timeframe, action, confidence, price, buy_score, sell_score,
                       technical_notes, mtf_notes, orderbook_notes, market_structure_notes, eval_candle_index):
        with self._conn() as c:
            cur = c.execute("""
                INSERT INTO signals (symbol, timeframe, action, confidence, price_at_signal,
                                      buy_score, sell_score, technical_notes, mtf_notes,
                                      orderbook_notes, market_structure_notes, created_at, eval_at_candle)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, timeframe, action, confidence, price, buy_score, sell_score,
                  json.dumps(technical_notes), json.dumps(mtf_notes), json.dumps(orderbook_notes),
                  json.dumps(market_structure_notes), datetime.now(timezone.utc).isoformat(), eval_candle_index))
            return cur.lastrowid

    def get_pending_signals(self, symbol):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM signals WHERE symbol=? AND status='pending' ORDER BY id", (symbol,)
            ).fetchall()
            return [dict(r) for r in rows]

    def resolve_signal(self, signal_id, price_at_eval, success_move_pct):
        with self._conn() as c:
            row = c.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
            if not row:
                return
            entry = row["price_at_signal"]
            pct_move = (price_at_eval - entry) / entry * 100 if entry else 0
            if row["action"] == "SELL":
                pct_move = -pct_move
            status = "correct" if pct_move >= success_move_pct else "incorrect"
            c.execute("""
                UPDATE signals SET status=?, price_at_eval=?, pct_move=?, evaluated_at=?
                WHERE id=?
            """, (status, price_at_eval, round(pct_move, 3), datetime.now(timezone.utc).isoformat(), signal_id))

    def get_recent_signals(self, symbol, limit=100):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM signals WHERE symbol=? ORDER BY id DESC LIMIT ?", (symbol, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_accuracy_stats(self, symbol):
        with self._conn() as c:
            rows = c.execute(
                "SELECT status FROM signals WHERE symbol=? AND status != 'pending'", (symbol,)
            ).fetchall()
        total = len(rows)
        correct = sum(1 for r in rows if r["status"] == "correct")
        with self._conn() as c:
            pending = c.execute(
                "SELECT COUNT(*) as n FROM signals WHERE symbol=? AND status='pending'", (symbol,)
            ).fetchone()["n"]
        return {
            "total_evaluated": total,
            "correct": correct,
            "incorrect": total - correct,
            "accuracy_pct": round(correct / total * 100, 1) if total else None,
            "pending": pending,
        }

    # ---- log ----------------------------------------------------------------
    def log(self, message, level="info"):
        with self._conn() as c:
            c.execute(
                "INSERT INTO activity_log (timestamp, level, message) VALUES (?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), level, message),
            )

    def get_recent_logs(self, limit=150):
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM activity_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]
