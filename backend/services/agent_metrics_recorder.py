"""Write path for agent execution metrics.

Execution services call record_agent_execution() once per agent run; the event
row (and its tool calls) is persisted in a background task on a fresh DB
session. Recording is best-effort: it never raises and never delays or breaks
the agent execution itself.
"""
import asyncio
import uuid
from datetime import datetime
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

# Keep strong references to in-flight writes so they are not garbage-collected
# before they finish (asyncio only keeps weak references to tasks).
_pending_writes: set[asyncio.Task] = set()


def record_agent_execution(*, event_id, fresh_agent, user_context, started_at,
                           finished_at, duration_ms, status, error_code,
                           error_message, result, image_files, message) -> None:
    """Build the metrics payload and persist it in the background. Never raises."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Sync call path with no event loop (e.g. a tool's _run): nothing to schedule on.
        logger.debug("record_agent_execution: no running event loop, metrics dropped")
        return
    try:
        payload = build_metrics_payload(
            event_id=event_id,
            fresh_agent=fresh_agent,
            user_context=user_context,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            status=status,
            error_code=error_code,
            error_message=error_message,
            result=result,
            image_files=image_files,
            message=message,
        )
        task = loop.create_task(persist_metrics_payload(payload))
        _pending_writes.add(task)
        task.add_done_callback(_pending_writes.discard)
    except Exception:
        logger.exception("record_agent_execution failed — metrics dropped, execution unaffected")


def _detect_caller_type(ctx: dict) -> str:
    """Classify the caller from the user_context each entry point builds."""
    if ctx.get('caller_type_override'):
        return ctx['caller_type_override']
    if ctx.get('source') == 'mcp' or ctx.get('mcp_caller', False):
        return "MCP"
    if ctx.get('api_key_id') is not None or ctx.get('api_key') is not None:
        return "PUBLIC_API"
    if ctx.get('parent_execution_id') is not None:
        return "AGENT_AS_TOOL"
    return "INTERNAL_PLAYGROUND"


def _int_or_none(value: Any) -> Optional[int]:
    """Only real integer ids fit the FK columns (e.g. public API user_id is "apikey_<hash>")."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def build_metrics_payload(*, event_id, fresh_agent, user_context, started_at,
                          finished_at, duration_ms, status, error_code,
                          error_message, result, image_files, message) -> dict[str, Any]:
    """Build the {"event": ..., "tool_calls": [...]} payload from the execution context."""
    ctx = user_context or {}
    caller_type = _detect_caller_type(ctx)

    input_tokens = None
    output_tokens = None
    total_tokens = None
    tool_calls_summary = None
    response_chars = None

    if result is not None and isinstance(result, dict):
        messages = result.get("messages") or []
        # The last message with usage_metadata belongs to this turn; earlier
        # ones may be conversation history restored from memory.
        for msg in reversed(messages):
            usage = getattr(msg, 'usage_metadata', None)
            if usage is not None:
                input_tokens = usage.get('input_tokens') or usage.get('prompt_tokens')
                output_tokens = usage.get('output_tokens') or usage.get('completion_tokens')
                total_tokens = usage.get('total_tokens')
                break

        tool_calls_list = []
        for msg in messages:
            tc_list = getattr(msg, 'tool_calls', None)
            if tc_list:
                for tc in tc_list:
                    if len(tool_calls_list) >= 20:
                        break
                    if isinstance(tc, dict):
                        tool_calls_list.append({
                            "tool_name": tc.get("name", ""),
                            "tool_type": "MCP",
                            "status": "SUCCESS",
                        })
        tool_calls_summary = tool_calls_list if tool_calls_list else None

        for msg in reversed(messages):
            content = getattr(msg, 'content', None)
            if content and isinstance(content, str):
                response_chars = len(content)
                break

    event_payload = {
        "event_id": event_id,
        "app_id": getattr(fresh_agent, 'app_id', None),
        "agent_id": getattr(fresh_agent, 'agent_id', None),
        "conversation_id": _int_or_none(ctx.get('conversation_id')),
        "user_id": _int_or_none(ctx.get('user_id')),
        "api_key_id": _int_or_none(ctx.get('api_key_id')),
        "caller_type": caller_type,
        "parent_execution_id": ctx.get('parent_execution_id'),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat() if finished_at else None,
        "duration_ms": duration_ms,
        "status": status,
        "error_code": error_code,
        "error_message": error_message,
        "model_name": getattr(getattr(fresh_agent, 'ai_service', None), 'description', None),
        "ai_service_id": getattr(fresh_agent, 'ai_service_id', None),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "tool_calls": tool_calls_summary,
        "retrieved_docs": None,
        "had_files": len(image_files) > 0,
        "file_count": len(image_files),
        "had_images": len(image_files) > 0,
        "output_parser_used": getattr(fresh_agent, 'output_parser_id', None) is not None,
        "parser_succeeded": None,
        "prompt_chars": len(message) if isinstance(message, str) else None,
        "response_chars": response_chars,
    }

    return {
        "event": event_payload,
        "tool_calls": [],
    }


def _parse_dt(value: Optional[Any]) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


async def persist_metrics_payload(payload: dict[str, Any]) -> None:
    """Persist a metrics payload on its own DB session. Best-effort, never raises."""
    from db.database import SessionLocal
    from models.agent_execution_event import AgentExecutionEvent
    from models.agent_tool_call import AgentToolCall

    db = SessionLocal()
    try:
        event_data = payload['event']
        event = AgentExecutionEvent(
            event_id=uuid.UUID(event_data['event_id']),
            app_id=event_data['app_id'],
            agent_id=event_data['agent_id'],
            conversation_id=event_data.get('conversation_id'),
            user_id=event_data.get('user_id'),
            api_key_id=event_data.get('api_key_id'),
            caller_type=event_data['caller_type'],
            parent_execution_id=(
                uuid.UUID(event_data['parent_execution_id'])
                if event_data.get('parent_execution_id') else None
            ),
            started_at=_parse_dt(event_data['started_at']),
            finished_at=_parse_dt(event_data.get('finished_at')),
            duration_ms=event_data.get('duration_ms'),
            status=event_data['status'],
            error_code=event_data.get('error_code'),
            error_message=event_data.get('error_message'),
            model_name=event_data.get('model_name'),
            ai_service_id=event_data.get('ai_service_id'),
            input_tokens=event_data.get('input_tokens'),
            output_tokens=event_data.get('output_tokens'),
            total_tokens=event_data.get('total_tokens'),
            tool_calls=event_data.get('tool_calls'),
            retrieved_docs=event_data.get('retrieved_docs'),
            had_files=event_data.get('had_files', False),
            file_count=event_data.get('file_count', 0),
            had_images=event_data.get('had_images', False),
            output_parser_used=event_data.get('output_parser_used', False),
            parser_succeeded=event_data.get('parser_succeeded'),
            prompt_chars=event_data.get('prompt_chars'),
            response_chars=event_data.get('response_chars'),
        )
        db.add(event)
        db.flush()

        for tc in payload.get('tool_calls', []):
            db.add(AgentToolCall(
                event_id=event.event_id,
                tool_name=tc['tool_name'],
                tool_type=tc['tool_type'],
                sub_agent_id=tc.get('sub_agent_id'),
                mcp_config_id=tc.get('mcp_config_id'),
                duration_ms=tc.get('duration_ms'),
                status=tc['status'],
                error_message=tc.get('error_message'),
                started_at=_parse_dt(tc['started_at']),
            ))

        db.commit()
    except Exception:
        logger.exception("persist_metrics_payload failed — rolling back")
        db.rollback()
    finally:
        db.close()
