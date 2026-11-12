"""初一有理数：只做整数与分数运算，步骤由程序生成，不交给语言模型口算。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from math import atan2, ceil, degrees, floor, gcd


class MathInputError(ValueError):
    pass


@dataclass(frozen=True)
class Q:
    n: int
    d: int = 1

    def __post_init__(self):
        if self.d == 0:
            raise ZeroDivisionError("分母是 0")
        n, d = self.n, self.d
        if d < 0:
            n, d = -n, -d
        g = gcd(abs(n), d) or 1
        object.__setattr__(self, "n", n // g)
        object.__setattr__(self, "d", d // g)

    def __neg__(self):
        return Q(-self.n, self.d)

    def __abs__(self):
        return Q(abs(self.n), self.d)

    def __add__(self, other: "Q") -> "Q":
        o = other
        return Q(self.n * o.d + o.n * self.d, self.d * o.d)

    def __sub__(self, other: "Q") -> "Q":
        return self + (-other)

    def __mul__(self, other: "Q") -> "Q":
        return Q(self.n * other.n, self.d * other.d)

    def __truediv__(self, other: "Q") -> "Q":
        if other.n == 0:
            raise ZeroDivisionError("除数是 0")
        return Q(self.n * other.d, self.d * other.n)

    def __pow__(self, exp: int) -> "Q":
        if not isinstance(exp, int) or isinstance(exp, bool):
            raise MathInputError("指数先用整数")
        if exp < 0:
            raise MathInputError("负指数初一先不写，可以写成倒数")
        if exp > 8:
            raise MathInputError("指数太大了，先换一道小一点的")
        return Q(self.n ** exp, self.d ** exp)

    def __lt__(self, other: "Q") -> bool:
        return self.n * other.d < other.n * self.d

    def __le__(self, other: "Q") -> bool:
        return self.n * other.d <= other.n * self.d


def show(q: Q) -> str:
    if q.d == 1:
        body = str(abs(q.n))
    else:
        body = f"{abs(q.n)}/{q.d}"
    if q.n < 0:
        return f"−{body}"
    return body


def _paren(q: Q) -> str:
    return f"({show(q)})" if q.n < 0 else show(q)


@dataclass
class Num:
    q: Q


@dataclass
class Neg:
    inner: object


@dataclass
class Abs:
    inner: object


@dataclass
class Add:
    left: object
    right: object


@dataclass
class Sub:
    left: object
    right: object


@dataclass
class Mul:
    left: object
    right: object


@dataclass
class Div:
    left: object
    right: object


@dataclass
class Pow:
    left: object
    right: object


_TRANS = str.maketrans(
    {
        "×": "*",
        "÷": "/",
        "（": "(",
        "）": ")",
        "－": "-",
        "−": "-",
        "—": "-",
        "–": "-",
        "＋": "+",
        "＾": "^",
        "｜": "|",
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
    }
)


def normalize_symbols(text: str) -> str:
    return text.strip().translate(_TRANS).replace("**", "^")


class Parser:
    def __init__(self, source: str):
        self.s = source
        self.i = 0

    def peek(self) -> str:
        self._skip()
        return self.s[self.i] if self.i < len(self.s) else ""

    def _skip(self):
        while self.i < len(self.s) and self.s[self.i] == " ":
            self.i += 1

    def eat(self, ch: str) -> bool:
        if self.peek() == ch:
            self.i += 1
            return True
        return False

    def parse(self):
        if len(self.s) > 120:
            raise MathInputError("式子太长了")
        node = self.expr()
        if self.peek():
            raise MathInputError("式子没读完")
        return node

    def expr(self):
        node = self.term()
        while (op := self.peek()) and op in "+-":
            self.i += 1
            right = self.term()
            node = Add(node, right) if op == "+" else Sub(node, right)
        return node

    def term(self):
        node = self.unary()
        while (op := self.peek()) and op in "*/":
            self.i += 1
            right = self.unary()
            node = Mul(node, right) if op == "*" else Div(node, right)
        return node

    def unary(self):
        if self.eat("+"):
            return self.unary()
        if self.eat("-"):
            return Neg(self.unary())
        return self.power()

    def power(self):
        base = self.primary()
        if self.eat("^"):
            exp = self.power()
            return Pow(base, exp)
        return base

    def primary(self):
        self._skip()
        if self.s[self.i : self.i + 4].lower() == "abs(":
            self.i += 4
            node = self.expr()
            if not self.eat(")"):
                raise MathInputError("abs 括号没配对")
            return Abs(node)
        if self.eat("("):
            node = self.expr()
            if not self.eat(")"):
                raise MathInputError("括号没配对")
            return node
        if self.eat("|"):
            node = self.expr()
            if not self.eat("|"):
                raise MathInputError("绝对值的竖线没配对")
            return Abs(node)
        return self.number()

    def number(self):
        self._skip()
        start = self.i
        if self.i < len(self.s) and self.s[self.i] == "+":
            self.i += 1
        saw = False
        while self.i < len(self.s) and self.s[self.i].isdigit():
            saw = True
            self.i += 1
        if self.i < len(self.s) and self.s[self.i] == ".":
            self.i += 1
            while self.i < len(self.s) and self.s[self.i].isdigit():
                saw = True
                self.i += 1
        token = self.s[start:self.i]
        if not saw:
            raise MathInputError("这里不是一个数")
        return Num(decimal_to_q(token))


def decimal_to_q(token: str) -> Q:
    token = token.lstrip("+")
    neg = token.startswith("-")
    if neg:
        token = token[1:]
    if "." in token:
        whole, frac = token.split(".", 1)
        if whole == "":
            whole = "0"
        if frac == "":
            raise MathInputError("小数点后面没有数字")
        num = int(whole + frac)
        den = 10 ** len(frac)
    else:
        num = int(token)
        den = 1
    if neg:
        num = -num
    return Q(num, den)


def parse_expr(text: str):
    return Parser(normalize_symbols(text)).parse()


def _add_rule(a: Q, b: Q) -> str:
    result = a + b
    line = f"{_paren(a)} + {_paren(b)} = {show(result)}。"
    if a.n == 0 or b.n == 0:
        return "加上 0，数不变。" + line
    same = (a.n > 0 and b.n > 0) or (a.n < 0 and b.n < 0)
    if same:
        return "同号相加，符号照旧，绝对值相加。" + line
    return "异号相加，取绝对值较大的那个符号，再用大的绝对值减小的。" + line


def _mul_rule(a: Q, b: Q) -> str:
    result = a * b
    line = f"{_paren(a)} × {_paren(b)} = {show(result)}。"
    if a.n == 0 or b.n == 0:
        return "有一个因数是 0，积就是 0。" + line
    same = (a.n > 0 and b.n > 0) or (a.n < 0 and b.n < 0)
    if same:
        return "同号相乘得正，绝对值相乘。" + line
    return "异号相乘得负，绝对值相乘。" + line


def evaluate(node) -> tuple[Q, list[str]]:
    if isinstance(node, Num):
        return node.q, []
    if isinstance(node, Neg):
        value, steps = evaluate(node.inner)
        if isinstance(node.inner, Pow):
            line = (
                f"负号写在乘方外面，不参与乘方。"
                f"先算得 {show(value)}，再带上负号，得 {show(-value)}。"
            )
        else:
            line = f"{show(value)} 的相反数是 {show(-value)}。相反数就是数轴上跟它关于原点对称的点，只改符号。"
        return -value, steps + [line]
    if isinstance(node, Abs):
        value, steps = evaluate(node.inner)
        line = (
            f"绝对值是这个数到原点的距离，距离不为负。"
            f"|{show(value)}| = {show(abs(value))}。"
        )
        return abs(value), steps + [line]
    if isinstance(node, Pow):
        base, base_steps = evaluate(node.left)
        exp, exp_steps = evaluate(node.right)
        if exp.d != 1:
            raise MathInputError("指数先用整数")
        e = exp.n
        result = base ** e
        if base.n < 0 and e % 2 == 0:
            rule = f"底数是 {show(base)}，指数是 {e}。负号在括号里，属于底数。指数是偶数，负数的偶次方是正数。"
        elif base.n < 0 and e % 2 == 1:
            rule = f"底数是 {show(base)}，指数是 {e}。负号在括号里。指数是奇数，负数的奇次方仍是负数。"
        else:
            rule = f"底数是 {show(base)}，指数是 {e}。"
        calc = f"{_paren(base)} 的 {e} 次方等于 {show(result)}。"
        return result, base_steps + exp_steps + [rule, calc]
    if isinstance(node, Add):
        a, sa = evaluate(node.left)
        b, sb = evaluate(node.right)
        return a + b, sa + sb + [_add_rule(a, b)]
    if isinstance(node, Sub):
        a, sa = evaluate(node.left)
        b, sb = evaluate(node.right)
        rewrite = f"减去一个数，等于加上它的相反数。{show(a)} − {_paren(b)} = {show(a)} + {_paren(-b)}。"
        return a - b, sa + sb + [rewrite, _add_rule(a, -b)]
    if isinstance(node, Mul):
        a, sa = evaluate(node.left)
        b, sb = evaluate(node.right)
        return a * b, sa + sb + [_mul_rule(a, b)]
    if isinstance(node, Div):
        a, sa = evaluate(node.left)
        b, sb = evaluate(node.right)
        if b.n == 0:
            raise ZeroDivisionError("除数是 0")
        result = a / b
        same = (a.n > 0 and b.n > 0) or (a.n < 0 and b.n < 0) or a.n == 0
        if a.n == 0:
            rule = "被除数是 0，商就是 0。"
        elif same:
            rule = "同号相除得正，绝对值相除。"
        else:
            rule = "异号相除得负，绝对值相除。"
        line = f"{_paren(a)} ÷ {_paren(b)} = {show(result)}。"
        return result, sa + sb + [rule + line]
    raise MathInputError("这个式子我还不会拆")


def root_topic(node) -> str | None:
    if isinstance(node, Abs):
        return "1.2.4"
    if isinstance(node, Pow) or (isinstance(node, Neg) and isinstance(node.inner, Pow)):
        return "2.3.1"
    if isinstance(node, Neg):
        return "1.2.3"
    if isinstance(node, Add):
        return "2.1.1"
    if isinstance(node, Sub):
        return "2.1.2"
    if isinstance(node, Mul):
        return "2.2.1"
    if isinstance(node, Div):
        return "2.2.2"
    return None


@dataclass
class Solution:
    node_id: str
    stem: str
    answer_display: str
    kind: str
    steps: list[str]
    summary: str
    figure: dict | None = None
    value: Q | None = None
    compare: str | None = None
    traps: dict[str, Q] = field(default_factory=dict)


def _clean_prompt(text: str) -> str:
    t = text.strip()
    t = re.sub(r"(这题|怎么做|咋做|怎么算|如何算|直接讲|讲透)", "", t)
    t = re.sub(r"^(帮我算|算一下|计算|求)\s*[:：]?\s*", "", t)
    t = re.sub(r"(等于多少|是多少|等于几|是几|等于什么|是什么)\s*[?？。]?$", "", t)
    t = t.strip(" ：:?？。")
    return t


def _try_expr(text: str) -> Solution | None:
    cleaned = _clean_prompt(text)
    if not cleaned or re.search(r"[\u4e00-\u9fff]", cleaned):
        return None
    if not re.search(r"[+\-*/^|()]", normalize_symbols(cleaned)):
        return None
    try:
        tree = parse_expr(cleaned)
        value, steps = evaluate(tree)
    except (MathInputError, ZeroDivisionError) as exc:
        if isinstance(exc, ZeroDivisionError):
            return Solution(
                node_id="2.2.2",
                stem=text.strip(),
                answer_display="",
                kind="explain",
                steps=["除数是 0。0 不能做除数，这个式子没有意义。"],
                summary="这题在考除法有没有意义。除数是 0，算式不能算。",
            )
        return None
    topic = root_topic(tree)
    if topic is None:
        return None
    traps: dict[str, Q] = {}
    if topic == "2.3.1" and (-value) != value:
        traps["power_sign"] = -value
    if isinstance(tree, Abs):
        inside, _ = evaluate(tree.inner)
        if inside.n < 0:
            traps["abs_as_drop"] = inside
    if isinstance(tree, Neg) and not isinstance(tree.inner, Pow) and value != evaluate(tree.inner)[0]:
        traps["opposite_sign"] = evaluate(tree.inner)[0]
    return Solution(
        node_id=topic,
        stem=text.strip(),
        answer_display=show(value),
        kind="number",
        steps=steps,
        summary=_focus(topic),
        value=value,
        traps=traps,
        figure=_figure_for_tree(tree, value),
    )


def _figure_for_tree(tree, value: Q) -> dict | None:
    if isinstance(tree, Abs):
        inside, _ = evaluate(tree.inner)
        if inside.d == 1 and abs(inside.n) <= 8:
            return _line_figure(
                [inside.n, 0],
                highlight=(inside.n, 0),
                points=[("A", inside.n)],
            )
    if isinstance(tree, Neg) and not isinstance(tree.inner, Pow):
        inside, _ = evaluate(tree.inner)
        if inside.d == 1 and abs(inside.n) <= 8 and value.d == 1:
            return _line_figure([inside.n, value.n], points=[("A", inside.n), ("A'", value.n)])
    return None


def _line_figure(values: list[int], points: list[tuple[str, int]] | None = None, highlight=None) -> dict:
    lo = min(values + [-5])
    hi = max(values + [5])
    fig = {
        "type": "number_line",
        "min": min(lo, -5),
        "max": max(hi, 5),
        "points": [{"label": label, "value": val} for label, val in (points or [])],
        "highlight": None,
    }
    if highlight is not None:
        a, b = highlight
        fig["highlight"] = {"from": a, "to": b}
    return fig


def _focus(node_id: str) -> str:
    return {
        "1.1": "这题在考正号和负号各表示哪种相反的意义。",
        "1.2.1": "这题在考有理数能不能写成两个整数的比。",
        "1.2.2": "这题在考数轴三件套：原点、正方向、单位长度。",
        "1.2.3": "这题在考相反数：只改符号，绝对值不变。",
        "1.2.4": "这题在考绝对值：到原点的距离，不为负。",
        "1.2.5": "这题在考数轴上左边的数更小。",
        "2.1.1": "这题在考有理数加法：先看同号还是异号。",
        "2.1.2": "这题在考减法：减去一个数，等于加上它的相反数。",
        "2.2.1": "这题在考乘法符号：同号得正，异号得负。",
        "2.2.2": "这题在考除法符号，算法和乘法同一套。",
        "2.3.1": "这题在考乘方的符号，关键看负号在不在括号里。",
        "2.3.2": "这题在考科学记数法：写成 a×10 的若干次方，1 ≤ |a| < 10。",
        "2.3.3": "这题在考四舍五入，要看清精确到哪一位。",
        "angle": "这题在看一个角有多大。一度就是把周角平均分成 360 份里的 1 份。",
    }.get(node_id, "这题按有理数的规则一步一步算。")


def sci_display(q: Q) -> str:
    if q.n == 0:
        return "0×10^0"
    dec = (Decimal(abs(q.n)) / Decimal(q.d)).normalize()
    digits = "".join(str(d) for d in dec.as_tuple().digits)
    exp = dec.as_tuple().exponent + len(digits) - 1
    mant = digits[0] + (("." + digits[1:]) if len(digits) > 1 else "")
    sign = "−" if q.n < 0 else ""
    return f"{sign}{mant}×10^{exp}"


def _parse_relation(text: str) -> str | None:
    t = text.strip().replace(" ", "")
    if "不等于" in t:
        return None
    if t in ("<", "＜", "小于"):
        return "<"
    if t in (">", "＞", "大于"):
        return ">"
    if t in ("=", "＝", "等于"):
        return "="
    if "小于" in t:
        return "<"
    if "大于" in t:
        return ">"
    if t in ("相等", "一样大"):
        return "="
    return None


_SCI_RE = re.compile(
    r"^([+-]?\d+(?:\.\d+)?)\s*[x×*]\s*10\s*(?:\^|\*\*)\s*([+-]?\d+)$"
)


def parse_sci_form(text: str) -> tuple[Q, bool] | None:
    t = normalize_symbols(text).replace(" ", "")
    t = t.replace("−", "-")
    match = _SCI_RE.fullmatch(t)
    if not match:
        return None
    mantissa = decimal_to_q(match.group(1))
    exp = int(match.group(2))
    if exp < 0 or exp > 12:
        return None
    value = mantissa * (Q(10) ** exp)
    form_ok = Q(1) <= abs(mantissa) < Q(10) or mantissa.n == 0
    return value, form_ok


def parse_answer_number(text: str) -> Q | None:
    t = text.strip()
    t = t.replace("负", "-").replace("正", "")
    t = _clean_prompt(t)
    if not t:
        return None
    sci = parse_sci_form(t)
    if sci is not None:
        return sci[0]
    try:
        tree = parse_expr(t)
        value, _ = evaluate(tree)
        return value
    except (MathInputError, ZeroDivisionError):
        return None


def check_answer(sol: Solution, student: str) -> dict:
    student = student.strip()
    if sol.kind == "compare":
        got = _parse_relation(student)
        if got is None:
            return {"ok": False, "code": "calculation", "note": "比较大小时，直接告诉我大于、小于或等于。"}
        if got == sol.compare:
            return {"ok": True, "code": "", "note": ""}
        return {"ok": False, "code": "compare_direction", "note": ""}
    if sol.kind == "scientific":
        formed = parse_sci_form(student)
        if formed is None:
            as_number = parse_answer_number(student)
            if as_number is not None and sol.value is not None and as_number == sol.value:
                return {
                    "ok": False,
                    "code": "sci_point",
                    "note": "数值对了，但科学记数法要写成 a×10^n，并且 1 ≤ |a| < 10。",
                }
            return {"ok": False, "code": "calculation", "note": ""}
        value, form_ok = formed
        if sol.value is not None and value == sol.value and form_ok:
            return {"ok": True, "code": "", "note": ""}
        if sol.value is not None and value == sol.value and not form_ok:
            return {
                "ok": False,
                "code": "sci_point",
                "note": "10 的次数可以再调整，让小数点左边只留一位不是 0 的数字。",
            }
        return {"ok": False, "code": "calculation", "note": ""}
    if sol.kind != "number" or sol.value is None:
        return {"ok": False, "code": "calculation", "note": ""}
    got = parse_answer_number(student)
    if got is None:
        return {"ok": False, "code": "calculation", "note": "我没读懂这个答案，可以写成分数、小数，或 a×10^n。"}
    if got == sol.value:
        return {"ok": True, "code": "", "note": ""}
    for code, wrong in sol.traps.items():
        if got == wrong:
            return {"ok": False, "code": code, "note": ""}
    return {"ok": False, "code": "calculation", "note": ""}


def _compare_symbol(a: Q, b: Q) -> str:
    if a < b:
        return "<"
    if b < a:
        return ">"
    return "="


_NUMBER_TOKEN = re.compile(r"[+＋−–-]?\d+\s*/\s*\d+|[+＋−–-]?\d+(?:\.\d+)?")
_OPPOSITE_WORDS = {
    "零上": "零下",
    "零下": "零上",
    "向东": "向西",
    "向西": "向东",
    "向南": "向北",
    "向北": "向南",
    "上升": "下降",
    "下降": "上升",
    "收入": "支出",
    "支出": "收入",
    "盈利": "亏损",
    "亏损": "盈利",
}


def _pretty_token(token: str) -> str:
    token = token.replace(" ", "").replace("＋", "+").replace("−", "-").replace("–", "-")
    if token.startswith("+"):
        token = token[1:]
    if token.startswith("-"):
        return "−" + token[1:]
    return token


def _token_value(token: str) -> Q:
    token = token.replace(" ", "").replace("＋", "+").replace("−", "-").replace("–", "-")
    if "/" in token:
        sign = -1 if token.startswith("-") else 1
        body = token[1:] if token[:1] in "+-" else token
        left, right = body.split("/", 1)
        return Q(sign * int(left), int(right))
    return decimal_to_q(token)


def _normalize_fractions(text: str) -> str:
    text = text.replace("／", "/").replace("⁄", "/").replace("∕", "/")

    def repl(match: re.Match) -> str:
        sign = match.group(1) or ""
        if sign in "＋":
            sign = ""
        if sign in "−–":
            sign = "-"
        return f"{sign}{match.group(2)}/{match.group(3)}"

    return re.sub(
        r"([+\-＋−–])?\s*\\[a-zA-Z]*frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}",
        repl,
        text,
    )


def _classify_signs(raw: str) -> Solution | None:
    if "正数" not in raw or "负数" not in raw:
        return None
    if not any(word in raw for word in ("指出", "哪些", "下列", "下面", "找出")):
        return None
    body = re.split(r"[:：]", _normalize_fractions(raw), maxsplit=1)[-1]
    tokens = _NUMBER_TOKEN.findall(body)
    if len(tokens) < 2:
        return None
    positive, negative, zero = [], [], []
    for token in tokens:
        value = _token_value(token)
        label = _pretty_token(token)
        if value.n > 0:
            positive.append(label)
        elif value.n < 0:
            negative.append(label)
        else:
            zero.append(label)
    lines = [
        "大于 0 的是正数，小于 0 的是负数。0 单独放着，它既不是正数也不是负数。",
        "正数：" + ("、".join(positive) if positive else "没有") + "。",
        "负数：" + ("、".join(negative) if negative else "没有") + "。",
    ]
    if zero:
        lines.append("这里的 0 不是正数，也不是负数。")
    answer = f"正数 {'、'.join(positive) or '无'}；负数 {'、'.join(negative) or '无'}"
    if zero:
        answer += "；0 既不是正数也不是负数"
    return Solution(
        node_id="1.1",
        stem=raw,
        answer_display=answer,
        kind="explain",
        steps=lines,
        summary=_focus("1.1"),
    )


def _opposite_meaning(raw: str) -> Solution | None:
    goal = re.search(r"进\s*(\d+(?:\.\d+)?)\s*个球?.{0,10}记作\s*([+＋−–-]?)(\d+(?:\.\d+)?)", raw)
    lost = re.search(r"失\s*(\d+(?:\.\d+)?)\s*个球?.{0,16}记作", raw)
    if goal and lost:
        gain_is_positive = goal.group(2) not in ("-", "−", "–")
        magnitude = decimal_to_q(lost.group(1))
        value = -magnitude if gain_is_positive else magnitude
        direction = "负" if value.n < 0 else "正"
        return Solution(
            node_id="1.1",
            stem=raw,
            answer_display=show(value),
            kind="number",
            steps=[
                f"进球记作 {goal.group(2) or '+'}{goal.group(3)}，进球是正方向。",
                f"失球和进球相反，所以失 {show(magnitude)} 个记作{direction}数 {show(value)}。",
            ],
            summary=_focus("1.1"),
            value=value,
            traps={"sign_meaning": magnitude if gain_is_positive else -magnitude},
        )

    defined = re.search(
        r"(零上|零下|向东|向西|向南|向北|上升|下降|收入|支出|盈利|亏损).{0,12}?"
        r"(\d+(?:\.\d+)?).{0,16}?记作\s*([+＋−–-]?)(\d+(?:\.\d+)?)",
        raw,
    )
    asked = None
    if defined:
        opposite = _OPPOSITE_WORDS[defined.group(1)]
        asked = re.search(
            re.escape(opposite) + r".{0,12}?(\d+(?:\.\d+)?).{0,16}?记作",
            raw,
        )
    if defined and asked:
        given_positive = defined.group(3) not in ("-", "−", "–")
        magnitude = decimal_to_q(asked.group(1))
        value = -magnitude if given_positive else magnitude
        given_show = show(decimal_to_q(defined.group(4)))
        if not given_positive:
            given_show = show(-decimal_to_q(defined.group(4)))
        return Solution(
            node_id="1.1",
            stem=raw,
            answer_display=show(value),
            kind="number",
            steps=[
                f"{defined.group(1)} {defined.group(2)} 记作 {given_show}，这一边规定为正。"
                if given_positive
                else f"{defined.group(1)} {defined.group(2)} 记作 {given_show}，这一边规定为负。",
                f"{_OPPOSITE_WORDS[defined.group(1)]}是相反方向，{asked.group(1)} 记作 {show(value)}。",
            ],
            summary=_focus("1.1"),
            value=value,
            traps={"sign_meaning": magnitude if given_positive else -magnitude},
        )

    west = re.search(r"向西走?\s*(\d+(?:\.\d+)?)", raw)
    east_positive = re.search(r"(?<![-−–])(\d+(?:\.\d+)?)\s*(?:m|米)\s*表示向东", raw)
    if west and east_positive and ("____" in raw or "___" in raw or "什么" in raw):
        magnitude = decimal_to_q(west.group(1))
        value = -magnitude
        return Solution(
            node_id="1.1",
            stem=raw,
            answer_display=show(value) + " m",
            kind="number",
            steps=[
                f"{east_positive.group(1)} m 表示向东，向东规定为正。",
                f"向西是相反方向，向西走 {show(magnitude)} m 记作 {show(value)} m。",
            ],
            summary=_focus("1.1"),
            value=value,
            traps={"sign_meaning": magnitude},
        )
    return None


def _side_key(text: str) -> str:
    return normalize_symbols(text).replace(" ", "").replace("-", "−")


def _as_compare(raw: str) -> Solution | None:
    text = re.sub(r"^[（(]\s*\d+\s*[）).、．]\s*", "", raw.strip())
    text = text.strip(" ；;。．.")
    match = re.search(r"^(?:比较\s*)?(.+?)\s*(?:和|与)\s*(.+)$", text)
    if not match:
        return None
    left_text = match.group(1).strip(" ：:?？。．.")
    right_text = re.sub(r"(的大小|哪个大|谁大).*$", "", match.group(2)).strip(" ：:?？。．.")
    if re.search(r"[\u4e00-\u9fff]", left_text + right_text):
        return None
    try:
        a, _ = evaluate(parse_expr(left_text))
        b, _ = evaluate(parse_expr(right_text))
    except (MathInputError, ZeroDivisionError):
        return None
    symbol = _compare_symbol(a, b)
    word = {"<": "小于", ">": "大于", "=": "等于"}[symbol]
    steps = ["数轴上，右边的数总比左边的大。两个负数，绝对值大的反而小。"]
    if _side_key(left_text) != _side_key(show(a)):
        steps.append(f"左边先算：{left_text} = {show(a)}。")
    if _side_key(right_text) != _side_key(show(b)):
        steps.append(f"右边先算：{right_text} = {show(b)}。")
    steps.append(f"{show(a)} {symbol} {show(b)}，也就是 {show(a)} {word} {show(b)}。")
    figure = None
    if a.d == 1 and b.d == 1 and abs(a.n) <= 8 and abs(b.n) <= 8:
        figure = _line_figure([a.n, b.n], points=[("A", a.n), ("B", b.n)])
    return Solution(
        node_id="1.2.5",
        stem=raw,
        answer_display=symbol,
        kind="compare",
        steps=steps,
        summary=_focus("1.2.5"),
        value=None,
        compare=symbol,
        figure=figure,
        traps={},
    )


def solve_text(text: str) -> Solution | None:
    raw = text.strip()
    if not raw or len(raw) > 400:
        return None

    angle = re.search(r"(\d+(?:\.\d+)?)\s*度", raw)
    if angle and "角" in raw and "计算" not in raw:
        deg = float(angle.group(1))
        if 0 < deg < 180:
            return Solution(
                node_id="angle",
                stem=raw,
                answer_display=f"{angle.group(1)}°",
                kind="explain",
                steps=[
                    "角可以看成由两条有公共端点的射线组成。",
                    f"图里两条射线张开的是 {angle.group(1)}°。一周是 360°，平角是 180°，直角是 90°。",
                    "看角的大小时，看张开的程度，不看边画得长不长。",
                ],
                summary=_focus("angle"),
                figure={"type": "angle", "degrees": deg, "label": f"{angle.group(1)}°"},
            )

    sign_case = re.search(r"上升为正.*?下降\s*(\d+(?:\.\d+)?)\s*米", raw)
    if sign_case:
        meters = decimal_to_q(sign_case.group(1))
        value = -meters
        return Solution(
            node_id="1.1",
            stem=raw,
            answer_display=show(value),
            kind="number",
            steps=[
                "上升为正，下降就是和上升相反的方向，记作负数。",
                f"下降 {show(meters)} 米，记作 {show(value)} 米。",
            ],
            summary=_focus("1.1"),
            value=value,
            traps={"sign_meaning": meters},
        )

    grouped = _classify_signs(raw)
    if grouped is not None:
        return grouped
    meaning = _opposite_meaning(raw)
    if meaning is not None:
        return meaning

    frac_case = re.search(r"把\s*([0-9]+(?:\.[0-9]+)?)\s*写成(?:分数|两个整数的比)", raw)
    if frac_case:
        value = decimal_to_q(frac_case.group(1))
        return Solution(
            node_id="1.2.1",
            stem=raw,
            answer_display=show(value),
            kind="number",
            steps=[
                "有理数都能写成两个整数相除的形式，小数点后面有几位，分母就是 1 后面几个 0。",
                f"{frac_case.group(1)} = {show(value)}。",
            ],
            summary=_focus("1.2.1"),
            value=value,
        )

    sci_case = re.search(r"(?:把|将)\s*(.+?)\s*(?:写成|表示成|用)科学记数法", raw)
    if sci_case:
        number_text = sci_case.group(1).strip(" ：:")
        try:
            value, _ = evaluate(parse_expr(number_text))
        except (MathInputError, ZeroDivisionError):
            value = None
        if value is not None:
            display = sci_display(value)
            return Solution(
                node_id="2.3.2",
                stem=raw,
                answer_display=display,
                kind="scientific",
                steps=[
                    "科学记数法是 a×10^n，小数点左边只留一位 1 到 9 的数字。",
                    f"{show(value)} 写成 {display}。",
                    "小数点往左移了几位，10 的指数就是几。",
                ],
                summary=_focus("2.3.2"),
                value=value,
                traps={"sci_point": value},
            )

    round_case = re.search(
        r"(.+?)\s*精确到\s*(个位|十分位|百分位|千分位)",
        raw,
    )
    if round_case:
        places = {"个位": 0, "十分位": 1, "百分位": 2, "千分位": 3}
        place_name = round_case.group(2)
        digits = places[place_name]
        try:
            value, _ = evaluate(parse_expr(_clean_prompt(round_case.group(1))))
        except (MathInputError, ZeroDivisionError):
            value = None
        if value is not None:
            dec = Decimal(value.n) / Decimal(value.d)
            quant = Decimal("1") if digits == 0 else Decimal("0." + "0" * (digits - 1) + "1")
            rounded = dec.quantize(quant, rounding=ROUND_HALF_UP)
            text_out = f"{rounded:.{digits}f}" if digits else str(int(rounded))
            return Solution(
                node_id="2.3.3",
                stem=raw,
                answer_display=text_out,
                kind="number",
                steps=[
                    f"精确到{place_name}，就看这一位后面的一位。",
                    "后面是 0、1、2、3、4，就舍去；是 5、6、7、8、9，就向前一位进 1。",
                    f"{show(value)} 精确到{place_name}是 {text_out}。",
                ],
                summary=_focus("2.3.3"),
                value=decimal_to_q(text_out),
            )

    compared = _as_compare(raw)
    if compared is not None:
        return compared

    opp_case = re.search(r"(.+?)的相反数", raw)
    if opp_case and "什么是" not in raw and "讲" not in raw:
        try:
            value, inner_steps = evaluate(parse_expr(_clean_prompt(opp_case.group(1))))
        except (MathInputError, ZeroDivisionError):
            value, inner_steps = None, []
        if value is not None:
            result = -value
            return Solution(
                node_id="1.2.3",
                stem=raw,
                answer_display=show(result),
                kind="number",
                steps=inner_steps
                + [
                    f"{show(value)} 的相反数是 {show(result)}。绝对值不变，符号改掉。0 的相反数仍是 0。",
                ],
                summary=_focus("1.2.3"),
                value=result,
                traps={} if result == value else {"opposite_sign": value},
                figure=_line_figure([value.n, result.n], points=[("A", value.n), ("A'", result.n)])
                if value.d == 1 and abs(value.n) <= 8
                else None,
            )

    abs_case = re.search(r"(.+?)的绝对值", raw)
    if abs_case and "什么是" not in raw and "讲" not in raw:
        try:
            value, inner_steps = evaluate(parse_expr(_clean_prompt(abs_case.group(1))))
        except (MathInputError, ZeroDivisionError):
            value, inner_steps = None, []
        if value is not None:
            result = abs(value)
            traps = {"abs_as_drop": value} if value.n < 0 else {}
            figure = None
            if value.d == 1 and abs(value.n) <= 8:
                figure = _line_figure([value.n, 0], points=[("A", value.n)], highlight=(value.n, 0))
            return Solution(
                node_id="1.2.4",
                stem=raw,
                answer_display=show(result),
                kind="number",
                steps=inner_steps
                + [f"{show(value)} 的绝对值是到原点的距离，等于 {show(result)}。"],
                summary=_focus("1.2.4"),
                value=result,
                traps=traps,
                figure=figure,
            )

    return _try_expr(raw)


def _show_float(value: float) -> str:
    half = round(value * 2) / 2
    if abs(value - half) < 1e-6:
        token = str(int(half)) if half == int(half) else str(half)
        return show(decimal_to_q(token))
    return show(decimal_to_q(f"{value:.4f}"))


def _axis_figure(pairs: list[tuple[str, float]]) -> dict:
    values = [value for _, value in pairs] or [0.0]
    lo = floor(min(values + [-1.0]))
    hi = ceil(max(values + [1.0]))
    if lo >= hi:
        hi = lo + 1
    return {
        "type": "number_line",
        "min": lo,
        "max": hi,
        "points": [{"label": label, "value": value} for label, value in pairs],
        "highlight": None,
    }


def _plot_list(raw: str) -> Solution | None:
    if "数轴" not in raw or not any(word in raw for word in ("画出", "表示下列", "表示下面")):
        return None
    body = _normalize_fractions(re.split(r"[:：]", raw, maxsplit=1)[-1])
    tokens = _NUMBER_TOKEN.findall(body)
    if len(tokens) < 2:
        return None
    pairs = []
    lines = ["数轴要有原点、向右的正方向，和单位长度。这里一格表示 1。"]
    for token in tokens:
        value = _token_value(token)
        label = _pretty_token(token)
        pairs.append((label, value.n / value.d))
        lines.append(f"{label} 标在 {show(value)} 的位置。")
    pairs.sort(key=lambda item: item[1])
    lines.append("从左到右是：" + "、".join(label for label, _ in pairs) + "。")
    return Solution(
        node_id="1.2.2",
        stem=raw,
        answer_display="、".join(label for label, _ in pairs),
        kind="explain",
        steps=lines,
        summary=_focus("1.2.2"),
        figure=_axis_figure(pairs),
    )


def _integers_between(raw: str) -> Solution | None:
    if "整数" not in raw or "之间" not in raw:
        return None
    found = re.search(
        r"([+\-−–]?\d+\s*/\s*\d+|[+\-−–]?\d+(?:\.\d+)?)\s*与\s*([+\-−–]?\d+\s*/\s*\d+|[+\-−–]?\d+(?:\.\d+)?)",
        _normalize_fractions(raw),
    )
    if not found:
        return None
    left = _token_value(found.group(1))
    right = _token_value(found.group(2))
    if right < left:
        left, right = right, left
    inclusive = "不包括" not in raw
    start = ceil(left.n / left.d)
    end = floor(right.n / right.d)
    if not inclusive:
        if left.n % left.d == 0:
            start += 1
        if right.n % right.d == 0:
            end -= 1
    numbers = list(range(start, end + 1))
    positive = [show(Q(n)) for n in numbers if n > 0]
    negative = [show(Q(n)) for n in numbers if n < 0]
    listed = "、".join(show(Q(n)) for n in numbers) or "没有"
    lines = [
        f"先把 {show(left)} 和 {show(right)} 放在数轴上，再数这两点之间的整数格。",
        "包括两端。" if inclusive else "两端本身不算。",
        f"整数有 {len(numbers)} 个：{listed}。",
        f"其中正整数有 {len(positive)} 个" + (f"：{'、'.join(positive)}。" if positive else "。"),
        f"负整数有 {len(negative)} 个" + (f"：{'、'.join(negative)}。" if negative else "。"),
    ]
    return Solution(
        node_id="1.2.2",
        stem=raw,
        answer_display=f"{len(numbers)}个；{listed}；正整数 {len(positive)} 个；负整数 {len(negative)} 个",
        kind="explain",
        steps=lines,
        summary=_focus("1.2.2"),
        figure=_axis_figure([(show(Q(n)), float(n)) for n in numbers]),
    )


def _move_on_line(raw: str) -> Solution | None:
    if "移动" not in raw or "单位" not in raw:
        return None
    origin = re.search(
        r"表示的数是\s*([+\-−–]?\d+\s*/\s*\d+|[+\-−–]?\d+(?:\.\d+)?)",
        _normalize_fractions(raw),
    )
    step_match = re.search(r"移动\s*(\d+(?:\.\d+)?)\s*个单位", raw)
    if not origin or not step_match:
        return None
    start = _token_value(origin.group(1))
    step = decimal_to_q(step_match.group(1))
    right_only = any(word in raw for word in ("正方向", "向右")) and "某一" not in raw and "一个方向" not in raw
    left_only = any(word in raw for word in ("负方向", "向左")) and not right_only
    right = start + step
    left = start - step
    if right_only:
        pairs = [("A", start.n / start.d), ("B", right.n / right.d)]
        lines = [
            f"点 A 是 {show(start)}。向右是正方向，走 {show(step)} 个单位就是加上 {show(step)}。",
            f"点 B 是 {show(right)}。",
        ]
        answer = show(right)
        value = right
    elif left_only:
        pairs = [("A", start.n / start.d), ("B", left.n / left.d)]
        lines = [
            f"点 A 是 {show(start)}。向左走 {show(step)} 个单位就是减去 {show(step)}。",
            f"点 B 是 {show(left)}。",
        ]
        answer = show(left)
        value = left
    else:
        pairs = [("A", start.n / start.d), ("右", right.n / right.d), ("左", left.n / left.d)]
        lines = [
            f"点 A 是 {show(start)}。题目说某一方向，向右和向左都要算。",
            f"向右 {show(step)} 个单位，{show(start)} + {show(step)} = {show(right)}。",
            f"向左 {show(step)} 个单位，{show(start)} - {show(step)} = {show(left)}。",
        ]
        answer = f"向右 {show(right)}，向左 {show(left)}"
        value = None
    return Solution(
        node_id="1.2.2",
        stem=raw,
        answer_display=answer,
        kind="number" if value is not None else "explain",
        steps=lines,
        summary=_focus("1.2.2"),
        value=value,
        figure=_axis_figure(pairs),
    )


def _read_axis(raw: str, figure: dict | None) -> Solution | None:
    if not isinstance(figure, dict) or figure.get("type") != "number_line":
        return None
    if not any(word in raw for word in ("如图", "写出", "表示的数")):
        return None
    if any(word in raw for word in ("画出", "移动", "下列")):
        return None
    pairs = []
    for point in figure.get("points") or []:
        try:
            value = float(point["value"])
        except (KeyError, TypeError, ValueError):
            continue
        pairs.append((str(point.get("label") or "点"), value))
    if not pairs:
        return None
    lines = ["原点是 0，箭头向右是正方向。每个点的数，用它对着的刻度，不另外编一个答案。"]
    bits = []
    for label, value in pairs:
        shown = _show_float(value)
        lines.append(f"{label} 对着 {shown}。")
        bits.append(f"{label} 是 {shown}")
    return Solution(
        node_id="1.2.2",
        stem=raw,
        answer_display="，".join(bits),
        kind="explain",
        steps=lines,
        summary=_focus("1.2.2"),
        figure=figure,
    )


def solve_item(stem: str, figure: dict | None = None) -> Solution | None:
    for solver in (_plot_list, _integers_between, _move_on_line):
        solved = solver(stem)
        if solved is not None:
            return solved
    read = _read_axis(stem, figure)
    if read is not None:
        return read
    return solve_text(stem)


def format_q_detail(q: Q) -> dict[str, str]:
    exact = show(q)
    if q.d == 1:
        return {"exact": exact, "decimal": exact, "display": exact}
    rem = q.d
    while rem % 2 == 0:
        rem //= 2
    while rem % 5 == 0:
        rem //= 5
    if rem == 1:
        dec = (Decimal(abs(q.n)) / Decimal(q.d)).normalize()
        dec_text = f"{dec:f}"
        if "." in dec_text:
            dec_text = dec_text.rstrip("0").rstrip(".")
        if q.n < 0:
            dec_text = f"−{dec_text}"
        return {
            "exact": exact,
            "decimal": dec_text,
            "display": f"{dec_text}（分数 {exact}）",
        }
    approx = Decimal(abs(q.n)) / Decimal(q.d)
    approx_text = f"{approx:.4f}".rstrip("0").rstrip(".")
    if q.n < 0:
        approx_text = f"−{approx_text}"
    return {
        "exact": exact,
        "decimal": f"≈{approx_text}",
        "display": exact,
    }


def _prepare_math_expr(
    raw: str,
    vars_map: dict | None = None,
    prev_values: dict[str, Q] | None = None,
) -> str:
    text = _normalize_fractions(raw.strip())
    text = text.replace("**", "^").replace("²", "^2").replace("³", "^3")
    text = re.sub(r"\\times\b", "*", text)
    text = re.sub(r"\\div\b", "/", text)
    text = re.sub(r"\\pi\b", "π", text)
    text = text.strip(" ；;。．.")
    if prev_values:
        for key in sorted(prev_values.keys(), key=len, reverse=True):
            q = prev_values[key]
            rep = f"({q.n}/{q.d})" if q.d != 1 else f"({q.n})"
            text = text.replace(key, rep)
    merged_vars: dict[str, str] = {"π": "3.14", "pi": "3.14", "PI": "3.14"}
    if isinstance(vars_map, dict):
        for k, v in vars_map.items():
            if k and v is not None:
                merged_vars[str(k).strip()] = str(v).strip()
    for name in sorted(merged_vars.keys(), key=len, reverse=True):
        val_str = merged_vars[name]
        if name.isascii() and name.isalpha() and len(name) > 1:
            text = re.sub(rf"(?<![a-zA-Z]){re.escape(name)}(?![a-zA-Z])", f"({val_str})", text)
        else:
            text = re.sub(rf"(?<![a-zA-Z]){re.escape(name)}(?![a-zA-Z])", f"({val_str})", text)
    text = normalize_symbols(text)
    text = re.sub(r"(\d|\))\s*(?=\()", r"\1*", text)
    text = re.sub(r"\)\s*(?=\d)", r")*", text)
    return text


def _eval_prepared(expr_text: str, vars_map: dict | None = None, prev_values: dict[str, Q] | None = None) -> tuple[Q, list[str]]:
    prepared = _prepare_math_expr(expr_text, vars_map=vars_map, prev_values=prev_values)
    tree = parse_expr(prepared)
    return evaluate(tree)


def _solve_linear_one(eq_raw: str, vars_map: dict | None = None) -> dict | None:
    cleaned = eq_raw.strip().strip(" ；;。．.")
    if cleaned.count("=") != 1:
        return None
    left_raw, right_raw = cleaned.split("=", 1)
    known = {"pi", "PI", "π", "abs", "ABS"}
    if isinstance(vars_map, dict):
        known.update(str(k).strip() for k in vars_map.keys())
    pre_left = _normalize_fractions(left_raw)
    pre_right = _normalize_fractions(right_raw)
    tokens = set(re.findall(r"[a-zA-Z]+", re.sub(r"\\(?:frac|times|div|pi)\b", " ", pre_left + " " + pre_right)))
    unknowns = sorted(tokens - known)
    if len(unknowns) != 1 or len(unknowns[0]) != 1:
        return None
    var = unknowns[0]

    def diff_at(x_val: Q) -> Q:
        local_vars = dict(vars_map or {})
        local_vars[var] = f"({x_val.n}/{x_val.d})" if x_val.d != 1 else str(x_val.n)
        lv, _ = _eval_prepared(left_raw, vars_map=local_vars)
        rv, _ = _eval_prepared(right_raw, vars_map=local_vars)
        return lv - rv

    try:
        d0 = diff_at(Q(0))
        d1 = diff_at(Q(1))
        d2 = diff_at(Q(2))
        dm1 = diff_at(Q(-1))
    except (MathInputError, ZeroDivisionError):
        return None
    k = d1 - d0
    if (d2 - d1) != k or (d0 - dm1) != k or k.n == 0:
        return None
    root = (-d0) / k
    try:
        check_vars = dict(vars_map or {})
        check_vars[var] = f"({root.n}/{root.d})" if root.d != 1 else str(root.n)
        lv, _ = _eval_prepared(left_raw, vars_map=check_vars)
        rv, _ = _eval_prepared(right_raw, vars_map=check_vars)
    except (MathInputError, ZeroDivisionError):
        return None
    if lv != rv:
        return None
    detail = format_q_detail(root)
    both = format_q_detail(lv)["display"]
    return {
        "ok": True,
        "kind": "equation",
        "equation": cleaned,
        "variable": var,
        "exact": detail["exact"],
        "decimal": detail["decimal"],
        "display": f"{var} = {detail['display']}",
        "verified": f"代入检验：左边 = 右边 = {both}",
        "q": root,
    }


def _run_single_math_step(step: dict | str, index: int, prev_values: dict[str, Q]) -> dict:
    if isinstance(step, str):
        step = {"expr": step}
    label = str(step.get("label") or f"步骤{index}").strip()
    expr_raw = str(step.get("expr") or step.get("equation") or "").strip()
    vars_map = step.get("vars") if isinstance(step.get("vars"), dict) else None

    if step.get("range") and isinstance(step["range"], dict):
        r = step["range"]
        low_q, _ = _eval_prepared(str(r.get("low", 0)), vars_map=vars_map, prev_values=prev_values)
        high_q, _ = _eval_prepared(str(r.get("high", 0)), vars_map=vars_map, prev_values=prev_values)
        if high_q < low_q:
            low_q, high_q = high_q, low_q
        inc = bool(r.get("inclusive", True))
        start = ceil(low_q.n / low_q.d)
        end = floor(high_q.n / high_q.d)
        if not inc:
            if low_q.n % low_q.d == 0:
                start += 1
            if high_q.n % high_q.d == 0:
                end -= 1
        nums = list(range(start, end + 1))
        pos = [n for n in nums if n > 0]
        neg = [n for n in nums if n < 0]
        listed = "、".join(show(Q(n)) for n in nums) or "无"
        return {
            "ok": True,
            "kind": "integers_between",
            "label": label,
            "count": len(nums),
            "integers": [show(Q(n)) for n in nums],
            "positive_count": len(pos),
            "negative_count": len(neg),
            "display": f"共 {len(nums)} 个整数：{listed}（正整数 {len(pos)} 个，负整数 {len(neg)} 个）",
        }

    # Check if this is a comparison step
    cmp_pair = None
    if isinstance(step.get("compare"), list) and len(step["compare"]) == 2:
        cmp_pair = (str(step["compare"][0]), str(step["compare"][1]))
    elif step.get("left") is not None and step.get("right") is not None:
        cmp_pair = (str(step["left"]), str(step["right"]))
    else:
        stripped = re.sub(r"^[（(]\s*\d+\s*[）).、．]\s*", "", expr_raw).strip(" ；;。．.")
        m = re.search(r"^(?:比较\s*)?(.+?)\s*(?:和|与|vs|VS|,|，|<|>|\?|？)\s*(.+)$", stripped)
        if m:
            left_cand = m.group(1).strip()
            right_cand = re.sub(r"(的大小|哪个大|谁大).*$", "", m.group(2)).strip(" ：:?？。．.")
            if "," not in right_cand and "，" not in right_cand:
                cmp_pair = (left_cand, right_cand)

    if cmp_pair is not None:
        left_s, right_s = cmp_pair
        try:
            a, sa = _eval_prepared(left_s, vars_map=vars_map, prev_values=prev_values)
            b, sb = _eval_prepared(right_s, vars_map=vars_map, prev_values=prev_values)
        except (MathInputError, ZeroDivisionError) as exc:
            return {"ok": False, "label": label, "expr": expr_raw, "error": str(exc)}
        sym = _compare_symbol(a, b)
        word = {"<": "小于", ">": "大于", "=": "等于"}[sym]
        da = format_q_detail(a)
        db = format_q_detail(b)
        return {
            "ok": True,
            "kind": "compare",
            "label": label,
            "left": {"expr": left_s, **da, "steps": sa},
            "right": {"expr": right_s, **db, "steps": sb},
            "relation": sym,
            "word": word,
            "display": f"{left_s} = {da['display']}，{right_s} = {db['display']} ⇒ {left_s} {sym} {right_s}（{word}）",
        }

    # Check if this is a multi-number sign classification list
    if ("," in expr_raw or "，" in expr_raw or "、" in expr_raw) and "=" not in expr_raw:
        norm = _normalize_fractions(expr_raw)
        tokens = _NUMBER_TOKEN.findall(norm)
        if len(tokens) >= 3:
            pos, neg, zero = [], [], []
            for tok in tokens:
                q = _token_value(tok)
                pretty = _pretty_token(tok)
                if q.n > 0:
                    pos.append(pretty)
                elif q.n < 0:
                    neg.append(pretty)
                else:
                    zero.append(pretty)
            summary = f"正数：{'、'.join(pos) or '无'}；负数：{'、'.join(neg) or '无'}"
            if zero:
                summary += "；0 既不是正数也不是负数"
            return {
                "ok": True,
                "kind": "classify_signs",
                "label": label,
                "positive": pos,
                "negative": neg,
                "zero": zero,
                "display": summary,
            }

    # Check if this is a single-variable linear equation
    if "=" in expr_raw:
        eq_res = _solve_linear_one(expr_raw, vars_map=vars_map)
        if eq_res is not None:
            q_val = eq_res.pop("q")
            prev_values[f"${index}"] = q_val
            prev_values[eq_res["variable"]] = q_val
            eq_res["label"] = label
            return eq_res
        # What if the model wrote "S = 1/2 * 10 * 17.3 - 3.14 * 2^2"?
        lhs, rhs = expr_raw.split("=", 1)
        if re.fullmatch(r"[a-zA-Z_]\w*", lhs.strip()):
            var_name = lhs.strip()
            try:
                val, steps = _eval_prepared(rhs, vars_map=vars_map, prev_values=prev_values)
                prev_values[f"${index}"] = val
                prev_values[var_name] = val
                detail = format_q_detail(val)
                return {
                    "ok": True,
                    "kind": "calc",
                    "label": label,
                    "expr": expr_raw,
                    "exact": detail["exact"],
                    "decimal": detail["decimal"],
                    "display": f"{var_name} = {detail['display']}",
                    "steps": steps,
                }
            except (MathInputError, ZeroDivisionError) as exc:
                return {"ok": False, "label": label, "expr": expr_raw, "error": str(exc)}

    # Standard arithmetic / substitution expression
    try:
        val, steps = _eval_prepared(expr_raw, vars_map=vars_map, prev_values=prev_values)
    except (MathInputError, ZeroDivisionError) as exc:
        return {"ok": False, "label": label, "expr": expr_raw, "error": str(exc)}
    prev_values[f"${index}"] = val
    detail = format_q_detail(val)
    return {
        "ok": True,
        "kind": "calc",
        "label": label,
        "expr": expr_raw,
        "exact": detail["exact"],
        "decimal": detail["decimal"],
        "display": f"{expr_raw} = {detail['display']}",
        "steps": steps,
    }


def _parse_coord(raw_val) -> float:
    if isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
        return float(raw_val)
    text = str(raw_val).strip()
    q = _token_value(text)
    return q.n / q.d


def validate_figure(figure) -> dict | None:
    if not isinstance(figure, dict):
        return None
    kind = figure.get("type")
    try:
        if kind == "number_line":
            points = []
            vals = []
            for point in figure.get("points") or []:
                value = _parse_coord(point["value"])
                if value != value or abs(value) > 100:
                    return None
                fill = str(point.get("fill") or "closed").strip().lower()
                if fill not in ("open", "closed"):
                    fill = "closed"
                ray = str(point.get("ray") or "").strip().lower()
                if ray not in ("left", "right"):
                    ray = ""
                points.append(
                    {
                        "label": str(point.get("label") or "A")[:8],
                        "value": value,
                        "fill": fill,
                        "ray": ray,
                    }
                )
                vals.append(value)
            raw_min = figure.get("min")
            raw_max = figure.get("max")
            lo = floor(_parse_coord(raw_min)) if raw_min is not None else floor(min(vals + [-5.0]))
            hi = ceil(_parse_coord(raw_max)) if raw_max is not None else ceil(max(vals + [5.0]))
            for v in vals:
                lo = min(lo, floor(v))
                hi = max(hi, ceil(v))
            if lo >= hi or hi - lo > 30:
                return None
            highlight = None
            if isinstance(figure.get("highlight"), dict):
                highlight = {
                    "from": _parse_coord(figure["highlight"]["from"]),
                    "to": _parse_coord(figure["highlight"]["to"]),
                }
            return {"type": "number_line", "min": lo, "max": hi, "points": points, "highlight": highlight}
        if kind == "angle":
            degrees = _parse_coord(figure["degrees"])
            if not 0 < degrees < 180:
                return None
            return {
                "type": "angle",
                "degrees": degrees,
                "label": str(figure.get("label") or f"{degrees:g}°")[:16],
            }
        if kind == "plane_geometry":
            pts_out = []
            pt_names = set()
            for pt in (figure.get("points") or [])[:24]:
                if not isinstance(pt, dict):
                    continue
                lbl = str(pt.get("label") or "").strip()[:12]
                if not lbl:
                    continue
                px = _parse_coord(pt.get("x", 0))
                py = _parse_coord(pt.get("y", 0))
                if abs(px) > 500 or abs(py) > 500:
                    return None
                pts_out.append({"label": lbl, "x": px, "y": py})
                pt_names.add(lbl)
            lines_out = []
            for ln in (figure.get("lines") or [])[:30]:
                if not isinstance(ln, dict):
                    continue
                p_from = str(ln.get("from") or "").strip()
                p_to = str(ln.get("to") or "").strip()
                if p_from not in pt_names or p_to not in pt_names or p_from == p_to:
                    continue
                l_kind = str(ln.get("kind") or "segment").strip().lower()
                if l_kind not in ("segment", "ray", "line"):
                    l_kind = "segment"
                l_style = str(ln.get("style") or "solid").strip().lower()
                if l_style not in ("solid", "dashed"):
                    l_style = "solid"
                parallel = ln.get("parallel")
                try:
                    parallel_n = int(parallel) if parallel not in (None, "", False) else 0
                except (TypeError, ValueError):
                    parallel_n = 0
                if parallel_n not in (0, 1, 2):
                    parallel_n = 0
                lines_out.append(
                    {
                        "kind": l_kind,
                        "from": p_from,
                        "to": p_to,
                        "style": l_style,
                        "label": str(ln.get("label") or "").strip()[:20],
                        "parallel": parallel_n,
                    }
                )
            circles_out = []
            for c in (figure.get("circles") or [])[:8]:
                if not isinstance(c, dict):
                    continue
                rad = _parse_coord(c.get("radius", 0))
                if rad <= 0 or rad > 200:
                    continue
                center_lbl = str(c.get("center") or "").strip()
                cx = _parse_coord(c["x"]) if "x" in c and c["x"] is not None else None
                cy = _parse_coord(c["y"]) if "y" in c and c["y"] is not None else None
                circles_out.append(
                    {
                        "center": center_lbl,
                        "x": cx,
                        "y": cy,
                        "radius": rad,
                        "label": str(c.get("label") or "").strip()[:16],
                    }
                )
            angles_out = []
            for ang in (figure.get("angles") or [])[:12]:
                if not isinstance(ang, dict):
                    continue
                vertex = str(ang.get("vertex") or "").strip()
                arm_from = str(ang.get("from") or ang.get("arm1") or "").strip()
                arm_to = str(ang.get("to") or ang.get("arm2") or "").strip()
                if vertex not in pt_names or arm_from not in pt_names or arm_to not in pt_names:
                    continue
                right = bool(ang.get("right"))
                angles_out.append(
                    {
                        "vertex": vertex,
                        "from": arm_from,
                        "to": arm_to,
                        "right": right,
                        "label": str(ang.get("label") or ("90°" if right else "")).strip()[:12],
                    }
                )
            if len(pts_out) < 2 and not circles_out:
                return None
            show_north = bool(figure.get("show_north") or figure.get("compass_from"))
            compass_from = str(figure.get("compass_from") or "").strip()
            bearings = _compass_bearings(pts_out, compass_from)
            if bearings:
                by_pair = {(item["from"], item["to"]): item["direction"] for item in bearings}
                for ln in lines_out:
                    pair = {ln["from"], ln["to"]}
                    for (start, end), direction in by_pair.items():
                        if pair == {start, end}:
                            ln["label"] = direction
            return {
                "type": "plane_geometry",
                "show_axes": bool(figure.get("show_axes", False)),
                "show_north": show_north,
                "compass_from": compass_from,
                "bearings": bearings,
                "points": pts_out,
                "lines": lines_out,
                "circles": circles_out,
                "angles": angles_out,
            }
        chart_items = _chart_items(figure.get("items") or figure.get("slices") or figure.get("bins"))
        if kind in ("bar_chart", "histogram", "line_chart") and len(chart_items) >= 1:
            return {"type": kind, "title": str(figure.get("title") or "")[:24], "items": chart_items}
        if kind == "pie_chart":
            slices = [item for item in chart_items if item["value"] > 0]
            if len(slices) >= 1:
                return {"type": "pie_chart", "title": str(figure.get("title") or "")[:24], "items": slices}
        if kind == "three_view":
            front = _cell_grid(figure.get("front"))
            left = _cell_grid(figure.get("left"))
            top = _cell_grid(figure.get("top"))
            mismatch = three_view_problem(front, left, top)
            if mismatch:
                return None
            if front or left or top:
                return {"type": "three_view", "front": front, "left": left, "top": top}
        if kind == "cube_solid":
            projected = _project_cube_solid(figure.get("layers"))
            if projected is None:
                return None
            front, left, top, count = projected
            expected = figure.get("cube_count")
            if expected is not None and int(_parse_coord(expected)) != count:
                return None
            return {
                "type": "three_view",
                "front": front,
                "left": left,
                "top": top,
                "cube_count": count,
            }
        if kind == "net":
            cells = _cell_grid(figure.get("cells") or figure.get("grid"), binary=True)
            labels = _label_grid(figure.get("labels"), len(cells), max((len(row) for row in cells), default=0))
            if any(cell for row in cells for cell in row):
                return {"type": "net", "cells": cells, "labels": labels}
    except (KeyError, TypeError, ValueError, ZeroDivisionError, MathInputError):
        return None
    return None


def compass_bearing(dx: float, dy: float) -> str | None:
    """东为正 x，北为正 y。分成正北、东北、正东、东南、正南、西南、正西、西北。"""
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    turned = degrees(atan2(dx, dy)) % 360
    names = ("正北", "东北", "正东", "东南", "正南", "西南", "正西", "西北")
    return names[int((turned + 22.5) // 45) % 8]


def _compass_bearings(points: list[dict], origin_label: str) -> list[dict]:
    if not origin_label:
        return []
    origin = next((point for point in points if point["label"] == origin_label), None)
    if origin is None:
        return []
    found = []
    for point in points:
        if point["label"] == origin_label:
            continue
        direction = compass_bearing(point["x"] - origin["x"], point["y"] - origin["y"])
        if direction:
            found.append({"from": origin_label, "to": point["label"], "direction": direction})
    return found


def _grid_shape(grid: list[list[int]]) -> tuple[int, int]:
    if not grid:
        return 0, 0
    return len(grid), max(len(row) for row in grid)


def three_view_problem(front: list[list[int]], left: list[list[int]], top: list[list[int]]) -> str | None:
    front_rows, front_cols = _grid_shape(front)
    left_rows, left_cols = _grid_shape(left)
    top_rows, top_cols = _grid_shape(top)
    problems = []
    if front and left and front_rows != left_rows:
        problems.append(f"正面有 {front_rows} 行，左面有 {left_rows} 行，高度对不上")
    if front and top and front_cols != top_cols:
        problems.append(f"正面有 {front_cols} 列，上面有 {top_cols} 列，左右宽度对不上")
    if left and top and left_cols != top_rows:
        problems.append(f"左面有 {left_cols} 列，上面有 {top_rows} 行，前后深度对不上")
    if not problems:
        return None
    return (
        "；".join(problems)
        + "。三个方向必须对得上：正面的列数等于上面的列数，左面的列数等于上面的行数，正面和左面的行数相同。"
        + "每一格是一个能看见的小正方形，第一行是最上面那一层。两层高就要两行，空位填 0，不要把台阶压成一行。"
        + "上面看只涂真正有积木的格子。"
    )


def figure_error(figure) -> str | None:
    if not isinstance(figure, dict):
        return None
    kind = figure.get("type")
    try:
        if kind == "cube_solid":
            projected = _project_cube_solid(figure.get("layers"))
            if projected is None:
                return "立体图的 layers 读不出来。请从下往上给每一层，第 0 行是前面，从左到右是列，有小立方体填 1，没有填 0。"
            count = projected[3]
            expected = figure.get("cube_count")
            if expected is not None and int(_parse_coord(expected)) != count:
                return (
                    f"你摆出了 {count} 个小立方体，题目是 {int(_parse_coord(expected))} 个。"
                    "请对照立体图，把漏掉或多出来的那一块补进 layers 再画。"
                    "正面能看到几列，每一层就要有几列，不要口头说 4 列、数组里只写 3 列。"
                )
            return None
        if kind != "three_view":
            return None
        return three_view_problem(
            _cell_grid(figure.get("front")),
            _cell_grid(figure.get("left")),
            _cell_grid(figure.get("top")),
        )
    except (TypeError, ValueError, ZeroDivisionError, MathInputError):
        return "三视图的表格读不出来，请用 0 和 1 组成的二维数组。"


def _project_cube_solid(raw) -> tuple[list[list[int]], list[list[int]], list[list[int]], int] | None:
    """layers 从下往上。每一层第 0 行是前面，列从左到右。投影成三视图。"""
    if not isinstance(raw, list) or not raw:
        return None
    layers = []
    for layer in raw[:6]:
        if not isinstance(layer, list):
            return None
        rows = []
        for row in layer[:6]:
            if not isinstance(row, list):
                return None
            rows.append([1 if int(_parse_coord(cell)) else 0 for cell in row[:6]])
        if rows:
            layers.append(rows)
    if not layers or not any(cell for layer in layers for row in layer for cell in row):
        return None
    height = len(layers)
    depth = max(len(layer) for layer in layers)
    width = max((len(row) for layer in layers for row in layer), default=0)
    if width == 0 or depth == 0:
        return None
    norm = []
    for layer in layers:
        padded = []
        for y in range(depth):
            src = layer[y] if y < len(layer) else []
            padded.append([src[x] if x < len(src) else 0 for x in range(width)])
        norm.append(padded)
    front = [[0 for _ in range(width)] for _ in range(height)]
    left = [[0 for _ in range(depth)] for _ in range(height)]
    for z, layer in enumerate(norm):
        row_from_top = height - 1 - z
        for y in range(depth):
            for x in range(width):
                if layer[y][x]:
                    front[row_from_top][x] = 1
                    left[row_from_top][y] = 1
    top = [[0 for _ in range(width)] for _ in range(depth)]
    for y in range(depth):
        out_row = depth - 1 - y
        for x in range(width):
            if any(norm[z][y][x] for z in range(height)):
                top[out_row][x] = 1
    count = sum(cell for layer in norm for row in layer for cell in row)
    return front, left, top, count


def _chart_items(raw) -> list[dict]:
    items = []
    for entry in (raw or [])[:8]:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or entry.get("name") or "")[:12]
        raw_value = entry.get("value", entry.get("count", entry.get("freq")))
        value = _parse_coord(raw_value if raw_value is not None else 0)
        if value < 0 or value > 100000:
            continue
        items.append({"label": label or str(len(items) + 1), "value": value})
    return items


def _cell_grid(raw, binary: bool = False) -> list[list[int]]:
    rows = []
    for row in (raw or [])[:6]:
        if not isinstance(row, list):
            continue
        nums = []
        for cell in row[:6]:
            number = int(_parse_coord(cell))
            if binary:
                number = 1 if number else 0
            else:
                number = max(0, min(number, 9))
            nums.append(number)
        if nums:
            rows.append(nums)
    width = max((len(row) for row in rows), default=0)
    return [row + [0] * (width - len(row)) for row in rows]


def _label_grid(raw, rows: int, cols: int) -> list[list[str]]:
    out = [["" for _ in range(cols)] for _ in range(rows)]
    if not isinstance(raw, list):
        return out
    for r, row in enumerate(raw[:rows]):
        if not isinstance(row, list):
            continue
        for c, cell in enumerate(row[:cols]):
            out[r][c] = str(cell or "")[:4]
    return out


def run_math_steps(steps: list) -> list[dict]:
    results = []
    prev_values: dict[str, Q] = {}
    for idx, item in enumerate(steps or [], start=1):
        results.append(_run_single_math_step(item, idx, prev_values))
    return results
