# Deployment Guide

> Part of [Mattin AI Documentation](../README.md)

## Overview

Mattin AI can be deployed using:
- **Docker Compose** (recommended for development/small deployments)
- **Kubernetes** (recommended for production/scalable deployments)
- **Manual deployment** (advanced users)

## Docker Compose

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum
- 20GB disk space

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/lksnext-ai-lab/ai-core-tools.git
cd ai-core-tools

# 2. Copy environment file
cp .env.docker.example .env

# 3. Edit .env with your API keys
nano .env

# 4. Start services
docker-compose up -d

# 5. Access services
# Backend:  http://localhost:8000
# Frontend: http://localhost:3000
# Database: localhost:5432
```

### docker-compose.yaml

Main docker-compose file for local development:

**Services**:
- **postgres**: PostgreSQL 17 with pgvector extension
- **backend**: FastAPI application (Python 3.11)
- **frontend**: React application (Node 20, Nginx)

**Key features**:
- Health checks for all services
- Volume persistence for database
- Auto-restart policies
- Custom network for service communication

**Ports**:
- Backend: `8000:8000`
- Frontend: `3000:80`
- PostgreSQL: `5432:5432`

### docker-compose-qdrant.yaml

Optional Qdrant vector database service:

```bash
docker-compose -f docker-compose-qdrant.yaml up -d
```

**Adds**:
- **qdrant**: Qdrant vector database

**Ports**:
- Qdrant REST API: `6333:6333`
- Qdrant gRPC: `6334:6334`

**Usage**: Set `VECTOR_DB_TYPE=QDRANT` in `.env`

### docker-compose-dockerhub.yaml

Pre-built images from Docker Hub (faster startup):

```bash
docker-compose -f docker-compose-dockerhub.yaml up -d
```

**Image**: `aritzglks/lks-next-ia-core-tools:latest`

**Use case**: Quick deployments without local builds

## Building Images

### Backend Dockerfile

Located at `backend/Dockerfile`:

**Multi-stage build**:

```dockerfile
# Stage 1: Builder (install dependencies)
FROM python:3.11-slim AS builder
- Install Poetry
- Install dependencies (production only)

# Stage 2: Production
FROM python:3.11-slim
- Copy dependencies from builder
- Copy application code
- Run gunicorn server
```

**Build command**:

```bash
docker build -t mattin-backend:latest -f backend/Dockerfile .
```

**Features**:
- Poetry for dependency management
- Multi-stage for smaller image size
- Gunicorn WSGI server (8 workers)
- Health check endpoint (`/health`)

### Frontend Dockerfile

Located at `frontend/Dockerfile`:

**Multi-stage build**:

```dockerfile
# Stage 1: Builder (build React app)
FROM node:20-alpine AS builder
- Install dependencies (npm)
- Build production bundle (Vite)

# Stage 2: Production
FROM nginx:alpine
- Copy build from builder to nginx
- Configure nginx for SPA routing
```

**Build command**:

```bash
docker build -t mattin-frontend:latest -f frontend/Dockerfile .
```

**Features**:
- Node 20 for build
- Vite for bundling
- Nginx for serving static files
- SPA fallback routing

## Kubernetes

### Prerequisites

- Kubernetes 1.24+
- kubectl configured
- Helm 3.0+ (optional, for easier management)
- Persistent volume provisioner

### Architecture

```
┌─────────────────────────────────────────┐
│           Ingress Controller            │
│  (nginx-ingress / Traefik / ALB)        │
└─────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼──────┐      ┌─────────▼──────┐
│   Frontend   │      │     Backend    │
│  Deployment  │      │   Deployment   │
│  (3 replicas)│      │  (5 replicas)  │
└──────────────┘      └────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
          ┌─────────▼────┐    ┌─────────▼──────┐
          │  PostgreSQL  │    │     Qdrant     │
          │  StatefulSet │    │  StatefulSet   │
          │  (persistent)│    │  (persistent)  │
          └──────────────┘    └────────────────┘
```

### ConfigMap

Store configuration:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mattin-config
data:
  AICT_LOGIN: "OIDC"
  VECTOR_DB_TYPE: "PGVECTOR"
  FRONTEND_URL: "https://mattin.your-domain.com"
```

### Secrets

Store sensitive data:

```bash
kubectl create secret generic mattin-secrets \
  --from-literal=DATABASE_PASSWORD=strong_password \
  --from-literal=SECRET_KEY=your-secret-key \
  --from-literal=OPENAI_API_KEY=sk-... \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-...
```

### Backend Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mattin-backend
spec:
  replicas: 5
  selector:
    matchLabels:
      app: mattin-backend
  template:
    metadata:
      labels:
        app: mattin-backend
    spec:
      containers:
      - name: backend
        image: mattin-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: SQLALCHEMY_DATABASE_URI
          value: "postgresql://mattin:password@postgres:5432/mattin_ai"
        - name: SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: mattin-secrets
              key: SECRET_KEY
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

### Frontend Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mattin-frontend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mattin-frontend
  template:
    metadata:
      labels:
        app: mattin-frontend
    spec:
      containers:
      - name: frontend
        image: mattin-frontend:latest
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

### PostgreSQL StatefulSet

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: pgvector/pgvector:pg17
        ports:
        - containerPort: 5432
        env:
        - name: POSTGRES_DB
          value: "mattin_ai"
        - name: POSTGRES_USER
          value: "mattin"
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: mattin-secrets
              key: DATABASE_PASSWORD
        volumeMounts:
        - name: postgres-data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: postgres-data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      resources:
        requests:
          storage: 50Gi
```

### Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: mattin-ingress
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
  - hosts:
    - mattin.your-domain.com
    - api.mattin.your-domain.com
    secretName: mattin-tls
  rules:
  - host: mattin.your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: mattin-frontend
            port:
              number: 80
  - host: api.mattin.your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: mattin-backend
            port:
              number: 8000
```

### Persistent Storage

**PostgreSQL**:
- StorageClass: SSD-backed (for performance)
- Size: 50GB minimum (100GB+ for production)
- Backup: Daily snapshots recommended

**File repositories**:
- StorageClass: Standard (cost-effective)
- Size: 100GB+ (depends on usage)
- Mount to backend pods at `/data/repositories`

## Environment Setup

### Backend .env

```bash
# Database
SQLALCHEMY_DATABASE_URI=postgresql://mattin:password@postgres:5432/mattin_ai

# Authentication
AICT_LOGIN=OIDC
SECRET_KEY=production-secret-key-256-bit
AICT_OMNIADMINS=admin@company.com

# Entra ID
ENTRA_TENANT_ID=your-tenant-id
ENTRA_CLIENT_ID=your-client-id
ENTRA_CLIENT_SECRET=your-client-secret

# LLM API Keys
OPENAI_API_KEY=sk-proj-...
ANTHROPIC_API_KEY=sk-ant-...

# Frontend URL
FRONTEND_URL=https://mattin.your-domain.com

# LangSmith (optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_...
LANGCHAIN_PROJECT=mattin-production
```

### Frontend .env

```bash
VITE_API_BASE_URL=https://api.mattin.your-domain.com
VITE_OIDC_ENABLED=true
VITE_OIDC_AUTHORITY=https://login.microsoftonline.com/{tenant-id}/v2.0
VITE_OIDC_CLIENT_ID=your-azure-client-id
VITE_OIDC_REDIRECT_URI=https://mattin.your-domain.com/auth/success
```

## Library Publishing

### Build Library

Build the base library for npm publishing:

```bash
cd frontend
npm run build:lib
```

**Output**: `frontend/dist-lib/` - Library build artifacts

### Publish to npm

```bash
# Manual publish
cd frontend
npm publish

# Or use script
./deploy/scripts/publish-library.sh
```

### Deploy Base Library

Automated deployment script:

```bash
./deploy/scripts/deploy-base-library.sh
```

**What it does**:
1. Bumps version in `package.json`
2. Builds library (`npm run build:lib`)
3. Publishes to npm
4. Tags git commit
5. Pushes changes

## CI/CD

### Jenkinsfile

Located at root: `Jenkinsfile`

**Pipeline stages**:
1. **Checkout**: Clone repository
2. **Build**: Build Docker images
3. **Test**: Run unit tests, linters
4. **SonarQube**: Code quality analysis
5. **Push**: Push images to registry
6. **Deploy**: Deploy to staging/production

**Trigger**: On push to `main` branch

### SonarQube Integration

**Configuration**:
```properties
sonar.projectKey=mattin-ai
sonar.sources=backend,frontend/src
sonar.exclusions=**/node_modules/**,**/dist/**,**/*.test.ts
sonar.python.coverage.reportPaths=coverage.xml
sonar.typescript.lcov.reportPaths=frontend/coverage/lcov.info
```

**Run locally**:
```bash
sonar-scanner \
  -Dsonar.projectKey=mattin-ai \
  -Dsonar.sources=. \
  -Dsonar.host.url=http://sonarqube:9000 \
  -Dsonar.login=your-token
```

## Monitoring & Logging

### Health Checks

**Backend**: `GET /health`
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "0.2.37"
}
```

**Frontend**: `GET /` (returns 200)

### Logging

**Backend**: Structured JSON logs
```python
logger.info("Agent execution started", extra={
    "agent_id": 10,
    "user_id": 123
})
```

**Collection**: Use Fluentd, Logstash, or CloudWatch

### Metrics

**Prometheus metrics** (optional):
- Request count
- Response time
- Error rate
- Active connections

## Scaling

### Horizontal Scaling

**Backend**:
- Stateless design
- Scale replicas: `kubectl scale deployment mattin-backend --replicas=10`
- Load balanced via Kubernetes Service

**Frontend**:
- Static assets cached
- Scale replicas: `kubectl scale deployment mattin-frontend --replicas=5`

### Vertical Scaling

**Database**:
- Increase CPU/RAM for PostgreSQL pod
- Use read replicas for high read load

**Vector DB**:
- Scale Qdrant replicas for distributed search

## Security

### Production Checklist

- [ ] HTTPS enabled (TLS certificates via cert-manager)
- [ ] Strong `SECRET_KEY` (256-bit random)
- [ ] Database credentials rotated
- [ ] API keys stored in Kubernetes Secrets
- [ ] CORS configured restrictively
- [ ] Rate limiting enabled
- [ ] Security headers configured (nginx)
- [ ] Regular backups configured
- [ ] Monitoring and alerting active

### Network Policies

Restrict pod-to-pod communication:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-policy
spec:
  podSelector:
    matchLabels:
      app: mattin-backend
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: mattin-frontend
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Backend won't start | Database connection failed | Check `SQLALCHEMY_DATABASE_URI`, ensure PostgreSQL is running |
| Frontend 502 error | Backend not ready | Check backend logs, verify health endpoint |
| Database connection timeout | Network issue | Check Kubernetes Service, DNS resolution |
| Out of memory | Insufficient resources | Increase memory limits in deployment |
| Slow performance | Under-provisioned | Scale replicas, increase CPU/RAM |

## See Also

- [Environment Variables](../reference/environment-variables.md) — Configuration reference
- [Authentication Guide](authentication.md) — OIDC setup for production
- [Backend Architecture](../architecture/backend.md) — Application structure
