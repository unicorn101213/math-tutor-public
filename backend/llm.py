"""TIR（工具集成推理）：多模态看图拆题 + 强制调用数学与画图工具核对。"""

from __future__ import annotations

import json
import logging
import re

import httpx

from config import settings
from curriculum import grade_profile, search_curriculum_context
from rational import figure_error, run_math_steps, validate_figure

log = logging.getLogger("tutor.llm")

TIR_SYSTEM_PROMPT = """你是人教版数学家庭教师。你语气温和、耐心、接地气，像坐在学生身边讲题的老师。

你必须遵守「核心工具核对 + 独立审题 + 贴合人教版课本」的工作方式：
1. 【看图与独立审题（忽略卷面已填答案）】：
   - 当学生发来一张或多张照片（几何图形、数轴、课本例题、或做过的试卷/练习册）时，如果卷面上已经有手写填入的答案、旁批草稿或别人写的数字：**你必须先剥离手写内容、只提取原始印刷题干，独立调用 `math_steps` 算出标准答案**！绝不能被卷面上已填的答案带偏或顺着错答案往下凑。
   - 如果学生在发图时附带了文字要求（例如“只看第3题”“这两张图合起来是同一道题”），严格按学生的要求解答指定题目；如果没有特别说明且图里有多道小题，按顺序一道道讲完，不要把总标题当成单独一道题。
   - 算完标准答案后，如果发现卷面手写答案算错了或有红叉（×），温和指出学生错在哪一步，并调用 `save_error_item` 存入错题库。
2. 【死规矩：一切计算与比大小必须调用 math_steps 工具】：
   - 严禁你自己心算或口算任何算式、乘方、绝对值、正负号化简、代数式求值、两个数比大小、区间内整数统计或解方程！
   - 凡是涉及算式计算（如 1/2 * 10 * 17.3 - 3.14 * 2^2）、化简（如 -(-0.5)、|-1.5|）、比大小（如 -(-0.5) 和 |-1.5|）、正负数分类、数轴移动加减、解一元一次方程，必须先调用 `math_steps` 工具，拿到工具返回的准确结果后，完全采用工具返回的数字写讲解。
   - 学生只是在追问刚才的概念、或要相关知识点时，不要调用 `math_steps`，也不要说这一句没有算式。
3. 【图形、数轴与平面几何作图统一调用 draw_figure 工具，并插在对应题目后面】：
   - 凡是涉及：
     * **数轴**（`type="number_line"`：写出数轴上点表示的数、在数轴上表示有理数、数轴上点的移动、数轴区间整数）
     * **角度**（`type="angle"`：画角、钟面角、余角补角示意图）
     * **平面几何作图与坐标系**（`type="plane_geometry"`：平面上给定点 A、B、C、D 画直线/射线/线段/延长线/反向延长线、三角形、圆或平面直角坐标系描点连线）
     都必须调用 `draw_figure` 把图真正画出来，**严禁只用字符画（如 `A----D----E`）敷衍**！
   - 当画 `plane_geometry`（如“连接 DA，并反向延长 DA 至 E，使 DE = 2AD”）时：
     * 先按原图相对位置给各点设定合理的二维坐标 `(x, y)`（例如 `A(2, 6), B(5.5, 5.2), C(6.5, 2.2), D(2, 3.5)`）；
     * 对于延长线/反向延长线（如反向延长 DA 至 E 使 DE = 2AD），根据向量算出 E 的准确坐标（从 A 到 D 是向下走 2.5，反向延长 DA 就是从 A 经过 D 继续向下走 2 倍的 AD，即 `E(2, 3.5 - 2*2.5) = E(2, -1.5)`，可用 `math_steps` 核对坐标），然后把直线（`kind="line"`，两端出头）、射线（`kind="ray"`，从起点穿过另一点、只在方向那头出头）、线段（`kind="segment"`，两端停在端点上）和延长线（可用 `style="dashed"` 虚线区分并加 `label="DE=2AD"`）传给 `draw_figure`。
     * 画板按课本画：直线和射线都不画箭头，只是线头伸出端点、不封口。讲解里不要说「我画了箭头」。
   - 【方位图，例如动物园、指路】观测点放在 (0, 0)，北是 y 增大，东是 x 增大。先看图上的指北针，再按每个地点相对观测点的真实位置估坐标，不要排成对称的十字。`show_north` 填 true，`compass_from` 填观测点名字（如「大门」）。斜方向（东北、西北、东南、西南）时，x 和 y 都要明显离开 0，而且大小差不多；只有地点几乎就在观测点的正上或正下，才让另一个坐标接近 0。不要自己写「正北」「东北」，工具会按坐标算出 `bearings`，讲解和线上的字都用这个结果。
   - 平面图还可以加这些记号，不要只用文字描述：
     * 角：`angles` 里写 `{vertex, from, to, label, right}`。`right=true` 画直角小方块；否则画角弧和度数。
     * 平行：同一组平行线的 `parallel` 填同一个数字 `1` 或 `2`，画板会在线上画对应的箭头记号。
   - 数轴上画不等式解集时，点要带 `fill`：`"closed"` 是实心点（有等号），`"open"` 是空心圈（没有等号）；方向用 `ray`：`"left"` 或 `"right"`。
   - 统计图和立体图也走 `draw_figure`，不要用字符画：
     * `bar_chart` 条形图、`histogram` 直方图、`line_chart` 折线图、`pie_chart` 扇形图。数据放 `items`：`[{label, value}]`，扇形图的 value 用人数或百分比。
     * 由小立方体搭成的立体图，不要自己分别猜 front、left、top。用 `type="cube_solid"`：`layers` 从下往上，每一层是一个二维数组，第 0 行是靠近观察者的前面，从左到右是列，有小立方体填 1。`cube_count` 填题目里的个数（例如 9）。程序会按这些方块投影出从前面看、从左面看、从上面看。块数不对会退回。正面能看到几列，每一层就要有几列，不能嘴里说 4 列、数组里只放 3 列。左视图的左边是物体的前面。
     * 只有题目已经印出了三视图、要你照着描时，才用 `three_view`。`front`、`left`、`top` 每一格是一个能看见的小正方形，0 是空，1 是有这块面。第一行是最上面那一层。
     * `net` 展开图：`cells` 是 0/1 方格，1 表示展开图上的一个面，位置要和课本那种方格图一致。
   - 【极其重要：数轴看图规则】读照片里已有的数轴时，必须先做一件事：**观察每一个点正下方有没有直接印着刻度数字**！
     * 如果点的正下方就有刻度竖线和数字（例如点 C 正下方直接标着 `1`，点 A 正下方标着 `0`，点 B 正下方标着 `-2`），那么这个点**正好落在该刻度上**（即 C = 1），绝不能看成两格中间的 1.5！
     * 只有当一个点明显画在两个相邻整数刻度竖线的正中间、且它正下方没有整数刻度（或者下方特意标了 `2.5`）时，才读成 `.5`（半格）。
   - 每次调用 `draw_figure` 成功后，工具会返回一个 `placeholder`（如 `[[FIGURE_1]]`、`[[FIGURE_2]]`）。在最终写讲解时，**请把 `[[FIGURE_1]]` 单独占一行，直接放在对应那道题（如第1题）的讲解文字紧后面**，不要把所有图堆在最后！
4. 【先翻课本防超纲 + 错题库与知识点库沉淀】：
   - 做学生当前年级的题目时，严格按照人教版七年级上下册（第1~12章）的方法讲题，不要使用高中或大学的工具。学生点名要听后面年级的内容时，直接把那一句讲完，开头用一句话说明是哪一册才学的，不要改答成当前年级里的别的知识。
   - 当遇到试卷错题、学生说“放到错题库/这题我做错了”、或学生反复问同一类易错题时，调用 `save_error_item` 把干净题干和完整解析存入错题库。
   - 学生问一个概念时，用话说完这一句。不要把知识卡片、章节目录或思维导图当成回答。
5. 【手机气泡排版要求】：
   - 不要输出任何 LaTeX 符号（严禁写 \\frac、\\times、\\div、$$、\\[、\\( 等）。
   - 分数直接写 1/2、5/2、-3/4；乘号写 ×；除号写 ÷；平方写 ² 或 ^2；圆周率写 π。
   - 每一道题都把思路、代入过程和最终结果讲完整，不要藏着答案。"""

TIR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "math_steps",
            "description": (
                "【必调数学核对工具】用精确有理数/小数计算并核对所有数学步骤。"
                "支持：(1) 四则运算、乘方(^)、绝对值(|x| 或 abs(x))、相反数化简，如 '1/2 * 10 * 17.3'、'3.14 * 2^2'、'86.5 - 12.56'、'-(-0.5)'、'|-1.5|'；"
                "(2) 代数式代入求值，如 expr='1/2*a*b - pi*r^2', vars={'a':10,'b':17.3,'r':2}；"
                "(3) 比较两个数或式子的大小，如 expr='-(-0.5) 和 |-1.5|' 或 compare=['-(-1)', '-(+2)']；"
                "(4) 解一元一次方程，如 expr='3*(x-1) = x + 5'；"
                "(5) 一串有理数的正负数分类，如 expr='4/3, -1, 2.5, 1/4, 0, -3.14, 120, -2/7'；"
                "(6) 数轴两点之间的整数统计，如 range={'low':-2,'high':4,'inclusive':true}。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "description": "要执行的数学计算、化简、比较或方程步骤列表。可一次传入多个步骤或多个小题。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {
                                    "type": "string",
                                    "description": "步骤或小题说明，如 '三角形面积'、'圆的面积'、'(4) 比大小'",
                                },
                                "expr": {
                                    "type": "string",
                                    "description": "算式、比较式或方程，如 '1/2 * 10 * 17.3'、'-(-0.5) 和 |-1.5|'、'2*x - 3 = 5'",
                                },
                                "vars": {
                                    "type": "object",
                                    "description": "可选变量代入字典，如 {'a': 10, 'b': 17.3, 'r': 2}",
                                },
                                "compare": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "可选：要比大小的两个算式 [左式, 右式]",
                                },
                                "range": {
                                    "type": "object",
                                    "description": "可选：统计数轴区间 [low, high] 内的整数",
                                    "properties": {
                                        "low": {"type": "number"},
                                        "high": {"type": "number"},
                                        "inclusive": {"type": "boolean"},
                                    },
                                },
                            },
                        },
                    }
                },
                "required": ["steps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draw_figure",
            "description": (
                "【画图工具】绘制数轴、角、平面几何、统计图、三视图和展开图。"
                "数轴点可带 fill=closed/open 和 ray=left/right，用来画不等式解集。"
                "平面图的线可带 parallel=1 或 2 表示平行记号；angles 里 vertex/from/to/right 用来画角弧或直角符号。"
                "统计图用 bar_chart、histogram、line_chart、pie_chart，数据在 items。"
                "由若干小立方体搭成的立体图用 cube_solid：layers 从下往上，每层第 0 行是前面，cube_count 填题目个数，三视图由程序投影。"
                "题目里已经印好的三视图才用 three_view。展开图用 net 的 cells（0/1 方格）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "number_line",
                            "angle",
                            "plane_geometry",
                            "bar_chart",
                            "pie_chart",
                            "line_chart",
                            "histogram",
                            "three_view",
                            "cube_solid",
                            "net",
                        ],
                    },
                    "min": {"type": "number", "description": "数轴最小刻度，如 -5"},
                    "max": {"type": "number", "description": "数轴最大刻度，如 5"},
                    "points": {
                        "type": "array",
                        "description": "点列表。number_line 填 {label, value}；plane_geometry 填二维坐标 {label, x, y}",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string", "description": "点名称，如 'A'、'D'、'E' 或 '-7/2'"},
                                "value": {"type": "number", "description": "数轴上的数值（仅 number_line 用）"},
                                "x": {"type": "number", "description": "平面横坐标（仅 plane_geometry 用）"},
                                "y": {"type": "number", "description": "平面纵坐标（仅 plane_geometry 用）"},
                                "fill": {
                                    "type": "string",
                                    "enum": ["closed", "open"],
                                    "description": "数轴端点：closed=实心点（含等号），open=空心圈（不含等号）",
                                },
                                "ray": {
                                    "type": "string",
                                    "enum": ["left", "right"],
                                    "description": "不等式解集从该点向左或向右延伸",
                                },
                            },
                            "required": ["label"],
                        },
                    },
                    "lines": {
                        "type": "array",
                        "description": "平面几何中的线列表（仅 plane_geometry 用）：直线(line，两端出头、不封口、不画箭头)、射线(ray，从from出发穿过to、只在方向那头出头、不画箭头)、线段(segment，两端停在端点上)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["segment", "ray", "line"], "description": "segment=线段，ray=射线(起点from，方向经过to)，line=直线(穿过from和to向两端延伸)"},
                                "from": {"type": "string", "description": "起点或第一个点标签，如 'A'"},
                                "to": {"type": "string", "description": "终点或方向点标签，如 'B'"},
                                "style": {"type": "string", "enum": ["solid", "dashed"], "description": "solid=实线，dashed=虚线（常用于延长线或辅助线）"},
                                "label": {"type": "string", "description": "可选：线旁边的文字标注，如 '直线AB'、'射线BC'、'DE=2AD'"},
                                "parallel": {
                                    "type": "integer",
                                    "enum": [0, 1, 2],
                                    "description": "平行记号。同一组平行线填同一个 1 或 2，0 表示没有",
                                },
                            },
                            "required": ["kind", "from", "to"],
                        },
                    },
                    "circles": {
                        "type": "array",
                        "description": "可选：平面几何中的圆列表（仅 plane_geometry 用）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "center": {"type": "string", "description": "圆心点标签（若在 points 中已定义）"},
                                "x": {"type": "number", "description": "圆心横坐标"},
                                "y": {"type": "number", "description": "圆心纵坐标"},
                                "radius": {"type": "number", "description": "半径"},
                                "label": {"type": "string", "description": "标注，如 'r=2'"},
                            },
                            "required": ["radius"],
                        },
                    },
                    "show_axes": {
                        "type": "boolean",
                        "description": "plane_geometry 是否显示平面直角坐标系 x/y 轴（纯几何作图填 false，第九章坐标系题填 true）",
                    },
                    "show_north": {
                        "type": "boolean",
                        "description": "方位图填 true，画面上会画出指北针。北是 y 增大，东是 x 增大",
                    },
                    "compass_from": {
                        "type": "string",
                        "description": "方位图的观测点名称，如「大门」。工具会按其余点相对它的坐标算出正北、东北等八个方向",
                    },
                    "highlight": {
                        "type": "object",
                        "description": "可选：高亮数轴上的一段区间",
                        "properties": {
                            "from": {"type": "number"},
                            "to": {"type": "number"},
                        },
                    },
                    "degrees": {"type": "number", "description": "角度值（0 到 180 之间）"},
                    "label": {"type": "string", "description": "角度标注，如 '60°'"},
                    "caption": {"type": "string", "description": "图形下方的简短说明"},
                    "angles": {
                        "type": "array",
                        "description": "平面图上的角。right=true 画直角符号，否则画角弧",
                        "items": {
                            "type": "object",
                            "properties": {
                                "vertex": {"type": "string"},
                                "from": {"type": "string"},
                                "to": {"type": "string"},
                                "right": {"type": "boolean"},
                                "label": {"type": "string"},
                            },
                            "required": ["vertex", "from", "to"],
                        },
                    },
                    "items": {
                        "type": "array",
                        "description": "统计图数据，条形/直方/折线/扇形都用它",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "value": {"type": "number"},
                            },
                            "required": ["label", "value"],
                        },
                    },
                    "title": {"type": "string", "description": "统计图标题"},
                    "front": {
                        "type": "array",
                        "description": "三视图正面。二维数组，第一行是最上面一层，1 是能看见的小正方形，0 是空。列数必须等于 top 的列数",
                    },
                    "left": {
                        "type": "array",
                        "description": "三视图左面。行数必须等于 front 的行数，列数必须等于 top 的行数",
                    },
                    "top": {
                        "type": "array",
                        "description": "三视图上面。只涂真正有积木的格子，空位填 0",
                    },
                    "cells": {"type": "array", "description": "展开图方格，二维数组，1 表示有这个面"},
                    "layers": {
                        "type": "array",
                        "description": "cube_solid 用。从下往上的每一层。每层是二维数组，第 0 行是前面，从左到右是列，1 表示这个位置有一块小立方体",
                    },
                    "cube_count": {
                        "type": "integer",
                        "description": "题目里小立方体的个数，例如 9。必须和 layers 里 1 的个数相同",
                    },
                },
                "required": ["type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_error_item",
            "description": "【错题入库工具】当发现卷面手写错题、红叉，或学生要求放入错题库、或反复追问易错题时调用，将不含手写污染的干净题干和完整解析存入错题库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "教材小节编号，如 '1.1'、'1.2.2'(数轴)、'1.2.5'(比大小)、'2.3.1'(乘方)、'3.2'(代数式求值)、'4.2'(整式加减)、'5.2'(解一元一次方程)、'6.3.3'(余角补角)、'7.2'(平行线)、'8.1'(平方根)、'9.1'(坐标系)、'10.2'(二元一次方程组)、'11.2'(不等式)",
                    },
                    "stem": {"type": "string", "description": "剥离手写答案后的干净原始题干"},
                    "student_wrong": {"type": "string", "description": "学生原本写错的答案或易错点，没有可填 ''"},
                    "correct_answer": {"type": "string", "description": "经工具核对后的标准答案"},
                    "error_reason": {"type": "string", "description": "一句话错因标签，如 '两个负数比大小方向反了'、'乘方负号没在括号里'"},
                    "solution_steps": {"type": "string", "description": "完整的分步解析过程"},
                },
                "required": ["node_id", "stem", "correct_answer", "error_reason", "solution_steps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_knowledge_card",
            "description": "【知识点入库工具】当学生询问数学概念/定理（如无理数、勾股定理、二元一次方程组）或对话中总结重点专题时调用，生成图文思维导图卡片存入知识点库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "知识点标题，如 '勾股定理'、'二元一次方程组的消元法'"},
                    "node_id": {"type": "string", "description": "对应教材小节编号（如 '8.3'、'10.2'，若属八年级拓展如勾股定理可填 'ext'）"},
                    "volume": {"type": "string", "description": "所属册次或分类，如 '七年级上册'、'七年级下册'、'初中拓展专题'"},
                    "tags": {"type": "string", "description": "标签，用逗号分隔，如 '直角三角形,三边关系,面积割补'"},
                    "summary": {"type": "string", "description": "核心概念与公式总结（学生能听懂的语言）"},
                    "mindmap": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "思维导图/流程图节点列表（3~5条关键脉络）",
                    },
                    "example": {"type": "string", "description": "一道典型例题与简明解答"},
                },
                "required": ["title", "summary", "mindmap"],
            },
        },
    },
]

VISION_PROMPT = """你是数学读题员。只输出 JSON，不要计算，不要填空，不要改数字。
一张上有多道题就逐道抄进 items。像「(1)(2)(3)(4)」这种小题各算一道，总标题「比较下列各组数的大小」不要单独成题。填空保留 ____。分数写成 1/4 这种形式，不要用公式。看不清的字写成「看不清」，不要换成别的题。
{
  "items": [
    {"stem": "这一道的原文", "student_work": "", "marked_wrong": false, "figure": null}
  ]
}
student_work 只抄学生自己写的式子或答案，没有就空字符串。
图里如果有数轴，必须把读到的刻度写进 figure，点在半格上就写小数，例如 -3.5。看不清的点不要编。
figure 没有就 null，有就只能是这两种：
{"type":"number_line","min":-5,"max":5,"points":[{"label":"A","value":-3.5}]}
{"type":"angle","degrees":60,"label":"60°"}"""

EXPR_PROMPT = """把下面这道数学题改写成一个可计算的算式。只输出 JSON。
不要自己算出结果。算式使用 + - * / ^ 和括号，绝对值用竖线。
如果题里没有可以计算的算式，expression 用空字符串。
{"expression": ""}
题目：
"""


def _extract_json(text: str) -> dict | None:
    raw = text.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def clean_math_text(text: str) -> str:
    out = text or ""
    out = re.sub(
        r"\\[a-zA-Z]*frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}",
        r"\1/\2",
        out,
    )
    out = (
        out.replace("\\times", "×")
        .replace("\\div", "÷")
        .replace("\\cdot", "×")
        .replace("\\pi", "π")
        .replace("\\le", "≤")
        .replace("\\ge", "≥")
        .replace("\\neq", "≠")
        .replace("\\pm", "±")
        .replace("\\[", "")
        .replace("\\]", "")
        .replace("\\(", "")
        .replace("\\)", "")
        .replace("$$", "")
        .replace("$", "")
    )
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
    out = re.sub(r"^#{1,4}\s*", "", out, flags=re.M)
    return out.strip()


def _should_enforce_math_tool(user_text: str, has_image: bool, draft: str) -> bool:
    combined = f"{user_text}\n{draft}"
    if re.search(r"\d\s*[×÷*/^=<>]\s*[+\-−(]?\d", combined):
        return True
    if re.search(r"[+\-−]?\d+(?:\.\d+)?\s*[><=]\s*[+\-−]?\d+(?:\.\d+)?", combined):
        return True
    if any(k in combined for k in ("面积", "体积", "周长", "比较", "大于", "小于", "乘方", "绝对值", "科学记数法", "方程")):
        if re.search(r"\d", combined):
            return True
    if has_image and re.search(r"(?:结果|答案|等于|面积|所以)\s*[:：是为]?\s*[+\-−]?\d", draft):
        return True
    return False


def format_verification_footer(math_records: list[dict]) -> str:
    verified = [r for r in math_records if isinstance(r, dict) and r.get("ok")]
    if not verified:
        return ""
    lines = ["【工具验算核对】"]
    for item in verified[:10]:
        label = str(item.get("label") or "").strip()
        disp = str(item.get("display") or "").strip()
        if not disp:
            continue
        if label and not label.startswith("步骤") and label not in disp:
            lines.append(f"• {label}：{disp}")
        else:
            lines.append(f"• {disp}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _post_chat_raw(
    messages: list,
    timeout: float,
    tools: list | None = None,
    thinking: bool = False,
    temperature: float = 0.1,
) -> dict | None:
    if not settings.deepseek_api_key:
        return None
    body: dict = {
        "model": settings.deepseek_model,
        "messages": messages,
    }
    if tools:
        body["tools"] = tools
    if thinking:
        body["thinking"] = {"type": "enabled"}
        body["reasoning_effort"] = "low"
    else:
        body["temperature"] = temperature
        body["thinking"] = {"type": "disabled"}

    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.deepseek_api_key}"}
    try:
        with httpx.Client(trust_env=False, timeout=timeout) as http_client:
            response = http_client.post(url, headers=headers, json=body)
            if response.status_code == 400 and thinking:
                body.pop("reasoning_effort", None)
                body["thinking"] = {"type": "disabled"}
                body["temperature"] = temperature
                response = http_client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        detail = ""
        if isinstance(exc, httpx.HTTPStatusError):
            detail = exc.response.text[:300]
        log.warning("deepseek failed: %s %s", type(exc).__name__, detail)
        return None


def _post(messages: list, timeout: float, temperature: float = 0.1) -> str | None:
    message = _post_chat_raw(
        messages,
        timeout=timeout,
        tools=None,
        thinking=False,
        temperature=temperature,
    )
    if not message:
        return None
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or None


def _system_prompt(grade: str | None) -> str:
    profile = grade_profile(grade)
    text = TIR_SYSTEM_PROMPT.replace(
        "你是人教版数学家庭教师。",
        f"你是人教版{profile['label']}数学家庭教师。",
        1,
    )
    old_scope = "做学生当前年级的题目时，严格按照人教版七年级上下册（第1~12章）的方法讲题，不要使用高中或大学的工具。学生点名要听后面年级的内容时，直接把那一句讲完，开头用一句话说明是哪一册才学的，不要改答成当前年级里的别的知识。"
    new_scope = (
        f"做学生当前年级的题目时，用{profile['scope']}的方法。{profile['ceiling']}不要使用高中或大学的工具。"
        "学生点名要听后面年级的内容时，直接把那一句讲完，开头用一句话说明是哪一册才学的，不要改答成当前年级里的别的知识，也不要改成章节目录。"
    )
    return text.replace(old_scope, new_scope, 1)


class VisionClient:
    def enabled(self) -> bool:
        return bool(settings.deepseek_api_key)

    def run_tir(
        self,
        text: str,
        image_b64: str | None = None,
        images_b64: list[str] | None = None,
        history: list[dict] | None = None,
        student_note: str = "",
        grade: str | None = None,
    ) -> dict | None:
        if not self.enabled():
            return None

        all_images: list[str] = []
        if images_b64:
            all_images.extend(img for img in images_b64 if img)
        elif image_b64:
            all_images.append(image_b64)

        system_text = _system_prompt(grade)
        book_ctx = search_curriculum_context(text, grade)
        if book_ctx:
            system_text += "\n\n" + book_ctx
        if student_note:
            system_text += "\n\n" + student_note
        if history:
            hist_lines = []
            for item in history[-6:]:
                role_label = "学生" if item.get("role") == "user" else "老师"
                msg_text = str(item.get("content") or "").strip()
                if msg_text:
                    hist_lines.append(f"{role_label}：{msg_text[:1500]}")
            if hist_lines:
                system_text += (
                    "\n\n【本轮之前的对话记录】照片已标明「刚才这张 / 上一轮 / 上上轮」。"
                    "学生如果说上上轮第3题，要按那个轮次的讲解和这次附上的对应照片来找，不要改答成最新一张。"
                    "学生这一句如果没有再点名一个新概念，就是在问上面对话里刚讲过的内容，直接接着答，不要说对话里没有题目。\n"
                    + "\n".join(hist_lines)
                )

        user_prompt = (text or "").strip()
        if all_images:
            content_parts: list[dict] = []
            for img in all_images[:6]:
                url = img if img.startswith("data:") else f"data:image/jpeg;base64,{img}"
                content_parts.append({"type": "image_url", "image_url": {"url": url, "detail": "original"}})
            if not user_prompt:
                if len(all_images) > 1:
                    user_prompt = (
                        f"我上传了 {len(all_images)} 张图，请结合这些图片把里面的题目讲清楚。"
                        "注意忽略卷面上已手写填入的答案，独立调用 math_steps 核对所有计算；涉及数轴或角度调用 draw_figure 画图。"
                    )
                else:
                    user_prompt = (
                        "请看这张图，把里面的题目按顺序讲清楚。注意：若卷面上有手写填入的答案，请先忽略它、只提取原始题干独立调用 math_steps 工具核对；"
                        "若发现手写答案有误，调用 save_error_item 记入错题库；涉及数轴或角度请调用 draw_figure 画图。"
                    )
            else:
                user_prompt = (
                    f"学生的具体要求：{user_prompt}\n"
                    "（请严格按学生的要求针对性解答图片内容；忽略卷面已填答案干扰，所有计算调用 math_steps 核对。）"
                )
            content_parts.append({"type": "text", "text": user_prompt})
            user_content: list | str = content_parts
        else:
            user_content = user_prompt

        messages: list[dict] = [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_content},
        ]

        math_records: list[dict] = []
        figures: list[dict] = []
        saved_errors: list[dict] = []
        saved_cards: list[dict] = []
        enforced_once = False

        for _round in range(6):
            msg = _post_chat_raw(
                messages,
                timeout=65,
                tools=TIR_TOOLS,
                thinking=True,
            )
            if not msg:
                break

            raw_content = msg.get("content") or ""
            if isinstance(raw_content, list):
                raw_content = "".join(part.get("text", "") for part in raw_content if isinstance(part, dict))
            reasoning_content = msg.get("reasoning_content") or ""
            tool_calls = msg.get("tool_calls") or []

            assistant_entry: dict = {
                "role": "assistant",
                "content": raw_content,
                "reasoning_content": reasoning_content,
            }
            if tool_calls:
                assistant_entry["tool_calls"] = tool_calls
            messages.append(assistant_entry)

            if tool_calls:
                for tc in tool_calls:
                    tc_id = tc.get("id") or "call_0"
                    fn = tc.get("function") or {}
                    fn_name = fn.get("name") or ""
                    args = _extract_json(fn.get("arguments") or "{}") or {}

                    if fn_name == "math_steps":
                        steps_arg = args.get("steps")
                        if not isinstance(steps_arg, list):
                            steps_arg = [args] if args.get("expr") or args.get("compare") or args.get("range") else []
                        results = run_math_steps(steps_arg)
                        math_records.extend(results)
                        tool_out = json.dumps({"results": results}, ensure_ascii=False)
                    elif fn_name == "draw_figure":
                        problem = figure_error(args)
                        clean_fig = None if problem else validate_figure(args)
                        if clean_fig:
                            caption = str(args.get("caption") or "").strip()
                            block = {"type": "figure", "figure": clean_fig}
                            if caption:
                                block["caption"] = caption
                            existing_idx = None
                            for idx_f, b in enumerate(figures, start=1):
                                if b.get("figure") == clean_fig:
                                    existing_idx = idx_f
                                    break
                            if existing_idx is None:
                                figures.append(block)
                                existing_idx = len(figures)
                            placeholder = f"[[FIGURE_{existing_idx}]]"
                            bearings = clean_fig.get("bearings") or []
                            instruction = f"请在对应这道题的讲解段落末尾单独另起一行写上 {placeholder}，系统会自动把这张图插在那个位置。"
                            if bearings:
                                instruction += " 方位必须采用 bearings 里的 direction，不要改成别的方向。"
                            if clean_fig.get("cube_count"):
                                instruction += (
                                    f" 这是按 {clean_fig['cube_count']} 个小立方体投影出来的三视图，"
                                    "讲解里的格子形状以 drawn 的 front、left、top 为准。"
                                )
                            tool_out = json.dumps(
                                {
                                    "ok": True,
                                    "figure_index": existing_idx,
                                    "placeholder": placeholder,
                                    "instruction": instruction,
                                    "bearings": bearings,
                                    "drawn": clean_fig,
                                },
                                ensure_ascii=False,
                            )
                        else:
                            tool_out = json.dumps(
                                {
                                    "ok": False,
                                    "error": problem or "图形参数不合法，请检查 min/max/points 或 degrees",
                                },
                                ensure_ascii=False,
                            )
                    elif fn_name == "save_error_item":
                        stem_val = str(args.get("stem") or "").strip()
                        if stem_val:
                            err_entry = {
                                "node_id": str(args.get("node_id") or "1.1").strip(),
                                "stem": stem_val,
                                "student_wrong": str(args.get("student_wrong") or "").strip(),
                                "correct_answer": str(args.get("correct_answer") or "").strip(),
                                "error_reason": str(args.get("error_reason") or "审题或计算偏差").strip(),
                                "solution_steps": str(args.get("solution_steps") or "").strip(),
                            }
                            saved_errors.append(err_entry)
                            tool_out = json.dumps({"ok": True, "saved_error": err_entry["stem"][:60]}, ensure_ascii=False)
                        else:
                            tool_out = json.dumps({"ok": False, "error": "缺少题干 stem"}, ensure_ascii=False)
                    elif fn_name == "save_knowledge_card":
                        title_val = str(args.get("title") or "").strip()
                        summary_val = str(args.get("summary") or "").strip()
                        if title_val and summary_val:
                            mm_raw = args.get("mindmap")
                            mm_list = [str(x).strip() for x in mm_raw if str(x).strip()] if isinstance(mm_raw, list) else []
                            card_entry = {
                                "title": title_val,
                                "node_id": str(args.get("node_id") or "").strip(),
                                "volume": str(args.get("volume") or "七年级专题").strip(),
                                "tags": str(args.get("tags") or "").strip(),
                                "summary": summary_val,
                                "mindmap": mm_list,
                                "example": str(args.get("example") or "").strip(),
                            }
                            saved_cards.append(card_entry)
                            tool_out = json.dumps({"ok": True, "saved_card": title_val}, ensure_ascii=False)
                        else:
                            tool_out = json.dumps({"ok": False, "error": "缺少 title 或 summary"}, ensure_ascii=False)
                    else:
                        tool_out = json.dumps({"ok": False, "error": f"未知工具 {fn_name}"}, ensure_ascii=False)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": tool_out,
                        }
                    )
                continue

            # Model stopped without tool_calls -> check Hard Rule
            if not math_records and not enforced_once and _should_enforce_math_tool(text, bool(all_images), raw_content):
                enforced_once = True
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "【系统强制校验】你的回答包含了数学计算、代值或比大小结论，但本轮还没有调用 math_steps 工具！"
                            "请立即调用 math_steps 工具核对所有算式与比较，再根据工具返回结果输出讲解。"
                        ),
                    }
                )
                continue

            cleaned = clean_math_text(raw_content)
            if not cleaned and math_records:
                cleaned = format_verification_footer(math_records)
            if not cleaned:
                return None
            return {
                "text": cleaned,
                "verification": format_verification_footer(math_records),
                "figures": figures,
                "math_records": math_records,
                "saved_errors": saved_errors,
                "saved_cards": saved_cards,
            }

        return None

    def parse_image(self, image_b64: str) -> dict | None:
        if image_b64.startswith("data:"):
            url = image_b64
        else:
            url = f"data:image/jpeg;base64,{image_b64}"
        content = _post(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": url, "detail": "original"}},
                        {"type": "text", "text": VISION_PROMPT},
                    ],
                }
            ],
            timeout=50,
        )
        if not content:
            return None
        data = _extract_json(content)
        if data is not None:
            return data
        if re.search(r"\d+[\.、．]", content):
            return {"stem": content, "student_work": "", "marked_wrong": False, "figure": None}
        log.warning("vision text was not a problem: %s", content[:200])
        return None

    def reexplain(self, previous: str, ask: str, verified: str = "", grade: str | None = None) -> str | None:
        """用已经核对过的得数，把同一道题再讲细一点。不重新调用计算工具。"""
        checked = verified.strip() or "讲解里已经写出的得数和式子都不要改。"
        prompt = (
            f"你是{grade_profile(grade)['label']}数学家庭教师。学生希望把一道已经讲过的题再讲一遍，而且要更仔细，像坐在旁边说话。\n"
            "要求：\n"
            "1. 先用一句人话说明这道题在问什么，再一步一步讲为什么要这样算，不要只把式子重抄一遍。\n"
            "2. 比上次更细：每一步都说清这一步在干什么、为什么要这样做。\n"
            "3. 下面已经核对过的得数和式子必须原样沿用，不许另算一套，不许改数字。\n"
            "4. 不要写「工具验算核对」这几个字，核对结果由程序另外附上。\n"
            "5. 不要说「根据上次的回答」。直接重新讲。学生如果点了第几题，就只展开那一题。\n\n"
            f"学生原话：{ask[:300]}\n\n"
            f"已经核对过的结果：\n{checked[:1200]}\n\n"
            f"上次的讲法，仅供你知道讲到了哪，不要照抄：\n{previous[:1800]}"
        )
        content = _post(
            [{"role": "user", "content": prompt}],
            timeout=45,
            temperature=0.4,
        )
        if not content:
            return None
        if "【工具验算核对】" in content:
            content = content.split("【工具验算核对】", 1)[0]
        return content.strip() or None

    def to_expression(self, stem: str) -> str | None:
        content = _post(
            [{"role": "user", "content": EXPR_PROMPT + stem[:1500]}],
            timeout=25,
        )
        if not content:
            return None
        data = _extract_json(content)
        if not data:
            return None
        expr = str(data.get("expression") or "").strip()
        return expr or None
