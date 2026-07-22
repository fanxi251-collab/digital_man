import asyncio
from pathlib import Path
import re

import httpx
import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.api.app import create_app
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.rag.embeddings import HashingEmbeddingProvider
from lingjing_ai.rag.generator import ExtractiveAnswerGenerator
from lingjing_ai.rag.pipeline import RagPipeline
from lingjing_ai.storage.vector_store import JsonVectorStore


def build_pipeline(tmp_path: Path) -> RagPipeline:
    settings = AppSettings.for_workspace(tmp_path)
    return RagPipeline(
        settings=settings,
        embedding_provider=HashingEmbeddingProvider(dimensions=64),
        vector_store=JsonVectorStore(tmp_path / "vectors.json"),
        answer_generator=ExtractiveAnswerGenerator(),
    )


def request_path(app, path: str) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    return asyncio.run(send())


def test_admin_documents_page_and_assets_are_served(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    page = request_path(app, "/admin/documents")
    script = request_path(app, "/static/admin_documents.js")

    assert page.status_code == 200
    assert "知识库资料管理" in page.text
    assert 'id="documentPreviewPanel" hidden' in page.text
    assert "/static/admin_documents.js" in page.text
    assert script.status_code == 200
    assert 'fetch("/api/admin/documents"' in script.text
    assert 'fetch(`/api/admin/documents/${documentId}/content`' in script.text
    assert 'fetch(`/api/admin/documents/${documentId}/reindex`' in script.text
    assert 'fetch(`/api/admin/documents/${documentId}`' in script.text
    assert "documentPreviewPanel.hidden = false" in script.text
    assert "documentPreviewPanel.hidden = true" in script.text
    assert "confirm(" in script.text


def test_admin_attractions_page_and_crud_assets_are_served(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    page = request_path(app, "/admin/attractions")
    script = request_path(app, "/static/admin_attractions.js")

    assert page.status_code == 200
    assert "景点资料管理" in page.text
    assert "/admin/documents" in page.text
    assert "/static/admin_attractions.js" in page.text
    assert script.status_code == 200
    assert 'fetch("/api/admin/attractions"' in script.text
    assert 'fetch(`/api/admin/attractions/${attractionId}/images?' in script.text
    assert 'fetch("/api/tools/map/search?' in script.text
    assert "景点已归档" in script.text


def test_all_admin_pages_share_sidebar_navigation(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    for path in (
        "/admin/analytics",
        "/admin/attractions",
        "/admin/documents",
        "/admin/foods",
        "/admin/feedback",
    ):
        page = request_path(app, path)

        assert page.status_code == 200
        assert "灵境智导" in page.text
        assert "LingJing AI" not in page.text
        assert "LingJing AI Admin" not in page.text
        assert 'class="admin-sidebar"' in page.text
        assert 'href="/admin/analytics"' in page.text
        assert 'href="/admin/attractions"' in page.text
        assert 'href="/admin/documents"' in page.text
        assert 'href="/admin/foods"' in page.text
        assert 'href="/admin/feedback"' in page.text
        assert f'class="admin-nav-item active" href="{path}"' in page.text
        assert page.text.count('class="admin-nav-item') == 5
        assert page.text.count('class="admin-nav-item active"') == 1
        assert "<<<<<<<" not in page.text
        assert "=======" not in page.text
        assert ">>>>>>>" not in page.text
        assert "/static/admin.css" in page.text


def test_admin_pages_disable_html_caching(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    for path in (
        "/admin/analytics",
        "/admin/attractions",
        "/admin/documents",
        "/admin/foods",
        "/admin/feedback",
    ):
        page = request_path(app, path)

        assert page.status_code == 200
        assert page.headers["cache-control"] == "no-store"


def test_admin_sidebar_prevents_navigation_items_from_crossing_its_boundary(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))
    styles = request_path(app, "/static/admin.css")

    assert styles.status_code == 200
    assert re.search(r"\.admin-sidebar\s*\{[^}]*min-width:\s*0;[^}]*overflow:\s*hidden;", styles.text, re.S)
    assert re.search(r"\.admin-sidebar-nav\s*\{[^}]*width:\s*100%;[^}]*min-width:\s*0;", styles.text, re.S)
    assert re.search(r"\.admin-nav-item\s*\{[^}]*width:\s*100%;[^}]*max-width:\s*100%;", styles.text, re.S)


def test_admin_foods_page_exposes_crud_location_and_image_workflow(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_foods=False)

    page = request_path(app, "/admin/foods")
    script = request_path(app, "/static/admin_foods.js")

    assert page.status_code == 200
    assert "美食推荐管理" in page.text
    assert "/static/admin_foods.js" in page.text
    assert script.status_code == 200
    assert 'fetch("/api/admin/foods"' in script.text
    assert 'fetch(`/api/admin/foods/${foodId}/images?' in script.text
    assert 'fetch("/api/tools/map/search?' in script.text
    assert "美食内容已归档" in script.text


def test_admin_feedback_page_exposes_filters_reply_and_no_delete_action(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path), seed_foods=False)

    page = request_path(app, "/admin/feedback")
    script = request_path(app, "/static/admin_feedback.js")

    assert page.status_code == 200
    assert "游客反馈处理" in page.text
    assert "/static/admin_feedback.js" in page.text
    assert script.status_code == 200
    assert 'fetch("/api/admin/feedback"' in script.text
    assert 'fetch(`/api/admin/feedback/${selected.feedback_id}`' in script.text
    assert 'method: "PATCH"' in script.text
    assert 'method: "DELETE"' not in script.text


def test_admin_analytics_page_and_local_chart_assets_are_served(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))

    page = request_path(app, "/admin/analytics")
    script = request_path(app, "/static/admin_analytics.js")
    charts = request_path(app, "/static/vendor/echarts.min.js")

    assert page.status_code == 200
    assert "游客数据分析" in page.text
    assert "为产品组合与服务优化提供依据" in page.text
    assert "四象限图中的气泡大小表示访问量" in page.text
    assert "帮助运营人员快速识别重点机会" in page.text
    assert "帮助判断分析结果的完整性与可靠程度" in page.text
    assert "/static/vendor/echarts.min.js" in page.text
    assert "/static/admin_analytics.js" in page.text
    assert script.status_code == 200
    assert 'fetch("/api/admin/analytics/dashboard")' in script.text
    assert "response.status === 503" in script.text
    assert "retryButton" in script.text
    assert "window.echarts" in script.text
    assert charts.status_code == 200


def test_admin_analytics_reveals_dashboard_before_initializing_charts(tmp_path: Path):
    app = create_app(build_pipeline(tmp_path))
    script = request_path(app, "/static/admin_analytics.js")

    success_sequence = "dashboard = data;\n    showDashboard();\n    renderDashboard(data);"
    normalized_script = script.text.replace("\r\n", "\n")
    assert success_sequence in normalized_script
