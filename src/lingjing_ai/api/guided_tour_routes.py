from __future__ import annotations

from fastapi import APIRouter

from lingjing_ai.guided_tour.catalog import GuidedTourCatalog


def build_guided_tour_router(catalog: GuidedTourCatalog) -> APIRouter:
    router = APIRouter()

    @router.get("/api/visitor/guided-tour/classic")
    def get_classic_guided_tour() -> dict:
        # A defensive catalog copy keeps one visitor response from mutating the shared demo route.
        return catalog.get_classic_route()

    return router
