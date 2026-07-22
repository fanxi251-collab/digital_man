import pytest

pytestmark = pytest.mark.usefixtures("postgres_test_context")

from lingjing_ai.services.conversation_store import ConversationStore


def test_conversation_store_creates_session_and_reads_recent_messages(pg_dsn: str, conversations_schema: str):
    store = ConversationStore(pg_dsn, schema=conversations_schema)

    session = store.create_session("visitor_a", "灵山胜境有什么特色？")
    store.append_message(session.session_id, "visitor_a", "user", "灵山胜境有什么特色？")
    store.append_message(session.session_id, "visitor_a", "assistant", "灵山胜境以灵山大佛闻名。")

    sessions = store.list_sessions("visitor_a")
    messages = store.recent_messages(session.session_id, "visitor_a", limit=12)

    assert sessions[0].session_id == session.session_id
    assert sessions[0].title == "灵山胜境有什么特色？"
    assert sessions[0].recent_question == "灵山胜境有什么特色？"
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[1].content == "灵山胜境以灵山大佛闻名。"


def test_conversation_store_isolates_visitors_and_deletes_single_session(pg_dsn: str, conversations_schema: str):
    store = ConversationStore(pg_dsn, schema=conversations_schema)
    visitor_a_session = store.create_session("visitor_a", "灵山胜境")
    visitor_b_session = store.create_session("visitor_b", "拈花湾")
    store.append_message(visitor_a_session.session_id, "visitor_a", "user", "灵山胜境怎么玩？")
    store.append_message(visitor_b_session.session_id, "visitor_b", "user", "拈花湾怎么玩？")

    assert store.get_session(visitor_a_session.session_id, "visitor_b") is None
    assert store.recent_messages(visitor_a_session.session_id, "visitor_b") == []
    assert store.delete_session(visitor_a_session.session_id, "visitor_b") is False

    assert store.delete_session(visitor_a_session.session_id, "visitor_a") is True

    assert store.get_session(visitor_a_session.session_id, "visitor_a") is None
    assert store.recent_messages(visitor_a_session.session_id, "visitor_a") == []
    assert store.get_session(visitor_b_session.session_id, "visitor_b") is not None
