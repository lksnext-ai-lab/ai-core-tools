# IA Core Tools - Kubernetes Deployment

Este directorio contiene los archivos de configuración de Kubernetes para desplegar la aplicación IA Core Tools con el nuevo stack React + FastAPI.

## Arquitectura

La aplicación ahora está compuesta por:

- **Frontend**: Aplicación React servida por Nginx
- **Backend**: API FastAPI con Python
- **Database**: PostgreSQL con extensión pgvector

## Estructura de archivos

```
kubernetes/
├── test/
│   ├── configmap.yaml              # ConfigMap con variables de entorno
│   ├── secrets.yaml                # Secrets con API keys y credenciales
│   ├── ia-core-tools-ingress-test.yaml  # Ingress para routing
│   ├── backend/
│   │   └── deployment.yaml         # Deployment y Service del backend
│   ├── frontend/
│   │   └── deployment.yaml         # Deployment y Service del frontend
│   ├── postgreSQL/
│   │   ├── postgreSQL-test.yaml    # Deployment y Service de PostgreSQL
│   │   ├── postgreSQL-test-secret.yaml  # Credenciales de la BD
│   │   └── postgreSQL-test-pvc.yaml     # PersistentVolume para PostgreSQL
│   └── storage/
│       └── storage-pv.yaml         # PersistentVolumes para datos y logs
```

## Variables de entorno importantes

### ConfigMap (configmap.yaml)
- `VITE_API_URL`: URL del backend para el frontend
- `FRONTEND_URL`: URL del frontend para CORS y redirects
- `DATABASE_*`: Configuración de la base de datos
- `AICT_MODE`: Modo de la aplicación (SELF-HOSTED)
- `LANGCHAIN_*`: Configuración de LangChain

### Secrets (secrets.yaml)
- `OPENAI_API_KEY`: Clave de OpenAI
- `ANTHROPIC_API_KEY`: Clave de Anthropic
- `GOOGLE_CLIENT_*`: Credenciales OAuth de Google
- `SECRET_KEY`: Clave secreta para JWT
- `LANGCHAIN_API_KEY`: Clave de LangSmith

## Despliegue

### 1. Crear namespace
```bash
kubectl create namespace test
```

### 2. Aplicar configuraciones base
```bash
kubectl apply -f configmap.yaml
kubectl apply -f secrets.yaml
```

### 3. Crear almacenamiento
```bash
kubectl apply -f storage/storage-pv.yaml
kubectl apply -f postgreSQL/postgreSQL-test-pvc.yaml
```

### 4. Desplegar PostgreSQL
```bash
kubectl apply -f postgreSQL/postgreSQL-test-secret.yaml
kubectl apply -f postgreSQL/postgreSQL-test.yaml
```

### 5. Desplegar aplicaciones
```bash
kubectl apply -f backend/deployment.yaml
kubectl apply -f frontend/deployment.yaml
```

### 6. Configurar Ingress
```bash
kubectl apply -f ia-core-tools-ingress-test.yaml
```

## Routing

El Ingress está configurado para manejar:

- `/api/*` → Backend (FastAPI)
- `/docs` → Documentación de la API (Swagger)
- `/redoc` → Documentación alternativa de la API
- `/auth/*` → Endpoints de autenticación
- `/*` → Frontend (React SPA)

## Builds de Docker

### Backend
```bash
docker build -f backend/Dockerfile -t registry.lksnext.com/ia-core-tools/backend:latest .
```

### Frontend
```bash
docker build -f frontend/Dockerfile -t registry.lksnext.com/ia-core-tools/frontend:latest .
```

## Diferencias con la versión Flask

1. **Separación de servicios**: Frontend y backend ahora son deployments independientes
2. **Puertos diferentes**: 
   - Frontend: puerto 80 (Nginx)
   - Backend: puerto 8000 (FastAPI)
3. **Variables de entorno nuevas**:
   - `VITE_API_URL` para el frontend
   - Variables específicas de FastAPI
   - Configuración JWT separada
4. **Health checks**: Añadidos readiness y liveness probes
5. **Recursos optimizados**: Diferentes requirements para frontend vs backend

## Monitoreo

- Backend health check: `GET aict-desa.lksnext.com/api/`
- Frontend health check: `GET aict-desa.lksnext.com/health`
- Logs del backend: `kubectl logs -f deployment/ia-core-tools-backend-test -n test`
- Logs del frontend: `kubectl logs -f deployment/ia-core-tools-frontend-test -n test`
