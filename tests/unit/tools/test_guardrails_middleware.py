"""Unit tests for GuardrailsMiddleware and guardrail compose functions."""
import pytest
from tools.middleware.guardrails import (
    compose_guardrail_message,
    compose_input_guardrail_message,
    compose_output_guardrail_message,
    GUARDRAILS_DEFAULT_CONFIG,
    GUARDRAILS_DEFAULT_CUSTOM_PROMPT,
    GuardrailsMiddleware,
)


class TestComposeInputGuardrailMessage:
    def test_all_input_flags_on(self):
        config = {"input": {"block_malicious_prompts": True, "block_jailbreak": True}, "custom_prompt": ""}
        result = compose_input_guardrail_message(config)
        assert result is not None
        assert "INPUT GUARDRAIL" in result
        assert "[Input]" in result

    def test_no_input_flags_no_prompt_returns_none(self):
        config = {"input": {"block_malicious_prompts": False, "block_jailbreak": False}, "custom_prompt": ""}
        result = compose_input_guardrail_message(config)
        assert result is None

    def test_custom_prompt_included_in_input_message(self):
        config = {"input": {"block_malicious_prompts": False, "block_jailbreak": False}, "custom_prompt": "Only cats."}
        result = compose_input_guardrail_message(config)
        assert result is not None
        assert "Only cats." in result

    def test_missing_flags_default_to_on(self):
        result = compose_input_guardrail_message({})
        assert result is not None
        assert "[Input]" in result

    def test_whitespace_custom_prompt_treated_as_empty(self):
        config = {"input": {"block_malicious_prompts": False, "block_jailbreak": False}, "custom_prompt": "   "}
        result = compose_input_guardrail_message(config)
        assert result is None


class TestComposeOutputGuardrailMessage:
    def test_all_output_flags_on(self):
        config = {"output": {"prevent_pii_leakage": True, "block_toxic_biased": True, "enforce_business_facts": True}}
        result = compose_output_guardrail_message(config)
        assert result is not None
        assert "OUTPUT GUARDRAIL" in result
        assert "[Output]" in result

    def test_no_output_flags_returns_none(self):
        config = {"output": {"prevent_pii_leakage": False, "block_toxic_biased": False, "enforce_business_facts": False}}
        result = compose_output_guardrail_message(config)
        assert result is None

    def test_missing_flags_default_to_on(self):
        result = compose_output_guardrail_message({})
        assert result is not None
        assert "[Output]" in result


class TestComposeGuardrailMessage:
    """Backward-compat combined compose function."""

    def test_all_flags_on_returns_both_sections(self):
        config = {
            "input": {"block_malicious_prompts": True, "block_jailbreak": True},
            "output": {"prevent_pii_leakage": True, "block_toxic_biased": True, "enforce_business_facts": True},
            "custom_prompt": "",
        }
        result = compose_guardrail_message(config)
        assert result is not None
        assert "[Input]" in result
        assert "[Output]" in result

    def test_no_flags_no_prompt_returns_none(self):
        config = {
            "input": {"block_malicious_prompts": False, "block_jailbreak": False},
            "output": {"prevent_pii_leakage": False, "block_toxic_biased": False, "enforce_business_facts": False},
            "custom_prompt": "",
        }
        result = compose_guardrail_message(config)
        assert result is None

    def test_missing_flags_default_to_on(self):
        result = compose_guardrail_message({})
        assert result is not None
        assert "[Input]" in result
        assert "[Output]" in result

    def test_default_config_produces_message(self):
        config = dict(GUARDRAILS_DEFAULT_CONFIG)
        config["custom_prompt"] = GUARDRAILS_DEFAULT_CUSTOM_PROMPT
        assert compose_guardrail_message(config) is not None


class TestGuardrailsMiddlewareBeforeModel:
    def test_no_injection_when_no_input_rules(self):
        config = {
            "input": {"block_malicious_prompts": False, "block_jailbreak": False},
            "output": {"prevent_pii_leakage": True, "block_toxic_biased": True, "enforce_business_facts": True},
            "custom_prompt": "",
        }
        mw = GuardrailsMiddleware(config)
        from langchain.messages import HumanMessage
        state = {"messages": [HumanMessage(content="hello")]}
        result = mw.before_model(state, None)
        assert result is None  # no input rules → before_model is a no-op

    def test_injects_input_system_message_before_human(self):
        config = {
            "input": {"block_malicious_prompts": True, "block_jailbreak": True},
            "output": {"prevent_pii_leakage": True, "block_toxic_biased": True, "enforce_business_facts": True},
            "custom_prompt": "",
        }
        mw = GuardrailsMiddleware(config)
        from langchain.messages import HumanMessage, SystemMessage
        state = {"messages": [HumanMessage(content="hello")]}
        result = mw.before_model(state, None)
        assert result is not None
        msgs = result["messages"]
        sys_idx = next(i for i, m in enumerate(msgs) if isinstance(m, SystemMessage))
        hum_idx = next(i for i, m in enumerate(msgs) if isinstance(m, HumanMessage))
        assert sys_idx < hum_idx
        assert "INPUT GUARDRAIL" in msgs[sys_idx].content

    def test_before_model_does_not_inject_output_rules(self):
        config = {
            "input": {"block_malicious_prompts": True, "block_jailbreak": True},
            "output": {"prevent_pii_leakage": True, "block_toxic_biased": True, "enforce_business_facts": True},
            "custom_prompt": "",
        }
        mw = GuardrailsMiddleware(config)
        from langchain.messages import HumanMessage, SystemMessage
        state = {"messages": [HumanMessage(content="hello")]}
        result = mw.before_model(state, None)
        assert result is not None
        injected = next(m for m in result["messages"] if isinstance(m, SystemMessage))
        assert "[Output]" not in injected.content
        assert "OUTPUT GUARDRAIL" not in injected.content


class TestGuardrailsMiddlewareAfterModel:
    def test_no_injection_when_no_output_rules(self):
        config = {
            "input": {"block_malicious_prompts": True, "block_jailbreak": True},
            "output": {"prevent_pii_leakage": False, "block_toxic_biased": False, "enforce_business_facts": False},
            "custom_prompt": "",
        }
        mw = GuardrailsMiddleware(config)
        from langchain.messages import HumanMessage, AIMessage
        state = {"messages": [HumanMessage(content="hello"), AIMessage(content="hi there")]}
        result = mw.after_model(state, None)
        assert result is None  # no output rules → after_model is a no-op

    def test_injects_output_system_message_after_ai_response(self):
        config = {
            "input": {"block_malicious_prompts": True, "block_jailbreak": True},
            "output": {"prevent_pii_leakage": True, "block_toxic_biased": True, "enforce_business_facts": True},
            "custom_prompt": "",
        }
        mw = GuardrailsMiddleware(config)
        from langchain.messages import HumanMessage, AIMessage, SystemMessage
        state = {"messages": [HumanMessage(content="hello"), AIMessage(content="hi there")]}
        result = mw.after_model(state, None)
        assert result is not None
        msgs = result["messages"]
        last_msg = msgs[-1]
        assert isinstance(last_msg, SystemMessage)
        assert "OUTPUT GUARDRAIL" in last_msg.content
        assert "[Output]" in last_msg.content

    def test_after_model_does_not_inject_input_rules(self):
        config = {
            "input": {"block_malicious_prompts": True, "block_jailbreak": True},
            "output": {"prevent_pii_leakage": True, "block_toxic_biased": True, "enforce_business_facts": True},
            "custom_prompt": "",
        }
        mw = GuardrailsMiddleware(config)
        from langchain.messages import HumanMessage, AIMessage, SystemMessage
        state = {"messages": [HumanMessage(content="hello"), AIMessage(content="hi there")]}
        result = mw.after_model(state, None)
        assert result is not None
        last_msg = result["messages"][-1]
        assert "[Input]" not in last_msg.content
        assert "INPUT GUARDRAIL" not in last_msg.content
