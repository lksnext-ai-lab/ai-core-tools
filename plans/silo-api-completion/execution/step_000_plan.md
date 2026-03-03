# Execution Plan: Silo API Completion & Security Hardening

> **Plan ID**: silo-api-completion
> **Created**: 2026-03-03
> **Source**: /plans/silo-api-completion/spec.md

## Scope Summary

This execution implements missing public silo API functionality and closes internal cross-app access validation gaps identified in issue #99. The work adds real behavior to three public endpoints, introduces one missing service method, and applies a reusable ownership validation helper across internal endpoints that currently contain TODO security comments.

The implementation preserves endpoint contracts and existing auth flows while hardening tenant isolation with consistent 403/404 behavior and warning-level security logs for access violations. Changes are intentionally scoped to silo routers and silo service behavior required by the plan.

## Functional Requirements → Agent Mapping

| FR | Description | Agent(s) | Phase |
|----|-------------|----------|-------|
| FR-1 | Implement public docs count endpoint | @backend-expert | Backend |
| FR-2 | Implement public bulk index endpoint | @backend-expert | Backend |
| FR-3 | Add delete-all service + public endpoint wiring | @backend-expert | Backend |
| FR-4 | Add reusable silo ownership validator helper | @backend-expert | Backend |
| FR-5 | Apply ownership validation to all internal silo endpoints | @backend-expert | Backend |
| FR-6 | Remove silo router TODO comments | @backend-expert | Backend |

## Execution Phases

1. **Setup**: Create feature branch `feat/silo-api-completion` from `develop`
2. **Service & Public Router Completion**: FR-1, FR-2, FR-3
3. **Internal Router Security Hardening**: FR-4, FR-5, FR-6
4. **Documentation Review**: Validate whether docs updates are required
5. **Finalize**: PR creation

## Known Risks & Blockers

- `list_silos` app-level validation approach has design ambiguity in decisions notes; execution will follow spec and keep behavior compatible with existing role decorator.
- Vector store backends must already support full-collection delete through current abstraction; if not, step will document and adapt through existing interfaces.
