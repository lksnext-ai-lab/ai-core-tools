# LKS Next IA Core Tools Development Guide

## Alembic migrations

### Install
```bash
pip install alembic
```


### Create a new migration from an existing model
```bash
alembic revision --autogenerate -m "Initial revision"
alembic upgrade head
```


docker-compose -f docker-compose.yaml --env-file .env up postgres
