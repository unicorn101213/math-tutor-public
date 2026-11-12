"""给熟人发登录验证码或兑换码。在服务器的 backend 目录运行。

登录码：python issue_code.py 13800138000
月卡：python issue_code.py --redeem 100
小包：python issue_code.py --redeem 30
"""

import sys
from pathlib import Path

from accounts import ensure_schema, issue_login_code, issue_redeem, normalize_phone
from config import DATA_DIR
from store import Store


def main() -> None:
    store = Store(DATA_DIR / "tutor.db")
    ensure_schema(store)
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--redeem":
        credits = int(args[1])
        if credits < 1:
            raise SystemExit("次数要大于 0")
        print(issue_redeem(store, credits))
        return
    if len(args) == 1:
        phone = normalize_phone(args[0])
        if phone is None:
            raise SystemExit("手机号要是 11 位")
        print(issue_login_code(store, phone))
        return
    raise SystemExit("用法：python issue_code.py 手机号    或    python issue_code.py --redeem 100")


if __name__ == "__main__":
    main()
