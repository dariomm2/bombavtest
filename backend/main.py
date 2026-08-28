from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from . import admin, auth, practice, simulations, statistics
from .config import FRONTEND_DIR, app_revision, app_version
from .db import get_db

app = FastAPI(
    title="BombAvTest",
    version=app_version(),
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.middleware("http")(auth.bombavtest_request_context)
app.include_router(auth.router)
app.include_router(practice.router)
app.include_router(simulations.router)
app.include_router(statistics.router)
app.include_router(admin.router)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


@app.get("/health", include_in_schema=False)
def health():
    get_db().execute("SELECT 1").fetchone()
    return {"ok": True, "status": "healthy", "version": app_version(), "revision": app_revision()}


@app.get("/version.js", include_in_schema=False)
def version_script():
    import json

    body = (
        f"window.BOMBAVTEST_VERSION = {json.dumps(app_version())};\n"
        f"window.BOMBAVTEST_REVISION = {json.dumps(app_revision())};\n"
    )
    return PlainTextResponse(body, media_type="application/javascript", headers={"Cache-Control": "no-store"})


@app.get("/styles.css", include_in_schema=False)
def styles():
    return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")


@app.get("/script.js", include_in_schema=False)
def script():
    return FileResponse(FRONTEND_DIR / "script.js", media_type="text/javascript")


@app.get("/", include_in_schema=False)
@app.get("/login", include_in_schema=False)
@app.get("/statistics", include_in_schema=False)
@app.get("/questions", include_in_schema=False)
@app.get("/admin", include_in_schema=False)
@app.get("/aviso-legal", include_in_schema=False)
@app.get("/politica-privacidad", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(http_request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and http_request.url.path.rstrip("/") in {"/docs", "/redoc", "/openapi.json"}:
        return PlainTextResponse("Not Found", status_code=404)
    if exc.status_code == 404 and not http_request.url.path.startswith("/api/"):
        return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")
    if http_request.url.path.startswith("/api/"):
        error = "Recurso no encontrado." if exc.status_code == 404 else str(exc.detail)
        return JSONResponse({"ok": False, "error": error}, status_code=exc.status_code)
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_exception_handler(http_request: Request, exc: Exception):
    if http_request.url.path.startswith("/api/"):
        return JSONResponse({"ok": False, "error": "Ha ocurrido un error interno."}, status_code=500)
    return PlainTextResponse("Error interno", status_code=500)
