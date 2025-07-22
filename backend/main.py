from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from routers.internal import internal_router
from routers.public.v1 import public_v1_router

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# Mount routers
app.include_router(internal_router, prefix="/internal", tags=["internal"])
app.include_router(public_v1_router, prefix="/api/v1", tags=["public-v1"])

# Custom docs endpoints
@app.get("/docs/internal", include_in_schema=False)
def custom_internal_docs():
    return get_swagger_ui_html(openapi_url="/openapi/internal.json", title="Internal API Docs")

@app.get("/openapi/internal.json", include_in_schema=False)
def internal_openapi():
    return app.openapi()

@app.get("/docs/public", include_in_schema=False)
def custom_public_docs():
    return get_swagger_ui_html(openapi_url="/openapi/public.json", title="Public API Docs")

@app.get("/openapi/public.json", include_in_schema=False)
def public_openapi():
    return app.openapi() 