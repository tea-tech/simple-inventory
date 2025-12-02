"""Box schemas for request/response validation."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class BoxBase(BaseModel):
    """Base box schema."""
    barcode: str
    name: str
    description: Optional[str] = None


class BoxCreate(BoxBase):
    """Schema for creating a box."""
    warehouse_id: int


class BoxUpdate(BaseModel):
    """Schema for updating a box."""
    barcode: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    warehouse_id: Optional[int] = None


class BoxResponse(BoxBase):
    """Schema for box response."""
    id: int
    warehouse_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class BoxWithItems(BoxResponse):
    """Schema for box with items."""
    items: List["ItemResponse"] = []


# Forward reference for circular import
from app.schemas.item import ItemResponse
BoxWithItems.model_rebuild()
