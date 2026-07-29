from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, WebSocket

from lingjing_ai.config.settings import AppSettings
from lingjing_ai.realtime.avatar_profiles import DEFAULT_AVATAR_ID, resolve_avatar_profile
from lingjing_ai.realtime.conversation import RealtimeConversationService
from lingjing_ai.realtime.qwen_audio import QwenAudioRealtimeClient
from lingjing_ai.realtime.session import VisitorRealtimeSession


RealtimeClientFactory = Callable[[AppSettings], QwenAudioRealtimeClient]


def build_realtime_router(
    settings: AppSettings,
    conversation_service: RealtimeConversationService,
    client_factory: RealtimeClientFactory | None = None,
) -> APIRouter:
    router = APIRouter()
    create_client = client_factory or QwenAudioRealtimeClient

    @router.websocket("/api/visitor/realtime")
    async def visitor_realtime(
        websocket: WebSocket,
        visitor_id: str = "",
        session_id: str = "",
        avatar_id: str = DEFAULT_AVATAR_ID,
    ) -> None:
        await websocket.accept()
        normalized_visitor = visitor_id.strip()
        normalized_session = session_id.strip()
        if not normalized_visitor:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "VISITOR_REQUIRED",
                    "message": "visitor_id 不能为空。",
                    "recoverable": False,
                }
            )
            await websocket.close(code=1008)
            return
        normalized_avatar = str(avatar_id or DEFAULT_AVATAR_ID).strip()
        if resolve_avatar_profile(settings, normalized_avatar) is None:
            await websocket.send_json(
                {
                    "type": "error",
                    "code": "INVALID_AVATAR",
                    "message": "不支持的数字人角色。",
                    "recoverable": False,
                }
            )
            await websocket.close(code=1008)
            return
        if normalized_session:
            try:
                conversation_service.upstream_history(normalized_session, normalized_visitor)
            except PermissionError as exc:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "SESSION_FORBIDDEN",
                        "message": str(exc),
                        "recoverable": False,
                    }
                )
                await websocket.close(code=1008)
                return

        realtime_session = VisitorRealtimeSession(
            browser=websocket,
            visitor_id=normalized_visitor,
            session_id=normalized_session,
            settings=settings,
            conversation_service=conversation_service,
            qwen_client=create_client(settings),
            qwen_client_factory=lambda: create_client(settings),
            avatar_id=normalized_avatar,
        )
        await realtime_session.open()
        await realtime_session.run()

    return router
