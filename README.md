# Mattin AI - Your AI Toolbox

[![License: AGPL 3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

Mattin AI is a comprehensive AI toolbox that provides a wide range of artificial intelligence capabilities and tools. This project offers various AI functionalities including:

- Large Language Models (LLMs) integration and management
- Retrieval-Augmented Generation (RAG) systems
- Semantic search capabilities
- Vector database management
- AI agents and automation
- And more...

The project aims to simplify the integration and use of AI technologies, providing a unified platform for various AI-powered solutions.

## Features

- **LLM Integration**: Easy access and management of various Large Language Models
- **RAG Systems**: Implementation of Retrieval-Augmented Generation for enhanced AI responses
- **Semantic Search**: Advanced search capabilities using semantic understanding
- **Vector Databases**: Efficient storage and retrieval of vector embeddings
- **AI Agents**: Framework for building and deploying AI agents
- **Modular Architecture**: Easy to extend and customize for specific needs

---

## Quick Start

### Prerequisites

- **For Docker**: Docker 20.10+ and Docker Compose v2+
- **For local development**: Python 3.11+, Node.js 18+, PostgreSQL with pgvector

### 1. Clone the Repository

```bash
git clone https://github.com/lksnext-ai-lab/ai-core-tools.git
cd ai-core-tools
```

---

## Option 1: Docker Compose (Recommended)

The fastest way to get started. Includes all services pre-configured.

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Edit .env with your API keys (see Configuration section)

# 3. Start all services
docker-compose up -d

# 4. Wait ~30 seconds and access:
#    - Frontend: http://localhost:3000
#    - Backend:  http://localhost:8000
#    - API Docs: http://localhost:8000/docs/internal
```

### Docker Commands

```bash
# View logs in real-time
docker-compose logs -f

# View logs for a specific service
docker-compose logs -f backend

# Stop services
docker-compose down

# Rebuild images (after code changes)
docker-compose build --no-cache && docker-compose up -d

# Remove everything (including database data)
docker-compose down -v
```

---

## Option 2: Local Development (Without Docker)

For active development on the source code.

### 1. Database Setup

You need PostgreSQL with the pgvector extension:

```bash
# Option A: Only PostgreSQL with Docker
docker run -d --name mattin-postgres \
  -e POSTGRES_DB=mattin_ai \
  -e POSTGRES_USER=mattin \
  -e POSTGRES_PASSWORD=mattin_secure_2024 \
  -p 5432:5432 \
  pgvector/pgvector:pg17

# Option B: PostgreSQL installed locally
# Make sure to install the pgvector extension
```

### 2. Backend (FastAPI)

```bash
# Create virtual environment
python -m venv venv

# Activate environment (Windows)
.\venv\Scripts\activate

# Activate environment (Linux/Mac)
source venv/bin/activate

# Install Poetry
pip install poetry

# Install dependencies with Poetry (from project root)
poetry install

# Configure environment variables
cp .env.example .env
# Edit .env: change DATABASE_HOST=localhost

# Run migrations
alembic upgrade head

# Start server
uvicorn backend.main:app --reload --port 8000
```

### 3. Frontend (React)

```bash
# In another terminal
cd frontend

# Install dependencies
npm install

# Configure environment variables
cp .env.example .env
```

Edit `frontend/.env` with the following configuration for local development:

```env
# API Configuration
VITE_API_BASE_URL=http://localhost:8000

# Authentication - disable OIDC for local development
VITE_OIDC_ENABLED=false

# IMPORTANT: If using OIDC in local development, change the redirect URI
# Docker uses port 3000, local development uses port 5173
VITE_OIDC_REDIRECT_URI=http://localhost:5173/auth/success
```

> **Note**: When running without Docker, the frontend runs on port 5173 (Vite default), so `VITE_OIDC_REDIRECT_URI` must be updated accordingly if you enable OIDC authentication.

```bash
# Start development server
npm run dev
```

The frontend will be available at http://localhost:5173

---

## Configuration

Edit the `.env` file according to your environment:

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | `sk-proj-xxx...` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-xxx...` |
| `MISTRAL_API_KEY` | Mistral API key | `xxx...` |
| `AICT_OMNIADMINS` | Administrator email(s) | `admin@company.com` |

> You need at least ONE AI API key configured.

### Environment-Specific Variables

| Variable | Docker | Local |
|----------|--------|-------|
| `DATABASE_HOST` | (not needed) | `localhost` |
| `FRONTEND_URL` | `http://localhost:3000` | `http://localhost:5173` |
| `VITE_API_BASE_URL` | `http://localhost:8000` | `http://localhost:8000` |

### AI Service Configuration

The platform supports multiple AI providers:

- OpenAI (GPT models)
- Anthropic (Claude models)
- Azure OpenAI
- Mistral AI
- Ollama (local models)

Configure these through the web interface or environment variables.

---

## Authentication Modes

### Development Mode (AICT_LOGIN=FAKE)

- Simple email login
- Ideal for testing and development
- No additional configuration required
- Email must exist in the database

### Production Mode (AICT_LOGIN=OIDC)

- Authentication with Microsoft Entra ID (Azure AD)
- Requires configuration:

```env
AICT_LOGIN=OIDC
ENTRA_TENANT_ID=your-tenant-id
ENTRA_CLIENT_ID=your-client-id
ENTRA_CLIENT_SECRET=your-client-secret
VITE_OIDC_ENABLED=true
VITE_OIDC_AUTHORITY=https://login.microsoftonline.com/{tenant-id}/v2.0
VITE_OIDC_CLIENT_ID=your-client-id
```

---

## Services and Ports

| Service | Docker | Local |
|---------|--------|-------|
| Frontend | http://localhost:3000 | http://localhost:5173 |
| Backend | http://localhost:8000 | http://localhost:8000 |
| PostgreSQL | localhost:5432 | localhost:5432 |
| API Docs | http://localhost:8000/docs/internal | http://localhost:8000/docs/internal |

---

## Architecture

The project consists of several main components:

- **Backend**: FastAPI-based REST API with Python
- **Frontend**: React-based web interface with TypeScript
- **Database**: PostgreSQL with pgvector for vector storage
- **AI Services**: Modular integration with various LLM providers

---

## Troubleshooting

### Frontend doesn't load

1. Verify the backend is running
2. Check browser console (F12)
3. Ensure `VITE_API_BASE_URL` points to the correct backend

### Database connection error

1. Verify PostgreSQL is running
2. Check credentials in `.env`
3. For Docker, wait ~30 seconds for PostgreSQL to fully start

### API keys don't work

1. Verify the `.env` file is in the project root
2. Restart services after changing `.env`
3. Check that the key has no extra spaces

### Clean and start fresh (Docker)

```bash
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

---

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](docs/README.md#contributing) for details.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Documentation

- [Full Documentation](docs/README.md)
- [API Documentation](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT.md)

## License

This project is available under a dual licensing model:

- **Open Source**: GNU Affero General Public License v3.0 (AGPL 3.0)
- **Commercial**: Proprietary license with enhanced rights and features

### Open Source (AGPL 3.0)
- Free to use for development and personal use
- Community contributions welcome
- Source code disclosure required for network use
- Copyleft obligations for modifications

### Commercial License
- Full AICT functionality without restrictions
- Commercial use rights without copyleft obligations
- Client modification rights for specific projects
- Enterprise features and support
- No source code disclosure requirements

For more information, see:
- [LICENSING.md](LICENSING.md) - Detailed licensing information
- [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md) - Commercial license terms
- [CLIENT_LICENSE_AGREEMENT.md](CLIENT_LICENSE_AGREEMENT.md) - Client agreement template

**Contact LKS Next for commercial licensing inquiries.**

## Support

- Create an issue for bug reports or feature requests
- Check the documentation for common questions
- Join our community discussions

## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Frontend powered by [React](https://reactjs.org/)
- Vector operations with [pgvector](https://github.com/pgvector/pgvector)
- AI integrations via [LangChain](https://langchain.com/)
