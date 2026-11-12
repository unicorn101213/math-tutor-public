import random
import tempfile
import unittest
from pathlib import Path

from curriculum import match_topic
from problems import GENERATORS, generate
from rational import Q, check_answer, show, solve_text
from store import Store
from tutor import handle, validate_figure


class EngineTests(unittest.TestCase):
    def test_power_with_parentheses(self):
        sol = solve_text("计算：(-3)^2")
        self.assertIsNotNone(sol)
        self.assertEqual(sol.value, Q(9))
        self.assertEqual(sol.node_id, "2.3.1")
        judged = check_answer(sol, "-9")
        self.assertFalse(judged["ok"])
        self.assertEqual(judged["code"], "power_sign")

    def test_power_without_parentheses(self):
        sol = solve_text("-3^2")
        self.assertEqual(sol.value, Q(-9))
        judged = check_answer(sol, "9")
        self.assertEqual(judged["code"], "power_sign")

    def test_absolute_and_opposite(self):
        sol = solve_text("计算：|-7|")
        self.assertEqual(sol.value, Q(7))
        self.assertEqual(check_answer(sol, "-7")["code"], "abs_as_drop")
        opp = solve_text("(-4)的相反数")
        self.assertEqual(opp.value, Q(4))
        self.assertIsNotNone(opp.figure)

    def test_operations_and_compare(self):
        self.assertEqual(solve_text("计算：(-3)+(-5)").value, Q(-8))
        self.assertEqual(solve_text("计算：(-3)-(-5)").value, Q(2))
        self.assertEqual(solve_text("计算：(-2)×(-3)").value, Q(6))
        self.assertEqual(solve_text("计算：(-12)÷(-3)").value, Q(4))
        compared = solve_text("比较 -1/2 和 -1/3")
        self.assertEqual(solve_text("(1) 5 和 -2").compare, ">")
        self.assertEqual(solve_text("(2) -3 和 -7").compare, ">")
        self.assertEqual(solve_text("(3) -(-1) 和 -(+2)").compare, ">")
        self.assertEqual(solve_text("(4) -(-0.5) 和 |-1|").compare, "<")
        self.assertEqual(solve_text("-(-0.5) 和 |-1.5|.").compare, "<")
        self.assertEqual(compared.compare, "<")
        self.assertTrue(check_answer(compared, "小于")["ok"])
        self.assertEqual(check_answer(compared, ">")["code"], "compare_direction")

    def test_scientific_and_rounding(self):
        sci = solve_text("把 3200 写成科学记数法")
        self.assertEqual(sci.answer_display, "3.2×10^3")
        self.assertTrue(check_answer(sci, "3.2×10^3")["ok"])
        self.assertEqual(check_answer(sci, "3200")["code"], "sci_point")
        rounded = solve_text("5.614精确到百分位")
        self.assertEqual(rounded.answer_display, "5.61")

    def test_zero_division_and_sign(self):
        sol = solve_text("计算：5÷0")
        self.assertEqual(sol.kind, "explain")
        signed = solve_text("规定上升为正，下降 5 米记作什么数？")
        grouped = solve_text(r"指出下面各数中的正数、负数：\frac{1}{4}，-1，2.5，-\frac{4}{3}，0，-3.14，120，-\frac{2}{7}")
        self.assertIn("1/4", grouped.answer_display)
        self.assertIn("−4/3", grouped.answer_display)
        self.assertIn("−2/7", grouped.answer_display)
        self.assertNotIn("正数 1、", grouped.answer_display)
        self.assertEqual(signed.value, Q(-5))
        self.assertEqual(check_answer(signed, "5")["code"], "sign_meaning")

    def test_fraction_display(self):
        sol = solve_text("把 0.75 写成两个整数的比")
        self.assertEqual(sol.value, Q(3, 4))
        self.assertEqual(show(sol.value), "3/4")

    def test_generators_match_answers(self):
        rng = random.Random(7)
        for node_id, fn in GENERATORS.items():
            for _ in range(4):
                sol = fn(rng)
                self.assertIsNotNone(sol.stem)
                if sol.kind == "number":
                    self.assertIsNotNone(sol.value)
                    self.assertTrue(check_answer(sol, sol.answer_display)["ok"])
                elif sol.kind == "compare":
                    self.assertTrue(check_answer(sol, sol.answer_display)["ok"])
                elif sol.kind == "scientific":
                    self.assertTrue(check_answer(sol, sol.answer_display)["ok"])
                if sol.figure:
                    self.assertIsNotNone(validate_figure(sol.figure))

    def test_angle_figure(self):
        sol = solve_text("画一个 60 度的角")
        self.assertEqual(sol.figure["type"], "angle")
        self.assertEqual(validate_figure(sol.figure)["degrees"], 60)


class TutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "t.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_explain_practice_and_error_bank(self):
        first = handle(self.store, "device-001", "讲讲数轴")
        types = [block["type"] for block in first["blocks"]]
        text = "\n".join(block.get("text", "") for block in first["blocks"] if block["type"] == "text")
        self.assertNotIn("tree", types)
        self.assertNotIn("knowledge_card", types)
        self.assertIn("数轴", text)
        self.assertIn("figure", types)
        self.assertEqual(match_topic("讲讲有理数"), "ch1")
        self.assertEqual(match_topic("平行线的判定"), "7.2.2")
        self.assertEqual(match_topic("三元一次方程组"), "10.4")
        self.assertEqual(match_topic("直方图"), "12.2.2")
        self.assertEqual(match_topic("趋势图"), "12.2.3")
        self.assertIsNone(match_topic("全等三角形"))
        self.assertEqual(match_topic("全等三角形", "j2"), "14.1")
        self.assertIsNone(match_topic("二次函数", "j2"))
        self.assertEqual(match_topic("二次函数", "j3"), "26.1")
        self.assertEqual(match_topic("相似三角形的判定", "j3"), "sim.2.1")
        self.assertEqual(match_topic("第二十六章", "j3"), "b26.1.1")
        self.assertEqual(match_topic("第二十七章", "j3"), "sim.1")
        self.assertEqual(match_topic("反比例函数", "j3"), "b26.1.1")
        self.assertEqual(match_topic("锐角三角函数", "j3"), "rt.1")

        posed = handle(self.store, "device-001", "再来一道", first["session_id"])
        self.assertTrue(any(block["type"] == "figure" for block in posed["blocks"]))
        session = self.store.get_session(first["session_id"])
        self.assertEqual(session["awaiting"], "answer")

        wrong = handle(self.store, "device-001", "100", first["session_id"])
        self.assertTrue(any("错题" in block.get("text", "") for block in wrong["blocks"] if block["type"] == "text"))
        bank = handle(self.store, "device-001", "翻翻错题", first["session_id"])
        errors = next(block for block in bank["blocks"] if block["type"] == "errors")
        self.assertGreaterEqual(len(errors["items"]), 1)

    def test_typed_problem_is_explained_in_full(self):
        reply = handle(self.store, "device-001", "(-3)^2 怎么做")
        text = "\n".join(block["text"] for block in reply["blocks"] if block["type"] == "text")
        self.assertIn("9", text)
        self.assertIn("括号", text)

    def test_who_and_photo_sheet(self):
        who = handle(self.store, "device-001", "介绍下自己")
        who_text = "\n".join(block["text"] for block in who["blocks"] if block["type"] == "text")
        self.assertIn("数学家庭教师", who_text)

        plotted = solve_text("画出数轴，并表示下列有理数：-5，3.5，-7/2，-1/2，3/2，5，9/2")
        self.assertIsNone(plotted)
        from rational import solve_item

        plotted = solve_item("画出数轴，并在数轴上表示下列有理数：-5，3.5，-7/2，-1/2，3/2，5，9/2")
        self.assertIn("−7/2", plotted.answer_display)
        self.assertEqual(plotted.figure["type"], "number_line")
        between = solve_item("在数轴上，表示 -2 与 4 的点之间（包括这两个点）有几个整数")
        self.assertIn("7个", between.answer_display)
        self.assertIn("正整数 4 个", between.answer_display)
        moved = solve_item("在数轴上，点 A 表示的数是 -3，从点 A 出发，沿数轴向某一方向移动 4 个单位长度到达点 B")
        self.assertIn("1", moved.answer_display)
        self.assertIn("−7", moved.answer_display)
        read = solve_item(
            "如图，写出数轴上点 A、B 表示的数",
            {"type": "number_line", "min": -5, "max": 5, "points": [{"label": "A", "value": -4}, {"label": "B", "value": 2.5}]},
        )
        self.assertIn("A 是 −4", read.answer_display)
        self.assertIn("B 是 5/2", read.answer_display)

        class Reader:
            def enabled(self):
                return True

            def parse_image(self, _image):
                return {
                    "items": [
                        {"stem": "指出下面各数中的正数、负数：1/4，-1，2.5，0，120", "student_work": "", "marked_wrong": False, "figure": None},
                        {"stem": "如果80 m表示向东走80 m，那么____表示向西走60 m", "student_work": "", "marked_wrong": False, "figure": None},
                        {"stem": "白天最高温度零上126℃，如果把它记作126℃，那么零下150℃记作", "student_work": "", "marked_wrong": False, "figure": None},
                        {"stem": "进3个球，记作+3个，失3个球，记作", "student_work": "", "marked_wrong": False, "figure": None},
                    ]
                }

            def to_expression(self, _stem):
                return None

        reply = handle(self.store, "device-001", "", None, "abc", Reader())
        text = "\n".join(block.get("text", "") for block in reply["blocks"])
        self.assertIn("这张上有 4 道", text)
        self.assertIn("正数", text)
        self.assertIn("−60", text)
        self.assertIn("−150", text)
        self.assertIn("−3", text)
        again = handle(self.store, "device-001", "把上面第2题重做", reply["session_id"])
        again_text = "\n".join(block.get("text", "") for block in again["blocks"])
        self.assertIn("第 2 题", again_text)
        self.assertIn("−60", again_text)

    def test_tir_math_steps(self):
        from rational import run_math_steps

        results = run_math_steps(
            [
                {"label": "三角形面积", "expr": "1/2 * a * b", "vars": {"a": 10, "b": 17.3}},
                {"label": "圆面积", "expr": "pi * r^2", "vars": {"r": 2}},
                {"label": "三角尺面积", "expr": "$1 - $2"},
                {"label": "(4)比较", "expr": "-(-0.5) 和 abs(-1.5)"},
                {"label": "解方程", "expr": "3*(x - 1) = x + 5"},
            ]
        )
        self.assertEqual(results[0]["decimal"], "86.5")
        self.assertEqual(results[1]["decimal"], "12.56")
        self.assertEqual(results[2]["decimal"], "73.94")
        self.assertEqual(results[3]["relation"], "<")
        self.assertEqual(results[4]["exact"], "4")

        from tutor import _interleave_text_and_figures

        figs = [
            {"type": "figure", "figure": {"type": "number_line", "min": -3, "max": 3, "points": []}, "caption": "第1题"},
            {"type": "figure", "figure": {"type": "number_line", "min": -6, "max": 6, "points": []}, "caption": "第2题"},
        ]
        interleaved = _interleave_text_and_figures(
            "【第 1 题】讲完\n[[FIGURE_1]]\n【第 2 题】讲完\n[[FIGURE_2]]",
            figs,
        )
        self.assertEqual([b["type"] for b in interleaved], ["text", "figure", "text", "figure"])

        from tutor import build_error_catalog, build_knowledge_catalog

        kb = build_knowledge_catalog(self.store, "device-001")
        ids = {ch["id"] for ch in kb["chapters"]}
        self.assertIn("ch1", ids)
        self.assertIn("p1a1", ids)
        self.assertGreater(len(ids), 12)
        self.store.upsert_knowledge_card(
            device_id="device-001",
            title="勾股定理",
            summary="直角三角形两直角边的平方和等于斜边的平方：a² + b² = c²。",
            mindmap=["识别直角三角形", "两直角边平方和 = 斜边平方", "已知两边求第三边"],
            tags="直角三角形,勾股定理",
        )
        kb_search = build_knowledge_catalog(self.store, "device-001", query="勾股定理")
        self.assertEqual(len(kb_search["dynamic_cards"]), 1)

        s1 = handle(self.store, "device-001", "(-3)^2 怎么做")
        s2 = handle(self.store, "device-001", "把这道题放到错题库", s1["session_id"])
        ec = build_error_catalog(self.store, "device-001")
        self.assertGreaterEqual(ec["total"], 1)
        self.assertTrue(any(it["source"] == "user_saved" for it in ec["items"]))

        kb_abs = build_knowledge_catalog(self.store, "device-001", query="绝对值")
        self.assertGreaterEqual(len(kb_abs["matched_nodes"]), 1)
        self.assertEqual(kb_abs["matched_nodes"][0]["id"], "1.2.4")

        geom_fig = validate_figure(
            {
                "type": "plane_geometry",
                "points": [
                    {"label": "A", "x": 2, "y": 6},
                    {"label": "B", "x": 6, "y": 5},
                    {"label": "C", "x": 7, "y": 2},
                    {"label": "D", "x": 2, "y": 3.5},
                    {"label": "E", "x": 2, "y": -1.5},
                ],
                "lines": [
                    {"kind": "line", "from": "A", "to": "B", "label": "直线AB"},
                    {"kind": "ray", "from": "B", "to": "C", "label": "射线BC"},
                    {"kind": "segment", "from": "C", "to": "D"},
                    {"kind": "segment", "from": "D", "to": "A"},
                    {"kind": "segment", "from": "D", "to": "E", "style": "dashed", "label": "DE=2AD"},
                ],
            }
        )
        self.assertIsNotNone(geom_fig)
        self.assertEqual(geom_fig["type"], "plane_geometry")
        self.assertEqual(len(geom_fig["lines"]), 5)

        hist = self.store.get_device_history("device-001")
        self.assertGreaterEqual(len(hist["messages"]), 2)
        self.store.clear_device_history("device-001")
        self.assertEqual(len(self.store.get_device_history("device-001")["messages"]), 0)

    def test_history_after_id_skips_older_turns(self):
        session_id = self.store.ensure_session("device-after", None)
        first = self.store.add_message(session_id, "user", "旧题")
        self.store.add_message(
            session_id,
            "assistant",
            "新讲解",
            blocks=[{"type": "text", "text": "新讲解"}],
        )
        fresh = self.store.get_device_history("device-after", after_id=first, include_images=False)
        self.assertEqual([item["text"] for item in fresh["messages"]], ["新讲解"])
        self.assertEqual(fresh["messages"][0]["images"], [])

    def test_power_practice_trap(self):
        sol = generate("2.3.1", random.Random(1))
        self.assertIsNotNone(sol)
        posed = handle(self.store, "device-001", "再来一道乘方")
        session_id = posed["session_id"]
        pending = self.store.get_session(session_id)
        self.assertEqual(pending["node_id"], "2.3.1")
        if sol.traps.get("power_sign") is not None:
            from store import load_solution

            current = load_solution(pending["problem_json"])
            if "power_sign" in current.traps:
                reply = handle(self.store, "device-001", show(current.traps["power_sign"]), session_id)
                text = "\n".join(block.get("text", "") for block in reply["blocks"])
                self.assertIn("负号", text)

    def test_history_images_tasks_figures_and_weakness(self):
        from store import parse_task

        session_id = self.store.ensure_session("device-001", None)
        message_id = self.store.add_message(session_id, "user", "[照片]解题")
        self.store.save_message_images(message_id, ["aGVsbG8="])
        hist = self.store.get_device_history("device-001")
        self.assertEqual(hist["messages"][-1]["images"], ["aGVsbG8="])

        task = parse_task("明天上午8点帮我出一个有理数的数学题")
        self.assertIsNotNone(task)
        self.assertEqual(task["kind"], "problem")
        self.assertEqual(task["topic"], "ch1")
        self.assertIn("T08:00:00", task["due_at"])

        self.store.add_reminder("device-001", "出一道相反数", "2000-01-01T08:00:00", kind="problem", topic="1.2.3")
        due = handle(self.store, "device-001", "你是谁")
        due_text = "\n".join(block.get("text", "") for block in due["blocks"])
        self.assertIn("到点了", due_text)
        self.assertIn("相反数", due_text)

        empty = handle(self.store, "device-002", "我现在哪里比较薄弱，把做错的题列出来")
        empty_text = "\n".join(block.get("text", "") for block in empty["blocks"])
        self.assertIn("空的", empty_text)
        self.store.record_error("device-002", "2.3.1", "power_sign", "计算：(-3)^2", "-9", "9", "负号")
        weak = handle(self.store, "device-002", "我的薄弱点，把当时做错的题列出来")
        weak_text = "\n".join(block.get("text", "") for block in weak["blocks"])
        self.assertIn("乘方", weak_text)
        self.assertTrue(any(block["type"] == "errors" for block in weak["blocks"]))
        stems = []
        for block in weak["blocks"]:
            if block["type"] == "errors":
                stems.extend(item["stem"] for item in block["items"])
        self.assertIn("计算：(-3)^2", stems)

        line = validate_figure(
            {
                "type": "number_line",
                "min": -1,
                "max": 5,
                "points": [{"label": "2", "value": 2, "fill": "open", "ray": "right"}],
            }
        )
        self.assertEqual(line["points"][0]["fill"], "open")
        self.assertEqual(line["points"][0]["ray"], "right")
        marked = validate_figure(
            {
                "type": "plane_geometry",
                "points": [
                    {"label": "A", "x": 0, "y": 0},
                    {"label": "B", "x": 4, "y": 0},
                    {"label": "C", "x": 4, "y": 3},
                    {"label": "D", "x": 0, "y": 3},
                ],
                "lines": [
                    {"kind": "line", "from": "A", "to": "B", "parallel": 1},
                    {"kind": "line", "from": "D", "to": "C", "parallel": 1},
                    {"kind": "segment", "from": "B", "to": "C"},
                ],
                "angles": [{"vertex": "B", "from": "A", "to": "C", "right": True, "label": "90°"}],
            }
        )
        self.assertEqual(marked["lines"][0]["parallel"], 1)
        self.assertTrue(marked["angles"][0]["right"])
        bar = validate_figure(
            {"type": "bar_chart", "title": "成绩", "items": [{"label": "甲", "value": 12}, {"label": "乙", "value": 8}]}
        )
        self.assertEqual(len(bar["items"]), 2)
        pie = validate_figure({"type": "pie_chart", "items": [{"label": "A", "value": 1}, {"label": "B", "value": 3}]})
        self.assertEqual(pie["type"], "pie_chart")
        views = validate_figure(
            {"type": "three_view", "front": [[1, 1], [1, 0]], "left": [[1], [1]], "top": [[1, 1]]}
        )
        self.assertEqual(views["front"][0], [1, 1])
        net = validate_figure({"type": "net", "cells": [[0, 1, 0], [1, 1, 1], [0, 1, 0], [0, 1, 0]]})
        self.assertEqual(sum(cell for row in net["cells"] for cell in row), 6)

        from rational import compass_bearing, figure_error

        self.assertEqual(compass_bearing(0, 1), "正北")
        self.assertEqual(compass_bearing(1, 1), "东北")
        self.assertEqual(compass_bearing(-1, -1), "西南")
        zoo = validate_figure(
            {
                "type": "plane_geometry",
                "show_north": True,
                "compass_from": "大门",
                "points": [
                    {"label": "大门", "x": 0, "y": 0},
                    {"label": "大象馆", "x": 3, "y": 4},
                    {"label": "狮山", "x": -4, "y": 3},
                ],
                "lines": [
                    {"kind": "segment", "from": "大门", "to": "大象馆", "label": "正北"},
                    {"kind": "segment", "from": "大门", "to": "狮山"},
                ],
            }
        )
        self.assertEqual(zoo["lines"][0]["label"], "东北")
        self.assertEqual(zoo["lines"][1]["label"], "西北")
        self.assertTrue(zoo["show_north"])
        bad = {
            "type": "three_view",
            "front": [[1, 1, 1, 1]],
            "left": [[1, 1, 1, 1, 1]],
            "top": [[1, 1, 1], [1, 1, 1], [1, 1, 1]],
        }
        self.assertIsNone(validate_figure(bad))
        self.assertIn("对不上", figure_error(bad))
        solid = validate_figure(
            {
                "type": "cube_solid",
                "cube_count": 3,
                "layers": [[[1, 1]], [[1, 0]]],
            }
        )
        self.assertEqual(solid["front"], [[1, 0], [1, 1]])
        self.assertEqual(solid["left"], [[1], [1]])
        self.assertEqual(solid["top"], [[1, 1]])
        self.assertEqual(solid["cube_count"], 3)
        short = {"type": "cube_solid", "cube_count": 9, "layers": [[[1, 1]], [[1, 0]]]}
        self.assertIsNone(validate_figure(short))
        self.assertIn("9", figure_error(short))

    def test_retry_sends_the_last_photo_again(self):
        class Client:
            def __init__(self):
                self.images = None
                self.text = ""

            def enabled(self):
                return True

            def run_tir(self, text, image_b64=None, images_b64=None, history=None, student_note="", grade="j1"):
                self.images = list(images_b64 or [])
                self.text = text
                return {"text": "再讲一遍：甲用的绳子更短。", "figures": [], "saved_errors": [], "saved_cards": []}

        client = Client()
        first = handle(self.store, "device-retry", "讲这张", image_b64="photo-1", client=client)
        second = handle(self.store, "device-retry", "再试", first["session_id"], client=client)
        self.assertEqual(client.images, ["photo-1"])
        self.assertIn("不要说没收到图片", client.text)
        self.assertIn("再讲一遍", second["blocks"][0]["text"])

    def test_earlier_round_photo_can_be_found_again(self):
        class Client:
            def __init__(self):
                self.images = None
                self.text = ""
                self.history = None
                self.calls = 0

            def enabled(self):
                return True

            def run_tir(self, text, image_b64=None, images_b64=None, history=None, student_note="", grade="j1"):
                self.calls += 1
                self.images = list(images_b64 or [])
                self.text = text
                self.history = history
                label = self.images[0] if self.images else "none"
                if label == "img-b":
                    body = "长方形ABCD面积是24。"
                else:
                    body = f"讲完{label}的第3题。"
                return {"text": body, "figures": [], "saved_errors": [], "saved_cards": []}

        client = Client()
        for name in ("img-a", "img-b", "img-c"):
            handle(self.store, "device-turns", "讲这张", image_b64=name, client=client)
        self.assertEqual(client.calls, 3)
        older = handle(self.store, "device-turns", "把上上轮的第3道题再讲一遍", client=client)
        self.assertEqual(client.calls, 3)
        older_text = " ".join(block.get("text", "") for block in older["blocks"])
        self.assertIn("讲完img-a", older_text)
        named = handle(self.store, "device-turns", "把上上个算 abcd 面积的题再解一遍", client=client)
        self.assertEqual(client.calls, 3)
        joined = " ".join(block.get("text", "") for block in named["blocks"])
        self.assertIn("ABCD", joined)
        self.assertIn("面积", joined)
        handle(self.store, "device-turns", "第3题再讲一遍", client=client)
        self.assertEqual(client.images, ["img-c"])

    def test_reteach_keeps_checked_numbers_and_asks_for_a_fuller_telling(self):
        class Client:
            def __init__(self):
                self.verified = ""
                self.ask = ""

            def enabled(self):
                return True

            def reexplain(self, previous, ask, verified="", grade="j1"):
                self.verified = verified
                self.ask = ask
                return "先看这道题要我们求长方形的面积。长是横着的那条边，宽是竖着的那条边，所以用长乘宽。"

            def run_tir(self, text, image_b64=None, images_b64=None, history=None, student_note="", grade="j1"):
                raise AssertionError("不应重新验算")

        session_id = self.store.ensure_session("device-reteach", None)
        self.store.add_message(
            session_id,
            "assistant",
            "长方形ABCD面积是24。\n【工具验算核对】\n• 面积：6*4 = 24",
            blocks=[
                {"type": "text", "text": "长方形ABCD面积是24。"},
                {"type": "figure", "figure": {"type": "plane_geometry"}},
                {"type": "text", "text": "【工具验算核对】\n• 面积：6*4 = 24"},
            ],
        )
        client = Client()
        result = handle(self.store, "device-reteach", "上上个题能再讲的仔细点吗？", client=client)
        joined = " ".join(block.get("text", "") for block in result["blocks"] if block.get("type") == "text")
        self.assertIn("长乘宽", joined)
        self.assertIn("6*4 = 24", joined)
        self.assertIn("仔细", client.ask)
        self.assertIn("6*4 = 24", client.verified)
        self.assertTrue(any(block.get("type") == "figure" for block in result["blocks"]))

    def test_slow_chat_heartbeat_still_parses_as_json(self):
        import asyncio
        import json

        from main import stream_with_heartbeat

        async def collect(job, interval):
            parts = []
            async for piece in stream_with_heartbeat(job, interval=interval):
                parts.append(piece)
            return b"".join(parts)

        async def run():
            loop = asyncio.get_running_loop()
            slow = loop.create_future()

            async def finish():
                await asyncio.sleep(0.05)
                slow.set_result({"session_id": "s", "blocks": [{"type": "text", "text": "讲完了"}]})

            done = asyncio.create_task(finish())
            raw = await collect(slow, 0.01)
            await done
            self.assertTrue(raw.startswith(b"\n"))
            self.assertEqual(json.loads(raw)["blocks"][0]["text"], "讲完了")

            fast = loop.create_future()
            fast.set_result({"ok": 1})
            self.assertEqual(json.loads(await collect(fast, 0.01))["ok"], 1)

            broken = loop.create_future()
            broken.set_exception(RuntimeError("boom"))
            failed = json.loads(await collect(broken, 0.01))
            self.assertIn("没讲完", failed["blocks"][0]["text"])

        asyncio.run(run())


class LimitTests(unittest.TestCase):
    def test_text_and_image_caps(self):
        import base64

        import limits

        self.assertIsNone(limits.check_chat_input("题" * 800, []))
        self.assertEqual(limits.check_chat_input("题" * 801, []), limits.TEXT_TOO_LONG)
        self.assertEqual(limits.check_chat_input("", ["a"] * 4), limits.TOO_MANY_IMAGES)
        self.assertEqual(limits.check_chat_input("", ["????"]), limits.IMAGE_UNREADABLE)

        old_bytes = limits.MAX_IMAGE_BYTES
        old_total = limits.MAX_TOTAL_BYTES
        try:
            limits.MAX_IMAGE_BYTES = 8
            raw = base64.b64encode(b"123456789").decode()
            self.assertEqual(limits.check_chat_input("", [raw]), limits.IMAGE_TOO_BIG)
            limits.MAX_IMAGE_BYTES = old_bytes
            limits.MAX_TOTAL_BYTES = 10
            one = base64.b64encode(b"123456").decode()
            self.assertEqual(limits.check_chat_input("", [one, one]), limits.IMAGES_TOO_BIG)
        finally:
            limits.MAX_IMAGE_BYTES = old_bytes
            limits.MAX_TOTAL_BYTES = old_total

    def test_send_gate_blocks_overlap_and_burst(self):
        from limits import STILL_TEACHING, TOO_SOON, SendGate

        now = [0.0]
        gate = SendGate(interval=10, clock=lambda: now[0])
        self.assertIsNone(gate.claim("phone"))
        self.assertEqual(gate.claim("phone"), STILL_TEACHING)
        gate.release("phone")
        self.assertEqual(gate.claim("phone"), TOO_SOON)
        now[0] = 10
        self.assertIsNone(gate.claim("phone"))
        self.assertIsNone(gate.claim("other"))


class AccountAndPrimaryTests(unittest.TestCase):
    def test_followup_does_not_spend_a_new_photo_does(self):
        from accounts import consumes_turn

        self.assertFalse(consumes_turn("再讲细一点", 0))
        self.assertTrue(consumes_turn("再讲细一点", 1))
        self.assertTrue(consumes_turn("计算 36×15", 0))

    def test_phone_gets_five_and_redeem_adds(self):
        from accounts import ensure_schema, hold_credit, issue_login_code, issue_redeem, redeem, verify_login
        from store import Store

        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        ensure_schema(store)
        phone = "13800138000"
        code = issue_login_code(store, phone)
        logged = verify_login(store, phone, code, "device-new-0001")
        self.assertEqual(logged["credits"], 5)
        self.assertIsNone(hold_credit(store, 1))
        card = issue_redeem(store, 100)
        added = redeem(store, logged["token"], card)
        self.assertEqual(added["added"], 100)
        self.assertEqual(added["credits"], 104)

    def test_phone_request_keeps_the_code_just_issued(self):
        from accounts import ensure_schema, issue_login_code, verify_login
        from store import Store

        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        ensure_schema(store)
        phone = "13900002222"
        issued = issue_login_code(store, phone)
        self.assertEqual(issue_login_code(store, phone, replace=False), "")
        logged = verify_login(store, phone, issued, "device-keep")
        self.assertIsNotNone(logged)

    def test_admin_page_issues_login_code(self):
        from fastapi.testclient import TestClient

        import main
        from config import settings

        previous = settings.admin_password
        settings.admin_password = "desk-pass"
        try:
            client = TestClient(main.app)
            denied = client.post("/admin/login-code", json={"phone": "13900001111"})
            self.assertEqual(denied.status_code, 401)
            wrong = client.post("/admin/login", json={"password": "nope"})
            self.assertEqual(wrong.status_code, 401)
            ok = client.post("/admin/login", json={"password": "desk-pass"})
            self.assertEqual(ok.status_code, 200)
            made = client.post("/admin/login-code", json={"phone": "13900001111"})
            self.assertEqual(made.status_code, 200)
            self.assertEqual(len(made.json()["code"]), 6)
            card = client.post("/admin/redeem-code", json={"credits": 30})
            self.assertTrue(card.json()["code"].startswith("M"))
            page = client.get("/admin")
            self.assertIn("发登录验证码", page.text)
            stranger = TestClient(main.app)
            self.assertEqual(stranger.get("/admin/state").status_code, 401)
        finally:
            settings.admin_password = previous

    def test_primary_grades_do_not_steal_junior_topics(self):
        self.assertEqual(match_topic("表内乘法", "p2"), "p2a2")
        self.assertIsNone(match_topic("表内乘法", "p1"))
        self.assertEqual(match_topic("三角形", "p4"), "p4b5")
        self.assertEqual(match_topic("三角形", "j2"), "13.1")
        self.assertEqual(match_topic("二次函数", "j3"), "26.1")
        self.assertEqual(match_topic("讲讲负数", "j1"), "1.1")
        self.assertEqual(match_topic("顺便讲讲等腰直角三角形呢", "j2"), "15.3.3")
        self.assertEqual(match_topic("三角形", "j2"), "13.1")
        self.assertIsNone(match_topic("二次函数", "p3"))
        self.assertEqual(match_topic("讲讲二次函数", "p3", any_grade=True), "26.1")
        self.assertEqual(match_topic("三角形", "p3", any_grade=True), "p4b5")
        self.assertEqual(match_topic("顺便讲讲等腰直角三角形呢", "p3", any_grade=True), "15.3.3")

    def test_younger_student_hears_later_topic_in_words(self):
        from store import Store
        from tutor import handle

        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        reply = handle(store, "device-p3", "讲讲二次函数", grade="p3")
        types = [block["type"] for block in reply["blocks"]]
        text = "\n".join(block.get("text", "") for block in reply["blocks"] if block["type"] == "text")
        self.assertNotIn("knowledge_card", types)
        self.assertNotIn("tree", types)
        self.assertIn("九年级上册才学的", text)
        self.assertIn("二次函数", text)

    def test_followup_uses_the_topic_just_discussed(self):
        from store import Store
        from tutor import handle

        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        handle(store, "device-j2", "等边三角形", grade="j2")
        reply = handle(store, "device-j2", "找找相关的知识点卡片", grade="j2")
        text = "\n".join(block.get("text", "") for block in reply["blocks"] if block["type"] == "text")
        self.assertIn("等边三角形", text)
        self.assertIn("等腰三角形", text)
        self.assertNotIn("数轴", text)

        young = handle(store, "device-p3", "等边三角形", grade="p3")
        young_text = "\n".join(block.get("text", "") for block in young["blocks"] if block["type"] == "text")
        self.assertIn("八年级上册才学的", young_text)

    def test_new_question_does_not_stay_on_the_previous_topic(self):
        from store import Store
        from tutor import handle

        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        first = handle(store, "device-j2", "三角函数", grade="j2")
        first_text = "\n".join(block.get("text", "") for block in first["blocks"] if block["type"] == "text")
        self.assertIn("正弦", first_text)
        self.assertIn("九年级下册才学的", first_text)
        reply = handle(store, "device-j2", "方程怎么解", grade="j2")
        text = "\n".join(block.get("text", "") for block in reply["blocks"] if block["type"] == "text")
        self.assertIn("移项", text)
        self.assertIn("相关的还有", text)
        self.assertNotIn("正弦", text)

    def test_saved_error_keeps_the_original_photo(self):
        from store import Store
        from tutor import _is_save_error, build_error_catalog, handle

        self.assertTrue(_is_save_error("能否把这两道题都收到错题库"))
        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        first = handle(store, "device-photo", "余角是多少")
        store.save_last_images(first["session_id"], ["aGVsbG8="])
        handle(store, "device-photo", "收到错题库", first["session_id"])
        items = build_error_catalog(store, "device-photo")["items"]
        self.assertEqual(items[0]["images"], ["aGVsbG8="])
        self.assertEqual(items[0]["source"], "user_saved")

    def test_delete_error_removes_only_that_item(self):
        from store import Store
        from tutor import build_error_catalog

        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        first = store.record_error("device-del", "5.2", "calculation", "2x=4", "", "2", "移项", "解完")
        second = store.record_error("device-del", "5.2", "calculation", "3x=9", "", "3", "移项", "解完", images=["aGVsbG8="])
        self.assertFalse(store.delete_error("other-device", first))
        self.assertTrue(store.delete_error("device-del", second))
        left = build_error_catalog(store, "device-del")["items"]
        self.assertEqual([item["stem"] for item in left], ["2x=4"])
        self.assertEqual(store.error_images(second), [])

    def test_junior_catalog_keeps_grade_nine(self):
        from store import Store
        from tutor import build_knowledge_catalog

        store = Store(Path(tempfile.mkdtemp()) / "t.db")
        kb = build_knowledge_catalog(store, "device-001", grade="j2")
        volumes = {ch["volume"] for ch in kb["chapters"]}
        self.assertIn("九年级上册", volumes)
        self.assertIn("九年级下册", volumes)
        ahead = {ch["volume"] for ch in kb["chapters"] if ch.get("ahead")}
        self.assertIn("九年级上册", ahead)
        self.assertNotIn("八年级下册", ahead)


if __name__ == "__main__":
    unittest.main()
