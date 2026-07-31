from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import re
from xml.sax.saxutils import escape

import httpx


XIAOXIAO_VOICE = "zh-CN-XiaoxiaoNeural"
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
REGION_PATTERN = re.compile(r"^[a-z0-9-]{2,40}$")
SpeechRequester = Callable[..., Awaitable[httpx.Response]]


class NarrationSpeechUnavailable(RuntimeError):
    """Raised when the optional online narration service is not configured."""


class NarrationSpeechError(RuntimeError):
    """Raised with a sanitized message when Azure cannot return playable audio."""


class GuidedTourSpeechService:
    def __init__(
        self,
        *,
        enabled: bool,
        subscription_key: str,
        region: str,
        requester: SpeechRequester | None = None,
        timeout_seconds: float = 8,
    ) -> None:
        self.enabled = bool(enabled)
        self.subscription_key = str(subscription_key or "").strip()
        self.region = str(region or "").strip().lower()
        self.requester = requester or _request_speech
        self.timeout_seconds = max(1.0, min(10.0, float(timeout_seconds)))

    async def synthesize(self, text: str) -> bytes:
        narration = str(text or "").strip()
        if not self.enabled or not self.subscription_key or not self.region:
            raise NarrationSpeechUnavailable("在线晓晓语音未配置。")
        if not REGION_PATTERN.fullmatch(self.region):
            # Region validation prevents configuration text from changing the upstream host.
            raise NarrationSpeechUnavailable("在线晓晓语音区域配置无效。")
        if not narration:
            raise NarrationSpeechError("讲解内容为空，无法合成语音。")

        endpoint = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        headers = {
            "Ocp-Apim-Subscription-Key": self.subscription_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
            "User-Agent": "lingjing-guided-tour",
        }
        content = _xiaoxiao_ssml(narration).encode("utf-8")
        for attempt in range(2):
            try:
                response = await self.requester(
                    endpoint,
                    headers=headers,
                    content=content,
                    timeout=self.timeout_seconds,
                )
            except (httpx.HTTPError, asyncio.TimeoutError) as error:
                if attempt == 0:
                    continue
                raise NarrationSpeechError("在线语音连接失败，请使用文字讲解。") from error
            content_type = str(response.headers.get("content-type", "")).lower()
            if response.status_code == 200 and content_type.startswith("audio/") and response.content:
                return bytes(response.content)
            if response.status_code >= 500 and attempt == 0:
                continue
            break
        # Never include the upstream body because it can echo credentials or provider internals.
        raise NarrationSpeechError("在线语音暂时不可用，请使用文字讲解。")


async def _request_speech(url: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient() as client:
        return await client.post(url, **kwargs)


def _xiaoxiao_ssml(text: str) -> str:
    safe_text = escape(text)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="zh-CN">'
        f'<voice name="{XIAOXIAO_VOICE}">'
        '<mstts:express-as style="gentle" styledegree="1.05">'
        f'<prosody rate="-4%">{safe_text}</prosody>'
        "</mstts:express-as></voice></speak>"
    )
