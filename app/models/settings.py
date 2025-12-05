"""Settings model for application configuration."""
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from app.database import Base


class Settings(Base):
    """Application settings - stored in database."""
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())


# Default settings keys
SETTINGS_KEYS = {
    "barcode_pattern": {
        "default": "",
        "description": "Barcode pattern for inventory items. Use # for digits 0-9, * for any character. Example: INV-##### for INV-00000 to INV-99999"
    },
    "auto_lookup_external": {
        "default": "true",
        "description": "Automatically lookup EAN/UPC/ISBN in online databases when barcode doesn't match pattern"
    }
}
