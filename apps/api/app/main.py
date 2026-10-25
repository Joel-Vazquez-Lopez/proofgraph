import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Dynamically add repository root and apps/api to sys.path
current_dir = Path(__file__).resolve().parent
repo_root = current_dir
for _ in range(5):
    if (repo_root / "packages").exists():
        break
    repo_root = repo_root.parent

if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

api_dir = current_dir.parent  # apps/api
if str(api_dir) not in sys.path:
    sys.path.insert(0, str(api_dir))

from app.config import settings
from app.models.db_models import init_db
from app.routers.health import router as health_router
from app.routers.disputes import router as disputes_router
from app.routers.evidence import router as evidence_router


# Ensure database tables exist
init_db()

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Autonomous AI-assisted PayPal dispute investigation platform. "
        "Constructs typed evidence graphs, actively selects Next-Best-Evidence, "
        "and prepares decision-ready case packages for human and PayPal adjudication review."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(disputes_router, prefix=settings.API_V1_PREFIX)
app.include_router(evidence_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {
        "service": settings.PROJECT_NAME,
        "docs_url": "/docs",
        "api_prefix": settings.API_V1_PREFIX,
        "status": "online"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
