"""Order schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class OrderItemBase(BaseModel):
    """Base schema for order items."""
    item_barcode: str
    item_name: str
    quantity: int = 1
    price: Optional[float] = None


class OrderItemCreate(BaseModel):
    """Schema for adding item to order."""
    item_id: int
    quantity: int = 1


class OrderItemResponse(OrderItemBase):
    """Response schema for order items."""
    id: int
    order_id: int
    item_id: Optional[int] = None
    source_box_id: Optional[int] = None
    source_box_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OrderBase(BaseModel):
    """Base schema for orders."""
    barcode: str
    name: str
    description: Optional[str] = None


class OrderCreate(OrderBase):
    """Schema for creating an order."""
    pass


class OrderUpdate(BaseModel):
    """Schema for updating an order."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class OrderResponse(OrderBase):
    """Response schema for orders."""
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    order_items: List[OrderItemResponse] = []
    
    class Config:
        from_attributes = True


class OrderSummary(BaseModel):
    """Summary schema for order list."""
    id: int
    barcode: str
    name: str
    status: str
    item_count: int = 0
    total_quantity: int = 0
    created_at: datetime

    class Config:
        from_attributes = True
