from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.database import Base


class CheckStatus(str, enum.Enum):
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class InventoryCheck(Base):
    __tablename__ = "inventory_checks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(CheckStatus), default=CheckStatus.in_progress)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    check_items = relationship("CheckItem", back_populates="inventory_check", cascade="all, delete-orphan")
    creator = relationship("User", back_populates="inventory_checks")


class CheckItem(Base):
    __tablename__ = "check_items"

    id = Column(Integer, primary_key=True, index=True)
    check_id = Column(Integer, ForeignKey("inventory_checks.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("entities.id"), nullable=False)
    
    # Snapshot of item info at check time
    item_barcode = Column(String, nullable=False)
    item_name = Column(String, nullable=False)
    box_id = Column(Integer, nullable=True)  # Parent entity ID (container)
    box_name = Column(String, nullable=True)
    
    # Quantities
    expected_quantity = Column(Integer, nullable=False)  # Quantity in system when checked
    actual_quantity = Column(Integer, nullable=True)  # Quantity counted (null = not yet checked)
    
    # Price for value calculation
    price = Column(Float, nullable=True)
    
    checked_at = Column(DateTime, nullable=True)
    
    # Relationships
    inventory_check = relationship("InventoryCheck", back_populates="check_items")
    entity = relationship("Entity")
