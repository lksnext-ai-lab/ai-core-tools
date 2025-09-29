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

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Node.js 18 or higher
- PostgreSQL with pgvector extension
- Docker and Docker Compose (optional)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/ia-core-tools.git
   cd ia-core-tools
   ```

2. **Set up the backend**:
   ```bash
   cd backend
   cp env.example .env
   # Edit .env with your configuration
   pip install -r requirements.txt
   ```

3. **Set up the frontend**:
   ```bash
   cd frontend
   npm install
   ```

4. **Set up the database**:
   ```bash
   # Using Docker Compose (recommended)
   docker-compose up -d postgres
   
   # Or install PostgreSQL with pgvector manually
   ```

5. **Run the application**:
   ```bash
   # Backend
   cd backend
   python main.py
   
   # Frontend (in another terminal)
   cd frontend
   npm run dev
   ```

### Using Docker Compose

The easiest way to get started:

```bash
# Copy environment file
cp backend/env.example .env
# Edit .env with your configuration

# Start all services
docker-compose up -d
```

## Configuration

### Environment Variables

Key environment variables you need to configure:

- `DATABASE_*`: PostgreSQL database configuration
- `OPENAI_API_KEY`: Your OpenAI API key
- `ANTHROPIC_API_KEY`: Your Anthropic API key
- `SECRET_KEY`: Secret key for session management
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: Google OAuth credentials

See `backend/env.example` for a complete list of configuration options.

### AI Service Configuration

The platform supports multiple AI providers:

- OpenAI (GPT models)
- Anthropic (Claude models)
- Azure OpenAI
- Mistral AI
- Ollama (local models)

Configure these through the web interface or environment variables.

## Architecture

The project consists of several main components:

- **Backend**: FastAPI-based REST API with Python
- **Frontend**: React-based web interface with TypeScript
- **Database**: PostgreSQL with pgvector for vector storage
- **AI Services**: Modular integration with various LLM providers

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