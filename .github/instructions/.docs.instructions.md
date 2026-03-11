---
description: Conventions and rules for documentation files in the docs/ directory
applyTo: "docs/**"
---

# Documentation Conventions

## File Naming
- Use `kebab-case.md` for all documentation files (e.g., `dev-guide.md`, `getting-started.md`)
- Use lowercase directory names (e.g., `docs/guides/`, `docs/api/`)

## Document Structure
Every documentation page should follow this structure:

1. **Title** — A single `# Heading` at the top
2. **Navigation Breadcrumb** (optional) — Link back to index: `> Part of [Mattin AI Documentation](../index.md)`
3. **Overview** — 1-3 sentences explaining what this page covers
4. **Content Sections** — Use `##` for major sections, `###` for subsections
5. **Examples** — Include code examples with language-tagged fenced code blocks
6. **See Also** (optional) — Links to related documentation pages

## Markdown Standards
- Use ATX-style headings (`#`, `##`, `###`) — not underline style
- Always specify language in fenced code blocks: ` ```python `, ` ```bash `, ` ```typescript `
- Use relative links for internal references: `[Dev Guide](dev-guide.md)`, not absolute paths
- One blank line before and after headings, code blocks, and lists
- Use `>` blockquotes for important notes or callouts
- Prefer tables for structured data over nested lists

## Metadata Tracking
- `docs/.doc-metadata.yaml` tracks the git commit baseline for documentation freshness
- This file is managed by the `@docs-manager` agent — do not edit manually
- Every documentation update should be accompanied by a baseline advancement in this file

## Index Management
- `docs/index.md` is the authoritative Table of Contents
- Every documentation page MUST be linked from the index
- Orphan pages (not in index) should be either linked or deleted
- The index should show the last-synced commit date at the top

## Content Guidelines
- Write for developers — assume technical familiarity but not project-specific knowledge
- Keep pages focused — one topic per page
- Use concrete examples from the actual codebase, not hypothetical ones
- Do not duplicate content from `CLAUDE.md` or root `README.md` — link to them instead
- Document what EXISTS, not what is planned
