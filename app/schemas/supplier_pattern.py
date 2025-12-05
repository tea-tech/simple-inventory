"""Supplier pattern schemas for request/response validation."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class SupplierPatternBase(BaseModel):
    """Base supplier pattern schema."""
    name: str = Field(..., min_length=1, max_length=100, description="Supplier name")
    pattern: str = Field(..., min_length=1, max_length=100, description="Barcode pattern (# = digit, * = any char)")
    search_url: str = Field(..., min_length=1, max_length=500, description="Search URL with {barcode} placeholder")
    description: Optional[str] = None
    enabled: bool = True


class SupplierPatternCreate(SupplierPatternBase):
    """Schema for creating a supplier pattern."""
    pass


class SupplierPatternUpdate(BaseModel):
    """Schema for updating a supplier pattern."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    pattern: Optional[str] = Field(None, min_length=1, max_length=100)
    search_url: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    enabled: Optional[bool] = None


class SupplierPatternResponse(SupplierPatternBase):
    """Schema for supplier pattern response."""
    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class SupplierPatternMatch(BaseModel):
    """Result of checking a barcode against supplier patterns."""
    barcode: str
    matched: bool
    supplier: Optional[SupplierPatternResponse] = None
    search_url: Optional[str] = None  # URL with barcode substituted
