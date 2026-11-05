"""Print the <active_chat_filters> block an agent would get for a given selection.

Reads a real agent from the configured database and renders exactly what
``create_agent`` would append to its system prompt — no LLM call, no vector store,
no LangSmith. Use it to check the wiring (Gate 1 whitelisting + block rendering)
against your own agents before testing in the Playground.

Usage, from the repo root:

    poetry run python scripts/inspect_chat_filter_block.py --simulate 2
    poetry run python scripts/inspect_chat_filter_block.py --list
    poetry run python scripts/inspect_chat_filter_block.py --agent-id 42
    poetry run python scripts/inspect_chat_filter_block.py --agent-id 42 \
        --filter source_type=SAT --filter machine_model=X100

With no --filter, it uses the agent's exposed_chat_filters with placeholder values,
which is enough to confirm the block renders and the routing text appears.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from tools.chat_filter_scope import build_chat_filter_prompt_block  # noqa: E402


def _parse_filters(pairs):
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--filter expects field=value, got: {pair!r}")
        field, _, value = pair.partition("=")
        out[field.strip()] = value.strip()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--agent-id", type=int, help="Agent to inspect")
    ap.add_argument("--filter", action="append", help="field=value (repeatable)")
    ap.add_argument("--list", action="store_true", help="List agents that expose filters")
    ap.add_argument(
        "--simulate",
        type=int,
        metavar="N_SUBAGENTS",
        help="Render the block for a fake agent with N sub-agents — no database needed",
    )
    args = ap.parse_args()

    if args.simulate is not None:
        from types import SimpleNamespace

        selected = _parse_filters(args.filter) or {"source_type": "SAT"}
        fake = SimpleNamespace(tool_associations=[object()] * args.simulate)
        print(f"Simulated agent with {args.simulate} sub-agent tool(s)")
        print(f"Selection: {selected}")
        print("\n" + "=" * 70)
        print(build_chat_filter_prompt_block(fake, selected) or "(no block)")
        print("=" * 70)
        return

    from db.database import SessionLocal  # noqa: PLC0415
    from models.agent import Agent  # noqa: PLC0415

    with SessionLocal() as db:
        if args.list or not args.agent_id:
            agents = db.query(Agent).all()
            print(f"{'id':>6}  {'subagents':>9}  {'exposed_chat_filters'}")
            print("-" * 70)
            for a in agents:
                exposed = getattr(a, "exposed_chat_filters", None) or []
                n_subs = len(getattr(a, "tool_associations", None) or [])
                if exposed or n_subs:
                    print(f"{a.agent_id:>6}  {n_subs:>9}  {a.name} -> {exposed}")
            if not args.agent_id:
                return

        agent = db.query(Agent).filter(Agent.agent_id == args.agent_id).first()
        if agent is None:
            raise SystemExit(f"Agent {args.agent_id} not found")

        exposed = list(getattr(agent, "exposed_chat_filters", None) or [])
        subs = [assoc.tool.name for assoc in (agent.tool_associations or []) if assoc.tool]

        print(f"\nAgent {agent.agent_id}: {agent.name}")
        print(f"  exposed_chat_filters : {exposed or '(none — no block will ever render)'}")
        print(f"  sub-agent tools      : {subs or '(none — routing text is omitted)'}")

        selected = _parse_filters(args.filter) or {f: f"<{f}-value>" for f in exposed}
        print(f"  simulated selection  : {selected or '(nothing selected)'}")

        # Gate 1: exactly the whitelisting create_agent applies before building the block.
        whitelisted = {k: v for k, v in selected.items() if k in set(exposed)}
        dropped = sorted(set(selected) - set(whitelisted))
        if dropped:
            print(f"  dropped by Gate 1    : {dropped}")

        block = build_chat_filter_prompt_block(agent, whitelisted)

        print("\n" + "=" * 70)
        print(block if block else "(no block — nothing would be appended to the system prompt)")
        print("=" * 70)


if __name__ == "__main__":
    main()
