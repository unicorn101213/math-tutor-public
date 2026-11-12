"""按教师卡片出题。答案和步骤都由运算程序产生。"""

from __future__ import annotations

import random

from rational import Q, Solution, _focus, _line_figure, show, solve_text


def _solved(stem: str) -> Solution:
    sol = solve_text(stem)
    if sol is None:
        raise RuntimeError(f"出题失败：{stem}")
    return sol


def gen_sign(rng: random.Random) -> Solution:
    meters = rng.choice([3, 4, 5, 6, 8, 12])
    return _solved(f"规定上升为正，下降 {meters} 米记作什么数？")


def gen_fraction(rng: random.Random) -> Solution:
    text = rng.choice(["0.5", "0.25", "0.75", "1.5", "0.2"])
    return _solved(f"把 {text} 写成两个整数的比")


def gen_number_line(rng: random.Random) -> Solution:
    value = rng.choice([i for i in range(-4, 5) if i != 0])
    side = "右" if value > 0 else "左"
    return Solution(
        node_id="1.2.2",
        stem="看图，点 A 表示的数是多少？原点是 0，向右为正，每一格是 1 个单位长度。",
        answer_display=show(Q(value)),
        kind="number",
        steps=[
            "先找标着 0 的原点。",
            "箭头向右，所以右边是正方向，左边是负方向。",
            f"点 A 在原点的{side}边，数 {abs(value)} 格，表示 {show(Q(value))}。",
        ],
        summary=_focus("1.2.2"),
        value=Q(value),
        figure=_line_figure([value], points=[("A", value)]),
        traps={"reversed_direction": Q(-value)},
    )


def gen_opposite(rng: random.Random) -> Solution:
    value = rng.choice([-8, -5, -2, -1, 3, 6, 0])
    return _solved(f"({value})的相反数")


def gen_abs(rng: random.Random) -> Solution:
    value = rng.choice([-8, -6, -3, -1, 4, 7])
    return _solved(f"计算：|{value}|")


def gen_compare(rng: random.Random) -> Solution:
    left, right = rng.choice(
        [("-1/2", "-1/3"), ("-5", "-2"), ("-7", "3"), ("1/2", "-1/2"), ("-4", "0"), ("-8", "-3")]
    )
    return _solved(f"比较 {left} 和 {right}")


def gen_add(rng: random.Random) -> Solution:
    a = rng.choice([-9, -6, -3, -1, 2, 5])
    b = rng.choice([-8, -4, -2, 3, 6, 7])
    return _solved(f"计算：({a})+({b})")


def gen_sub(rng: random.Random) -> Solution:
    a = rng.choice([-6, -2, 1, 4, 8])
    b = rng.choice([-5, -3, 2, 6])
    return _solved(f"计算：({a})-({b})")


def gen_mul(rng: random.Random) -> Solution:
    a = rng.choice([-6, -3, -2, 3, 4])
    b = rng.choice([-5, -1, 2, 5])
    return _solved(f"计算：({a})×({b})")


def gen_div(rng: random.Random) -> Solution:
    b = rng.choice([-4, -2, -1, 2, 3])
    a = b * rng.choice([-6, -3, 2, 4])
    return _solved(f"计算：({a})÷({b})")


def gen_power(rng: random.Random) -> Solution:
    base = rng.choice([-4, -3, -2, 2, 3, 5])
    exp = rng.choice([2, 3])
    if base < 0 and rng.random() < 0.5:
        stem = f"计算：{base}^{exp}"
    else:
        stem = f"计算：({base})^{exp}"
    return _solved(stem)


def gen_sci(rng: random.Random) -> Solution:
    number = rng.choice([3200, 45000, 8700, 102000, 60100])
    return _solved(f"把 {number} 写成科学记数法")


def gen_round(rng: random.Random) -> Solution:
    text, place = rng.choice(
        [("5.614", "百分位"), ("3.1416", "千分位"), ("2.76", "十分位"), ("18.5", "个位")]
    )
    return _solved(f"{text}精确到{place}")


GENERATORS = {
    "1.1": gen_sign,
    "1.2.1": gen_fraction,
    "1.2.2": gen_number_line,
    "1.2.3": gen_opposite,
    "1.2.4": gen_abs,
    "1.2.5": gen_compare,
    "2.1.1": gen_add,
    "2.1.2": gen_sub,
    "2.2.1": gen_mul,
    "2.2.2": gen_div,
    "2.3.1": gen_power,
    "2.3.2": gen_sci,
    "2.3.3": gen_round,
}


def generate(node_id: str, rng: random.Random | None = None) -> Solution | None:
    fn = GENERATORS.get(node_id)
    if fn is None:
        return None
    return fn(rng or random.Random())
