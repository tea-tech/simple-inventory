"""Entity model - unified model for items, boxes, packages, and other inventory entities."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


class EntityOperationType(str, enum.Enum):
    """Entity operation types for history tracking."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MOVE = "move"  # Changed parent/warehouse
    CONVERT = "convert"  # Changed entity type
    ADD_CHILD = "add_child"
    REMOVE_CHILD = "remove_child"
    SPLIT = "split"
    MERGE = "merge"
    QUANTITY_CHANGE = "quantity_change"


class Entity(Base):
    """
    Unified entity model - can represent items, boxes, packages, racks, or any inventory entity.
    
    Entities can contain other entities (parent-child relationship).
    Entity types are configurable via EntityType settings.
    """
    __tablename__ = "entities"
    
    id = Column(Integer, primary_key=True, index=True)
    barcode = Column(String(100), unique=True, index=True, nullable=False)
    origin_barcode = Column(String(100), nullable=True, index=True)  # Original EAN/UPC/ISBN
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Entity type - references entity_types.code
    entity_type = Column(String(50), nullable=False, index=True)
    
    # Quantity of this entity itself (e.g., 5 screws, 1 box)
    quantity = Column(Integer, default=1, nullable=False)
    
    # Price per unit
    price = Column(Float, nullable=True, default=None)
    
    # Location - entities can be in a warehouse directly or inside another entity
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=True)
    parent_id = Column(Integer, ForeignKey("entities.id"), nullable=True)
    
    # Custom fields stored as JSON for flexibility
    custom_fields = Column(JSON, nullable=True, default=dict)
    
    # Status for workflow (e.g., for packages: new, sourcing, packed, done, cancelled)
    status = Column(String(50), nullable=True, default=None)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    warehouse = relationship("Warehouse", back_populates="entities")
    parent = relationship("Entity", remote_side=[id], back_populates="children")
    children = relationship("Entity", back_populates="parent", cascade="all, delete-orphan")
    
    # Relations where this entity is the parent (for quantity tracking)
    child_relations = relationship(
        "EntityRelation", 
        foreign_keys="EntityRelation.parent_id",
        back_populates="parent",
        cascade="all, delete-orphan"
    )
    # Relations where this entity is the child
    parent_relations = relationship(
        "EntityRelation",
        foreign_keys="EntityRelation.child_id", 
        back_populates="child",
        cascade="all, delete-orphan"
    )
    
    # History
    history = relationship("EntityHistory", back_populates="entity", cascade="all, delete-orphan")


class EntityRelation(Base):
    """
    Relationship between entities with quantity tracking.
    
    This allows tracking "how many of entity X are in entity Y" separately
    from the entity's own quantity. Useful for packages/orders.
    """
    __tablename__ = "entity_relations"
    
    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    child_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    
    # Quantity of child entity in this relationship
    quantity = Column(Integer, default=1, nullable=False)
    
    # Optional: price at time of relation (for orders/packages)
    price_snapshot = Column(Float, nullable=True)
    
    # Optional: notes about this relationship
    notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    parent = relationship("Entity", foreign_keys=[parent_id], back_populates="child_relations")
    child = relationship("Entity", foreign_keys=[child_id], back_populates="parent_relations")


class EntityHistory(Base):
    """
    History log for entity operations.
    
    Tracks what operations were performed on entities for audit purposes.
    """
    __tablename__ = "entity_history"
    
    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(Integer, ForeignKey("entities.id"), nullable=False, index=True)
    
    # Operation type
    operation = Column(String(50), nullable=False)
    
    # Optional: related entity (e.g., for MOVE - the new parent, for ADD_CHILD - the child)
    related_entity_id = Column(Integer, nullable=True)
    
    # Optional: additional details as JSON
    details = Column(JSON, nullable=True)
    
    # Who performed the operation (user_id)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    entity = relationship("Entity", back_populates="history")
