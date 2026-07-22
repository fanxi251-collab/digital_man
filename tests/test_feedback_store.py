import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.services.feedback_store import FeedbackStore


def test_feedback_store_is_idempotent_and_isolates_visitors(pg_dsn: str, feedback_schema: str):
    store = FeedbackStore(pg_dsn, schema=feedback_schema)
    payload = {
        "visitor_id": "visitor_alpha",
        "request_id": "request_1",
        "rating": 5,
        "category": "guide",
        "content": "数字人讲解自然，路线建议也很清楚。",
        "contact": "visitor@example.com",
    }

    first = store.create_feedback(payload)
    repeated = store.create_feedback(payload)
    store.create_feedback({**payload, "visitor_id": "visitor_beta", "request_id": "request_2"})

    assert repeated.feedback_id == first.feedback_id
    assert [item.feedback_id for item in store.list_for_visitor("visitor_alpha")] == [first.feedback_id]
    assert store.list_for_visitor("visitor_unknown") == []


def test_feedback_store_filters_and_updates_processing_reply(pg_dsn: str, feedback_schema: str):
    store = FeedbackStore(pg_dsn, schema=feedback_schema)
    created = store.create_feedback(
        {
            "visitor_id": "visitor_alpha",
            "request_id": "request_1",
            "rating": 3,
            "category": "facility",
            "content": "部分路口的指引牌可以再醒目一些。",
            "contact": "13800000000",
        }
    )

    updated = store.update_feedback(created.feedback_id, status="processing", admin_reply="已安排现场核查。")
    filtered = store.list_feedback(status="processing", category="facility", rating=3, q="指引牌")

    assert updated is not None
    assert updated.status == "processing"
    assert updated.admin_reply == "已安排现场核查。"
    assert [item.feedback_id for item in filtered] == [created.feedback_id]
    assert filtered[0].contact == "13800000000"
