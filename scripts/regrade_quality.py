#!/usr/bin/env python3
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'symptom_logs.db'

THRESHOLD = 0.6


def main() -> None:
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    # good if > 0.6 else poor (unknown은 유지하지 않고 새 기준으로 덮어씀)
    cur.execute(
        """
        UPDATE symptom_logs
        SET advice_quality = CASE WHEN rag_confidence > ? THEN 'good' ELSE 'poor' END
        """,
        (THRESHOLD,),
    )
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM symptom_logs")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM symptom_logs WHERE advice_quality='good'")
    good = cur.fetchone()[0]
    conn.close()
    print(f"Regraded {total} rows. good={good}, poor={total-good}")


if __name__ == '__main__':
    main()
