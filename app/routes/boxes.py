"""Box routes."""
from typing import List, Optional
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import require_manager, require_viewer
from app.database import get_db
from app.models.user import User
from app.models.box import Box
from app.models.warehouse import Warehouse
from app.schemas.box import BoxCreate, BoxResponse, BoxUpdate, BoxWithItems

router = APIRouter(prefix="/boxes", tags=["Boxes"])


@router.get("/", response_model=List[BoxResponse])
async def list_boxes(
    skip: int = 0,
    limit: int = 100,
    warehouse_id: Optional[int] = Query(None, description="Filter by warehouse"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """List all boxes, optionally filtered by warehouse."""
    query = db.query(Box)
    if warehouse_id:
        query = query.filter(Box.warehouse_id == warehouse_id)
    boxes = query.offset(skip).limit(limit).all()
    return boxes


@router.post("/", response_model=BoxResponse, status_code=status.HTTP_201_CREATED)
async def create_box(
    box_data: BoxCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Create a new box (manager or admin)."""
    # Check if warehouse exists
    warehouse = db.query(Warehouse).filter(Warehouse.id == box_data.warehouse_id).first()
    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found"
        )
    
    # Check if barcode is unique
    existing = db.query(Box).filter(Box.barcode == box_data.barcode).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Barcode already exists"
        )
    
    db_box = Box(**box_data.model_dump())
    db.add(db_box)
    db.commit()
    db.refresh(db_box)
    return db_box


@router.get("/barcode/{barcode}", response_model=BoxWithItems)
async def get_box_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get a box by its barcode."""
    box = db.query(Box).filter(Box.barcode == barcode).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Box not found"
        )
    return box


@router.get("/{box_id}", response_model=BoxWithItems)
async def get_box(
    box_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get a specific box with its items."""
    box = db.query(Box).filter(Box.id == box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Box not found"
        )
    return box


@router.put("/{box_id}", response_model=BoxResponse)
async def update_box(
    box_id: int,
    box_update: BoxUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Update a box (manager or admin)."""
    box = db.query(Box).filter(Box.id == box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Box not found"
        )
    
    # Check if new warehouse exists
    if box_update.warehouse_id:
        warehouse = db.query(Warehouse).filter(Warehouse.id == box_update.warehouse_id).first()
        if not warehouse:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Warehouse not found"
            )
    
    # Check if new barcode is unique
    if box_update.barcode and box_update.barcode != box.barcode:
        existing = db.query(Box).filter(Box.barcode == box_update.barcode).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Barcode already exists"
            )
    
    update_data = box_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(box, field, value)
    
    db.commit()
    db.refresh(box)
    return box


@router.delete("/{box_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_box(
    box_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Delete a box (manager or admin)."""
    box = db.query(Box).filter(Box.id == box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Box not found"
        )
    
    # Check if box has items
    if box.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete box with items. Remove all items first."
        )
    
    db.delete(box)
    db.commit()
    return None


@router.post("/{box_id}/move/{target_warehouse_id}", response_model=BoxResponse)
async def move_box(
    box_id: int,
    target_warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Move a box to a different warehouse (manager or admin)."""
    box = db.query(Box).filter(Box.id == box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Box not found"
        )
    
    warehouse = db.query(Warehouse).filter(Warehouse.id == target_warehouse_id).first()
    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target warehouse not found"
        )
    
    box.warehouse_id = target_warehouse_id
    db.commit()
    db.refresh(box)
    return box


@router.get("/export/csv")
async def export_boxes_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Export all boxes to CSV file."""
    boxes = db.query(Box).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow(['barcode', 'name', 'description', 'warehouse_name'])
    
    # Write data
    for box in boxes:
        warehouse = db.query(Warehouse).filter(Warehouse.id == box.warehouse_id).first()
        writer.writerow([
            box.barcode,
            box.name,
            box.description or '',
            warehouse.name if warehouse else ''
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=boxes.csv"}
    )


@router.post("/import/csv")
async def import_boxes_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Import boxes from CSV file. Creates new boxes or updates existing by barcode."""
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
            warehouse_name = row.get('warehouse_name', '').strip()
            
            if not barcode or not name:
                errors.append(f"Row {row_num}: barcode and name are required")
                continue
            
            # Find warehouse by name
            warehouse = db.query(Warehouse).filter(Warehouse.name == warehouse_name).first()
            if not warehouse:
                errors.append(f"Row {row_num}: Warehouse '{warehouse_name}' not found")
                continue
            
            # Check if box exists
            existing = db.query(Box).filter(Box.barcode == barcode).first()
            if existing:
                existing.name = name
                existing.description = description
                existing.warehouse_id = warehouse.id
                updated += 1
            else:
                new_box = Box(
                    barcode=barcode,
                    name=name,
                    description=description,
                    warehouse_id=warehouse.id
                )
                db.add(new_box)
                created += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    db.commit()
    
    return {
        "created": created,
        "updated": updated,
        "errors": errors
    }
