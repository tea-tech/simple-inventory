"""Entity routes - unified CRUD for all inventory entities."""
from typing import List, Optional
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.auth import require_manager, require_viewer
from app.database import get_db
from app.models.user import User
from app.models.entity import Entity, EntityRelation, EntityHistory, EntityOperationType
from app.models.entity_type import EntityType, DEFAULT_ENTITY_TYPES
from app.models.warehouse import Warehouse
from app.schemas.entity import (
    EntityCreate, EntityResponse, EntityUpdate, EntitySummary, EntityWithChildren,
    EntityMove, EntityConvert, EntitySplit, EntityMerge,
    EntityRelationCreate, EntityRelationUpdate, EntityRelationResponse,
    AddChildRequest, RemoveChildRequest, EntityHistoryResponse
)

router = APIRouter(prefix="/entities", tags=["Entities"])


# ============================================================================
# Helper Functions
# ============================================================================

def log_history(
    db: Session,
    entity_id: int,
    operation: EntityOperationType,
    user_id: Optional[int] = None,
    related_entity_id: Optional[int] = None,
    details: Optional[dict] = None
):
    """Log an operation to entity history."""
    history = EntityHistory(
        entity_id=entity_id,
        operation=operation.value,
        user_id=user_id,
        related_entity_id=related_entity_id,
        details=details
    )
    db.add(history)


def ensure_default_types(db: Session):
    """Create default entity types if they don't exist."""
    for type_data in DEFAULT_ENTITY_TYPES:
        existing = db.query(EntityType).filter(EntityType.code == type_data["code"]).first()
        if not existing:
            new_type = EntityType(**type_data, is_builtin=True)
            db.add(new_type)
    db.commit()


def validate_entity_type(db: Session, type_code: str) -> EntityType:
    """Validate entity type exists and is active."""
    # Ensure default types exist
    ensure_default_types(db)
    
    entity_type = db.query(EntityType).filter(
        EntityType.code == type_code,
        EntityType.is_active == True
    ).first()
    if not entity_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or inactive entity type: {type_code}"
        )
    return entity_type


def validate_parent_child_relationship(
    db: Session,
    parent: Entity,
    child_type_code: str
):
    """Validate that parent can contain child of given type."""
    parent_type = db.query(EntityType).filter(EntityType.code == parent.entity_type).first()
    if not parent_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parent entity type not found: {parent.entity_type}"
        )
    
    if not parent_type.can_contain_children:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entity type '{parent_type.name}' cannot contain children"
        )
    
    if parent_type.allowed_child_types and child_type_code not in parent_type.allowed_child_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entity type '{parent_type.name}' cannot contain '{child_type_code}' entities"
        )


def get_children_count(entity: Entity) -> int:
    """Get total count of children (both direct children and via relations)."""
    direct = len(entity.children) if entity.children else 0
    relations = len(entity.child_relations) if entity.child_relations else 0
    return direct + relations


# ============================================================================
# Entity CRUD
# ============================================================================

@router.get("/", response_model=List[EntitySummary])
async def list_entities(
    skip: int = 0,
    limit: int = 100,
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    warehouse_id: Optional[int] = Query(None, description="Filter by warehouse"),
    parent_id: Optional[int] = Query(None, description="Filter by parent entity"),
    root_only: bool = Query(False, description="Only show root entities (no parent)"),
    search: Optional[str] = Query(None, description="Search by name, barcode, or description"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """List entities with optional filters."""
    query = db.query(Entity)
    
    if entity_type:
        query = query.filter(Entity.entity_type == entity_type)
    
    if warehouse_id:
        query = query.filter(Entity.warehouse_id == warehouse_id)
    
    if parent_id:
        query = query.filter(Entity.parent_id == parent_id)
    elif root_only:
        query = query.filter(Entity.parent_id == None)
    
    if status_filter:
        query = query.filter(Entity.status == status_filter)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Entity.name.ilike(search_term),
                Entity.description.ilike(search_term),
                Entity.barcode.ilike(search_term)
            )
        )
    
    entities = query.order_by(Entity.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for entity in entities:
        result.append(EntitySummary(
            id=entity.id,
            barcode=entity.barcode,
            name=entity.name,
            entity_type=entity.entity_type,
            quantity=entity.quantity,
            status=entity.status,
            children_count=get_children_count(entity),
            warehouse_id=entity.warehouse_id,
            parent_id=entity.parent_id,
            created_at=entity.created_at
        ))
    
    return result


@router.post("/", response_model=EntityResponse, status_code=status.HTTP_201_CREATED)
async def create_entity(
    entity_data: EntityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Create a new entity."""
    # Validate entity type
    entity_type = validate_entity_type(db, entity_data.entity_type)
    
    # Check barcode uniqueness
    existing = db.query(Entity).filter(Entity.barcode == entity_data.barcode).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Barcode already exists"
        )
    
    # Validate warehouse if provided
    if entity_data.warehouse_id:
        warehouse = db.query(Warehouse).filter(Warehouse.id == entity_data.warehouse_id).first()
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warehouse not found"
            )
    
    # Validate parent if provided
    if entity_data.parent_id:
        parent = db.query(Entity).filter(Entity.id == entity_data.parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent entity not found"
            )
        validate_parent_child_relationship(db, parent, entity_data.entity_type)
    
    # Set default status if not provided
    data = entity_data.model_dump()
    if not data.get("status") and entity_type.default_status:
        data["status"] = entity_type.default_status
    
    # Create entity
    db_entity = Entity(**data)
    db.add(db_entity)
    db.flush()
    
    # Log history
    log_history(db, db_entity.id, EntityOperationType.CREATE, current_user.id)
    
    db.commit()
    db.refresh(db_entity)
    return db_entity


@router.get("/barcode/{barcode}", response_model=EntityWithChildren)
async def get_entity_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get an entity by its barcode."""
    entity = db.query(Entity).filter(Entity.barcode == barcode).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    return entity


@router.get("/{entity_id}", response_model=EntityWithChildren)
async def get_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get an entity by ID with its children."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    return entity


@router.put("/{entity_id}", response_model=EntityResponse)
async def update_entity(
    entity_id: int,
    entity_update: EntityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Update an entity."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    
    update_data = entity_update.model_dump(exclude_unset=True)
    
    # Validate new entity type if changing
    if "entity_type" in update_data and update_data["entity_type"] != entity.entity_type:
        validate_entity_type(db, update_data["entity_type"])
    
    # Validate new barcode if changing
    if "barcode" in update_data and update_data["barcode"] != entity.barcode:
        existing = db.query(Entity).filter(Entity.barcode == update_data["barcode"]).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Barcode already exists"
            )
    
    # Validate new warehouse if changing
    if "warehouse_id" in update_data and update_data["warehouse_id"]:
        warehouse = db.query(Warehouse).filter(Warehouse.id == update_data["warehouse_id"]).first()
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warehouse not found"
            )
    
    # Validate new parent if changing
    if "parent_id" in update_data and update_data["parent_id"]:
        parent = db.query(Entity).filter(Entity.id == update_data["parent_id"]).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent entity not found"
            )
        # Prevent circular reference
        if parent.id == entity.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Entity cannot be its own parent"
            )
        new_type = update_data.get("entity_type", entity.entity_type)
        validate_parent_child_relationship(db, parent, new_type)
    
    # Apply updates
    for field, value in update_data.items():
        setattr(entity, field, value)
    
    # Log history
    log_history(
        db, entity.id, EntityOperationType.UPDATE, current_user.id,
        details={"updated_fields": list(update_data.keys())}
    )
    
    db.commit()
    db.refresh(entity)
    return entity


@router.delete("/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity(
    entity_id: int,
    force: bool = Query(False, description="Force delete even if has children"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Delete an entity."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    
    # Check for children
    if not force and (entity.children or entity.child_relations):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete entity with children. Use force=true or remove children first."
        )
    
    db.delete(entity)
    db.commit()
    return None


# ============================================================================
# Entity Operations
# ============================================================================

@router.post("/{entity_id}/move", response_model=EntityResponse)
async def move_entity(
    entity_id: int,
    move_data: EntityMove,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Move an entity to a different location (warehouse or parent)."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    
    old_warehouse_id = entity.warehouse_id
    old_parent_id = entity.parent_id
    
    # If quantity specified, split first
    if move_data.quantity and move_data.quantity < entity.quantity:
        # Create new split entity
        split_entity = Entity(
            barcode=f"{entity.barcode}-split-{entity.id}",
            origin_barcode=entity.origin_barcode,
            name=entity.name,
            description=entity.description,
            entity_type=entity.entity_type,
            quantity=move_data.quantity,
            price=entity.price,
            warehouse_id=move_data.target_warehouse_id or entity.warehouse_id,
            parent_id=move_data.target_parent_id,
            custom_fields=entity.custom_fields,
            status=entity.status
        )
        db.add(split_entity)
        
        entity.quantity -= move_data.quantity
        
        db.flush()
        log_history(db, entity.id, EntityOperationType.SPLIT, current_user.id,
                   related_entity_id=split_entity.id, details={"quantity": move_data.quantity})
        log_history(db, split_entity.id, EntityOperationType.CREATE, current_user.id,
                   details={"split_from": entity.id})
        
        db.commit()
        db.refresh(split_entity)
        return split_entity
    
    # Validate new parent if provided
    if move_data.target_parent_id:
        new_parent = db.query(Entity).filter(Entity.id == move_data.target_parent_id).first()
        if not new_parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target parent entity not found"
            )
        if new_parent.id == entity.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Entity cannot be its own parent"
            )
        validate_parent_child_relationship(db, new_parent, entity.entity_type)
        entity.parent_id = move_data.target_parent_id
        entity.warehouse_id = None  # Entity is now inside another entity
    elif move_data.target_warehouse_id:
        warehouse = db.query(Warehouse).filter(Warehouse.id == move_data.target_warehouse_id).first()
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target warehouse not found"
            )
        entity.warehouse_id = move_data.target_warehouse_id
        entity.parent_id = None  # Entity is now at warehouse level
    
    # Log history
    log_history(
        db, entity.id, EntityOperationType.MOVE, current_user.id,
        details={
            "from_warehouse": old_warehouse_id,
            "from_parent": old_parent_id,
            "to_warehouse": entity.warehouse_id,
            "to_parent": entity.parent_id
        }
    )
    
    db.commit()
    db.refresh(entity)
    return entity


@router.post("/{entity_id}/convert", response_model=EntityResponse)
async def convert_entity(
    entity_id: int,
    convert_data: EntityConvert,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Convert an entity to a different type."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    
    old_type = entity.entity_type
    
    # Validate new type
    new_type = validate_entity_type(db, convert_data.new_type)
    
    # Validate parent relationship if entity has parent
    if entity.parent_id:
        parent = db.query(Entity).filter(Entity.id == entity.parent_id).first()
        if parent:
            parent_type = db.query(EntityType).filter(EntityType.code == parent.entity_type).first()
            if parent_type and parent_type.allowed_child_types:
                if convert_data.new_type not in parent_type.allowed_child_types:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Parent entity cannot contain '{convert_data.new_type}' entities"
                    )
    
    # Validate children relationships if entity has children
    if entity.children:
        for child in entity.children:
            if new_type.allowed_child_types and child.entity_type not in new_type.allowed_child_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"New type '{convert_data.new_type}' cannot contain '{child.entity_type}' entities"
                )
    
    entity.entity_type = convert_data.new_type
    
    # Set new status if provided, or use default for new type
    if convert_data.new_status:
        entity.status = convert_data.new_status
    elif new_type.default_status:
        entity.status = new_type.default_status
    
    # Log history
    log_history(
        db, entity.id, EntityOperationType.CONVERT, current_user.id,
        details={"from_type": old_type, "to_type": convert_data.new_type}
    )
    
    db.commit()
    db.refresh(entity)
    return entity


@router.post("/{entity_id}/split", response_model=EntityResponse)
async def split_entity(
    entity_id: int,
    split_data: EntitySplit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Split an entity into two (reduce quantity and create new entity)."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    
    if split_data.quantity >= entity.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Split quantity must be less than current quantity ({entity.quantity})"
        )
    
    # Check new barcode uniqueness
    existing = db.query(Entity).filter(Entity.barcode == split_data.new_barcode).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New barcode already exists"
        )
    
    # Validate target if provided
    target_warehouse_id = split_data.target_warehouse_id or entity.warehouse_id
    target_parent_id = split_data.target_parent_id or entity.parent_id
    
    if target_parent_id:
        parent = db.query(Entity).filter(Entity.id == target_parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target parent entity not found"
            )
        validate_parent_child_relationship(db, parent, entity.entity_type)
        target_warehouse_id = None
    elif target_warehouse_id:
        warehouse = db.query(Warehouse).filter(Warehouse.id == target_warehouse_id).first()
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target warehouse not found"
            )
    
    # Create new entity with split quantity
    new_entity = Entity(
        barcode=split_data.new_barcode,
        origin_barcode=entity.origin_barcode,
        name=entity.name,
        description=entity.description,
        entity_type=entity.entity_type,
        quantity=split_data.quantity,
        price=entity.price,
        warehouse_id=target_warehouse_id,
        parent_id=target_parent_id,
        custom_fields=entity.custom_fields,
        status=entity.status
    )
    db.add(new_entity)
    
    # Reduce original quantity
    entity.quantity -= split_data.quantity
    
    db.flush()
    
    # Log history
    log_history(db, entity.id, EntityOperationType.SPLIT, current_user.id,
               related_entity_id=new_entity.id, details={"quantity": split_data.quantity})
    log_history(db, new_entity.id, EntityOperationType.CREATE, current_user.id,
               details={"split_from": entity.id})
    
    db.commit()
    db.refresh(new_entity)
    return new_entity


@router.post("/{entity_id}/merge", response_model=EntityResponse)
async def merge_entities(
    entity_id: int,
    merge_data: EntityMerge,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Merge multiple entities into one (combine quantities, delete sources)."""
    target = db.query(Entity).filter(Entity.id == entity_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target entity not found"
        )
    
    merged_count = 0
    for source_id in merge_data.source_entity_ids:
        if source_id == entity_id:
            continue
        
        source = db.query(Entity).filter(Entity.id == source_id).first()
        if not source:
            continue
        
        if source.entity_type != target.entity_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot merge entities of different types ({source.entity_type} vs {target.entity_type})"
            )
        
        # Add quantity
        target.quantity += source.quantity
        
        # Move children to target
        for child in source.children[:]:
            child.parent_id = target.id
        
        # Log and delete source
        log_history(db, target.id, EntityOperationType.MERGE, current_user.id,
                   related_entity_id=source.id, details={"merged_quantity": source.quantity})
        
        db.delete(source)
        merged_count += 1
    
    db.commit()
    db.refresh(target)
    return target


@router.post("/{entity_id}/quantity", response_model=EntityResponse)
async def adjust_quantity(
    entity_id: int,
    adjustment: int = Query(..., description="Quantity adjustment (positive to add, negative to remove)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Adjust entity quantity (add or remove)."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    
    new_quantity = entity.quantity + adjustment
    if new_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reduce quantity below 0. Current: {entity.quantity}, adjustment: {adjustment}"
        )
    
    old_quantity = entity.quantity
    entity.quantity = new_quantity
    
    # Log history
    log_history(
        db, entity.id, EntityOperationType.QUANTITY_CHANGE, current_user.id,
        details={"from": old_quantity, "to": new_quantity, "adjustment": adjustment}
    )
    
    db.commit()
    db.refresh(entity)
    return entity


# ============================================================================
# Child Management via Relations
# ============================================================================

@router.get("/{entity_id}/children", response_model=List[EntityRelationResponse])
async def get_entity_children(
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get all children of an entity (via relations)."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    
    relations = db.query(EntityRelation).filter(EntityRelation.parent_id == entity_id).all()
    return relations


@router.post("/{entity_id}/children", response_model=EntityRelationResponse)
async def add_child_to_entity(
    entity_id: int,
    child_data: AddChildRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Add a child entity to this entity (creates relation with quantity)."""
    parent = db.query(Entity).filter(Entity.id == entity_id).first()
    if not parent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent entity not found"
        )
    
    # Find child by barcode or ID
    if child_data.child_barcode:
        child = db.query(Entity).filter(Entity.barcode == child_data.child_barcode).first()
    elif child_data.child_id:
        child = db.query(Entity).filter(Entity.id == child_data.child_id).first()
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either child_barcode or child_id"
        )
    
    if not child:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Child entity not found"
        )
    
    # Validate relationship
    validate_parent_child_relationship(db, parent, child.entity_type)
    
    # Check quantity
    if child_data.remove_from_source and child_data.quantity > child.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot add {child_data.quantity} items. Only {child.quantity} available."
        )
    
    # Check for existing relation
    existing_relation = db.query(EntityRelation).filter(
        EntityRelation.parent_id == entity_id,
        EntityRelation.child_id == child.id
    ).first()
    
    if existing_relation:
        # Update quantity on existing relation
        existing_relation.quantity += child_data.quantity
        if child_data.price_snapshot:
            existing_relation.price_snapshot = child_data.price_snapshot
        if child_data.notes:
            existing_relation.notes = child_data.notes
        relation = existing_relation
    else:
        # Create new relation
        relation = EntityRelation(
            parent_id=entity_id,
            child_id=child.id,
            quantity=child_data.quantity,
            price_snapshot=child_data.price_snapshot or child.price,
            notes=child_data.notes
        )
        db.add(relation)
    
    # Remove from source if requested
    if child_data.remove_from_source:
        if child_data.quantity >= child.quantity:
            # Keep the entity but with 0 quantity? Or delete?
            # Keep it - it's referenced by the relation
            child.quantity = 0
        else:
            child.quantity -= child_data.quantity
    
    # Log history
    log_history(db, parent.id, EntityOperationType.ADD_CHILD, current_user.id,
               related_entity_id=child.id, details={"quantity": child_data.quantity})
    
    db.commit()
    db.refresh(relation)
    return relation


@router.delete("/{entity_id}/children/{relation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_child_from_entity(
    entity_id: int,
    relation_id: int,
    return_quantity: bool = Query(False, description="Return quantity back to child entity"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Remove a child relation from an entity."""
    relation = db.query(EntityRelation).filter(
        EntityRelation.id == relation_id,
        EntityRelation.parent_id == entity_id
    ).first()
    
    if not relation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relation not found"
        )
    
    # Return quantity if requested
    if return_quantity:
        child = db.query(Entity).filter(Entity.id == relation.child_id).first()
        if child:
            child.quantity += relation.quantity
    
    # Log history
    log_history(db, entity_id, EntityOperationType.REMOVE_CHILD, current_user.id,
               related_entity_id=relation.child_id, details={"quantity": relation.quantity})
    
    db.delete(relation)
    db.commit()
    return None


@router.put("/{entity_id}/children/{relation_id}", response_model=EntityRelationResponse)
async def update_child_relation(
    entity_id: int,
    relation_id: int,
    relation_update: EntityRelationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Update a child relation (quantity, notes, etc.)."""
    relation = db.query(EntityRelation).filter(
        EntityRelation.id == relation_id,
        EntityRelation.parent_id == entity_id
    ).first()
    
    if not relation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relation not found"
        )
    
    update_data = relation_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(relation, field, value)
    
    db.commit()
    db.refresh(relation)
    return relation


# ============================================================================
# History
# ============================================================================

@router.get("/{entity_id}/history", response_model=List[EntityHistoryResponse])
async def get_entity_history(
    entity_id: int,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get operation history for an entity."""
    entity = db.query(Entity).filter(Entity.id == entity_id).first()
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found"
        )
    
    history = db.query(EntityHistory).filter(
        EntityHistory.entity_id == entity_id
    ).order_by(EntityHistory.created_at.desc()).offset(skip).limit(limit).all()
    
    return history


# ============================================================================
# Export/Import
# ============================================================================

@router.get("/export/csv")
async def export_entities_csv(
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Export entities to CSV file."""
    query = db.query(Entity)
    if entity_type:
        query = query.filter(Entity.entity_type == entity_type)
    entities = query.all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'barcode', 'origin_barcode', 'name', 'description', 'entity_type',
        'quantity', 'price', 'status', 'warehouse_id', 'parent_barcode'
    ])
    
    # Write data
    for entity in entities:
        parent_barcode = ""
        if entity.parent_id:
            parent = db.query(Entity).filter(Entity.id == entity.parent_id).first()
            parent_barcode = parent.barcode if parent else ""
        
        writer.writerow([
            entity.barcode,
            entity.origin_barcode or '',
            entity.name,
            entity.description or '',
            entity.entity_type,
            entity.quantity,
            entity.price if entity.price is not None else '',
            entity.status or '',
            entity.warehouse_id or '',
            parent_barcode
        ])
    
    output.seek(0)
    filename = f"entities-{entity_type}.csv" if entity_type else "entities.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/import/csv")
async def import_entities_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Import entities from CSV file."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV"
        )
    
    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))
    
    created = 0
    updated = 0
    errors = []
    
    for row_num, row in enumerate(reader, start=2):
        try:
            barcode = row.get('barcode', '').strip()
            name = row.get('name', '').strip()
            entity_type = row.get('entity_type', '').strip()
            
            if not barcode or not name or not entity_type:
                errors.append(f"Row {row_num}: barcode, name, and entity_type are required")
                continue
            
            # Validate entity type
            type_obj = db.query(EntityType).filter(EntityType.code == entity_type).first()
            if not type_obj:
                errors.append(f"Row {row_num}: Invalid entity type '{entity_type}'")
                continue
            
            # Parse optional fields
            description = row.get('description', '').strip() or None
            origin_barcode = row.get('origin_barcode', '').strip() or None
            quantity = int(row.get('quantity', 1) or 1)
            price_str = row.get('price', '').strip()
            price = float(price_str) if price_str else None
            status_val = row.get('status', '').strip() or None
            warehouse_id_str = row.get('warehouse_id', '').strip()
            warehouse_id = int(warehouse_id_str) if warehouse_id_str else None
            parent_barcode = row.get('parent_barcode', '').strip()
            
            # Resolve parent
            parent_id = None
            if parent_barcode:
                parent = db.query(Entity).filter(Entity.barcode == parent_barcode).first()
                if parent:
                    parent_id = parent.id
                else:
                    errors.append(f"Row {row_num}: Parent with barcode '{parent_barcode}' not found")
                    continue
            
            # Check if entity exists
            existing = db.query(Entity).filter(Entity.barcode == barcode).first()
            if existing:
                existing.name = name
                existing.description = description
                existing.origin_barcode = origin_barcode
                existing.entity_type = entity_type
                existing.quantity = quantity
                existing.price = price
                existing.status = status_val
                existing.warehouse_id = warehouse_id
                existing.parent_id = parent_id
                updated += 1
            else:
                new_entity = Entity(
                    barcode=barcode,
                    name=name,
                    description=description,
                    origin_barcode=origin_barcode,
                    entity_type=entity_type,
                    quantity=quantity,
                    price=price,
                    status=status_val,
                    warehouse_id=warehouse_id,
                    parent_id=parent_id
                )
                db.add(new_entity)
                created += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    db.commit()
    
    return {
        "created": created,
        "updated": updated,
        "errors": errors
    }
