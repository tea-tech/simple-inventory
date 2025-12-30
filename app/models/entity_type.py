"""EntityType model - configurable entity types with field visibility settings."""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from sqlalchemy.sql import func

from app.database import Base


# Default entity types that will be created on first run
DEFAULT_ENTITY_TYPES = [
    {
        "code": "item",
        "name": "Item",
        "description": "Basic inventory item (leaf node)",
        "icon": "📦",
        "color": "#4CAF50",
        "can_contain_children": False,
        "can_be_child": True,
        "allowed_parent_types": ["container", "package"],
        "allowed_child_types": [],
        "visible_fields": ["barcode", "origin_barcode", "name", "description", "quantity", "price"],
        "required_fields": ["barcode", "name"],
        "available_statuses": [],
        "sort_order": 1,
    },
    {
        "code": "container",
        "name": "Container",
        "description": "Container for items (box, bin, shelf, rack, etc.)",
        "icon": "📥",
        "color": "#2196F3",
        "can_contain_children": True,
        "can_be_child": True,
        "allowed_parent_types": ["container"],  # Containers can be nested
        "allowed_child_types": ["item", "container"],
        "visible_fields": ["barcode", "name", "description"],
        "required_fields": ["barcode", "name"],
        "available_statuses": [],
        "sort_order": 2,
    },
    {
        "code": "package",
        "name": "Package",
        "description": "Collection of items for orders or production",
        "icon": "📋",
        "color": "#FF9800",
        "can_contain_children": True,
        "can_be_child": False,
        "allowed_parent_types": [],
        "allowed_child_types": ["item"],
        "visible_fields": ["barcode", "name", "description", "status"],
        "required_fields": ["barcode", "name"],
        "available_statuses": ["new", "sourcing", "packed", "done", "cancelled"],
        "sort_order": 3,
    },
]


class EntityType(Base):
    """
    Configurable entity type with field visibility and behavior settings.
    
    This allows the system to be extended with new entity types (like racks, shelves, etc.)
    without code changes. Each type defines:
    - What fields are visible/required
    - Whether it can contain children
    - What types it can contain or be contained by
    - Available statuses for workflow
    """
    __tablename__ = "entity_types"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Unique code for referencing (e.g., "item", "container", "package")
    code = Column(String(50), unique=True, index=True, nullable=False)
    
    # Display name
    name = Column(String(100), nullable=False)
    
    # Description
    description = Column(Text, nullable=True)
    
    # Visual settings
    icon = Column(String(10), nullable=True, default="📦")  # Emoji or icon code
    color = Column(String(20), nullable=True, default="#808080")  # Hex color
    
    # Hierarchy settings
    can_contain_children = Column(Boolean, default=False, nullable=False)
    can_be_child = Column(Boolean, default=True, nullable=False)
    
    # Allowed relationships (JSON arrays of type codes)
    allowed_parent_types = Column(JSON, nullable=True, default=list)  # Types this can be child of
    allowed_child_types = Column(JSON, nullable=True, default=list)   # Types this can contain
    
    # Field visibility (JSON arrays of field names)
    visible_fields = Column(JSON, nullable=True, default=list)   # Fields shown in UI
    required_fields = Column(JSON, nullable=True, default=list)  # Fields required for creation
    
    # Available statuses for this type (JSON array)
    available_statuses = Column(JSON, nullable=True, default=list)
    
    # Default status when creating entities of this type
    default_status = Column(String(50), nullable=True, default=None)
    
    # Sort order for UI
    sort_order = Column(Integer, default=0, nullable=False)
    
    # Whether this type is active (can create new entities)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Whether this is a built-in type (cannot be deleted)
    is_builtin = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
