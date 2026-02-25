# Contributing to Mattin AI

Thank you for your interest in contributing to Mattin AI! This document provides guidelines and information to make the contribution process smooth for everyone.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Style Guidelines](#code-style-guidelines)
- [Commit Conventions](#commit-conventions)
- [Pull Request Process](#pull-request-process)
- [Licensing of Contributions](#licensing-of-contributions)

## Code of Conduct

This project follows a Code of Conduct to ensure a welcoming and inclusive environment for everyone. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before participating.

## How Can I Contribute?

### Reporting Bugs

If you find a bug, please open a [GitHub Issue](https://github.com/lksnext-ai-lab/ai-core-tools/issues/new) with the following information:

- **Clear title** describing the problem
- **Steps to reproduce** the issue
- **Expected behavior** vs. **actual behavior**
- **Environment details** (OS, Python version, Node.js version, Docker version if applicable)
- **Screenshots or logs** if relevant

Use the `bug` label when creating the issue.

### Suggesting Features

We welcome feature requests! Please open a [GitHub Issue](https://github.com/lksnext-ai-lab/ai-core-tools/issues/new) with:

- **Clear title** describing the feature
- **Use case** — why this feature would be useful
- **Proposed solution** — how you envision it working
- **Alternatives considered** — other approaches you thought of

Use the `enhancement` label when creating the issue.

### Your First Contribution

Look for issues labeled `good-first-issue` or `help-wanted` — these are specifically curated for new contributors.

## Development Setup

### Prerequisites

- **Python** 3.11+
- **Node.js** 18+
- **PostgreSQL** with pgvector extension
- **Docker** 20.10+ and Docker Compose v2+ (for containerized development)
- **Poetry** (Python dependency management)

### Option 1: Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/lksnext-ai-lab/ai-core-tools.git
cd ai-core-tools

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Start all services
docker-compose up -d

# Frontend: http://localhost:3000
# Backend:  http://localhost:8000
# API Docs: http://localhost:8000/docs/internal
```

### Option 2: Local Development

#### Backend

```bash
# Install Python dependencies
poetry install

# Set up PostgreSQL (Docker shortcut)
docker run -d --name mattin-postgres \
  -e POSTGRES_DB=mattin_ai \
  -e POSTGRES_USER=mattin \
  -e POSTGRES_PASSWORD=mattin_secure_2024 \
  -p 5432:5432 \
  pgvector/pgvector:pg17

# Apply database migrations
alembic upgrade head

# Start the backend
uvicorn backend.main:app --reload --port 8000
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
# Dev server at http://localhost:5173
```

## Development Workflow

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/ai-core-tools.git
   cd ai-core-tools
   ```
3. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Make your changes** — keep commits focused and atomic
5. **Test your changes** (see [Testing](#testing) below)
6. **Push** to your fork and **open a Pull Request**

### Testing

#### Backend

```bash
# Run all tests
pytest tests/

# Run a specific test file
pytest tests/test_specific.py

# Run a specific test by name
pytest -k "test_name" -v
```

#### Frontend

```bash
cd frontend
npm run lint
```

### Database Migrations

If your changes modify SQLAlchemy models, you **must** create an Alembic migration:

```bash
# Create a migration
alembic revision --autogenerate -m "Add field_name to model_name"

# Apply it
alembic upgrade head

# Test rollback (required!)
alembic downgrade -1

# Re-apply
alembic upgrade head
```

> Always test both upgrade **and** downgrade before submitting.

## Code Style Guidelines

### Python (Backend)

- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE_CASE` for constants
- **Type hints**: Always use type hints for function signatures
- **Async**: Use `async/await` for I/O-bound and LangChain operations
- **Architecture**: Keep business logic in `services/`, data access in `repositories/`, never in `routers/`
- **Auth**: Use `@require_min_role(AppRole.OWNER)` for role-based access control
- **DB sessions**: Use dependency injection: `db: Session = Depends(get_db)`

```python
# Good
async def get_agent(agent_id: int, db: Session) -> Agent | None:
    pass

# Bad — no type hints, logic in router
@router.get("/agents/{id}")
def get_agent(id):
    result = db.query(Agent).filter_by(id=id).first()
    return result
```

### TypeScript/React (Frontend)

- **Components**: `PascalCase` for component names and files
- **Hooks**: `use` prefix for custom hooks
- **Event handlers**: `handle` prefix (e.g., `handleSubmit`)
- **Styling**: Tailwind CSS utility classes — no inline styles or CSS modules
- **API calls**: Always use the centralized `api.ts` service — never use `fetch()` directly
- **State**: React Context for global state, local hooks for component state

```typescript
// Good
const UserProfile: React.FC<UserProfileProps> = ({ userId }) => {
  const [isLoading, setIsLoading] = useState(false);
  const handleSubmit = () => { /* ... */ };
  return <div className="p-4">{/* JSX */}</div>;
};

// Bad — direct fetch, inline styles
const userProfile = ({ userId }) => {
  fetch(`/api/users/${userId}`);
  return <div style={{ padding: '16px' }}></div>;
};
```

### Things to Avoid

- Direct `fetch()` calls in the frontend — use `api.ts`
- Business logic in routers — use services
- Raw SQL queries — use SQLAlchemy ORM
- Hardcoded secrets — use environment variables
- Modifying the base library for client-specific features — use `clientConfig.ts`

## Commit Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): description
```

### Types

| Type | Use For |
|------|---------|
| `feat` | New features |
| `fix` | Bug fixes |
| `docs` | Documentation changes |
| `style` | Code formatting (no logic changes) |
| `refactor` | Code restructuring (no feature/fix) |
| `test` | Adding or updating tests |
| `chore` | Build, CI, tooling changes |
| `perf` | Performance improvements |

### Examples

```
feat(agents): add memory summarization support
fix(auth): handle session timeout in OIDC flow
docs: update contributing guidelines
refactor(services): extract vector store factory
```

### Commit Signing

All commits **must** be signed with a GPG key:

```bash
# Configure globally
git config --global commit.gpgsign true

# Or sign individually
git commit -S -m "feat(scope): description"
```

Ensure your GPG key is [associated with your GitHub account](https://docs.github.com/en/authentication/managing-commit-signature-verification).

## Pull Request Process

1. **Ensure your branch is up to date** with `main`:
   ```bash
   git pull origin main
   ```
2. **Run tests** and linting before submitting
3. **Fill out the PR description** with:
   - What the PR does and why
   - How it was tested
   - Any breaking changes
   - Related issue numbers (e.g., `Closes #42`)
4. **Request review** from a maintainer
5. **Address feedback** promptly — push additional commits to the same branch
6. A maintainer will merge once approved

### PR Checklist

- [ ] Code follows the project's style guidelines
- [ ] Self-reviewed the changes
- [ ] Added/updated tests if applicable
- [ ] Database migrations tested (upgrade and downgrade) if applicable
- [ ] Documentation updated if applicable
- [ ] No hardcoded secrets or credentials
- [ ] Commit messages follow Conventional Commits format
- [ ] Commits are signed

## Licensing of Contributions

Mattin AI uses a **dual-license model**:

- **AGPL-3.0** for open-source use (see [LICENSE](LICENSE))
- **Commercial License** for proprietary use (see [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md))

By submitting a contribution (pull request, patch, or any other form), you agree that:

1. Your contribution is your original work, or you have the right to submit it
2. You grant the project maintainers (LKS Next) the right to distribute your contribution under both the AGPL-3.0 and the Commercial License
3. You understand that your contribution will be publicly available under the AGPL-3.0 terms

For more details on the licensing model, see [LICENSING.md](LICENSING.md).

> If you have questions about licensing, please open an issue with the `question` label or contact the maintainers before contributing.

## Questions?

- **Bug or feature?** Open a [GitHub Issue](https://github.com/lksnext-ai-lab/ai-core-tools/issues/new)
- **General question?** Use the `question` label on a GitHub Issue
- **Licensing?** See [LICENSING.md](LICENSING.md) or open an issue

Thank you for contributing to Mattin AI!
