"""Item routes."""
from typing import List, Optional
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import require_manager, require_viewer
from app.database import get_db
from app.models.user import User
from app.models.item import Item
from app.models.box import Box
from app.schemas.item import ItemCreate, ItemResponse, ItemUpdate, ItemMove

router = APIRouter(prefix="/items", tags=["Items"])


@router.get("/", response_model=List[ItemResponse])
async def list_items(
    skip: int = 0,
    limit: int = 100,
    box_id: Optional[int] = Query(None, description="Filter by box"),
    search: Optional[str] = Query(None, description="Search by name or description"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """List all items, optionally filtered by box or search term."""
    query = db.query(Item)
    
    if box_id:
        query = query.filter(Item.box_id == box_id)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Item.name.ilike(search_term)) | 
            (Item.description.ilike(search_term)) |
            (Item.barcode.ilike(search_term))
        )
    
    items = query.offset(skip).limit(limit).all()
    return items


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    item_data: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Create a new item (manager or admin) - stores item in a box."""
    # Check if box exists
    box = db.query(Box).filter(Box.id == item_data.box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Box not found"
        )
    
    # Check if barcode is unique
    existing = db.query(Item).filter(Item.barcode == item_data.barcode).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Barcode already exists"
        )
    
    db_item = Item(**item_data.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/barcode/{barcode}", response_model=ItemResponse)
async def get_item_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get an item by its barcode."""
    item = db.query(Item).filter(Item.barcode == barcode).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    return item


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get a specific item."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    return item


@router.put("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    item_update: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Update an item (manager or admin)."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    # Check if new box exists
    if item_update.box_id:
        box = db.query(Box).filter(Box.id == item_update.box_id).first()
        if not box:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Box not found"
            )
    
    # Check if new barcode is unique
    if item_update.barcode and item_update.barcode != item.barcode:
        existing = db.query(Item).filter(Item.barcode == item_update.barcode).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Barcode already exists"
            )
    
    update_data = item_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)
    
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Delete an item (manager or admin) - takes item out of inventory."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    db.delete(item)
    db.commit()
    return None


@router.post("/{item_id}/move", response_model=ItemResponse)
async def move_item(
    item_id: int,
    move_data: ItemMove,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Move an item to a different box (manager or admin)."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    target_box = db.query(Box).filter(Box.id == move_data.target_box_id).first()
    if not target_box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target box not found"
        )
    
    # If quantity specified and less than total, split the item
    if move_data.quantity and move_data.quantity < item.quantity:
        # Create new item in target box with specified quantity
        new_item = Item(
            barcode=f"{item.barcode}-split-{item.id}",
            name=item.name,
            description=item.description,
            quantity=move_data.quantity,
            box_id=move_data.target_box_id
        )
        db.add(new_item)
        
        # Reduce quantity in original item
        item.quantity -= move_data.quantity
        db.commit()
        db.refresh(new_item)
        return new_item
    else:
        # Move entire item
        item.box_id = move_data.target_box_id
        db.commit()
        db.refresh(item)
        return item


@router.post("/{item_id}/take", response_model=ItemResponse)
async def take_item(
    item_id: int,
    quantity: int = Query(1, description="Quantity to take"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Take items from inventory (reduce quantity or remove)."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    if quantity > item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot take {quantity} items. Only {item.quantity} available."
        )
    
    if quantity == item.quantity:
        # Remove item entirely
        db.delete(item)
        db.commit()
        # Return empty response with 204
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail="Item fully taken from inventory"
        )
    
    item.quantity -= quantity
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/store", response_model=ItemResponse)
async def store_item(
    item_id: int,
    quantity: int = Query(1, description="Quantity to store/add"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Store more items (increase quantity)."""
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    item.quantity += quantity
    db.commit()
    db.refresh(item)
    return item


@router.get("/export/csv")
async def export_items_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Export all items to CSV file."""
    items = db.query(Item).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['barcode', 'name', 'description', 'quantity', 'price', 'box_barcode'])
    
    # Write data
    for item in items:
        box = db.query(Box).filter(Box.id == item.box_id).first()
        writer.writerow([
            item.barcode,
            item.name,
            item.description or '',
            item.quantity,
            item.price if item.price is not None else '',
            box.barcode if box else ''
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=items.csv"}
    )


@router.post("/import/csv")
async def import_items_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Import items from CSV file. Creates new items or updates existing by barcode."""
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
            description = row.get('description', '').strip() or None
            quantity = int(row.get('quantity', 1) or 1)
            price_str = row.get('price', '').strip()
            price = float(price_str) if price_str else None
            box_barcode = row.get('box_barcode', '').strip()
            
            if not barcode or not name:
                errors.append(f"Row {row_num}: barcode and name are required")
                continue
            
            # Find box by barcode
            box = db.query(Box).filter(Box.barcode == box_barcode).first()
            if not box:
                errors.append(f"Row {row_num}: Box with barcode '{box_barcode}' not found")
                continue
            
            # Check if item exists
            existing = db.query(Item).filter(Item.barcode == barcode).first()
            if existing:
                existing.name = name
                existing.description = description
                existing.quantity = quantity
                existing.price = price
                existing.box_id = box.id
                updated += 1
            else:
                new_item = Item(
                    barcode=barcode,
                    name=name,
                    description=description,
                    quantity=quantity,
                    price=price,
                    box_id=box.id
                )
                db.add(new_item)
                created += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    db.commit()
    
    return {
        "created": created,
        "updated": updated,
        "errors": errors
    }
