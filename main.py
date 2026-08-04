# ------------------------------------------------------------
# Punto de entrada de FastAPI.
#   - Arranque de BD (lifespan)
#   - CORS
#   - Registro de routers (auth, servicios)
# ------------------------------------------------------------
import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import create_db_and_tables
from core.config import settings
from routers.auth import router as auth_router
from routers.services import router as services_router
from routers.providers import router as providers_router
from routers.users import router as users_router
from routers.reservations import router as reservations_router
from routers.reviews import router as reviews_router
from routers.payments import router as payments_router
from routers.groups import router as groups_router

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Crear tablas al iniciar la app
    create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

# CORS (modo dev): habilitamos orígenes configurados en settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(services_router)
app.include_router(providers_router)
app.include_router(users_router)
app.include_router(reservations_router)
app.include_router(reviews_router)
app.include_router(payments_router)
app.include_router(groups_router)

# Healthcheck / demo
@app.get("/")
async def root():
    return {"message": "Test API"}
