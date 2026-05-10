"""
SkillRouterService — isolated Skill pre-selection before main LLM turn.

The preferred route uses a small LLM call with only the latest user request and
Skill catalog metadata. No conversation memory, file contents, system prompt, or
tool outputs are passed into this decision. A keyword scorer remains as a safe
fallback for tests and provider failures.
"""
from __future__ import annotations

from typing import Any
import logging
import json
import inspect

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDict-like dicts
# ---------------------------------------------------------------------------

class SkillRouteDecision(dict):
    """Keys: selected_skill_names (list[str]), reason (str)."""


class SkillCatalogItem(dict):
    """Keys: skill_id (int), name (str), description (str),
    when_to_use (str|None), disable_model_invocation (bool)."""


class SkillToolRouteDecision(dict):
    """Keys: instructions (str), tool_guidance (list[dict])."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SkillRouterService:
    """Metadata-only skill pre-selector.

    Usage::

        router = SkillRouterService()
        decision = router.route(user_messages, catalog)
        selected = set(decision["selected_skill_names"])
    """

    MAX_AUTO_SELECTED: int = 2

    async def route_with_llm(
        self,
        user_messages: list[dict],
        skill_catalog: list[SkillCatalogItem],
        *,
        llm: Any,
    ) -> SkillRouteDecision:
        """Select skills with an isolated LLM call, falling back to keywords.

        The LLM receives only:
        - the latest user message text;
        - skill names/descriptions/when_to_use metadata;
        - the maximum number of allowed selections.

        It does not receive the agent system prompt, conversation history,
        attached file contents, or any tool traces.
        """
        if not skill_catalog:
            return SkillRouteDecision(selected_skill_names=[], reason="no match")

        eligible = [s for s in skill_catalog if not s.get("disable_model_invocation", False)]
        if not eligible:
            return SkillRouteDecision(selected_skill_names=[], reason="no eligible skills")

        last_user_content = _extract_last_user_text(user_messages)
        if not last_user_content:
            return SkillRouteDecision(selected_skill_names=[], reason="no user message")

        if llm is None:
            return self.route(user_messages, skill_catalog)

        try:
            decision = await self._select_skills_with_llm(
                llm=llm,
                user_text=last_user_content,
                eligible=eligible,
            )
            return decision
        except Exception as exc:
            logger.warning(
                "SkillRouterService.route_with_llm failed: %s — falling back to keyword route.",
                exc,
            )
            fallback = self.route(user_messages, skill_catalog)
            if fallback["selected_skill_names"]:
                fallback["reason"] = f"llm error, keyword fallback: {fallback['reason']}"
            return fallback

    def route(
        self,
        user_messages: list[dict],
        skill_catalog: list[SkillCatalogItem],
    ) -> SkillRouteDecision:
        """Select at most MAX_AUTO_SELECTED skills for the current turn.

        Skills with ``disable_model_invocation=True`` are filtered out before
        scoring — they are never shown in the system prompt.

        Returns an empty selection on any error (safe default).
        """
        if not skill_catalog:
            return SkillRouteDecision(selected_skill_names=[], reason="no match")

        eligible = [s for s in skill_catalog if not s.get("disable_model_invocation", False)]
        if not eligible:
            return SkillRouteDecision(selected_skill_names=[], reason="no eligible skills")

        try:
            return self._select_skills(user_messages, eligible)
        except Exception as exc:
            logger.warning(
                "SkillRouterService.route failed: %s — returning empty selection.", exc
            )
            return SkillRouteDecision(
                selected_skill_names=[],
                reason=f"router error: {exc}",
            )

    async def _select_skills_with_llm(
        self,
        *,
        llm: Any,
        user_text: str,
        eligible: list[SkillCatalogItem],
    ) -> SkillRouteDecision:
        catalog = [
            {
                "name": skill.get("name", ""),
                "description": skill.get("description", ""),
                "when_to_use": skill.get("when_to_use") or "",
            }
            for skill in eligible
        ]
        allowed_names = {item["name"] for item in catalog if item["name"]}
        prompt = (
            "Select which Skill tools are relevant for the user's request.\n"
            "You only decide routing; do not solve the task.\n"
            f"Select at most {self.MAX_AUTO_SELECTED} skill names from the catalog.\n"
            "Return strict JSON with this schema:\n"
            '{"selected_skill_names":["skill-name"],"reason":"short reason"}\n'
            "Return an empty list when no Skill is directly useful.\n\n"
            f"User request:\n{user_text}\n\n"
            f"Skill catalog:\n{json.dumps(catalog, ensure_ascii=False)}"
        )

        result = await _invoke_llm_text(llm, prompt)
        parsed = _parse_llm_route_json(result)
        selected = [
            name
            for name in parsed.get("selected_skill_names", [])
            if isinstance(name, str) and name in allowed_names
        ][: self.MAX_AUTO_SELECTED]
        reason = str(parsed.get("reason") or "llm selection")
        return SkillRouteDecision(selected_skill_names=selected, reason=reason)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_skills(
        self,
        user_messages: list[dict],
        eligible: list[SkillCatalogItem],
    ) -> SkillRouteDecision:
        if not user_messages:
            return SkillRouteDecision(selected_skill_names=[], reason="no messages")

        last_user_content = _extract_last_user_text(user_messages)
        if not last_user_content:
            return SkillRouteDecision(selected_skill_names=[], reason="no user message")

        scored: list[tuple[int, str]] = []
        for skill in eligible:
            score = _keyword_score(last_user_content, skill)
            if score > 0:
                scored.append((score, skill["name"]))

        scored.sort(reverse=True)
        selected = [name for _, name in scored[: self.MAX_AUTO_SELECTED]]

        if not selected:
            return SkillRouteDecision(selected_skill_names=[], reason="no match")

        return SkillRouteDecision(
            selected_skill_names=selected,
            reason=f"keyword match: {selected}",
        )


class SkillToolRouterService:
    """Select preferred execution tools for already-selected Skills.

    This second router does not decide whether a Skill is relevant. It receives
    only the selected Skill instruction bodies plus available tool metadata, and
    returns a compact instruction block for the main model.
    """

    async def route_with_llm(
        self,
        *,
        selected_skills: list[dict],
        available_tools: list[dict],
        llm: Any,
    ) -> SkillToolRouteDecision | None:
        if not selected_skills or not available_tools or llm is None:
            return None

        try:
            decision = await self._route_with_llm(
                selected_skills=selected_skills,
                available_tools=available_tools,
                llm=llm,
            )
        except Exception as exc:
            logger.warning(
                "SkillToolRouterService.route_with_llm failed: %s — skipping tool guidance.",
                exc,
            )
            return None

        return decision if decision.get("tool_guidance") else None

    async def _route_with_llm(
        self,
        *,
        selected_skills: list[dict],
        available_tools: list[dict],
        llm: Any,
    ) -> SkillToolRouteDecision:
        tool_names = {
            str(tool.get("name", "")).strip()
            for tool in available_tools
            if tool.get("name")
        }
        skill_names = {
            str(skill.get("name", "")).strip()
            for skill in selected_skills
            if skill.get("name")
        }

        prompt = (
            "You are routing code execution tools for selected agent Skills.\n"
            "Do not solve the user task. Only decide which available tools are "
            "best suited for operations described in each Skill when code must run.\n"
            "Prefer the most direct language REPL for implementation work. Use shell/Bash "
            "mainly for setup, dependency checks, filesystem inspection, or command-line "
            "orchestration.\n"
            "Return strict JSON with this schema:\n"
            "{"
            '"instructions":"short imperative guidance for the main model",'
            '"tool_guidance":[{"skill_name":"skill","operation":"operation",'
            '"preferred_tool":"tool_name","fallback_tools":["tool_name"],'
            '"reason":"short reason"}]'
            "}\n"
            "Only use skill names and tool names from the provided lists.\n\n"
            f"Selected Skills:\n{json.dumps(selected_skills, ensure_ascii=False)}\n\n"
            f"Available tools:\n{json.dumps(available_tools, ensure_ascii=False)}"
        )

        result = await _invoke_llm_text(llm, prompt)
        parsed = _parse_llm_route_json(result)
        guidance = []

        for item in parsed.get("tool_guidance", []):
            if not isinstance(item, dict):
                continue
            skill_name = str(item.get("skill_name", "")).strip()
            preferred_tool = str(item.get("preferred_tool", "")).strip()
            if skill_name not in skill_names or preferred_tool not in tool_names:
                continue
            fallback_tools = [
                str(tool).strip()
                for tool in item.get("fallback_tools", [])
                if str(tool).strip() in tool_names and str(tool).strip() != preferred_tool
            ]
            guidance.append(
                {
                    "skill_name": skill_name,
                    "operation": str(item.get("operation", "")).strip(),
                    "preferred_tool": preferred_tool,
                    "fallback_tools": fallback_tools[:3],
                    "reason": str(item.get("reason", "")).strip(),
                }
            )

        return SkillToolRouteDecision(
            instructions=str(parsed.get("instructions", "")).strip(),
            tool_guidance=guidance,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _extract_last_user_text(messages: list[dict]) -> str:
    """Return the lowercased text of the last user message, or empty string."""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content.lower()
            if isinstance(content, list):
                return " ".join(
                    part.get("text", "")
                    for part in content
                    if part.get("type") == "text"
                ).lower()
    return ""


def _keyword_score(user_text: str, skill: SkillCatalogItem) -> int:
    """Return a simple keyword overlap score between *user_text* and *skill* metadata."""
    target_text = " ".join(
        filter(
            None,
            [
                skill.get("name", ""),
                skill.get("description", ""),
                skill.get("when_to_use") or "",
            ],
        )
    ).lower()

    score = 0
    for word in user_text.split():
        if len(word) > 3 and word in target_text:
            score += 1
    return score


def format_skill_tool_guidance_section(decision: SkillToolRouteDecision | None) -> str | None:
    """Return a system-prompt section from a tool-routing decision."""
    if not decision or not decision.get("tool_guidance"):
        return None

    lines = [
        "<skill_tool_guidance>",
        "When selected Skill instructions require code execution, follow this tool guidance:",
    ]
    instructions = str(decision.get("instructions") or "").strip()
    if instructions:
        lines.append(f"- {instructions}")

    for item in decision["tool_guidance"]:
        operation = item.get("operation") or "code execution"
        preferred = item["preferred_tool"]
        fallbacks = item.get("fallback_tools") or []
        reason = item.get("reason") or ""
        line = (
            f"- Skill `{item['skill_name']}` / {operation}: prefer `{preferred}`"
        )
        if fallbacks:
            line += f"; fallback: {', '.join(f'`{tool}`' for tool in fallbacks)}"
        if reason:
            line += f". Reason: {reason}"
        lines.append(line)

    lines.append(
        "Call `load_skill` before executing code for a Skill. Use repair/setup tools only when the preferred tool cannot perform the step."
    )
    lines.append("</skill_tool_guidance>")
    return "\n".join(lines)


async def _invoke_llm_text(llm: Any, prompt: str) -> str:
    """Invoke a LangChain-style chat/text model and return plain text."""
    ainvoke = getattr(llm, "ainvoke", None)
    if callable(ainvoke):
        response = ainvoke(prompt)
        if inspect.isawaitable(response):
            response = await response
    else:
        response = llm.invoke(prompt)

    content = getattr(response, "content", response)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    parts.append(str(text))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def _parse_llm_route_json(text: str) -> dict:
    """Parse strict or fenced JSON returned by the router model."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(raw[start:end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("Skill router LLM response must be a JSON object")
    names = parsed.get("selected_skill_names", [])
    if not isinstance(names, list):
        parsed["selected_skill_names"] = []
    return parsed
