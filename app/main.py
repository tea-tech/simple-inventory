"""FastAPI application entry point."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.config import settings
from app.database import engine, Base
from app.routes import auth, users, warehouses, boxes, items, packages, inventory_checks, barcode_lookup, settings as settings_routes, supplier_patterns

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="A simple inventory management system with role-based access control",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(warehouses.router, prefix="/api")
app.include_router(boxes.router, prefix="/api")
app.include_router(items.router, prefix="/api")
app.include_router(packages.router, prefix="/api")
app.include_router(inventory_checks.router, prefix="/api")
app.include_router(barcode_lookup.router, prefix="/api")
app.include_router(settings_routes.router, prefix="/api")
app.include_router(supplier_patterns.router, prefix="/api")


@app.get("/")
async def root():
    """Redirect to the GUI."""
    return RedirectResponse(url="/static/login.html")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
