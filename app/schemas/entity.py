"""Entity schemas for request/response validation."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================================================
# Entity Schemas
# ============================================================================

class EntityBase(BaseModel):
    """Base entity schema with common fields."""
    barcode: str = Field(..., min_length=1, max_length=100)
    origin_barcode: Optional[str] = Field(None, max_length=100)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    entity_type: str = Field(..., min_length=1, max_length=50)
    quantity: int = Field(default=1, ge=0)
    price: Optional[float] = Field(None, ge=0)
    status: Optional[str] = Field(None, max_length=50)
    custom_fields: Optional[Dict[str, Any]] = None


class EntityCreate(EntityBase):
    """Schema for creating an entity."""
    warehouse_id: Optional[int] = None
    parent_id: Optional[int] = None


class EntityUpdate(BaseModel):
    """Schema for updating an entity."""
    barcode: Optional[str] = Field(None, min_length=1, max_length=100)
    origin_barcode: Optional[str] = Field(None, max_length=100)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    entity_type: Optional[str] = Field(None, min_length=1, max_length=50)
    quantity: Optional[int] = Field(None, ge=0)
    price: Optional[float] = Field(None, ge=0)
    status: Optional[str] = Field(None, max_length=50)
    custom_fields: Optional[Dict[str, Any]] = None
    warehouse_id: Optional[int] = None
    parent_id: Optional[int] = None


class EntityResponse(EntityBase):
    """Schema for entity response."""
    id: int
    warehouse_id: Optional[int] = None
    parent_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class EntityWithChildren(EntityResponse):
    """Schema for entity response including children."""
    children: List["EntityResponse"] = []
    child_relations: List["EntityRelationResponse"] = []
    
    class Config:
        from_attributes = True


class EntitySummary(BaseModel):
    """Summary schema for entity lists."""
    id: int
    barcode: str
    name: str
    entity_type: str
    quantity: int
    status: Optional[str] = None
    children_count: int = 0
    warehouse_id: Optional[int] = None
    parent_id: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class EntityMove(BaseModel):
    """Schema for moving an entity."""
    target_warehouse_id: Optional[int] = None
    target_parent_id: Optional[int] = None
    quantity: Optional[int] = None  # If set, split entity


class EntityConvert(BaseModel):
    """Schema for converting entity type."""
    new_type: str = Field(..., min_length=1, max_length=50)
    new_status: Optional[str] = None


class EntitySplit(BaseModel):
    """Schema for splitting an entity."""
    quantity: int = Field(..., gt=0)
    new_barcode: str = Field(..., min_length=1, max_length=100)
    target_warehouse_id: Optional[int] = None
    target_parent_id: Optional[int] = None


class EntityMerge(BaseModel):
    """Schema for merging entities."""
    source_entity_ids: List[int] = Field(..., min_length=1)


# ============================================================================
# Entity Relation Schemas
# ============================================================================

class EntityRelationBase(BaseModel):
    """Base schema for entity relations."""
    child_id: int
    quantity: int = Field(default=1, ge=1)
    price_snapshot: Optional[float] = None
    notes: Optional[str] = None


class EntityRelationCreate(EntityRelationBase):
    """Schema for creating an entity relation."""
    pass


class EntityRelationUpdate(BaseModel):
    """Schema for updating an entity relation."""
    quantity: Optional[int] = Field(None, ge=1)
    price_snapshot: Optional[float] = None
    notes: Optional[str] = None


class EntityRelationResponse(EntityRelationBase):
    """Schema for entity relation response."""
    id: int
    parent_id: int
    created_at: datetime
    
    # Include child entity basic info
    child: Optional[EntitySummary] = None
    
    class Config:
        from_attributes = True


class AddChildRequest(BaseModel):
    """Schema for adding a child to an entity."""
    child_barcode: Optional[str] = None  # Find by barcode
    child_id: Optional[int] = None       # Or by ID
    quantity: int = Field(default=1, ge=1)
    remove_from_source: bool = True      # Remove quantity from source entity
    price_snapshot: Optional[float] = None
    notes: Optional[str] = None


class RemoveChildRequest(BaseModel):
    """Schema for removing a child from an entity."""
    quantity: Optional[int] = None  # If None, remove all
    return_to_source: bool = False  # Return to original location


# ============================================================================
# Entity History Schemas
# ============================================================================

class EntityHistoryResponse(BaseModel):
    """Schema for entity history response."""
    id: int
    entity_id: int
    operation: str
    related_entity_id: Optional[int] = None
    details: Optional[Dict[str, Any]] = None
    user_id: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============================================================================
# Entity Type Schemas
# ============================================================================

class EntityTypeBase(BaseModel):
    """Base schema for entity types."""
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = Field("📦", max_length=10)
    color: Optional[str] = Field("#808080", max_length=20)
    can_contain_children: bool = False
    can_be_child: bool = True
    allowed_parent_types: List[str] = []
    allowed_child_types: List[str] = []
    visible_fields: List[str] = []
    required_fields: List[str] = []
    available_statuses: List[str] = []
    default_status: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class EntityTypeCreate(EntityTypeBase):
    """Schema for creating an entity type."""
    pass


class EntityTypeUpdate(BaseModel):
    """Schema for updating an entity type."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=10)
    color: Optional[str] = Field(None, max_length=20)
    can_contain_children: Optional[bool] = None
    can_be_child: Optional[bool] = None
    allowed_parent_types: Optional[List[str]] = None
    allowed_child_types: Optional[List[str]] = None
    visible_fields: Optional[List[str]] = None
    required_fields: Optional[List[str]] = None
    available_statuses: Optional[List[str]] = None
    default_status: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class EntityTypeResponse(EntityTypeBase):
    """Schema for entity type response."""
    id: int
    is_builtin: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# Update forward references
EntityWithChildren.model_rebuild()
