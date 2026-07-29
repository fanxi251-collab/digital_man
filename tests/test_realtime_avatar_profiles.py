from pathlib import Path

from lingjing_ai.config.settings import AppSettings
from lingjing_ai.realtime.avatar_profiles import (
    DEFAULT_AVATAR_ID,
    avatar_ids,
    build_avatar_session_instructions,
    resolve_avatar_profile,
)


def test_realtime_avatar_profiles_are_server_controlled(tmp_path: Path):
    settings = AppSettings.for_workspace(tmp_path)

    assert DEFAULT_AVATAR_ID == "mao_pro"
    assert avatar_ids() == ("mao_pro", "chitose", "haruto")
    assert resolve_avatar_profile(settings, "mao_pro").voice == "longanqian"
    assert resolve_avatar_profile(settings, "chitose").voice == "longanlufeng"
    assert resolve_avatar_profile(settings, "haruto").voice == "longanxiaoxin"
    haruto = resolve_avatar_profile(settings, "haruto")
    instructions = build_avatar_session_instructions(settings, haruto)
    assert haruto.display_name == "Haruto儿童导游"
    assert "稍快但清晰" in haruto.pace_rule
    assert "使用“大家”" in haruto.address_rule
    assert "不得改变路线距离" in instructions
    assert "常规文字模式" in instructions
    assert "完整步骤由路线面板展示" in instructions
    assert "错误提示" in instructions
    assert resolve_avatar_profile(settings, "remote-model") is None
