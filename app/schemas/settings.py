"""Settings schemas for request/response validation."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class SettingBase(BaseModel):
    """Base setting schema."""
    key: str
    value: Optional[str] = None
    description: Optional[str] = None


class SettingUpdate(BaseModel):
    """Schema for updating a setting."""
    value: Optional[str] = None


class SettingResponse(SettingBase):
    """Schema for setting response."""
    id: int
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class AllSettingsResponse(BaseModel):
    """Schema for all settings response."""
    barcode_pattern: str
    auto_lookup_external: bool


class BarcodePatternTest(BaseModel):
    """Schema for testing barcode pattern."""
    pattern: str
    barcode: str


class BarcodePatternTestResult(BaseModel):
    """Result of barcode pattern test."""
    pattern: str
    barcode: str
    matches: bool
    is_internal: bool  # True if matches pattern, False if external (EAN/UPC/ISBN)
    message: str
