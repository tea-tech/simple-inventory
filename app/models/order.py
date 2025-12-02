"""Order model."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class OrderStatus(str, enum.Enum):
    """Order status enum."""
    NEW = "new"
    SOURCING = "sourcing"
    PACKED = "packed"
    DONE = "done"
    CANCELLED = "cancelled"


class Order(Base):
    """Order model - collection of items to be picked."""
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    barcode = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=OrderStatus.NEW.value, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    order_items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """Order item model - items in an order with quantity."""
    __tablename__ = "order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=True)  # Nullable in case item is deleted
    item_barcode = Column(String(100), nullable=False)  # Store barcode for reference
    item_name = Column(String(100), nullable=False)  # Store name for reference
    source_box_id = Column(Integer, ForeignKey("boxes.id"), nullable=True)  # Where item came from
    source_box_name = Column(String(100), nullable=True)  # Store box name for reference
    quantity = Column(Integer, default=1, nullable=False)
    price = Column(Float, nullable=True, default=None)  # Price at time of order
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    order = relationship("Order", back_populates="order_items")
