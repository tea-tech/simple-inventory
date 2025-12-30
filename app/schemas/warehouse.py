"""Warehouse schemas for request/response validation."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class WarehouseBase(BaseModel):
    """Base warehouse schema."""
    name: str
    description: Optional[str] = None
    location: Optional[str] = None


class WarehouseCreate(WarehouseBase):
    """Schema for creating a warehouse."""
    pass


class WarehouseUpdate(BaseModel):
    """Schema for updating a warehouse."""
    name: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None


class WarehouseResponse(WarehouseBase):
    """Schema for warehouse response."""
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class WarehouseWithEntities(WarehouseResponse):
    """Schema for warehouse with entities."""
    entities: List["EntitySummary"] = []


# Forward reference for circular import
from app.schemas.entity import EntitySummary
WarehouseWithEntities.model_rebuild()
