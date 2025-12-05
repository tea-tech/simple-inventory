"""Supplier pattern model for barcode-based supplier lookups."""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func

from app.database import Base


class SupplierPattern(Base):
    """
    Supplier barcode patterns - maps barcode patterns to supplier search URLs.
    
    When a barcode matches a supplier pattern, the system can provide a direct 
    link to search for that item on the supplier's website.
    
    Example:
    - pattern: "LA######*" 
    - name: "LaskaKit"
    - search_url: "https://laskakit.cz/vyhledavani/?string={barcode}"
    
    When barcode "LA150177M" is scanned, it matches the pattern and provides
    a search link: https://laskakit.cz/vyhledavani/?string=LA150177M
    """
    __tablename__ = "supplier_patterns"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)  # Supplier name (e.g., "LaskaKit")
    pattern = Column(String(100), nullable=False)  # Pattern using # for digit, * for any char
    search_url = Column(String(500), nullable=False)  # URL with {barcode} placeholder
    description = Column(Text, nullable=True)  # Optional description
    enabled = Column(Boolean, default=True, nullable=False)  # Enable/disable pattern
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
