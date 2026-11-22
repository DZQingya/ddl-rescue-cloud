"""多通知工作台的 SQLite 持久化层。

只负责保存和读取，不依赖 Streamlit，方便后续做多通知聚合和测试。
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


APP_TIMEZONE = timezone(timedelta(hours=8))
DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "workspace.db"


def _db_path(db_path: str | Path | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(os.environ.get("WORKSPACE_DB", str(DEFAULT_DB_PATH)))
VALID_STATUSES = {"pending", "reopened", "primary", "active", "done", "stuck"}
DDL_STATUSES = VALID_STATUSES - {"primary"}


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str | Path | None = None) -> None:
    connection = _connect(db_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notice_records (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Additive migration: preserve the legacy notice table and its status column.
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ddl_statuses (
                notice_id TEXT NOT NULL,
                ddl_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'reopened', 'active', 'done', 'stuck')),
                updated_at TEXT NOT NULL,
                PRIMARY KEY (notice_id, ddl_id)
            )
            """
        )
        # primary 是界面派生状态；把旧版本写入 DDL 表的值归一为 pending。
        connection.execute(
            "UPDATE ddl_statuses SET status = 'pending' WHERE status = 'primary'"
        )
        _ensure_ddl_status_rows(connection)
        connection.commit()
    finally:
        connection.close()


def _ensure_ddl_status_rows(
    connection: sqlite3.Connection, record_id: str | None = None
) -> None:
    query = "SELECT id, parsed_json, status, updated_at FROM notice_records"
    params: tuple[str, ...] = ()
    if record_id is not None:
        query += " WHERE id = ?"
        params = (record_id,)
    for row in connection.execute(query, params).fetchall():
        try:
            parsed = json.loads(row["parsed_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(parsed, dict):
            continue
        legacy_status = row["status"] if row["status"] in DDL_STATUSES else "pending"
        for item in parsed.get("ddl_items") or []:
            if not isinstance(item, dict):
                continue
            ddl_id = str(item.get("id") or "").strip()
            if not ddl_id:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO ddl_statuses (notice_id, ddl_id, status, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (row["id"], ddl_id, legacy_status, row["updated_at"]),
            )


def _row_to_record(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "raw_text": row["raw_text"],
        "parsed": json.loads(row["parsed_json"]),
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_notice(
    parsed: dict[str, Any],
    raw_text: str | None = None,
    status: str = "pending",
    record_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """新增或更新一条通知记录，返回可被 UI 使用的记录。"""
    if not isinstance(parsed, dict):
        raise TypeError("parsed 必须是字典")
    if status not in VALID_STATUSES:
        raise ValueError(f"无效状态: {status}")
    now = datetime.now(APP_TIMEZONE).isoformat()
    init_db(db_path)
    connection = _connect(db_path)
    try:
        if record_id:
            existing = connection.execute(
                "SELECT created_at FROM notice_records WHERE id = ?",
                (record_id,),
            ).fetchone()
            if existing is None:
                record_id = None
        if record_id:
            created_at = existing["created_at"]
            connection.execute(
                """
                UPDATE notice_records
                SET title = ?, raw_text = ?, parsed_json = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(parsed.get("title") or "未命名通知"),
                    str(raw_text or parsed.get("raw_text") or ""),
                    json.dumps(parsed, ensure_ascii=False),
                    status,
                    now,
                    record_id,
                ),
            )
        else:
            record_id = uuid.uuid4().hex
            created_at = now
            connection.execute(
                """
                INSERT INTO notice_records
                    (id, title, raw_text, parsed_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    str(parsed.get("title") or "未命名通知"),
                    str(raw_text or parsed.get("raw_text") or ""),
                    json.dumps(parsed, ensure_ascii=False),
                    status,
                    created_at,
                    now,
                ),
            )
        connection.commit()
        _ensure_ddl_status_rows(connection, record_id)
        connection.commit()
        row = connection.execute(
            "SELECT * FROM notice_records WHERE id = ?", (record_id,)
        ).fetchone()
        return _row_to_record(row)
    finally:
        connection.close()


def list_notices(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    init_db(db_path)
    connection = _connect(db_path)
    try:
        rows = connection.execute(
            "SELECT * FROM notice_records ORDER BY updated_at DESC, created_at DESC"
        ).fetchall()
        return [_row_to_record(row) for row in rows]
    finally:
        connection.close()


def get_notice(record_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    init_db(db_path)
    connection = _connect(db_path)
    try:
        row = connection.execute(
            "SELECT * FROM notice_records WHERE id = ?", (record_id,)
        ).fetchone()
        return _row_to_record(row) if row else None
    finally:
        connection.close()


def update_status(
    record_id: str,
    status: str,
    db_path: str | Path | None = None,
) -> bool:
    if status not in VALID_STATUSES:
        raise ValueError(f"无效状态: {status}")
    init_db(db_path)
    connection = _connect(db_path)
    try:
        cursor = connection.execute(
            "UPDATE notice_records SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now(APP_TIMEZONE).isoformat(), record_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def list_ddl_statuses(
    record_id: str, db_path: str | Path | None = None
) -> list[dict[str, str]]:
    """列出通知内 DDL 状态，顺序与 parsed.ddl_items 一致。"""
    init_db(db_path)
    connection = _connect(db_path)
    try:
        notice = connection.execute(
            "SELECT parsed_json FROM notice_records WHERE id = ?", (record_id,)
        ).fetchone()
        if notice is None:
            return []
        rows = connection.execute(
            "SELECT ddl_id, status, updated_at FROM ddl_statuses WHERE notice_id = ?",
            (record_id,),
        ).fetchall()
        by_id = {row["ddl_id"]: row for row in rows}
        parsed = json.loads(notice["parsed_json"])
        result = []
        for item in parsed.get("ddl_items") or []:
            if not isinstance(item, dict):
                continue
            ddl_id = str(item.get("id") or "").strip()
            row = by_id.get(ddl_id)
            if row is not None:
                result.append({
                    "notice_id": record_id,
                    "ddl_id": ddl_id,
                    "status": row["status"],
                    "updated_at": row["updated_at"],
                })
        return result
    finally:
        connection.close()


def get_ddl_status(
    record_id: str, ddl_id: str, db_path: str | Path | None = None
) -> dict[str, str] | None:
    """读取单个 DDL 状态；不存在时返回 None。"""
    init_db(db_path)
    connection = _connect(db_path)
    try:
        row = connection.execute(
            "SELECT notice_id, ddl_id, status, updated_at FROM ddl_statuses "
            "WHERE notice_id = ? AND ddl_id = ?",
            (record_id, ddl_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def update_ddl_status(
    record_id: str,
    ddl_id: str,
    status: str,
    db_path: str | Path | None = None,
) -> bool:
    """更新一个 DDL 状态，不影响同通知中的其他 DDL。"""
    if status not in DDL_STATUSES:
        raise ValueError(f"无效 DDL 状态: {status}")
    init_db(db_path)
    connection = _connect(db_path)
    try:
        cursor = connection.execute(
            "UPDATE ddl_statuses SET status = ?, updated_at = ? "
            "WHERE notice_id = ? AND ddl_id = ?",
            (status, datetime.now(APP_TIMEZONE).isoformat(), record_id, ddl_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def mark_ddl_done(
    record_id: str, ddl_id: str, db_path: str | Path | None = None
) -> bool:
    """将指定 DDL 标记为完成。"""
    return update_ddl_status(record_id, ddl_id, "done", db_path)


def reopen_ddl(
    record_id: str, ddl_id: str, db_path: str | Path | None = None
) -> bool:
    """重新打开指定 DDL。"""
    return update_ddl_status(record_id, ddl_id, "reopened", db_path)


def delete_ddl_status(
    record_id: str,
    ddl_id: str,
    db_path: str | Path | None = None,
) -> bool:
    """删除单个 DDL 的状态行，不触碰同一通知内的其他任务。"""
    init_db(db_path)
    connection = _connect(db_path)
    try:
        cursor = connection.execute(
            "DELETE FROM ddl_statuses WHERE notice_id = ? AND ddl_id = ?",
            (record_id, ddl_id),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def delete_notice(record_id: str, db_path: str | Path | None = None) -> bool:
    init_db(db_path)
    connection = _connect(db_path)
    try:
        connection.execute("DELETE FROM ddl_statuses WHERE notice_id = ?", (record_id,))
        cursor = connection.execute("DELETE FROM notice_records WHERE id = ?", (record_id,))
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()
