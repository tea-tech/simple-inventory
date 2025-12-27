"""Package schemas - replaces Order schemas."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class PackageItemBase(BaseModel):
    """Base schema for package items."""
    item_barcode: str
    item_name: str
    quantity: int = 1
    price: Optional[float] = None


class PackageItemCreate(BaseModel):
    """Schema for adding item to package."""
    item_id: int
    quantity: int = 1


class PackageItemResponse(PackageItemBase):
    """Response schema for package items."""
    id: int
    package_id: int
    item_id: Optional[int] = None
    source_box_id: Optional[int] = None
    source_box_name: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PackageBase(BaseModel):
    """Base schema for packages."""
    barcode: str
    name: str
    description: Optional[str] = None


class PackageCreate(PackageBase):
    """Schema for creating a package."""
    pass


class PackageUpdate(BaseModel):
    """Schema for updating a package."""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class PackageResponse(PackageBase):
    """Response schema for packages."""
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    package_items: List[PackageItemResponse] = []
    
    class Config:
        from_attributes = True


class PackageSummary(BaseModel):
    """Summary schema for package list."""
    id: int
    barcode: str
    name: str
    status: str
    item_count: int = 0
    total_quantity: int = 0
    created_at: datetime

    class Config:
        from_attributes = True
