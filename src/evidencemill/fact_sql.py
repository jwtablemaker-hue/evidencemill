from __future__ import annotations

import json
import sqlite3
from typing import Iterable

from evidencemill.worker import FactCandidate


STAGING_TABLE = "evidencemill_fact_candidates"


def create_sqlite_fact_staging(
    connection: sqlite3.Connection,
    *,
    table: str = STAGING_TABLE,
) -> None:
    quoted = '"' + table.replace('"', '""') + '"'
    connection.execute(
        f"""CREATE TABLE IF NOT EXISTS {quoted}(
          candidate_id TEXT PRIMARY KEY,
          source_id TEXT NOT NULL,
          source_location TEXT,
          source_text TEXT,
          observation_kind TEXT NOT NULL,
          subject_hint TEXT,
          predicate_hint TEXT,
          value_json TEXT,
          unit TEXT,
          qualifiers_json TEXT NOT NULL,
          conditions_json TEXT NOT NULL,
          context_json TEXT NOT NULL,
          readiness TEXT NOT NULL,
          review_reason TEXT,
          review_reasons_json TEXT NOT NULL DEFAULT '[]',
          confidence REAL NOT NULL
        )"""
    )
    existing_columns = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({quoted})")
    }
    if "review_reasons_json" not in existing_columns:
        connection.execute(
            f"""ALTER TABLE {quoted}
                ADD COLUMN review_reasons_json TEXT NOT NULL DEFAULT '[]'"""
        )


def _row(candidate: FactCandidate) -> tuple:
    return (
        candidate.candidate_id,
        candidate.source.source_id,
        candidate.source.location,
        candidate.source.raw_text,
        candidate.observation_kind,
        candidate.subject_hint,
        candidate.predicate_hint,
        json.dumps(candidate.value, ensure_ascii=False, separators=(",", ":"), default=str),
        candidate.unit,
        json.dumps(list(candidate.qualifiers), ensure_ascii=False, separators=(",", ":")),
        json.dumps(candidate.conditions, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
        json.dumps(candidate.context, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str),
        candidate.readiness,
        candidate.review_reason,
        json.dumps(
            list(candidate.review_reasons),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        candidate.confidence,
    )


def stage_candidates_sqlite(
    connection: sqlite3.Connection,
    candidates: Iterable[FactCandidate],
    *,
    table: str = STAGING_TABLE,
) -> int:
    create_sqlite_fact_staging(connection, table=table)
    quoted = '"' + table.replace('"', '""') + '"'
    sql = f"""INSERT INTO {quoted}(
      candidate_id,source_id,source_location,source_text,observation_kind,
      subject_hint,predicate_hint,value_json,unit,qualifiers_json,
      conditions_json,context_json,readiness,review_reason,review_reasons_json,confidence
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(candidate_id) DO UPDATE SET
      source_text=excluded.source_text,
      subject_hint=excluded.subject_hint,
      predicate_hint=excluded.predicate_hint,
      value_json=excluded.value_json,
      unit=excluded.unit,
      qualifiers_json=excluded.qualifiers_json,
      conditions_json=excluded.conditions_json,
      context_json=excluded.context_json,
      readiness=excluded.readiness,
      review_reason=excluded.review_reason,
      review_reasons_json=excluded.review_reasons_json,
      confidence=excluded.confidence"""
    rows = [_row(candidate) for candidate in candidates]
    connection.executemany(sql, rows)
    return len(rows)
