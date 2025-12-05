"""Item schemas for request/response validation."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ItemBase(BaseModel):
    """Base item schema."""
    barcode: str
    origin_barcode: Optional[str] = None  # Original EAN/UPC/ISBN
    name: str
    description: Optional[str] = None
    quantity: int = 1
    price: Optional[float] = None


class ItemCreate(ItemBase):
    """Schema for creating an item."""
    box_id: int


class ItemUpdate(BaseModel):
    """Schema for updating an item."""
    barcode: Optional[str] = None
    origin_barcode: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    box_id: Optional[int] = None


class ItemMove(BaseModel):
    """Schema for moving an item to a different box."""
    target_box_id: int
    quantity: Optional[int] = None  # If None, move all


class ItemResponse(ItemBase):
    """Schema for item response."""
    id: int
    box_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
