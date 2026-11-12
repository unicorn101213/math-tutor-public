"""给安装包的人用的网页：发登录验证码和兑换码。口令只放在服务器的环境变量里。"""

from __future__ import annotations

import hashlib
import secrets
import time

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from accounts import CODE_MINUTES, admin_desk, issue_login_code, issue_redeem, normalize_phone
from config import settings

router = APIRouter()
COOKIE = "tutor_admin"
_sessions: set[str] = set()
_fails: dict[str, list[float]] = {}


def _same(left: str, right: str) -> bool:
    return secrets.compare_digest(
        hashlib.sha256(left.encode()).digest(),
        hashlib.sha256(right.encode()).digest(),
    )


def _locked(ip: str) -> bool:
    now = time.time()
    hits = [item for item in _fails.get(ip, []) if now - item < 600]
    _fails[ip] = hits
    return len(hits) >= 8


def _store():
    from main import store

    return store


def _authed(request: Request) -> bool:
    token = request.cookies.get(COOKIE, "")
    return bool(token) and token in _sessions


def _deny():
    return JSONResponse({"ok": False, "message": "请先填写管理员口令。"}, status_code=401)


@router.get("/admin", response_class=HTMLResponse)
def admin_page():
    return HTMLResponse(PAGE, headers={"Cache-Control": "no-store"})


@router.post("/admin/login")
def admin_login(body: dict, request: Request):
    password = str(body.get("password") or "")
    expected = settings.admin_password
    ip = request.client.host if request.client else ""
    if not expected or _locked(ip) or not _same(password, expected):
        _fails.setdefault(ip, []).append(time.time())
        return JSONResponse({"ok": False, "message": "口令不对。"}, status_code=401)
    token = secrets.token_urlsafe(24)
    _sessions.add(token)
    response = JSONResponse({"ok": True})
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", max_age=12 * 3600, path="/")
    return response


@router.post("/admin/logout")
def admin_logout(request: Request):
    token = request.cookies.get(COOKIE, "")
    _sessions.discard(token)
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/admin/state")
def admin_state(request: Request):
    if not _authed(request):
        return _deny()
    return admin_desk(_store())


@router.post("/admin/login-code")
def admin_login_code(body: dict, request: Request):
    if not _authed(request):
        return _deny()
    phone = normalize_phone(str(body.get("phone") or ""))
    if phone is None:
        return {"ok": False, "message": "请填写 11 位手机号。"}
    code = issue_login_code(_store(), phone)
    return {"ok": True, "phone": phone, "code": code, "minutes": CODE_MINUTES}


@router.post("/admin/redeem-code")
def admin_redeem_code(body: dict, request: Request):
    if not _authed(request):
        return _deny()
    try:
        credits = int(body.get("credits") or 0)
    except (TypeError, ValueError):
        credits = 0
    if credits < 1 or credits > 500:
        return {"ok": False, "message": "次数要在 1 到 500 之间。"}
    code = issue_redeem(_store(), credits)
    return {"ok": True, "code": code, "credits": credits}


PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>验证码</title>
<style>
:root {
  --primary: #5645d4;
  --primary-pressed: #4534b3;
  --on-primary: #ffffff;
  --canvas: #ffffff;
  --surface: #f6f5f4;
  --ink: #1a1a1a;
  --charcoal: #37352f;
  --slate: #5d5b54;
  --hairline: #e5e3df;
  --hairline-strong: #c8c4be;
  --lavender: #e6e0f5;
  --success: #1aae39;
  --error: #e03131;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--surface);
  color: var(--ink);
  font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 16px;
  line-height: 1.55;
}
main { max-width: 720px; margin: 0 auto; padding: 32px 16px 48px; }
h1 { font-size: 28px; line-height: 1.25; font-weight: 600; margin: 0 0 8px; }
h2 { font-size: 18px; line-height: 1.4; font-weight: 600; margin: 0 0 12px; }
p { margin: 0; color: var(--slate); font-size: 14px; }
.card {
  background: var(--canvas);
  border: 1px solid var(--hairline);
  border-radius: 12px;
  padding: 20px;
  margin-top: 16px;
}
label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 8px; }
input {
  width: 100%;
  border: 1px solid var(--hairline-strong);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 16px;
  color: var(--ink);
  background: var(--canvas);
}
.row { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
button {
  border: 0;
  border-radius: 8px;
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.3;
  cursor: pointer;
  background: var(--primary);
  color: var(--on-primary);
}
button:active { background: var(--primary-pressed); }
button.ghost {
  background: transparent;
  color: var(--ink);
  border: 1px solid var(--hairline-strong);
}
button:disabled { background: var(--hairline); color: #bbb8b1; cursor: default; }
.flash {
  margin-top: 16px;
  background: var(--lavender);
  border-radius: 12px;
  padding: 16px;
}
.flash b {
  display: block;
  margin-top: 4px;
  font-size: 36px;
  line-height: 1.2;
  letter-spacing: 2px;
  color: var(--primary);
  font-weight: 600;
}
.err { color: var(--error); font-size: 14px; margin-top: 8px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { text-align: left; padding: 8px 4px; border-bottom: 1px solid var(--hairline); }
th { color: var(--slate); font-size: 13px; font-weight: 600; }
code { font-size: 14px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
</style>
</head>
<body>
<main>
  <section id="gate" class="card" hidden>
    <h1>验证码</h1>
    <p>填写管理员口令后，可以为手机号生成 6 位登录码，也可以生成兑换码。</p>
    <div style="margin-top:16px">
      <label for="password">管理员口令</label>
      <input id="password" type="password" autocomplete="current-password">
    </div>
    <div class="row"><button id="enter" type="button">进入</button></div>
    <div id="gate-err" class="err"></div>
  </section>
  <section id="desk" hidden>
    <div class="head">
      <div>
        <h1>验证码</h1>
        <p>登录码 10 分钟内有效。对方第一次登录送 5 次。兑换码在对话页的票券里填写，用过一次就作废。</p>
      </div>
      <button id="leave" class="ghost" type="button">退出</button>
    </div>
    <section class="card">
      <h2>发登录验证码</h2>
      <label for="phone">手机号</label>
      <input id="phone" inputmode="numeric" maxlength="11" placeholder="11 位手机号">
      <div class="row"><button id="make-code" type="button">生成验证码</button></div>
      <div id="code-box"></div>
    </section>
    <section class="card">
      <h2>发兑换码</h2>
      <label for="credits">次数</label>
      <input id="credits" inputmode="numeric" value="100">
      <div class="row">
        <button id="pack-30" class="ghost" type="button">30 次</button>
        <button id="pack-100" class="ghost" type="button">100 次</button>
        <button id="make-card" type="button">生成兑换码</button>
      </div>
      <div id="card-box"></div>
    </section>
    <section class="card">
      <h2>还没使用的兑换码</h2>
      <div id="redeem-list"></div>
    </section>
    <section class="card">
      <h2>已注册</h2>
      <div id="user-list"></div>
    </section>
  </section>
</main>
<script>
const root = location.pathname.replace(/\/+$/, "");
const gate = document.getElementById("gate");
const desk = document.getElementById("desk");
function show(id, html) { document.getElementById(id).innerHTML = html; }
async function call(path, body) {
  const response = await fetch(root + path, {
    method: body ? "POST" : "GET",
    headers: body ? {"Content-Type": "application/json"} : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) { gate.hidden = false; desk.hidden = true; }
  return { ok: response.ok, data };
}
function flash(id, label, value, note) {
  show(id, '<div class="flash"><span>' + label + '</span><b>' + value + '</b><p>' + note + '</p></div>');
}
async function refresh() {
  const { ok, data } = await call("/state");
  if (!ok) return;
  gate.hidden = true;
  desk.hidden = false;
  const users = data.users || [];
  const redeems = data.redeems || [];
  show("user-list", users.length ? '<table><tr><th>手机号</th><th>剩余</th><th>今日</th><th>注册</th></tr>' +
    users.map(u => '<tr><td>' + u.phone + '</td><td>' + u.credits + '</td><td>' + u.day_used + '</td><td>' + u.created_at + '</td></tr>').join("") +
    '</table>' : '<p>还没有人注册。</p>');
  show("redeem-list", redeems.length ? '<table><tr><th>兑换码</th><th>次数</th><th>生成时间</th></tr>' +
    redeems.map(r => '<tr><td><code>' + r.code + '</code></td><td>' + r.credits + '</td><td>' + r.created_at + '</td></tr>').join("") +
    '</table>' : '<p>没有待使用的兑换码。</p>');
}
document.getElementById("enter").onclick = async () => {
  const { ok, data } = await call("/login", { password: document.getElementById("password").value });
  document.getElementById("gate-err").textContent = ok ? "" : (data.message || "口令不对。");
  if (ok) refresh();
};
document.getElementById("leave").onclick = async () => { await call("/logout", {}); location.reload(); };
document.getElementById("make-code").onclick = async () => {
  const { ok, data } = await call("/login-code", { phone: document.getElementById("phone").value });
  if (!ok) { show("code-box", '<div class="err">' + (data.message || "没生成。") + '</div>'); return; }
  flash("code-box", data.phone, data.code, "把这 6 位告诉对方，" + data.minutes + " 分钟内有效。");
};
document.getElementById("pack-30").onclick = () => { document.getElementById("credits").value = "30"; };
document.getElementById("pack-100").onclick = () => { document.getElementById("credits").value = "100"; };
document.getElementById("make-card").onclick = async () => {
  const { ok, data } = await call("/redeem-code", { credits: document.getElementById("credits").value });
  if (!ok) { show("card-box", '<div class="err">' + (data.message || "没生成。") + '</div>'); return; }
  flash("card-box", data.credits + " 次", data.code, "把这组码告诉对方。对方登录后在对话页兑换。");
  refresh();
};
document.getElementById("password").addEventListener("keydown", (event) => {
  if (event.key === "Enter") document.getElementById("enter").click();
});
refresh();
</script>
</body>
</html>
"""
