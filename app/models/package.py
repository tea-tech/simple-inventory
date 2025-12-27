"""Package model - replaces Order."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class PackageStatus(str, enum.Enum):
    """Package status enum."""
    NEW = "new"
    SOURCING = "sourcing"
    PACKED = "packed"
    DONE = "done"
    CANCELLED = "cancelled"


class Package(Base):
    """Package model - collection of items to be picked."""
    __tablename__ = "packages"
    
    id = Column(Integer, primary_key=True, index=True)
    barcode = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=PackageStatus.NEW.value, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    package_items = relationship("PackageItem", back_populates="package", cascade="all, delete-orphan")


class PackageItem(Base):
    """Package item model - items in a package with quantity."""
    __tablename__ = "package_items"
    
    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("packages.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=True)  # Nullable in case item is deleted
    item_barcode = Column(String(100), nullable=False)  # Store barcode for reference
    item_name = Column(String(100), nullable=False)  # Store name for reference
    source_box_id = Column(Integer, ForeignKey("boxes.id"), nullable=True)  # Where item came from
    source_box_name = Column(String(100), nullable=True)  # Store box name for reference
    quantity = Column(Integer, default=1, nullable=False)
    price = Column(Float, nullable=True, default=None)  # Price at time of package
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    package = relationship("Package", back_populates="package_items")
