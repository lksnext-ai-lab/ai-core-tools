# Configuración de Qdrant

Actualmente, al cambiar de un tipo de base de datos vectorial a otra, los datos de los repositorios creados en una no se transfieren a la otra.

## Prerrequisitos
1. Instala las dependencias necesarias ejecutando el siguiente comando dentro del entorno virtual `aict-env`:
   ```bash
   pip install -r backend/requirements-qdrant.txt
   ```
2. Asegúrate de que Docker Desktop esté en ejecución.

## Configuración
1. En el archivo `.env`, configura las siguientes variables:
   ```env
   VECTOR_DB_TYPE=QDRANT
   QDRANT_URL=http://localhost:6333
   ```

## Arranque de Qdrant
1. Levanta el servicio de Qdrant utilizando el siguiente comando:
   ```bash
   docker-compose -f docker-compose-qdrant.yaml up -d
   ```
2. Verifica que el servicio esté funcionando correctamente accediendo a `http://localhost:6333/healthz`. Deberías obtener la respuesta:
   ```
   healthz check passed
   ```
## Uso
1. Crea un silo asignándole un servicio de embeddings.
2. Sube archivos al silo.
3. Verifica las búsquedas.