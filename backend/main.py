import asyncio
import json
import logging

from fastapi import FastAPI, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from admin_page import router as admin_router
from accounts import (
    consumes_turn,
    hold_credit,
    is_legacy,
    issue_login_code,
    normalize_phone,
    redeem,
    refund_credit,
    user_by_token,
    verify_login,
)
from config import DATA_DIR, settings
from limits import SendGate, check_chat_input
from llm import VisionClient
from store import Store
from tutor import build_error_catalog, build_knowledge_catalog, deliver_due, handle

log = logging.getLogger("tutor")

app = FastAPI(title="数学家教")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
store = Store(DATA_DIR / "tutor.db")
client = VisionClient()
send_gate = SendGate()
_inflight: set[asyncio.Future] = set()


def _note_unfinished(device_id: str) -> None:
    try:
        hist = store.get_device_history(device_id, limit=1, include_images=False)
        messages = hist["messages"]
        if not messages or messages[-1]["role"] != "user":
            return
        text = "这道题这次没讲完。再发一次就好。"
        store.add_message(
            messages[-1]["session_id"],
            "assistant",
            text,
            blocks=[{"type": "text", "text": text}],
        )
    except Exception:
        log.exception("unfinished note failed")


class ChatIn(BaseModel):
    device_id: str = Field(min_length=4, max_length=80)
    session_id: str | None = None
    text: str = ""
    image_base64: str | None = None
    images_base64: list[str] | None = None
    grade_id: str = "j1"


class ClearIn(BaseModel):
    device_id: str = Field(min_length=4, max_length=80)


@app.get("/health")
def health():
    return {"ok": True, "vision": client.enabled(), "port": settings.port}


@app.get("/history")
def get_history(
    device_id: str = Query(default="default-device", min_length=4, max_length=80),
    after_id: int = Query(default=0, ge=0),
    lite: int = Query(default=0),
):
    return store.get_device_history(
        device_id,
        limit=40,
        after_id=after_id,
        include_images=not lite,
    )


@app.post("/history/clear")
def clear_history(body: ClearIn):
    deleted = store.clear_device_history(body.device_id)
    return {"ok": True, "deleted": deleted}


@app.get("/knowledge")
def get_knowledge(
    device_id: str = Query(default="default-device", min_length=4, max_length=80),
    q: str = Query(default=""),
    grade_id: str = Query(default="j1"),
):
    return build_knowledge_catalog(store, device_id, query=q, grade=grade_id)


@app.get("/errors")
def get_errors(
    device_id: str = Query(default="default-device", min_length=4, max_length=80),
    chapter_id: str = Query(default=""),
    grade_id: str = Query(default="j1"),
):
    return build_error_catalog(store, device_id, chapter_id=chapter_id, grade=grade_id)


class ErrorDeleteIn(BaseModel):
    device_id: str = Field(min_length=4, max_length=80)
    error_id: int = Field(ge=1)


@app.post("/errors/delete")
def delete_error(body: ErrorDeleteIn):
    return {"ok": store.delete_error(body.device_id, body.error_id)}


class TaskIn(BaseModel):
    device_id: str = Field(min_length=4, max_length=80)
    session_id: str | None = None


@app.post("/tasks/pull")
def pull_tasks(body: TaskIn):
    session_id = body.session_id
    if not session_id:
        session_id = store.get_device_history(body.device_id, limit=1)["session_id"]
    if not session_id:
        return {"session_id": None, "blocks": []}
    session_id = store.ensure_session(body.device_id, session_id)
    blocks = deliver_due(store, body.device_id, session_id, save=True)
    return {"session_id": session_id, "blocks": blocks}


async def stream_with_heartbeat(job: asyncio.Future, interval: float = 8.0):
    """讲题时每隔几秒先吐一个换行，避免手机网络把没动静的连接掐掉。

    JSON 允许前面有空白，现有 App 整段读完再解析，不用改安装包。
    """
    while not job.done():
        yield b"\n"
        try:
            await asyncio.wait_for(asyncio.shield(job), timeout=interval)
        except asyncio.TimeoutError:
            continue
    try:
        result = job.result()
    except Exception:
        log.exception("chat failed")
        result = {
            "session_id": "",
            "blocks": [{"type": "text", "text": "这道题这次没讲完。再发一次就好。"}],
        }
    if not isinstance(result, dict):
        result = {
            "session_id": "",
            "blocks": [{"type": "text", "text": "这道题这次没讲完。再发一次就好。"}],
        }
    yield json.dumps(result, ensure_ascii=False).encode("utf-8")


def _refuse(body: ChatIn, text: str):
    return {
        "session_id": body.session_id or "",
        "blocks": [{"type": "text", "text": text}],
    }


class PhoneIn(BaseModel):
    phone: str
    device_id: str = Field(min_length=4, max_length=80)


class VerifyIn(PhoneIn):
    code: str = Field(min_length=4, max_length=8)


class RedeemIn(BaseModel):
    device_id: str = Field(min_length=4, max_length=80)
    code: str = Field(min_length=4, max_length=32)


def _bearer(authorization: str | None) -> str:
    if not authorization:
        return ""
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return authorization.strip()


@app.get("/auth/status")
def auth_status(
    device_id: str = Query(min_length=4, max_length=80),
    authorization: str | None = Header(default=None),
):
    legacy = is_legacy(store, device_id)
    user = user_by_token(store, _bearer(authorization))
    if legacy and user is None:
        return {"login_required": False, "unlimited": True, "credits": None, "phone": ""}
    if user is None:
        return {"login_required": True, "unlimited": False, "credits": 0, "phone": ""}
    return {
        "login_required": False,
        "unlimited": False,
        "credits": user["credits"],
        "phone": user["phone"],
    }


@app.post("/auth/sms")
def auth_sms(body: PhoneIn):
    phone = normalize_phone(body.phone)
    if phone is None:
        return {"ok": False, "message": "请填写 11 位手机号。"}
    code = issue_login_code(store, phone, replace=False)
    if not code:
        return {"ok": True, "message": "验证码还是刚才那一组，10 分钟内有效。请向给你安装包的人要。"}
    return {"ok": True, "message": "验证码已经记好了。请向给你安装包的人要这 6 位数字，10 分钟内有效。"}


@app.post("/auth/verify")
def auth_verify(body: VerifyIn):
    phone = normalize_phone(body.phone)
    if phone is None:
        return {"ok": False, "message": "请填写 11 位手机号。"}
    result = verify_login(store, phone, body.code, body.device_id)
    if result is None:
        return {"ok": False, "message": "验证码不对或已经过期。请再要一次。"}
    return {"ok": True, **result}


@app.post("/auth/redeem")
def auth_redeem(body: RedeemIn, authorization: str | None = Header(default=None)):
    result = redeem(store, _bearer(authorization), body.code)
    if result is None:
        return {"ok": False, "message": "兑换码无效，或还没有登录。"}
    return {"ok": True, **result}


@app.post("/chat")
async def chat(body: ChatIn, authorization: str | None = Header(default=None)):
    text = body.text.strip()
    imgs: list[str] = []
    if body.images_base64:
        imgs = [x for x in body.images_base64 if x]
    elif body.image_base64:
        imgs = [body.image_base64]

    rejected = check_chat_input(text, imgs)
    if rejected:
        return _refuse(body, rejected)

    user = user_by_token(store, _bearer(authorization))
    charge = False
    if user is None:
        if not is_legacy(store, body.device_id):
            return _refuse(body, "请先用手机号登录。新装的应用要向给你安装包的人要验证码。")
    elif consumes_turn(text, len(imgs)):
        blocked = hold_credit(store, user["id"])
        if blocked:
            return _refuse(body, blocked)
        charge = True

    busy = send_gate.claim(body.device_id)
    if busy:
        if charge and user is not None:
            refund_credit(store, user["id"])
        return _refuse(body, busy)

    def _run():
        try:
            result = handle(
                store,
                body.device_id,
                text,
                body.session_id,
                imgs[0] if len(imgs) == 1 else None,
                client,
                imgs if imgs else None,
                body.grade_id,
            )
            if charge and user is not None and isinstance(result, dict):
                blocks = result.get("blocks") or []
                if blocks and "没讲完" in str(blocks[0].get("text", "")):
                    refund_credit(store, user["id"])
            return result
        except Exception:
            if charge and user is not None:
                refund_credit(store, user["id"])
            _note_unfinished(body.device_id)
            raise
        finally:
            send_gate.release(body.device_id)

    job = asyncio.get_running_loop().run_in_executor(None, _run)
    _inflight.add(job)
    job.add_done_callback(_inflight.discard)
    return StreamingResponse(
        stream_with_heartbeat(job),
        media_type="application/json",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
