from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum


class CheckStatus(str, Enum):
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


# Check Item schemas
class CheckItemBase(BaseModel):
    item_id: int
    actual_quantity: Optional[int] = None


class CheckItemCreate(CheckItemBase):
    pass


class CheckItemUpdate(BaseModel):
    actual_quantity: int


class CheckItemResponse(BaseModel):
    id: int
    check_id: int
    item_id: int
    item_barcode: str
    item_name: str
    box_id: Optional[int]
    box_name: Optional[str]
    expected_quantity: int
    actual_quantity: Optional[int]
    price: Optional[float]
    checked_at: Optional[datetime]
    difference: Optional[int] = None  # Computed field
    
    class Config:
        from_attributes = True


# Inventory Check schemas
class InventoryCheckCreate(BaseModel):
    name: str
    description: Optional[str] = None


class InventoryCheckUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class InventoryCheckSummary(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: CheckStatus
    started_at: datetime
    completed_at: Optional[datetime]
    total_items: int = 0
    checked_items: int = 0
    items_with_difference: int = 0
    
    class Config:
        from_attributes = True


class InventoryCheckResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: CheckStatus
    started_at: datetime
    completed_at: Optional[datetime]
    created_by: Optional[int]
    check_items: List[CheckItemResponse] = []
    
    class Config:
        from_attributes = True


# For grouped view by box
class BoxCheckGroup(BaseModel):
    box_id: Optional[int]
    box_name: str
    total_items: int
    checked_items: int
    items: List[CheckItemResponse]


class InventoryCheckGrouped(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: CheckStatus
    started_at: datetime
    completed_at: Optional[datetime]
    boxes: List[BoxCheckGroup]


# For comparison between checks
class CheckComparison(BaseModel):
    item_id: int
    item_barcode: str
    item_name: str
    box_name: Optional[str]
    previous_expected: Optional[int]
    previous_actual: Optional[int]
    current_expected: int
    current_actual: Optional[int]
    change_since_last: Optional[int]  # Difference from previous actual to current expected
