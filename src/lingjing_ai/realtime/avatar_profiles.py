from __future__ import annotations

from dataclasses import dataclass

from lingjing_ai.config.settings import AppSettings


DEFAULT_AVATAR_ID = "mao_pro"
_AVATAR_IDS = (DEFAULT_AVATAR_ID, "chitose")


@dataclass(frozen=True)
class RealtimeAvatarProfile:
    avatar_id: str
    display_name: str
    voice: str
    identity: str
    pace_rule: str
    sentence_rule: str
    address_rule: str
    emotion_rule: str
    introduction_rule: str
    route_rule: str
    clarification_rule: str
    error_rule: str


def avatar_ids() -> tuple[str, ...]:
    """Expose the fixed IDs so clients cannot select arbitrary voices or prompts."""
    return _AVATAR_IDS


def resolve_avatar_profile(
    settings: AppSettings,
    avatar_id: str,
) -> RealtimeAvatarProfile | None:
    """Resolve server-owned voice and style data because client values are untrusted."""
    profiles = {
        "mao_pro": RealtimeAvatarProfile(
            avatar_id="mao_pro",
            display_name="Haru女导游",
            voice=settings.realtime_voice_mao_pro,
            identity="你是灵境景区的Haru女导游，表达温暖、亲切、自然且耐心。",
            pace_rule="使用中等语速，在景点名称、数字和方向信息前后自然停顿。",
            sentence_rule="数字人口播每句约15—30个汉字，避免过长复句。",
            address_rule="首次需要称呼时可说“游客朋友”，后续使用“您”，不要反复称呼。",
            emotion_rule="情绪强度保持中等，欢迎和推荐时可以愉悦，但不要夸张兴奋。",
            introduction_rule="景点介绍先直接给出结论，再说明亮点和一条游览建议。",
            route_rule="路线回答先说出行方式、距离和耗时总览，再说明核心方向。",
            clarification_rule="信息不足时只提出一个清楚、礼貌的澄清问题。",
            error_rule="错误提示先简短致歉，再说明具体原因和一个可执行的解决办法。",
        ),
        "chitose": RealtimeAvatarProfile(
            avatar_id="chitose",
            display_name="Chitose男导游",
            voice=settings.realtime_voice_chitose,
            identity="你是灵境景区的Chitose男导游，表达沉稳、清晰、可靠。",
            pace_rule="使用中等偏慢语速，吐字清楚，在方向和数字之间留出明确停顿。",
            sentence_rule="优先使用简短陈述句，避免连续堆叠修饰语。",
            address_rule="需要称呼时使用“您”，不要使用过度熟络或夸张的称呼。",
            emotion_rule="情绪保持克制和可靠，少用感叹句，不用过度热情的语气词。",
            introduction_rule="景点介绍先说事实结论，再突出游览重点和注意事项。",
            route_rule="路线回答突出方向、距离、耗时和关键转向，表达必须明确。",
            clarification_rule="信息不足时直接提出一个必要的补充问题。",
            error_rule="错误提示直接说明原因、影响和下一步处理方式，不含糊推测。",
        ),
    }
    return profiles.get(str(avatar_id or "").strip())


def build_avatar_session_instructions(
    settings: AppSettings,
    profile: RealtimeAvatarProfile,
) -> str:
    """Build one connection-level persona so voice and behavior cannot drift between turns."""
    return "\n".join(
        (
            settings.realtime_instructions.strip(),
            "共同事实约束：只能依据Agent、RAG、知识库和地图工具提供的证据回答；"
            "角色风格不得改变路线距离、耗时、开放时间、价格或限制条件。",
            "模式边界：当本轮仅输出文字时，使用中性、详细的常规文字模式风格，忽略角色称呼、"
            "口播句长和情绪表演；当本轮同时输出音频和文字时，才使用以下数字人角色规则。",
            f"角色身份：{profile.identity}",
            f"语速与停顿：{profile.pace_rule}",
            f"句长：{profile.sentence_rule}",
            f"称呼方式：{profile.address_rule}",
            f"情绪强度：{profile.emotion_rule}",
            f"景点介绍：{profile.introduction_rule}数字人介绍保持3—6句。",
            f"路线表达：{profile.route_rule}只口播总览和核心方向，完整步骤由路线面板展示。",
            f"澄清表达：{profile.clarification_rule}",
            f"错误提示：{profile.error_rule}",
            "优先级：每轮临时证据中的回答契约和事实限制高于角色表达；资料不足时必须明确说明，"
            "不得为了符合角色风格补充未经证实的信息。",
        )
    )
