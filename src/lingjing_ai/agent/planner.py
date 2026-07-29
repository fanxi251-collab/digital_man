from lingjing_ai.agent.models import AgentPlan, AgentStep
from lingjing_ai.config.settings import AppSettings
from lingjing_ai.kg.extractor import classify_kg_scenario
from lingjing_ai.services.tool_intent import classify_fast_tool_intent


class AgentPlanner:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def plan(self, question: str, profile: str = "full") -> AgentPlan:
        # lite：实时路径只要 rag + 必要地图/KG，跳过改写与文档二次检索以降首答延迟。
        lite = str(profile or "full").strip().lower() == "lite"
        steps: list[AgentStep] = []
        if self.settings.agent_use_query_rewrite and not lite:
            steps.append(AgentStep(tool_name="query_rewrite", tool_input=question))
        steps.append(AgentStep(tool_name="rag_search", tool_input=question))
        if classify_kg_scenario(question):
            steps.append(AgentStep(tool_name="kg_search", tool_input=question))
        intent = classify_fast_tool_intent(question) if self.settings.agent_use_map_tools else None
        if intent is not None:
            steps.append(AgentStep(tool_name=intent.tool_name, tool_input=question))
        if self.settings.agent_use_document_search and not lite:
            steps.append(AgentStep(tool_name="document_search", tool_input=question))
        if self.settings.agent_use_web_search and not lite:
            steps.append(AgentStep(tool_name="web_search", tool_input=question))
        return AgentPlan(question=question, steps=steps[: self.settings.agent_max_steps])
