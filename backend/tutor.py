"""对话外壳：讲题（含多图+指定题号）、错题库（4类入库标准+章节归档+完整解析）、知识点库（全12章导图+动态入库）。"""

from __future__ import annotations

import random
import re

from curriculum import (
    CHAPTERS,
    ERROR_OPEN,
    LOCKED,
    NODES,
    chapter_of,
    chapters_for,
    error_label,
    grade_profile,
    _grade_rank,
    match_topic,
    node_title,
    normalize_grade,
)
from problems import GENERATORS, generate
from rational import Solution, check_answer, parse_answer_number, solve_item, solve_text, validate_figure
from store import Store, load_solution, parse_task

_EXPLAIN = ("讲讲", "梳理", "系统讲", "什么是", "怎么理解", "给我讲", "知识点", "知识库", "专题")
_CONTEXT = ("相关", "这个", "那个", "刚才", "上面", "卡片", "接着", "继续", "还有", "区别")
_DIAGRAM = ("如图", "看图", "画出", "数轴", "单位长度")
_SIMILAR = ("类似", "再来一道", "再出", "出一道", "出几道", "换一道", "换数字", "同型题")
_ERRORS = ("翻翻错题", "错题本", "错题库", "常错", "以前的错", "以前错", "查看错题", "看看错题")
_SAVE_ERROR = (
    "放入错题",
    "放到错题",
    "记入错题",
    "加入错题",
    "加到错题",
    "存到错题",
    "存入错题",
    "记进错题",
    "收到错题",
    "这题我做错了",
    "这道我做错了",
)
_REVEAL = ("这题咋做", "这题怎么做", "怎么做", "咋做", "直接讲", "讲透")
_FOLLOWUP = ("第", "重做", "再讲", "再试", "重试", "再发", "重新讲", "为什么", "为啥", "如果", "要是", "改成", "图里", "上面", "刚才")
_RETRY = ("再试", "重试", "再发", "重新讲", "再讲一遍", "再看一遍")
_PHOTO_TURN_LABELS = ("刚才这张", "上一轮", "上上轮", "上上上轮")

SOURCE_LABELS = {
    "exam_wrong": "试卷/拍照错题",
    "practice": "练习做错",
    "user_saved": "主动收入错题库",
    "frequent_ask": "高频反复追问",
}


def _tree(store: Store, device_id: str, grade: str | None = None) -> dict:
    mastery = store.mastery_map(device_id)

    def status_of(node_id: str) -> str:
        row = mastery.get(node_id)
        if row is None or row["asked_count"] == 0:
            return "new"
        if row["wrong_count"] > row["right_count"]:
            return "shaky"
        if row["right_count"] > 0:
            return "ok"
        if row["asked_count"] >= 2:
            return "shaky"
        return "new"

    chapters = []
    for chapter in chapters_for(grade):
        children = [
            {
                "id": node_id,
                "title": NODES[node_id]["title"],
                "status": status_of(node_id),
                "mindmap": NODES[node_id].get("mindmap", []),
            }
            for node_id in chapter["nodes"]
            if node_id in NODES
        ]
        own = "new"
        if any(item["status"] == "shaky" for item in children):
            own = "shaky"
        elif children and all(item["status"] == "ok" for item in children):
            own = "ok"
        chapters.append(
            {
                "id": chapter["id"],
                "volume": chapter.get("volume", "七年级"),
                "title": chapter["title"],
                "intro": chapter.get("intro", ""),
                "mindmap": chapter.get("mindmap", []),
                "status": own,
                "children": children,
            }
        )
    for item in LOCKED:
        chapters.append({"id": item["id"], "title": item["title"], "status": "locked", "children": []})
    return {"type": "tree", "chapters": chapters}


def build_knowledge_catalog(store: Store, device_id: str, query: str = "", grade: str | None = None) -> dict:
    tree_data = _tree(store, device_id, grade)["chapters"]
    dynamic_cards = store.list_knowledge_cards(device_id, query=query, limit=40)
    q = (query or "").strip().lower()
    chapters_out = []
    matched_nodes = []
    limit = _grade_rank(grade)
    ordered = [
        ch
        for _, ch in sorted(
            enumerate(CHAPTERS),
            key=lambda pair: (_grade_rank(pair[1].get("grade", "j1")), pair[0]),
        )
    ]
    for ch in ordered:
        ahead = _grade_rank(ch.get("grade", "j1")) > limit
        nodes_out = []
        for nid in ch["nodes"]:
            node = NODES.get(nid)
            if not node:
                continue
            card = {
                "id": nid,
                "node_id": nid,
                "chapter_id": ch["id"],
                "volume": ch["volume"],
                "chapter_title": ch["title"],
                "title": f"{nid} {node['title']}",
                "clean_title": node["title"],
                "tags": "、".join(node.get("aliases", [])[:4]),
                "summary": node["teach"],
                "mindmap": node.get("mindmap", []),
                "pitfalls": [e["label"] for e in node.get("errors", [])],
            }
            if q:
                title_low = f"{card['title']} {card['clean_title']}".lower()
                tags_low = card["tags"].lower()
                mm_low = " ".join(card["mindmap"]).lower()
                sum_low = f"{ch['title']} {card['summary']}".lower()
                score = 0
                if q in title_low:
                    score = 4
                elif q in tags_low:
                    score = 3
                elif q in mm_low:
                    score = 2
                elif q in sum_low or any(tok in (title_low + " " + tags_low + " " + sum_low) for tok in q.split() if tok):
                    score = 1
                if score == 0:
                    continue
                card["_score"] = score
                matched_nodes.append(dict(card))
            nodes_out.append(card)
        if q:
            nodes_out.sort(key=lambda x: x.get("_score", 0), reverse=True)
            for x in nodes_out:
                x.pop("_score", None)
        ch_hay = f"{ch['title']} {ch['intro']} {' '.join(ch.get('mindmap', []))}".lower()
        if not q or q in ch_hay or nodes_out:
            chapters_out.append(
                {
                    "id": ch["id"],
                    "volume": ch["volume"],
                    "title": ch["title"],
                    "intro": ch["intro"],
                    "mindmap": ch.get("mindmap", []),
                    "guard": ch.get("guard", ""),
                    "ahead": ahead,
                    "nodes": nodes_out,
                }
            )
    if q:
        matched_nodes.sort(key=lambda x: x.get("_score", 0), reverse=True)
        has_direct_book_hit = any(x.get("_score", 0) >= 3 for x in matched_nodes)
        for x in matched_nodes:
            x.pop("_score", None)
        if has_direct_book_hit:
            dynamic_cards = [
                c for c in dynamic_cards if q in f"{c.get('title','')} {c.get('tags','')}".lower()
            ]
    return {
        "chapters": chapters_out,
        "matched_nodes": matched_nodes[:12],
        "dynamic_cards": dynamic_cards,
        "tree": tree_data,
    }


def _node_error_label(node_id: str, code: str) -> str:
    node = NODES.get(node_id) or {}
    for item in node.get("errors") or []:
        if item.get("code") == code:
            return item["label"]
    if code == "calculation":
        return "计算或审题偏差"
    return error_label(code)


def build_error_catalog(store: Store, device_id: str, chapter_id: str = "", grade: str | None = None) -> dict:
    rows = store.list_errors(device_id, None, limit=60)
    allowed_chapters = {chapter["id"] for chapter in chapters_for(grade)}
    counts = store.error_counts(device_id)
    by_chapter: dict[str, dict] = {}
    items_out = []

    for row in rows:
        nid = row["node_id"] or "1.1"
        ch = chapter_of(nid)
        cid = (row["chapter_id"] if "chapter_id" in row.keys() and row["chapter_id"] else (ch["id"] if ch else "ch1"))
        if chapter_id and cid != chapter_id:
            continue
        if ch is not None and cid not in allowed_chapters:
            continue
        ch_title = ch["title"] if ch else "初一数学综合"
        vol = ch["volume"] if ch else "七年级"
        src = row["source"] if "source" in row.keys() and row["source"] else "practice"
        sol_text = row["solution"] if "solution" in row.keys() and row["solution"] else row["summary"]
        entry = {
            "id": row["id"],
            "chapter_id": cid,
            "chapter_title": ch_title,
            "volume": vol,
            "node_id": nid,
            "node_title": node_title(nid),
            "error_code": row["error_code"],
            "error_label": _node_error_label(nid, row["error_code"]),
            "source": src,
            "source_label": SOURCE_LABELS.get(src, "错题记录"),
            "stem": row["stem"],
            "images": store.error_images(int(row["id"])),
            "student_answer": row["student_answer"],
            "expected": row["expected"],
            "summary": row["summary"],
            "solution": sol_text or row["summary"],
            "when": row["created_at"],
        }
        items_out.append(entry)
        grp = by_chapter.setdefault(
            cid,
            {
                "chapter_id": cid,
                "volume": vol,
                "chapter_title": ch_title,
                "count": 0,
                "items": [],
            },
        )
        grp["count"] += 1
        grp["items"].append(entry)

    chapter_order = {c["id"]: idx for idx, c in enumerate(CHAPTERS)}
    grouped_list = sorted(by_chapter.values(), key=lambda g: chapter_order.get(g["chapter_id"], 99))
    stats = [
        {
            "node_id": r["node_id"],
            "node_title": node_title(r["node_id"]),
            "error_label": error_label(r["error_code"]),
            "count": r["n"],
        }
        for r in counts
    ]
    return {
        "total": len(items_out),
        "stats": stats,
        "chapters": grouped_list,
        "items": items_out,
    }


def _figure_block(figure, caption: str = "") -> dict | None:
    clean = validate_figure(figure)
    if not clean:
        return None
    block = {"type": "figure", "figure": clean}
    if caption:
        block["caption"] = caption
    return block


def _is_who(text: str) -> bool:
    if any(phrase in text for phrase in ("你是谁", "你叫什么", "你能做什么", "你是做什么", "自我介绍")):
        return True
    return "介绍" in text and "自己" in text


def _can_rewrite(stem: str) -> bool:
    if any(word in stem for word in _DIAGRAM):
        return False
    return not (re.search(r"(和|与)", stem) and re.search(r"\d", stem))


def _is_bare_heading(stem: str) -> bool:
    compact = re.sub(r"\s+", "", stem)
    if re.search(r"\d\s*(?:和|与)", compact) or re.search(r"(?:和|与)\s*[+\-−|(]", compact):
        return False
    return "比较下列" in compact or "各组数的大小" in compact


def _sheet_index(text: str) -> int | None:
    folded = text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    match = re.search(r"第\s*([0-9]+|[一二三四五六七八九十])\s*(?:题|道)", folded)
    if not match:
        return None
    token = match.group(1)
    if token.isdigit():
        number = int(token)
    else:
        number = "一二三四五六七八九十".index(token) + 1
    if number < 1:
        return None
    return number


def _lesson_blocks(sol: Solution, lead: str = "", figure_caption: str = "") -> list[dict]:
    parts = []
    if lead:
        parts.append(lead)
    if sol.summary:
        parts.append(sol.summary)
    parts.extend(sol.steps)
    if sol.answer_display:
        parts.append(f"结果是 {sol.answer_display}。")
    blocks = [{"type": "text", "text": "\n".join(parts)}]
    figure = _figure_block(sol.figure, figure_caption)
    if figure:
        blocks.append(figure)
    return blocks


def _pose_blocks(sol: Solution) -> list[dict]:
    blocks = [{"type": "text", "text": sol.stem + "\n把答案发我。想让我直接讲，就说「这题咋做」。"}]
    figure = _figure_block(sol.figure)
    if figure:
        blocks.insert(0, figure)
    return blocks


def _is_explain(text: str) -> bool:
    return any(word in text for word in _EXPLAIN)


def _is_similar(text: str) -> bool:
    return any(word in text for word in _SIMILAR)


def _is_save_error(text: str) -> bool:
    return any(word in text for word in _SAVE_ERROR)


def _is_errors(text: str) -> bool:
    if _is_save_error(text):
        return False
    return any(word in text for word in _ERRORS)


def _is_weakness(text: str) -> bool:
    if "错题库" in text and "薄弱" not in text:
        return False
    keys = (
        "薄弱",
        "不擅长",
        "短板",
        "哪里不行",
        "哪些不会",
        "错得比较多",
        "做错的",
        "列出错题",
        "之前的错题",
        "当时的错题",
        "错题列出来",
        "我的错题",
    )
    return any(word in text for word in keys)


def _is_reveal(text: str) -> bool:
    return any(word in text for word in _REVEAL)


def _is_short_answer(text: str) -> bool:
    if (
        len(text) > 24
        or _is_explain(text)
        or _is_similar(text)
        or _is_errors(text)
        or _is_save_error(text)
        or _is_reveal(text)
    ):
        return False
    from rational import _parse_relation, parse_sci_form

    return parse_answer_number(text) is not None or _parse_relation(text) is not None or parse_sci_form(text) is not None


def _recent_topic(history: list[dict], session: dict | None) -> str | None:
    for item in reversed(history or []):
        if item.get("role") != "user":
            continue
        hit = match_topic(str(item.get("content") or ""), any_grade=True)
        if hit:
            return hit
    node = str((session or {}).get("node_id") or "")
    if node in NODES or any(chapter["id"] == node for chapter in CHAPTERS):
        return node
    return None


def _topic_brief(topic_id: str | None, grade: str | None) -> str:
    if not topic_id:
        return ""
    if topic_id in NODES:
        node = NODES[topic_id]
        chapter = chapter_of(topic_id)
        lines = [_ahead_line(chapter, grade) + f"刚才讲的是「{node['title']}」。{node['teach']}"]
        if chapter:
            related = [
                NODES[nid]["title"]
                for nid in chapter["nodes"]
                if nid != topic_id and nid in NODES
            ]
            if related:
                lines.append("同一章里相关的还有：" + "、".join(related[:6]) + "。")
        return "".join(lines)
    chapter = next((item for item in CHAPTERS if item["id"] == topic_id), None)
    if chapter is None:
        return ""
    return _ahead_line(chapter, grade) + f"刚才讲的是「{chapter['title']}」。{chapter['intro']}"


def _related_answer(topic_id: str, grade: str | None) -> list[dict]:
    spoken = _topic_brief(topic_id, grade)
    if not spoken:
        return [{"type": "text", "text": "你把想听的那个词说一下，例如等边三角形。"}]
    spoken += "想听其中哪一个，直接说名字。"
    return [{"type": "text", "text": spoken}]


def _followup_prompt(text: str, topic_id: str | None, grade: str | None) -> str:
    brief = _topic_brief(topic_id, grade)
    return (
        f"{brief}\n\n学生这一句：{text}\n"
        "先读对话，这一句是在问刚才的内容，不要说对话里没有题目或概念。\n"
        "用上面的课本要点，用自己的话把这一句答完。不要改列无关的章节。\n"
        "这一句如果不是计算，不要调用 math_steps，也不要说核对过算式或没有算式。\n"
        "如果上面写了是后面才学的，开头先说是哪一册。"
    )


def _ahead_line(chapter: dict | None, grade: str | None) -> str:
    if not chapter:
        return ""
    if _grade_rank(chapter.get("grade", "j1")) <= _grade_rank(grade):
        return ""
    return f"这是{chapter['volume']}才学的。"


def _explain_topic(store: Store, device_id: str, session_id: str, topic: str, grade: str | None = None) -> list[dict]:
    chapter_match = next((item for item in CHAPTERS if item["id"] == topic), None)
    if chapter_match is not None:
        store.save_problem(session_id, topic, None, "")
        text = _ahead_line(chapter_match, grade) + chapter_match["intro"] + "想听里面的某一块，直接说名字。"
        return [{"type": "text", "text": text}]

    node = NODES[topic]
    asked_count = store.record_asked(device_id, topic)
    ch = chapter_of(topic)
    pitfalls = "；".join(item["label"] for item in node.get("errors", []))
    demo = generate(topic, random.Random(topic))
    example_text = ""
    if demo and demo.kind != "explain":
        ex_lines = [f"例题：{demo.stem}"]
        ex_lines.extend(demo.steps)
        if demo.answer_display:
            ex_lines.append(f"结果：{demo.answer_display}")
        example_text = "\n".join(ex_lines)
    if asked_count >= 2 and ch:
        store.upsert_knowledge_card(
            device_id=device_id,
            title=node["title"],
            summary=node["teach"],
            mindmap=node.get("mindmap", []),
            node_id=topic,
            chapter_id=ch["id"],
            volume=ch["volume"],
            tags="高频复习," + ",".join(node.get("aliases", [])[:3]),
            example=example_text,
        )

    spoken = _ahead_line(ch, grade) + node["teach"]
    if pitfalls:
        spoken += f"容易错在：{pitfalls}。"
    if ch:
        related = [NODES[nid]["title"] for nid in ch["nodes"] if nid != topic and nid in NODES]
        if related:
            spoken += "相关的还有：" + "、".join(related[:6]) + "。"
    blocks: list[dict] = [{"type": "text", "text": spoken}]
    if demo and demo.figure:
        figure = _figure_block(demo.figure, f"{node['title']}示意图")
        if figure:
            blocks.append(figure)
    blocks.append({"type": "text", "text": "哪一句没听懂，直接问。"})
    store.save_problem(session_id, topic, None, "")
    return blocks


def _student_note(store: Store, device_id: str) -> str:
    rows = store.weak_nodes(device_id)
    if not rows:
        return ""
    bits = [f"{node_title(row['node_id'])}错了{int(row['n'])}次" for row in rows[:5]]
    return "【这个学生目前的薄弱处，是按错题次数记的。讲到这些地方就多停一步】" + "；".join(bits) + "。"


def _photo_lookback(text: str) -> int | None:
    """0 是最新一张，1 是上一轮，2 是上上轮。说的是第几道题时不在这里数。"""
    if "上上上" in text:
        return 3
    if "上上" in text:
        return 2
    if any(word in text for word in ("上一轮", "上一次", "上次", "上一张", "前一张", "前一轮", "上一个", "上一题", "上个题")):
        return 1
    match = re.search(r"倒数第\s*([1-9])\s*[张轮]", text)
    if match:
        return int(match.group(1)) - 1
    return None


def _with_photo_labels(history: list[dict]) -> list[dict]:
    positions = [
        index
        for index, item in enumerate(history)
        if item.get("role") == "user" and str(item.get("content") or "").startswith("[照片")
    ]
    labeled: list[dict] = []
    for index, item in enumerate(history):
        copied = dict(item)
        if index in positions:
            from_end = len(positions) - 1 - positions.index(index)
            label = _PHOTO_TURN_LABELS[from_end] if from_end < len(_PHOTO_TURN_LABELS) else f"倒数第{from_end + 1}张"
            copied["content"] = re.sub(
                r"^\[照片(?:×\d+)?\]",
                f"[照片·{label}]",
                str(copied.get("content") or ""),
                count=1,
            )
        labeled.append(copied)
    return labeled


_REPLAY_HINTS = ("面积", "周长", "长方体", "正方体", "数轴", "方程", "坐标", "三角形", "平行四边形", "绳子", "捆扎")
_DETAIL = ("仔细", "详细", "细一点", "讲细", "慢一点", "讲透", "展开")


def _replay_hints(text: str) -> list[str]:
    hints = [match.group(0) for match in re.finditer(r"[A-Za-z]{2,}", text)]
    hints.extend(word for word in _REPLAY_HINTS if word in text)
    return hints


def _wants_reteach(text: str) -> bool:
    return _photo_lookback(text) is not None or "再解" in text or any(word in text for word in _DETAIL)


def _split_lesson(blocks: list[dict]) -> tuple[str, str, list[dict]]:
    figures = [block for block in blocks if block.get("type") == "figure"]
    texts = [str(block.get("text") or "") for block in blocks if block.get("type") == "text"]
    whole = "\n".join(part for part in texts if part).strip()
    marker = "【工具验算核对】"
    if marker in whole:
        head, tail = whole.split(marker, 1)
        return head.strip(), (marker + tail).strip(), figures
    return whole, "", figures


def _replay_blocks(store: Store, device_id: str, text: str, client=None, grade: str | None = None) -> list[dict] | None:
    """找到上上个题或学生点名的那道，沿用工具核对过的得数，把文字再讲细一点。"""
    if not _wants_reteach(text):
        return None
    lookback = _photo_lookback(text)
    answers = store.recent_answers(device_id, limit=12)
    if not answers:
        return [{"type": "text", "text": "之前讲过的题我没找到。点那张历史图片上的「再发一次」，我就按原图再讲。"}]
    hints = _replay_hints(text)
    picked = None
    label = "刚才那道"
    if hints:
        best = None
        best_score = 0
        for answer in answers:
            blob = answer["content"].lower()
            score = sum(1 for hint in hints if hint.lower() in blob)
            if score > best_score:
                best = answer
                best_score = score
        if best is not None:
            picked = best
            label = f"你说的「{'、'.join(hints[:3])}」那道"
    if picked is None and lookback is not None:
        index = min(lookback, len(answers) - 1)
        picked = answers[index]
        label = _PHOTO_TURN_LABELS[index] if index < len(_PHOTO_TURN_LABELS) else f"倒数第{index + 1}轮"
    if picked is None:
        picked = answers[0]
    previous, verified, figures = _split_lesson(picked["blocks"])
    fresh = None
    if client is not None and hasattr(client, "reexplain"):
        fresh = client.reexplain(previous, text, verified, grade=normalize_grade(grade))
    blocks: list[dict] = [{
        "type": "text",
        "text": f"这是{label}。得数还是上次工具核对过的，我按这个再讲细一点。",
    }]
    if fresh:
        blocks.append({"type": "text", "text": fresh})
    else:
        blocks.append({"type": "text", "text": previous or picked["content"]})
    blocks.extend(figures)
    if verified:
        blocks.append({"type": "text", "text": verified})
    return blocks


def _call_tir(store: Store, device_id: str, client, text: str, images_b64=None, history=None, grade: str | None = None):
    return client.run_tir(
        text,
        images_b64=images_b64,
        history=history,
        student_note=_student_note(store, device_id),
        grade=normalize_grade(grade),
    )


def _generator_pool(topic: str) -> list[str]:
    if topic in GENERATORS:
        return [topic]
    if not topic or topic == "ch1":
        prefix = "1."
    elif topic.startswith("ch") and topic[2:].isdigit():
        prefix = topic[2:] + "."
    elif topic[:1].isdigit():
        prefix = topic.split(".")[0] + "."
    else:
        prefix = ""
    return [key for key in GENERATORS if prefix and key.startswith(prefix)]


def _blocks_for_task(store: Store, device_id: str, session_id: str, row: dict) -> list[dict]:
    kind = row.get("kind") or "note"
    note = str(row.get("note") or "")
    if kind != "problem":
        return [{"type": "text", "text": "你之前让我提醒你：" + note}]
    topic = str(row.get("topic") or "")
    pool = _generator_pool(topic)
    if pool:
        node = random.choice(pool)
        posed = _pose(store, device_id, session_id, node)
        return [{"type": "text", "text": f"到点了。你之前说：{note}\n下面是一道{node_title(node)}。"}] + posed
    if topic:
        return [
            {"type": "text", "text": f"到点了。你之前说：{note}\n这一节还不能自动换数字出题，我先把要点摆出来。"}
        ] + _explain_topic(store, device_id, session_id, topic)
    posed = _pose(store, device_id, session_id, random.choice(list(GENERATORS)))
    return [{"type": "text", "text": f"到点了。你之前说：{note}"}] + posed


def deliver_due(store: Store, device_id: str, session_id: str, save: bool = False) -> list[dict]:
    blocks: list[dict] = []
    for row in store.take_due_reminders(device_id):
        blocks.extend(_blocks_for_task(store, device_id, session_id, row))
    if save and blocks:
        store.add_message(session_id, "assistant", _plain(blocks), blocks=blocks)
    return blocks


def _weakness_blocks(store: Store, device_id: str) -> list[dict]:
    catalog = build_error_catalog(store, device_id)
    if not catalog["items"]:
        return [
            {
                "type": "text",
                "text": "到现在错题库还是空的，所以我说不出哪里薄弱。卷子上的红叉、练习做错的、你说「放到错题库」的，我都会留下。过一段时间再问，我会按次数告诉你，并把那些题列出来。",
            }
        ]
    lines = [
        f"· {item['node_title']}：{item['error_label']}，{item['count']} 次"
        for item in catalog["stats"][:6]
    ]
    return [
        {
            "type": "text",
            "text": "按错题次数，目前比较薄弱的是这些：\n"
            + "\n".join(lines)
            + "\n下面是记下来的错题，题干和解析都还在。隔两个月再问，这些题也还在。",
        },
        {"type": "errors", "items": catalog["items"][:12]},
    ]


def _error_blocks(store: Store, device_id: str, topic: str | None) -> list[dict]:
    catalog = build_error_catalog(store, device_id)
    items = catalog["items"]
    if topic and topic in NODES:
        items = [it for it in items if it["node_id"] == topic]
    if not items:
        return [
            {
                "type": "text",
                "text": "错题库目前还是空的。入库标准有 4 类：① 拍照卷面上的错题/红叉；② 练习做错的题；③ 你反复追问的高频难点；④ 你在对话里跟我说「把这题放到错题库」。",
            }
        ]
    bits = [f"{s['node_title']}「{s['error_label']}」{s['count']}次" for s in catalog["stats"][:5]]
    summary = "按教材章节归档的错题如下（常错集中在：" + "；".join(bits) + "）。" if bits else "按教材章节归档的错题如下："
    return [
        {"type": "text", "text": summary + "\n每道题都保留了完整题干与解析。点任意一道可展开解析或重练同型题。"},
        {"type": "errors", "items": items[:15]},
    ]


def _grade(store: Store, device_id: str, session_id: str, sol: Solution, student: str) -> list[dict]:
    result = check_answer(sol, student)
    if result["ok"]:
        if sol.node_id in NODES:
            store.record_right(device_id, sol.node_id)
        store.save_problem(session_id, sol.node_id, None, "")
        reason = sol.steps[-1] if sol.steps else ""
        text = f"对，结果是 {sol.answer_display}。"
        if reason:
            text += "\n" + reason
        text += "\n要再来一道，说「再来一道」。"
        blocks = [{"type": "text", "text": text}]
        figure = _figure_block(sol.figure)
        if figure:
            blocks.append(figure)
        return blocks
    code = result["code"] or "calculation"
    opener = result["note"] or ERROR_OPEN.get(code, ERROR_OPEN["calculation"])
    full_sol = "\n".join(sol.steps + ([f"正确答案：{sol.answer_display}"] if sol.answer_display else []))
    if sol.node_id in NODES:
        store.record_error(
            device_id,
            sol.node_id,
            code,
            sol.stem,
            student,
            sol.answer_display,
            opener,
            solution=full_sol,
            source="practice",
        )
    store.save_problem(session_id, sol.node_id, None, "")
    lines = [opener, f"你的答案是 {student.strip()}。我们按步骤再走一遍。"]
    lines.extend(sol.steps)
    if sol.answer_display:
        lines.append(f"结果是 {sol.answer_display}。")
    lines.append("这道题（含完整题干与解析）已经归档进错题库对应章节。想换数字再练，说「再来一道」。")
    blocks = [{"type": "text", "text": "\n".join(lines)}]
    figure = _figure_block(sol.figure)
    if figure:
        blocks.append(figure)
    return blocks


def _pose(store: Store, device_id: str, session_id: str, node_id: str) -> list[dict]:
    if node_id not in NODES:
        return [{"type": "text", "text": "先告诉我练哪一节，比如数轴、绝对值、乘方或一元一次方程。"}]
    sol = generate(node_id)
    if sol is None or sol.kind == "explain":
        return [{"type": "text", "text": "这一节我们可以结合例题讲，你可以说「讲讲" + node_title(node_id) + "」或者拍一道这一节的题给我。"}]
    store.save_problem(session_id, node_id, sol, "answer")
    return _pose_blocks(sol)


def _split_stems(stem: str) -> list[str]:
    chunks = re.split(r"(?:^|\n)\s*(?=\d+[\.、．])", stem.strip())
    cleaned = []
    for chunk in chunks:
        text = re.sub(r"^\d+[\.、．]\s*", "", chunk).strip()
        if text:
            cleaned.append(text)
    return cleaned or ([stem.strip()] if stem.strip() else [])


def _photo_items(parsed: dict) -> list[dict]:
    raw_items = parsed.get("items")
    items = []
    if isinstance(raw_items, list):
        for item in raw_items:
            if isinstance(item, str) and item.strip():
                items.append({"stem": item.strip(), "student_work": "", "marked_wrong": False, "figure": None})
            elif isinstance(item, dict) and str(item.get("stem") or "").strip():
                items.append(item)
    if items:
        kept = [item for item in items if not _is_bare_heading(str(item.get("stem") or ""))]
        return (kept or items)[:8]
    stems = _split_stems(str(parsed.get("stem") or ""))
    if not stems:
        return []
    shared = {
        "student_work": parsed.get("student_work") or "",
        "marked_wrong": parsed.get("marked_wrong"),
        "figure": parsed.get("figure"),
    }
    if len(stems) == 1:
        return [{"stem": stems[0], **shared}]
    return [{"stem": stem, "student_work": "", "marked_wrong": False, "figure": None} for stem in stems]


def _solve_stem(stem: str, client, figure=None) -> Solution | None:
    sol = solve_item(stem, figure)
    if sol is not None or client is None or not _can_rewrite(stem):
        return sol
    expr = client.to_expression(stem)
    if not expr:
        return None
    sol = solve_text(expr)
    if sol is not None:
        sol.stem = stem
    return sol


def _attach_page_figure(items: list[dict]) -> None:
    shared = None
    for item in items:
        if isinstance(item.get("figure"), dict):
            shared = item["figure"]
            break
    if not shared:
        return
    for item in items:
        stem = str(item.get("stem") or "")
        if not item.get("figure") and "如图" in stem:
            item["figure"] = shared


def _extract_q_no(text: str) -> int | None:
    folded = (text or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    m = re.search(r"第\s*([0-9]+|[一二三四五六七八九十])\s*[题道问]", folded)
    if m:
        tok = m.group(1)
        return int(tok) if tok.isdigit() else ("一二三四五六七八九十".index(tok) + 1)
    m2 = re.search(r"[（(]\s*([0-9]+)\s*[）)]", folded)
    if m2:
        return int(m2.group(1))
    return None


def _interleave_text_and_figures(main_text: str, figures: list[dict]) -> list[dict]:
    if not figures:
        return [{"type": "text", "text": main_text}] if main_text else []

    placed: set[int] = set()
    token_re = re.compile(r"\[\[\s*FIGURE_(\d+)\s*\]\]")

    if token_re.search(main_text):
        blocks: list[dict] = []
        last_pos = 0
        for m in token_re.finditer(main_text):
            chunk = main_text[last_pos : m.start()].strip()
            if chunk:
                blocks.append({"type": "text", "text": chunk})
            idx = int(m.group(1))
            if 1 <= idx <= len(figures) and idx not in placed:
                blocks.append(figures[idx - 1])
                placed.add(idx)
            last_pos = m.end()
        tail = main_text[last_pos:].strip()
        if tail:
            blocks.append({"type": "text", "text": tail})
        for idx, fig in enumerate(figures, start=1):
            if idx not in placed:
                blocks.append(fig)
        return blocks

    fig_by_q: dict[int, list[tuple[int, dict]]] = {}
    for idx, fig in enumerate(figures, start=1):
        q_no = _extract_q_no(str(fig.get("caption") or ""))
        if q_no is not None:
            fig_by_q.setdefault(q_no, []).append((idx, fig))

    if fig_by_q:
        sec_re = re.compile(
            r"(?=(?:━━━━━━━━━━\s*\n\s*)?(?:【\s*第\s*\d+\s*题|【\s*[（(]\s*\d+\s*[）)]|第\s*\d+\s*题[。：:\s（(]|[（(]\s*\d+\s*[）)]))",
            re.M,
        )
        parts = [p.strip() for p in sec_re.split(main_text) if p.strip()]
        if len(parts) > 1:
            blocks = []
            for part in parts:
                blocks.append({"type": "text", "text": part})
                first_line = part.split("\n", 2)[0]
                if "━━━━" in first_line and "\n" in part:
                    first_line = part.split("\n", 2)[1]
                q_no = _extract_q_no(first_line)
                if q_no in fig_by_q:
                    for idx, fig in fig_by_q[q_no]:
                        if idx not in placed:
                            blocks.append(fig)
                            placed.add(idx)
            for idx, fig in enumerate(figures, start=1):
                if idx not in placed:
                    blocks.append(fig)
            return blocks

    blocks = [{"type": "text", "text": main_text}] if main_text else []
    blocks.extend(figures)
    return blocks


def _tir_blocks(
    store: Store,
    device_id: str,
    session_id: str,
    tir: dict,
    user_text: str = "",
    grade: str | None = None,
    images_b64: list[str] | None = None,
) -> list[dict]:
    main_text = str(tir.get("text") or "").strip()
    figures = [
        f for f in (tir.get("figures") or []) if isinstance(f, dict) and f.get("type") == "figure"
    ]
    blocks = _interleave_text_and_figures(main_text, figures)

    # Persist any saved knowledge cards from TIR tool calls
    for card_in in tir.get("saved_cards") or []:
        nid = card_in.get("node_id") or match_topic(card_in["title"] + " " + card_in["summary"], grade) or ""
        if nid not in NODES:
            nid = ""
        store.upsert_knowledge_card(
            device_id=device_id,
            title=card_in["title"],
            summary=card_in["summary"],
            mindmap=card_in.get("mindmap") or [],
            node_id=nid,
            volume=card_in.get("volume") or "七年级专题",
            tags=card_in.get("tags") or "",
            example=card_in.get("example") or "",
        )

    # Persist any saved error items from TIR tool calls
    saved_err_count = 0
    for err_in in tir.get("saved_errors") or []:
        nid = err_in.get("node_id") or ""
        if nid not in NODES:
            guessed = match_topic(err_in["stem"] + " " + err_in["solution_steps"], grade)
            nid = guessed if guessed in NODES else "1.1"
        src = "user_saved" if _is_save_error(user_text) else "exam_wrong"
        store.record_error(
            device_id=device_id,
            node_id=nid,
            code="calculation",
            stem=err_in["stem"],
            student=err_in.get("student_wrong") or "",
            expected=err_in.get("correct_answer") or "",
            summary=err_in.get("error_reason") or "审题或计算偏差",
            solution=err_in.get("solution_steps") or main_text,
            source=src,
            images=images_b64,
        )
        saved_err_count += 1

    inferred = match_topic(user_text + "\n" + main_text, grade)
    if inferred and inferred in NODES:
        asked_n = store.record_asked(device_id, inferred)
        store.save_problem(session_id, inferred, None, "")
        # High-frequency ask (>=3 times): automatically archive into Knowledge Base & Error Bank if not already saved
        if asked_n >= 3 and not tir.get("saved_cards"):
            node_info = NODES[inferred]
            ch = chapter_of(inferred)
            store.upsert_knowledge_card(
                device_id=device_id,
                title=node_info["title"],
                summary=node_info["teach"],
                mindmap=node_info.get("mindmap", []),
                node_id=inferred,
                chapter_id=ch["id"] if ch else "",
                volume=ch["volume"] if ch else "七年级",
                tags="高频提问专题",
                example=main_text[:600],
            )

    verification = str(tir.get("verification") or "").strip()
    if verification:
        blocks.append({"type": "text", "text": verification})
    if saved_err_count > 0:
        blocks.append(
            {
                "type": "text",
                "text": f"已将 {saved_err_count} 道错题（剥离手写干扰后的完整题干与解析）归档到【错题库】对应课本章节。",
            }
        )
    blocks.append({"type": "text", "text": "哪一步听着别扭，或者想把某道题收进错题库、改个数字继续问，直接跟我说。"})
    return blocks


def _from_photos(
    store: Store,
    device_id: str,
    session_id: str,
    images_b64: list[str],
    client,
    user_text: str = "",
    grade: str | None = None,
) -> list[dict]:
    if client is None or not client.enabled():
        return [{"type": "text", "text": "照片收到了。识图还没配 DeepSeek 的 key，你可以把题目里的算式打出来，例如 (-3)^2。"}]
    store.save_last_images(session_id, images_b64)
    if hasattr(client, "run_tir"):
        history = [dict(r) for r in store.recent_messages(session_id, limit=6)]
        if history and history[-1]["role"] == "user" and str(history[-1]["content"]).startswith("[照片"):
            history = history[:-1]
        tir = _call_tir(store, device_id, client, user_text, images_b64=images_b64, history=history, grade=grade)
        if tir and tir.get("text"):
            return _tir_blocks(
                store, device_id, session_id, tir, user_text=user_text, grade=grade, images_b64=images_b64
            )

    # Fallback single-image parser for offline/mock tests
    parsed = client.parse_image(images_b64[0])
    items = _photo_items(parsed) if isinstance(parsed, dict) else []
    if not items:
        return [{"type": "text", "text": "这张照片我没读清题。可以再拍近一点，或把算式打出来。"}]
    _attach_page_figure(items)
    blocks = []
    if len(items) > 1:
        blocks.append({"type": "text", "text": f"这张上有 {len(items)} 道，按顺序讲。"})
    saved = []
    last_node = ""
    for index, item in enumerate(items, start=1):
        stem = str(item.get("stem") or "").strip()
        figure = validate_figure(item.get("figure"))
        saved.append({"stem": stem, "figure": figure})
        student_work = str(item.get("student_work") or "").strip()
        sol = _solve_stem(stem, client, figure)
        prefix = f"第 {index} 题。题目：{stem}\n" if len(items) > 1 else f"题目：{stem}\n"
        if sol is None:
            if any(word in stem for word in _DIAGRAM):
                blocks.append({"type": "text", "text": f"{prefix}这道要看数轴。我没读到图上的点，所以不能替你报位置。你可以说 A 在哪一格，或再拍一张只含这根数轴的照片。"})
            else:
                blocks.append({"type": "text", "text": f"{prefix}我读到的是：{stem}\n这道还不能逐项核对。你把要求计算的那一行打出来，我来讲。"})
            continue
        lead = prefix
        full_sol = "\n".join(sol.steps + ([f"结果是 {sol.answer_display}。"] if sol.answer_display else []))
        if student_work and sol.kind == "number":
            judged = check_answer(sol, student_work)
            if not judged["ok"]:
                code = judged["code"] or "calculation"
                lead = prefix + ERROR_OPEN.get(code, "卷子上的这一步和结果对不上。") + f"\n你写下的是 {student_work}。"
                if sol.node_id in NODES:
                    store.record_error(
                        device_id,
                        sol.node_id,
                        code,
                        stem,
                        student_work,
                        sol.answer_display,
                        lead,
                        solution=full_sol,
                        source="exam_wrong",
                    )
            elif item.get("marked_wrong"):
                lead = prefix + "照片上这道被标错了。你写下的结果和核对后的结果一致，我们再把步骤走一遍，看错在过程里。"
        elif item.get("marked_wrong") and sol.node_id in NODES:
            store.record_error(
                device_id,
                sol.node_id,
                "calculation",
                stem,
                student_work,
                sol.answer_display,
                "这道在卷子上被标错了。",
                solution=full_sol,
                source="exam_wrong",
            )
            lead = prefix + "这道在卷子上被标错了，按步骤讲一遍。"
        caption = "图是按读到的刻度画的，点和照片对一下。" if figure and "如图" in stem else ""
        blocks.extend(_lesson_blocks(sol, lead, caption))
        extra = figure
        if extra and not any(block.get("type") == "figure" for block in blocks):
            blocks.append({"type": "figure", "figure": extra, "caption": caption or "按照片里的图整理的。"})
        last_node = sol.node_id
        if sol.node_id in NODES:
            store.record_asked(device_id, sol.node_id)
    blocks.append({"type": "text", "text": "哪一步听着别扭，直接问。想做一道类似的，说「再来一道」。"})
    if last_node:
        store.save_problem(session_id, last_node, None, "")
    store.save_sheet(session_id, saved)
    return blocks


def _save_recent_to_errors(
    store: Store,
    device_id: str,
    session_id: str,
    user_text: str,
    prior_history: list[dict],
    client,
    grade: str | None = None,
) -> list[dict]:
    if client is not None and hasattr(client, "run_tir") and client.enabled():
        ref_imgs = store.get_last_images(session_id)
        prompt = (
            f"学生要求：{user_text}\n"
            "请结合上一轮题目或图片，调用 save_error_item 把要留的题存入错题库。"
            "学生如果说两道、这两、都收，就每一道各调用一次。题干写干净的原题，解析写完整。"
            "原图由系统附上，不用在文字里描述图片存不了。"
        )
        tir = _call_tir(store, device_id, client, prompt, images_b64=ref_imgs, history=prior_history, grade=grade)
        if tir and (tir.get("saved_errors") or tir.get("text")):
            if not tir.get("saved_errors") and prior_history:
                last_assistant = next((m["content"] for m in reversed(prior_history) if m["role"] == "assistant"), "")
                last_user = next((m["content"] for m in reversed(prior_history) if m["role"] == "user"), "")
                nid = match_topic(last_user + " " + last_assistant, grade)
                if nid not in NODES:
                    nid = "1.1"
                store.record_error(
                    device_id=device_id,
                    node_id=nid,
                    code="calculation",
                    stem=last_user or user_text,
                    student="",
                    expected="",
                    summary="主动收入错题库",
                    solution=last_assistant or tir.get("text", ""),
                    source="user_saved",
                    images=ref_imgs,
                )
            return _tir_blocks(
                store, device_id, session_id, tir, user_text=user_text, grade=grade, images_b64=ref_imgs
            )

    if prior_history:
        last_assistant = next((m["content"] for m in reversed(prior_history) if m["role"] == "assistant"), "")
        last_user = next((m["content"] for m in reversed(prior_history) if m["role"] == "user"), "")
        nid = match_topic(last_user + " " + last_assistant, grade)
        if nid not in NODES:
            nid = "1.1"
        store.record_error(
            device_id=device_id,
            node_id=nid,
            code="calculation",
            stem=last_user or user_text,
            student="",
            expected="",
            summary="主动收入错题库",
            solution=last_assistant,
            source="user_saved",
            images=store.get_last_images(session_id),
        )
        return [
            {
                "type": "text",
                "text": f"好，已经把刚才这道题归档进【错题库 · {node_title(nid)}】，包含完整题干和解析。随时点下方「错题库」都能翻出来看。",
            }
        ]
    return [{"type": "text", "text": "先拍一道题或发一道算式给我讲完，再跟我说「放到错题库」，我就会连题干带解析一起存好。"}]


def handle(
    store: Store,
    device_id: str,
    text: str,
    session_id: str | None = None,
    image_b64: str | None = None,
    client=None,
    images_b64: list[str] | None = None,
    grade: str | None = None,
) -> dict:
    grade = normalize_grade(grade)
    session_id = store.ensure_session(device_id, session_id or None)
    text = (text or "").strip()
    due_blocks = deliver_due(store, device_id, session_id, save=False)
    blocks: list[dict] = list(due_blocks)

    all_images: list[str] = []
    if images_b64:
        all_images.extend(img for img in images_b64 if img)
    elif image_b64:
        all_images.append(image_b64)

    if all_images:
        tag = f"[照片×{len(all_images)}]" if len(all_images) > 1 else "[照片]"
        user_mid = store.add_message(session_id, "user", tag + text)
        store.save_message_images(user_mid, all_images)
        blocks.extend(_from_photos(store, device_id, session_id, all_images, client, text, grade))
        store.add_message(session_id, "assistant", _plain(blocks), blocks=blocks)
        return {"session_id": session_id, "blocks": blocks}

    if not text:
        if due_blocks:
            store.add_message(session_id, "assistant", _plain(due_blocks), blocks=due_blocks)
        blocks.append({"type": "text", "text": "把不会的题拍给我，或直接打字。也可以点下方「错题库」「知识点库」。"})
        return {"session_id": session_id, "blocks": blocks}

    prior_history = _with_photo_labels(store.recent_dialog(device_id, limit=12))
    store.add_message(session_id, "user", text)
    if _is_who(text):
        blocks.append({
            "type": "text",
            "text": f"我是你家的数学家庭教师。你现在{grade_profile(grade)['label']}，课本按{grade_profile(grade)['scope']}来讲。你把不会的题拍给我（支持一次贴多张图、或指定只讲第几题），我会先剥离卷面上的手写干扰，用数学工具一步步核对后再讲给你听。平时错题会自动归入「错题库」，常问的概念也会整理成导图卡片存进「知识点库」。",
        })
        store.add_message(session_id, "assistant", _plain(blocks), blocks=blocks)
        return {"session_id": session_id, "blocks": blocks}
    task = parse_task(text)
    if task:
        store.add_reminder(device_id, task["note"], task["due_at"], kind=task["kind"], topic=task["topic"])
        if task["kind"] == "problem":
            chapter_match = next((item for item in CHAPTERS if item["id"] == task["topic"]), None)
            if task["topic"] in NODES:
                label = node_title(task["topic"])
            elif chapter_match is not None:
                label = chapter_match["title"]
            else:
                label = "有理数"
            ready = bool(_generator_pool(task["topic"] or "ch1"))
            extra = (
                "到点我会直接出一道题放在这个对话里。"
                if ready
                else "这一节还不能自动换数字出题，到点我会把这一节的要点摆出来。"
            )
            reply = f"记下了。{task['when_label']}，我按「{label}」准备。{extra}页面开着会自己出现；当时没开，下次一打开我补上。"
        else:
            reply = f"记下了。{task['when_label']}，你一打开这个对话，我会先提一句。"
        blocks.append({"type": "text", "text": reply})
        store.add_message(session_id, "assistant", _plain(blocks), blocks=blocks)
        return {"session_id": session_id, "blocks": blocks}

    if _is_save_error(text):
        blocks.extend(_save_recent_to_errors(store, device_id, session_id, text, prior_history, client, grade))
        store.add_message(session_id, "assistant", _plain(blocks), blocks=blocks)
        return {"session_id": session_id, "blocks": blocks}

    session = store.get_session(session_id)
    pending = load_solution(session["problem_json"]) if session else None
    awaiting = session["awaiting"] if session else ""
    topic = match_topic(text, grade)
    explain_topic = match_topic(text, grade, any_grade=True)
    sheet_no = _sheet_index(text)
    sheet = store.get_sheet(session_id) if sheet_no else []
    if sheet_no and sheet:
        if sheet_no > len(sheet):
            blocks.append({"type": "text", "text": f"这张卷子我只记下 {len(sheet)} 道，没有第 {sheet_no} 题。"})
        else:
            item = sheet[sheet_no - 1]
            stem = str(item.get("stem") or "")
            sol = _solve_stem(stem, client, item.get("figure"))
            lead = f"第 {sheet_no} 题。题目：{stem}\n"
            if sol is None:
                blocks.append({"type": "text", "text": lead + "这道我还是不能逐项核对。你把要算的那一行打出来。"})
            else:
                blocks.extend(_lesson_blocks(sol, lead, "图是按读到的刻度画的，点和照片对一下。" if item.get("figure") else ""))
        store.add_message(session_id, "assistant", _plain(blocks), blocks=blocks)
        return {"session_id": session_id, "blocks": blocks}

    if _is_weakness(text):
        blocks.extend(_weakness_blocks(store, device_id))
        store.add_message(session_id, "assistant", _plain(blocks), blocks=blocks)
        return {"session_id": session_id, "blocks": blocks}

    if _is_errors(text):
        blocks.extend(_error_blocks(store, device_id, topic if topic in NODES else None))
    elif _is_similar(text):
        has_recent_context = bool(prior_history) and (
            bool(store.get_last_images(session_id)) or _sheet_index(text) is not None
        )
        if has_recent_context and client is not None and hasattr(client, "run_tir") and client.enabled():
            ref_imgs = store.get_last_images(session_id)
            tir = _call_tir(store, device_id, client, text, images_b64=ref_imgs, history=prior_history, grade=grade)
            if tir and tir.get("text"):
                blocks.extend(_tir_blocks(store, device_id, session_id, tir, user_text=text, grade=grade))
            else:
                node_id = topic if topic in NODES else (session["node_id"] if session else "")
                blocks.extend(_pose(store, device_id, session_id, node_id))
        else:
            node_id = topic if topic in NODES else (session["node_id"] if session else "")
            blocks.extend(_pose(store, device_id, session_id, node_id))
    elif awaiting == "answer" and pending is not None and _is_reveal(text):
        blocks.extend(_lesson_blocks(pending, "这道按步骤讲完。"))
        blocks.append({"type": "text", "text": "讲过的这道不算你做对。想自己做，说「再来一道」。"})
        store.save_problem(session_id, pending.node_id, None, "")
    elif awaiting == "answer" and pending is not None and _is_short_answer(text):
        blocks.extend(_grade(store, device_id, session_id, pending, text))
    elif _is_explain(text) and explain_topic:
        blocks.extend(_explain_topic(store, device_id, session_id, explain_topic, grade))
    elif _is_explain(text) and not explain_topic:
        context_topic = _recent_topic(prior_history, session)
        if client is not None and hasattr(client, "run_tir") and client.enabled():
            tir = _call_tir(
                store,
                device_id,
                client,
                _followup_prompt(text, context_topic, grade),
                history=prior_history,
                grade=grade,
            )
            if tir and tir.get("text"):
                blocks.extend(_tir_blocks(store, device_id, session_id, tir, user_text=text, grade=grade))
            elif context_topic:
                blocks.extend(_related_answer(context_topic, grade))
            else:
                blocks.append({"type": "text", "text": "你把想听的那个词说一下，例如等边三角形。"})
        elif context_topic:
            blocks.extend(_related_answer(context_topic, grade))
        else:
            blocks.append({"type": "text", "text": "你把想听的那个词说一下，例如等边三角形。"})
    else:
        is_followup = any(w in text for w in _FOLLOWUP) and bool(prior_history)
        solved = None if is_followup else solve_item(text)
        if solved is not None:
            if solved.node_id in NODES:
                store.record_asked(device_id, solved.node_id)
            blocks.extend(_lesson_blocks(solved))
            blocks.append({"type": "text", "text": "哪一步听着别扭，直接问。想做一道类似的，说「再来一道」。"})
            store.save_problem(session_id, solved.node_id, None, "")
        elif explain_topic and not is_followup and len(text) <= 12:
            blocks.extend(_explain_topic(store, device_id, session_id, explain_topic, grade))
        elif replay := _replay_blocks(store, device_id, text, client, grade):
            blocks.extend(replay)
        elif client is not None and hasattr(client, "run_tir") and client.enabled():
            wants_retry = any(word in text for word in _RETRY)
            lookback = _photo_lookback(text)
            photo_sets = (
                store.recent_photo_sets(device_id, limit=4)
                if (is_followup or wants_retry or lookback is not None)
                else []
            )
            ref_imgs = None
            model_text = text
            if lookback is not None and photo_sets:
                index = min(lookback, len(photo_sets) - 1)
                ref_imgs = photo_sets[index]
                label = _PHOTO_TURN_LABELS[index] if index < len(_PHOTO_TURN_LABELS) else f"倒数第{index + 1}张"
                model_text = (
                    f"学生要看的是{label}照片，不是最新一张。请只根据这张图，按学生的话作答，"
                    "不要说没收到图片。学生原话：" + text
                )
            elif (wants_retry or is_followup) and (photo_sets or store.get_last_images(session_id)):
                ref_imgs = photo_sets[0] if photo_sets else store.get_last_images(session_id)
                if wants_retry and ref_imgs:
                    model_text = (
                        "学生要重看刚才那张照片。请对着这张图把刚才那道题完整再讲一遍，"
                        "不要说没收到图片。学生原话：" + text
                    )
            if is_followup and lookback is None and not wants_retry:
                context_topic = explain_topic or _recent_topic(prior_history, session)
                model_text = _followup_prompt(text, context_topic, grade)
            tir = _call_tir(store, device_id, client, model_text, images_b64=ref_imgs, history=prior_history, grade=grade)
            if tir and tir.get("text"):
                blocks.extend(_tir_blocks(store, device_id, session_id, tir, user_text=text, grade=grade))
            else:
                blocks.append({"type": "text", "text": "你可以拍题，打一个算式，或者点下方「错题库」「知识点库」。"})
        elif explain_topic:
            blocks.extend(_explain_topic(store, device_id, session_id, explain_topic, grade))
        elif client is not None:
            expr = client.to_expression(text)
            solved = solve_text(expr) if expr else None
            if solved is not None:
                solved.stem = text
                if solved.node_id in NODES:
                    store.record_asked(device_id, solved.node_id)
                blocks.extend(_lesson_blocks(solved))
                store.save_problem(session_id, solved.node_id, None, "")
            else:
                blocks.append({"type": "text", "text": "你可以拍题，打一个算式，或者点下方「错题库」「知识点库」。"})
        else:
            blocks.append({"type": "text", "text": "你可以拍题，打一个算式，或者点下方「错题库」「知识点库」。"})

    store.add_message(session_id, "assistant", _plain(blocks), blocks=blocks)
    return {"session_id": session_id, "blocks": blocks}


def _plain(blocks: list[dict]) -> str:
    bits = []
    for block in blocks:
        if block.get("type") == "text":
            bits.append(block.get("text") or "")
        elif block.get("type") == "knowledge_card":
            c = block.get("card") or {}
            bits.append(f"【知识点卡：{c.get('title','')}】{c.get('summary','')}")
    return "\n".join(bits)[:4000]
