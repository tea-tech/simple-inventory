"""Entity type routes - manage configurable entity types."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin, require_viewer
from app.database import get_db
from app.models.user import User
from app.models.entity import Entity
from app.models.entity_type import EntityType, DEFAULT_ENTITY_TYPES
from app.schemas.entity import EntityTypeCreate, EntityTypeUpdate, EntityTypeResponse

router = APIRouter(prefix="/entity-types", tags=["Entity Types"])


def ensure_default_types(db: Session):
    """Create default entity types if they don't exist."""
    for type_data in DEFAULT_ENTITY_TYPES:
        existing = db.query(EntityType).filter(EntityType.code == type_data["code"]).first()
        if not existing:
            new_type = EntityType(**type_data, is_builtin=True)
            db.add(new_type)
    db.commit()


@router.get("/", response_model=List[EntityTypeResponse])
async def list_entity_types(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """List all entity types."""
    # Ensure defaults exist
    ensure_default_types(db)
    
    query = db.query(EntityType)
    if not include_inactive:
        query = query.filter(EntityType.is_active == True)
    
    types = query.order_by(EntityType.sort_order, EntityType.name).all()
    return types


@router.post("/", response_model=EntityTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_entity_type(
    type_data: EntityTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new entity type (admin only)."""
    # Check code uniqueness
    existing = db.query(EntityType).filter(EntityType.code == type_data.code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entity type with code '{type_data.code}' already exists"
        )
    
    db_type = EntityType(**type_data.model_dump(), is_builtin=False)
    db.add(db_type)
    db.commit()
    db.refresh(db_type)
    return db_type


@router.get("/{type_code}", response_model=EntityTypeResponse)
async def get_entity_type(
    type_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get a specific entity type by code."""
    entity_type = db.query(EntityType).filter(EntityType.code == type_code).first()
    if not entity_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity type not found"
        )
    return entity_type


@router.put("/{type_code}", response_model=EntityTypeResponse)
async def update_entity_type(
    type_code: str,
    type_update: EntityTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update an entity type (admin only)."""
    entity_type = db.query(EntityType).filter(EntityType.code == type_code).first()
    if not entity_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity type not found"
        )
    
    update_data = type_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entity_type, field, value)
    
    db.commit()
    db.refresh(entity_type)
    return entity_type


@router.delete("/{type_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity_type(
    type_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete an entity type (admin only). Cannot delete built-in types or types in use."""
    entity_type = db.query(EntityType).filter(EntityType.code == type_code).first()
    if not entity_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity type not found"
        )
    
    if entity_type.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete built-in entity type. You can deactivate it instead."
        )
    
    # Check if type is in use
    in_use = db.query(Entity).filter(Entity.entity_type == type_code).first()
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete entity type that is in use. Deactivate it instead."
        )
    
    db.delete(entity_type)
    db.commit()
    return None


@router.post("/{type_code}/activate", response_model=EntityTypeResponse)
async def activate_entity_type(
    type_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Activate an entity type."""
    entity_type = db.query(EntityType).filter(EntityType.code == type_code).first()
    if not entity_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity type not found"
        )
    
    entity_type.is_active = True
    db.commit()
    db.refresh(entity_type)
    return entity_type


@router.post("/{type_code}/deactivate", response_model=EntityTypeResponse)
async def deactivate_entity_type(
    type_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Deactivate an entity type (cannot create new entities of this type)."""
    entity_type = db.query(EntityType).filter(EntityType.code == type_code).first()
    if not entity_type:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity type not found"
        )
    
    entity_type.is_active = False
    db.commit()
    db.refresh(entity_type)
    return entity_type


@router.post("/init-defaults", response_model=List[EntityTypeResponse])
async def initialize_default_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Initialize/reset default entity types."""
    ensure_default_types(db)
    types = db.query(EntityType).order_by(EntityType.sort_order, EntityType.name).all()
    return types
