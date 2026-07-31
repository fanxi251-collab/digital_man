from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from lingjing_ai.guided_tour.catalog import GuidedTourCatalog
from lingjing_ai.guided_tour.speech import (
    GuidedTourSpeechService,
    NarrationSpeechError,
    NarrationSpeechUnavailable,
)
from lingjing_ai.services.attraction_store import AttractionStore


def build_guided_tour_speech_router(
    catalog: GuidedTourCatalog,
    attraction_store: AttractionStore,
    speech: GuidedTourSpeechService,
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/visitor/guided-tour/narrations/stops/{stop_id}/synthesize")
    async def synthesize_stop_narration(stop_id: str) -> Response:
        stop = catalog.get_stop(stop_id)
        if stop is None:
            raise HTTPException(status_code=404, detail="讲解点不存在。")
        return await _audio_response(speech, stop["narration_text"])

    @router.post(
        "/api/visitor/guided-tour/narrations/attractions/{attraction_id}/synthesize"
    )
    async def synthesize_attraction_narration(attraction_id: str) -> Response:
        attraction = attraction_store.get_attraction(attraction_id, public_only=True)
        summary = str(getattr(attraction, "summary", "") or "").strip()
        if attraction is None or not summary:
            # Published lookup is required so drafts and private notes never become public speech.
            raise HTTPException(status_code=404, detail="已发布景点讲解不存在。")
        return await _audio_response(speech, summary)

    return router


async def _audio_response(speech: GuidedTourSpeechService, text: str) -> Response:
    try:
        audio = await speech.synthesize(text)
    except NarrationSpeechUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except NarrationSpeechError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )
