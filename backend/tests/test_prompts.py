"""Confere a ligação das constantes de prompt ao agente e às ferramentas."""

from ailo.agent import system_prompt
from ailo.agent.system_prompt import SYSTEM_PROMPT
from ailo.agent.tools import TOOL_DEFINITIONS, TurnState, create_agent_tools
from ailo.sessions import Session


def test_each_registered_tool_uses_its_own_prompt_in_langchain():
    tools = create_agent_tools(Session(id="test-prompt-binding"), TurnState())
    bound_tools = {tool.name: tool for tool in tools}

    for definition in TOOL_DEFINITIONS:
        prompt = getattr(system_prompt, f"{definition.name.upper()}_PROMPT")
        assert definition.description == prompt
        assert bound_tools[definition.name].description == prompt
        assert definition.schema["type"] == "object"
        assert callable(definition.execute)


def test_general_prompt_preserves_dynamic_restriction_catalog():
    assert "doenca_celiaca" in SYSTEM_PROMPT
    assert "alergia_leite" in SYSTEM_PROMPT
    assert "Não apresente modo de preparo" in SYSTEM_PROMPT
