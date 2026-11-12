"""讲题请求的硬边界。超限直接退回，不送给模型。"""

from __future__ import annotations

import base64
import threading
import time

MAX_TEXT_CHARS = 800
MAX_IMAGES = 3
MAX_IMAGE_BYTES = 1_572_864
MAX_TOTAL_BYTES = 4_194_304
MAX_IMAGE_B64_CHARS = 2_200_000
MAX_TOTAL_B64_CHARS = 6_000_000
MIN_GAP_SECONDS = 10.0

TEXT_TOO_LONG = "一道题请控制在 800 字以内。题干留下即可，讲解可以下一条再问。"
TOO_MANY_IMAGES = "一次最多发 3 张图。请先框出要讲的那几道。"
IMAGE_TOO_BIG = "有一张图太大。请只框一道题再发。"
IMAGES_TOO_BIG = "这几张图加起来太大。请少发几张，或只框一道题。"
IMAGE_UNREADABLE = "有一张图没能读出来。请重新拍或重新选一张。"
STILL_TEACHING = "上一题还在讲。等它讲完再发下一题。"
TOO_SOON = "刚发过一道。等十秒再发下一题。"


def check_chat_input(text: str, images_b64: list[str]) -> str | None:
    if len(text) > MAX_TEXT_CHARS:
        return TEXT_TOO_LONG
    if len(images_b64) > MAX_IMAGES:
        return TOO_MANY_IMAGES
    if sum(len(item) for item in images_b64) > MAX_TOTAL_B64_CHARS:
        return IMAGES_TOO_BIG
    total = 0
    for item in images_b64:
        if len(item) > MAX_IMAGE_B64_CHARS:
            return IMAGE_TOO_BIG
        try:
            raw = base64.b64decode(item, validate=True)
        except Exception:
            return IMAGE_UNREADABLE
        if len(raw) > MAX_IMAGE_BYTES:
            return IMAGE_TOO_BIG
        total += len(raw)
    if total > MAX_TOTAL_BYTES:
        return IMAGES_TOO_BIG
    return None


class SendGate:
    """一个用户同时只讲一道，并且两次发送至少隔 10 秒。"""

    def __init__(self, interval: float = MIN_GAP_SECONDS, clock=None):
        self.interval = interval
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._inflight: set[str] = set()
        self._last_start: dict[str, float] = {}

    def claim(self, device_id: str) -> str | None:
        now = self._clock()
        with self._lock:
            if device_id in self._inflight:
                return STILL_TEACHING
            last = self._last_start.get(device_id)
            if last is not None and now - last < self.interval:
                return TOO_SOON
            self._inflight.add(device_id)
            self._last_start[device_id] = now
        return None

    def release(self, device_id: str) -> None:
        with self._lock:
            self._inflight.discard(device_id)
