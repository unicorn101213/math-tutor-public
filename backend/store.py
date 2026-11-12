"""一个学生一份账：会话、错题、掌握度、她自己约的提醒。"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from rational import Q, Solution


_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(timespec="seconds")


def _shanghai_now() -> datetime:
    return datetime.now(_SHANGHAI).replace(microsecond=0, tzinfo=None)


def dump_solution(sol: Solution) -> str:
    return json.dumps(
        {
            "node_id": sol.node_id,
            "stem": sol.stem,
            "answer_display": sol.answer_display,
            "kind": sol.kind,
            "steps": sol.steps,
            "summary": sol.summary,
            "figure": sol.figure,
            "value": [sol.value.n, sol.value.d] if sol.value else None,
            "compare": sol.compare,
            "traps": {key: [item.n, item.d] for key, item in sol.traps.items()},
        },
        ensure_ascii=False,
    )


def load_solution(raw: str | None) -> Solution | None:
    if not raw:
        return None
    data = json.loads(raw)
    value = Q(data["value"][0], data["value"][1]) if data.get("value") else None
    traps = {key: Q(pair[0], pair[1]) for key, pair in (data.get("traps") or {}).items()}
    return Solution(
        node_id=data["node_id"],
        stem=data["stem"],
        answer_display=data["answer_display"],
        kind=data["kind"],
        steps=data["steps"],
        summary=data["summary"],
        figure=data.get("figure"),
        value=value,
        compare=data.get("compare"),
        traps=traps,
    )


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    device_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    node_id TEXT DEFAULT '',
                    problem_json TEXT DEFAULT '',
                    awaiting TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    error_code TEXT NOT NULL,
                    stem TEXT NOT NULL,
                    student_answer TEXT DEFAULT '',
                    expected TEXT DEFAULT '',
                    summary TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mastery (
                    device_id TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    asked_count INTEGER DEFAULT 0,
                    wrong_count INTEGER DEFAULT 0,
                    right_count INTEGER DEFAULT 0,
                    last_error_code TEXT DEFAULT '',
                    PRIMARY KEY (device_id, node_id)
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    note TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    hinted INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS knowledge_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    node_id TEXT DEFAULT '',
                    chapter_id TEXT DEFAULT '',
                    volume TEXT DEFAULT '七年级',
                    title TEXT NOT NULL,
                    tags TEXT DEFAULT '',
                    summary TEXT NOT NULL,
                    mindmap_json TEXT DEFAULT '[]',
                    example TEXT DEFAULT '',
                    figure_json TEXT DEFAULT '',
                    ask_count INTEGER DEFAULT 1,
                    updated_at TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in con.execute("PRAGMA table_info(sessions)")}
            if "sheet_json" not in columns:
                con.execute("ALTER TABLE sessions ADD COLUMN sheet_json TEXT DEFAULT ''")
            err_cols = {row[1] for row in con.execute("PRAGMA table_info(errors)")}
            if "chapter_id" not in err_cols:
                con.execute("ALTER TABLE errors ADD COLUMN chapter_id TEXT DEFAULT ''")
            if "solution" not in err_cols:
                con.execute("ALTER TABLE errors ADD COLUMN solution TEXT DEFAULT ''")
            if "source" not in err_cols:
                con.execute("ALTER TABLE errors ADD COLUMN source TEXT DEFAULT 'practice'")
            msg_cols = {row[1] for row in con.execute("PRAGMA table_info(messages)")}
            if "blocks_json" not in msg_cols:
                con.execute("ALTER TABLE messages ADD COLUMN blocks_json TEXT DEFAULT ''")
            rem_cols = {row[1] for row in con.execute("PRAGMA table_info(reminders)")}
            if "kind" not in rem_cols:
                con.execute("ALTER TABLE reminders ADD COLUMN kind TEXT DEFAULT 'note'")
            if "topic" not in rem_cols:
                con.execute("ALTER TABLE reminders ADD COLUMN topic TEXT DEFAULT ''")
        from accounts import ensure_schema
        ensure_schema(self)

    @contextmanager
    def _conn(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def ensure_session(self, device_id: str, session_id: str | None) -> str:
        with self._conn() as con:
            if session_id:
                row = con.execute("SELECT id FROM sessions WHERE id = ? AND device_id = ?", (session_id, device_id)).fetchone()
                if row:
                    return session_id
            elif device_id:
                row = con.execute(
                    "SELECT id FROM sessions WHERE device_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                    (device_id,),
                ).fetchone()
                if row:
                    return row["id"]
            new_id = session_id or datetime.now().strftime("%Y%m%d%H%M%S%f")
            con.execute(
                "INSERT OR IGNORE INTO sessions (id, device_id, created_at) VALUES (?, ?, ?)",
                (new_id, device_id, _now()),
            )
            return new_id

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        with self._conn() as con:
            return con.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def save_problem(self, session_id: str, node_id: str, sol: Solution | None, awaiting: str):
        with self._conn() as con:
            con.execute(
                "UPDATE sessions SET node_id = ?, problem_json = ?, awaiting = ? WHERE id = ?",
                (node_id, dump_solution(sol) if sol else "", awaiting, session_id),
            )

    def save_sheet(self, session_id: str, items: list[dict]):
        with self._conn() as con:
            con.execute(
                "UPDATE sessions SET sheet_json = ? WHERE id = ?",
                (json.dumps(items, ensure_ascii=False), session_id),
            )

    def get_sheet(self, session_id: str) -> list[dict]:
        with self._conn() as con:
            row = con.execute("SELECT sheet_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row or not row["sheet_json"]:
            return []
        data = json.loads(row["sheet_json"])
        return data if isinstance(data, list) else []

    def save_last_images(self, session_id: str, images_b64: list[str]):
        safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
        if not safe_id or not images_b64:
            return
        img_file = self.path.parent / f"last_imgs_{safe_id}.json"
        img_file.write_text(json.dumps(images_b64, ensure_ascii=False), encoding="utf-8")
        # Also keep single-image file for backward compatibility
        single_file = self.path.parent / f"last_img_{safe_id}.b64"
        single_file.write_text(images_b64[0], encoding="utf-8")

    def get_last_images(self, session_id: str) -> list[str]:
        safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
        if not safe_id:
            return []
        img_file = self.path.parent / f"last_imgs_{safe_id}.json"
        if img_file.is_file():
            try:
                data = json.loads(img_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    return [str(x) for x in data if x]
            except json.JSONDecodeError:
                pass
        single = self.get_last_image(session_id)
        return [single] if single else []

    def save_last_image(self, session_id: str, image_b64: str):
        self.save_last_images(session_id, [image_b64])

    def get_last_image(self, session_id: str) -> str | None:
        safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
        if not safe_id:
            return None
        img_file = self.path.parent / f"last_img_{safe_id}.b64"
        if img_file.is_file():
            return img_file.read_text(encoding="utf-8")
        return None

    def add_message(self, session_id: str, role: str, content: str, blocks: list[dict] | None = None) -> int:
        b_json = json.dumps(blocks, ensure_ascii=False) if blocks else ""
        with self._conn() as con:
            cur = con.execute(
                "INSERT INTO messages (session_id, role, content, blocks_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, role, content[:4000], b_json, _now()),
            )
            return int(cur.lastrowid)

    def save_message_images(self, message_id: int, images_b64: list[str]) -> None:
        folder = self.path.parent / "chat_images"
        folder.mkdir(parents=True, exist_ok=True)
        for index, raw in enumerate(images_b64[:6]):
            text = str(raw or "").strip()
            if not text:
                continue
            (folder / f"{message_id}_{index}.b64").write_text(text, encoding="utf-8")

    def message_images(self, message_id: int) -> list[str]:
        folder = self.path.parent / "chat_images"
        if not folder.is_dir():
            return []
        found = []
        for index in range(6):
            path = folder / f"{message_id}_{index}.b64"
            if not path.is_file():
                break
            found.append(_strip_data_url(path.read_text(encoding="utf-8").strip()))
        return found

    def get_device_history(
        self,
        device_id: str,
        limit: int = 40,
        after_id: int = 0,
        include_images: bool = True,
    ) -> dict:
        with self._conn() as con:
            s_row = con.execute(
                "SELECT id FROM sessions WHERE device_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (device_id,),
            ).fetchone()
            latest_sid = s_row["id"] if s_row else None
            sql = """
                SELECT m.id, m.session_id, m.role, m.content, m.blocks_json, m.created_at
                FROM messages m
                JOIN sessions s ON m.session_id = s.id
                WHERE s.device_id = ?
            """
            params: list = [device_id]
            if after_id:
                sql += " AND m.id > ?"
                params.append(after_id)
            sql += " ORDER BY m.id DESC LIMIT ?"
            params.append(limit)
            rows = con.execute(sql, params).fetchall()
        messages_out = []
        for r in reversed(rows):
            blocks = []
            if r["blocks_json"]:
                try:
                    parsed = json.loads(r["blocks_json"])
                    if isinstance(parsed, list):
                        blocks = parsed
                except json.JSONDecodeError:
                    blocks = []
            if not blocks and r["role"] == "assistant" and r["content"]:
                blocks = [{"type": "text", "text": r["content"]}]
            messages_out.append(
                {
                    "id": r["id"],
                    "session_id": r["session_id"],
                    "role": r["role"],
                    "text": r["content"],
                    "blocks": blocks,
                    "images": self.message_images(r["id"]) if include_images and r["role"] == "user" else [],
                    "created_at": r["created_at"],
                }
            )
        photo_msgs = [
            item
            for item in messages_out
            if item["role"] == "user" and str(item["text"]).startswith("[照片")
        ]
        if include_images and photo_msgs and not photo_msgs[-1]["images"]:
            fallback = self.get_last_images(photo_msgs[-1]["session_id"])
            if fallback:
                photo_msgs[-1]["images"] = [_strip_data_url(img) for img in fallback]
        return {
            "session_id": latest_sid,
            "messages": messages_out,
        }

    def clear_device_history(self, device_id: str) -> int:
        with self._conn() as con:
            s_rows = con.execute("SELECT id FROM sessions WHERE device_id = ?", (device_id,)).fetchall()
            sids = [r["id"] for r in s_rows]
            deleted = 0
            msg_ids: list[int] = []
            if sids:
                placeholders = ",".join("?" for _ in sids)
                msg_ids = [
                    row[0]
                    for row in con.execute(
                        f"SELECT id FROM messages WHERE session_id IN ({placeholders})",
                        sids,
                    )
                ]
                cur = con.execute(f"DELETE FROM messages WHERE session_id IN ({placeholders})", sids)
                deleted = cur.rowcount
                con.execute("DELETE FROM sessions WHERE device_id = ?", (device_id,))
        folder = self.path.parent / "chat_images"
        for mid in msg_ids:
            if folder.is_dir():
                for path in folder.glob(f"{mid}_*.b64"):
                    try:
                        path.unlink()
                    except OSError:
                        pass
        for sid in sids:
            safe_id = "".join(ch for ch in sid if ch.isalnum() or ch in "-_")
            if safe_id:
                for fname in (f"last_img_{safe_id}.b64", f"last_imgs_{safe_id}.json"):
                    fpath = self.path.parent / fname
                    if fpath.is_file():
                        try:
                            fpath.unlink()
                        except OSError:
                            pass
        return deleted

    def recent_messages(self, session_id: str, limit: int = 8) -> list[sqlite3.Row]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def recent_dialog(self, device_id: str, limit: int = 12) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT m.id, m.role, m.content
                FROM messages m
                JOIN sessions s ON m.session_id = s.id
                WHERE s.device_id = ?
                ORDER BY m.id DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return [
            {"id": row["id"], "role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]

    def recent_photo_sets(self, device_id: str, limit: int = 4) -> list[list[str]]:
        """最新的在前。每一项是那一次发送带上的照片。"""
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT m.id
                FROM messages m
                JOIN sessions s ON m.session_id = s.id
                WHERE s.device_id = ? AND m.role = 'user' AND m.content LIKE '[照片%'
                ORDER BY m.id DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        sets: list[list[str]] = []
        for row in rows:
            images = self.message_images(row["id"])
            if images:
                sets.append(images)
        return sets

    def recent_answers(self, device_id: str, limit: int = 12) -> list[dict]:
        """最新的在前。跳过「没讲出来」那种很短的回复。"""
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT m.content, m.blocks_json
                FROM messages m
                JOIN sessions s ON m.session_id = s.id
                WHERE s.device_id = ? AND m.role = 'assistant'
                ORDER BY m.id DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        answers: list[dict] = []
        for row in rows:
            content = row["content"] or ""
            if "你可以拍题" in content and len(content) < 80:
                continue
            blocks = []
            if row["blocks_json"]:
                try:
                    parsed = json.loads(row["blocks_json"])
                    if isinstance(parsed, list):
                        blocks = parsed
                except json.JSONDecodeError:
                    blocks = []
            if not blocks:
                blocks = [{"type": "text", "text": content}]
            answers.append({"content": content, "blocks": blocks})
        return answers

    def record_error(
        self,
        device_id: str,
        node_id: str,
        code: str,
        stem: str,
        student: str,
        expected: str,
        summary: str,
        solution: str = "",
        source: str = "practice",
        images: list[str] | None = None,
    ) -> int:
        from curriculum import chapter_of

        ch = chapter_of(node_id)
        chapter_id = ch["id"] if ch else ""
        with self._conn() as con:
            cur = con.execute(
                """
                INSERT INTO errors (device_id, node_id, chapter_id, error_code, stem, student_answer, expected, summary, solution, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    node_id,
                    chapter_id,
                    code,
                    stem[:1500],
                    student[:400],
                    expected[:400],
                    summary[:600],
                    solution[:3500],
                    source,
                    _now(),
                ),
            )
            error_id = int(cur.lastrowid)
            con.execute(
                """
                INSERT INTO mastery (device_id, node_id, asked_count, wrong_count, right_count, last_error_code)
                VALUES (?, ?, 1, 1, 0, ?)
                ON CONFLICT(device_id, node_id) DO UPDATE SET
                    asked_count = asked_count + 1,
                    wrong_count = wrong_count + 1,
                    last_error_code = excluded.last_error_code
                """,
                (device_id, node_id, code),
            )
        if images:
            self.save_error_images(error_id, images)
        return error_id

    def save_error_images(self, error_id: int, images_b64: list[str]) -> None:
        folder = self.path.parent / "error_images"
        folder.mkdir(parents=True, exist_ok=True)
        kept = 0
        for raw in images_b64[:3]:
            text = _strip_data_url(str(raw or "").strip())
            if not text:
                continue
            (folder / f"{error_id}_{kept}.b64").write_text(text, encoding="utf-8")
            kept += 1

    def error_images(self, error_id: int) -> list[str]:
        folder = self.path.parent / "error_images"
        if not folder.is_dir():
            return []
        found = []
        for index in range(3):
            path = folder / f"{error_id}_{index}.b64"
            if not path.is_file():
                break
            found.append(path.read_text(encoding="utf-8").strip())
        return found

    def delete_error(self, device_id: str, error_id: int) -> bool:
        with self._conn() as con:
            row = con.execute(
                "SELECT id FROM errors WHERE id = ? AND device_id = ?",
                (error_id, device_id),
            ).fetchone()
            if row is None:
                return False
            con.execute("DELETE FROM errors WHERE id = ? AND device_id = ?", (error_id, device_id))
        folder = self.path.parent / "error_images"
        for index in range(3):
            path = folder / f"{error_id}_{index}.b64"
            if path.is_file():
                path.unlink()
        return True

    def record_right(self, device_id: str, node_id: str):
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO mastery (device_id, node_id, asked_count, wrong_count, right_count)
                VALUES (?, ?, 1, 0, 1)
                ON CONFLICT(device_id, node_id) DO UPDATE SET
                    asked_count = asked_count + 1,
                    right_count = right_count + 1
                """,
                (device_id, node_id),
            )

    def record_asked(self, device_id: str, node_id: str) -> int:
        if node_id not in _known_nodes():
            return 0
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO mastery (device_id, node_id, asked_count, wrong_count, right_count)
                VALUES (?, ?, 1, 0, 0)
                ON CONFLICT(device_id, node_id) DO UPDATE SET
                    asked_count = asked_count + 1
                """,
                (device_id, node_id),
            )
            row = con.execute(
                "SELECT asked_count FROM mastery WHERE device_id = ? AND node_id = ?",
                (device_id, node_id),
            ).fetchone()
            return int(row["asked_count"]) if row else 1

    def upsert_knowledge_card(
        self,
        device_id: str,
        title: str,
        summary: str,
        mindmap: list[str] | None = None,
        node_id: str = "",
        chapter_id: str = "",
        volume: str = "七年级拓展/专题",
        tags: str = "",
        example: str = "",
        figure: dict | None = None,
    ) -> dict:
        from curriculum import chapter_of

        title_clean = title.strip()[:80]
        if not chapter_id and node_id:
            ch = chapter_of(node_id)
            if ch:
                chapter_id = ch["id"]
                volume = ch["volume"]
        mm_json = json.dumps(mindmap or [], ensure_ascii=False)
        fig_json = json.dumps(figure, ensure_ascii=False) if figure else ""
        with self._conn() as con:
            existing = con.execute(
                "SELECT id, ask_count FROM knowledge_cards WHERE device_id = ? AND title = ?",
                (device_id, title_clean),
            ).fetchone()
            if existing:
                new_count = int(existing["ask_count"]) + 1
                con.execute(
                    """
                    UPDATE knowledge_cards
                    SET summary = ?, mindmap_json = ?, node_id = ?, chapter_id = ?, volume = ?,
                        tags = ?, example = ?, figure_json = ?, ask_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        summary[:2000],
                        mm_json,
                        node_id,
                        chapter_id,
                        volume,
                        tags[:200],
                        example[:1500],
                        fig_json,
                        new_count,
                        _now(),
                        existing["id"],
                    ),
                )
                card_id = existing["id"]
            else:
                cur = con.execute(
                    """
                    INSERT INTO knowledge_cards
                    (device_id, node_id, chapter_id, volume, title, tags, summary, mindmap_json, example, figure_json, ask_count, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        device_id,
                        node_id,
                        chapter_id,
                        volume,
                        title_clean,
                        tags[:200],
                        summary[:2000],
                        mm_json,
                        example[:1500],
                        fig_json,
                        _now(),
                    ),
                )
                card_id = cur.lastrowid
                new_count = 1
        return {
            "id": card_id,
            "title": title_clean,
            "node_id": node_id,
            "chapter_id": chapter_id,
            "volume": volume,
            "tags": tags,
            "summary": summary,
            "mindmap": mindmap or [],
            "example": example,
            "figure": figure,
            "ask_count": new_count,
        }

    def list_knowledge_cards(self, device_id: str, query: str | None = None, limit: int = 30) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT * FROM knowledge_cards WHERE device_id = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
        out = []
        q = (query or "").strip().lower()
        for r in rows:
            item = {
                "id": r["id"],
                "title": r["title"],
                "node_id": r["node_id"],
                "chapter_id": r["chapter_id"],
                "volume": r["volume"],
                "tags": r["tags"],
                "summary": r["summary"],
                "mindmap": json.loads(r["mindmap_json"] or "[]"),
                "example": r["example"],
                "figure": json.loads(r["figure_json"]) if r["figure_json"] else None,
                "ask_count": r["ask_count"],
                "updated_at": r["updated_at"],
            }
            if q:
                title_tags = f"{item['title']} {item['tags']}".lower()
                body_hay = f"{item['summary']} {item['example']}".lower()
                if q in title_tags:
                    item["_score"] = 3
                elif any(tok in title_tags for tok in q.split() if tok):
                    item["_score"] = 2
                elif q in body_hay:
                    item["_score"] = 1
                else:
                    continue
            out.append(item)
        if q:
            out.sort(key=lambda x: x.get("_score", 0), reverse=True)
            for x in out:
                x.pop("_score", None)
        return out

    def mastery_map(self, device_id: str) -> dict[str, sqlite3.Row]:
        with self._conn() as con:
            rows = con.execute("SELECT * FROM mastery WHERE device_id = ?", (device_id,)).fetchall()
        return {row["node_id"]: row for row in rows}

    def list_errors(self, device_id: str, node_id: str | None = None, limit: int = 12) -> list[sqlite3.Row]:
        with self._conn() as con:
            if node_id:
                return con.execute(
                    """
                    SELECT * FROM errors WHERE device_id = ? AND node_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (device_id, node_id, limit),
                ).fetchall()
            return con.execute(
                "SELECT * FROM errors WHERE device_id = ? ORDER BY id DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()

    def error_counts(self, device_id: str) -> list[sqlite3.Row]:
        with self._conn() as con:
            return con.execute(
                """
                SELECT error_code, node_id, COUNT(*) AS n
                FROM errors WHERE device_id = ?
                GROUP BY error_code, node_id
                ORDER BY n DESC LIMIT 6
                """,
                (device_id,),
            ).fetchall()

    def add_reminder(self, device_id: str, note: str, due_at: str, kind: str = "note", topic: str = ""):
        with self._conn() as con:
            con.execute(
                """
                INSERT INTO reminders (device_id, note, due_at, hinted, kind, topic)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (device_id, note, due_at, kind, topic),
            )

    def take_due_reminders(self, device_id: str) -> list[dict]:
        with self._conn() as con:
            rows = con.execute(
                """
                SELECT * FROM reminders
                WHERE device_id = ? AND hinted = 0 AND due_at <= ?
                ORDER BY due_at
                """,
                (device_id, _shanghai_now().isoformat(timespec="seconds")),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                marks = ",".join("?" for _ in ids)
                con.execute(f"UPDATE reminders SET hinted = 1 WHERE id IN ({marks})", ids)
            return [dict(row) for row in rows]

    def weak_nodes(self, device_id: str, limit: int = 6) -> list[sqlite3.Row]:
        with self._conn() as con:
            return con.execute(
                """
                SELECT node_id, COUNT(*) AS n
                FROM errors
                WHERE device_id = ?
                GROUP BY node_id
                ORDER BY n DESC, MAX(id) DESC
                LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()


def _known_nodes() -> set[str]:
    from curriculum import NODES

    return set(NODES)


def _strip_data_url(value: str) -> str:
    if value.startswith("data:"):
        comma = value.find(",")
        if comma != -1:
            return value[comma + 1 :]
    return value


_CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _cn_number(token: str) -> int | None:
    token = token.strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    if token == "十":
        return 10
    if token.startswith("十") and len(token) == 2 and token[1] in _CN_DIGIT:
        return 10 + _CN_DIGIT[token[1]]
    if "十" in token:
        left, right = token.split("十", 1)
        tens = _CN_DIGIT.get(left, 1) if left else 1
        ones = _CN_DIGIT.get(right, 0) if right else 0
        if left and left not in _CN_DIGIT:
            return None
        if right and right not in _CN_DIGIT:
            return None
        return tens * 10 + ones
    if len(token) == 1 and token in _CN_DIGIT:
        return _CN_DIGIT[token]
    return None


def _clock(text: str) -> tuple[int | None, int]:
    matched = re.search(r"(\d{1,2})\s*(?:[:：]\s*(\d{1,2}))?\s*[点时]", text)
    if matched:
        return int(matched.group(1)), int(matched.group(2) or 0)
    matched = re.search(r"([零〇一二两三四五六七八九十]{1,3})\s*点(?:\s*([零〇一二两三四五六七八九十]{1,3}|\d{1,2})\s*分)?", text)
    if matched:
        hour = _cn_number(matched.group(1))
        minute_token = matched.group(2) or ""
        minute = _cn_number(minute_token) if minute_token else 0
        if hour is None or minute is None:
            return None, 0
        return hour, minute
    matched = re.search(r"(\d{1,2})\s*[:：]\s*(\d{1,2})", text)
    if matched:
        return int(matched.group(1)), int(matched.group(2))
    return None, 0


def _apply_day_part(hour: int, text: str) -> int:
    if any(word in text for word in ("下午", "晚上", "今晚")) and hour < 12:
        return hour + 12
    if "中午" in text and hour < 11:
        return 12
    if any(word in text for word in ("上午", "早上", "早晨", "今早")) and hour == 12:
        return 0
    return hour


def parse_task(text: str) -> dict | None:
    """从一句话里读出预约。有钟点或今/明/后天，并且是在约提醒或约出题。"""
    if not text:
        return None
    if not any(word in text for word in ("提醒", "帮我", "出一", "出道", "出题", "来一道", "记得", "数学题")):
        return None
    now = _shanghai_now()
    if "大后天" in text:
        day = now + timedelta(days=3)
    elif "后天" in text:
        day = now + timedelta(days=2)
    elif "明天" in text:
        day = now + timedelta(days=1)
    elif any(word in text for word in ("今天", "今晚", "今早", "早上", "上午", "下午", "晚上")):
        day = now
    else:
        return None
    hour, minute = _clock(text)
    if hour is None:
        if any(word in text for word in ("今晚", "晚上")):
            hour, minute = 20, 0
        elif "下午" in text:
            hour, minute = 15, 0
        elif any(word in text for word in ("上午", "早上", "早晨", "今早")):
            hour, minute = 8, 0
        elif "中午" in text:
            hour, minute = 12, 0
        elif any(word in text for word in ("明天", "后天", "大后天")):
            hour, minute = 19, 0
        else:
            return None
    hour = _apply_day_part(hour, text)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    due = day.replace(hour=hour, minute=minute, second=0)
    if due <= now and not any(word in text for word in ("明天", "后天", "大后天")):
        due = due + timedelta(days=1)
    kind = "problem" if any(word in text for word in ("出一", "出道", "出题", "来一道", "数学题", "练一")) else "note"
    from curriculum import match_topic

    topic = match_topic(text) or ""
    return {
        "note": text.strip(),
        "due_at": due.isoformat(timespec="seconds"),
        "kind": kind,
        "topic": topic,
        "when_label": _when_label(due, now),
    }


def _when_label(due: datetime, now: datetime) -> str:
    days = (due.date() - now.date()).days
    prefix = {0: "今天", 1: "明天", 2: "后天", 3: "大后天"}.get(days, f"{due.month}月{due.day}日")
    hour = due.hour
    if hour < 6:
        part, shown = "凌晨", hour
    elif hour < 12:
        part, shown = "上午", hour
    elif hour == 12:
        part, shown = "中午", 12
    elif hour < 18:
        part, shown = "下午", hour - 12
    else:
        part, shown = "晚上", hour - 12
    clock = f"{shown}:{due.minute:02d}" if due.minute else f"{shown}点"
    return f"{prefix}{part}{clock}"
