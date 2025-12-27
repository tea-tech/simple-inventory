"""Package routes - replaces Order routes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.auth import require_manager, require_viewer
from app.database import get_db
from app.models.user import User
from app.models.package import Package, PackageItem, PackageStatus
from app.models.item import Item
from app.models.box import Box
from app.models.warehouse import Warehouse
from app.schemas.package import (
    PackageCreate, PackageResponse, PackageUpdate, PackageSummary,
    PackageItemCreate, PackageItemResponse
)

router = APIRouter(prefix="/packages", tags=["Packages"])


@router.get("/", response_model=List[PackageSummary])
async def list_packages(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """List all packages with summary info."""
    query = db.query(Package)
    
    if status_filter:
        query = query.filter(Package.status == status_filter)
    
    packages = query.order_by(Package.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for package in packages:
        item_count = len(package.package_items)
        total_quantity = sum(pi.quantity for pi in package.package_items)
        result.append(PackageSummary(
            id=package.id,
            barcode=package.barcode,
            name=package.name,
            status=package.status,
            item_count=item_count,
            total_quantity=total_quantity,
            created_at=package.created_at
        ))
    
    return result


@router.post("/", response_model=PackageResponse, status_code=status.HTTP_201_CREATED)
async def create_package(
    package_data: PackageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Create a new package."""
    # Check if barcode is unique
    existing = db.query(Package).filter(Package.barcode == package_data.barcode).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Package barcode already exists"
        )
    
    db_package = Package(**package_data.model_dump())
    db.add(db_package)
    db.commit()
    db.refresh(db_package)
    return db_package


@router.get("/barcode/{barcode}", response_model=PackageResponse)
async def get_package_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get a package by its barcode."""
    package = db.query(Package).filter(Package.barcode == barcode).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    return package


@router.get("/{package_id}", response_model=PackageResponse)
async def get_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get a specific package with all items."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    return package


@router.put("/{package_id}", response_model=PackageResponse)
async def update_package(
    package_id: int,
    package_update: PackageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Update a package."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    update_data = package_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(package, field, value)
    
    db.commit()
    db.refresh(package)
    return package


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Delete a package."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    db.delete(package)
    db.commit()
    return None


@router.post("/{package_id}/items", response_model=PackageItemResponse)
async def add_item_to_package(
    package_id: int,
    item_data: PackageItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Add an item to a package (removes from inventory)."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    if package.status in [PackageStatus.PACKED.value, PackageStatus.DONE.value, PackageStatus.CANCELLED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot add items to package with status '{package.status}'"
        )
    
    item = db.query(Item).filter(Item.id == item_data.item_id).first()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found"
        )
    
    if item_data.quantity > item.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot add {item_data.quantity} items. Only {item.quantity} available."
        )
    
    # Get source box info
    box = db.query(Box).filter(Box.id == item.box_id).first()
    
    # Create package item
    package_item = PackageItem(
        package_id=package_id,
        item_id=item.id,
        item_barcode=item.barcode,
        item_name=item.name,
        source_box_id=item.box_id,
        source_box_name=box.name if box else None,
        quantity=item_data.quantity,
        price=item.price
    )
    db.add(package_item)
    
    # Remove from inventory
    if item_data.quantity >= item.quantity:
        db.delete(item)
    else:
        item.quantity -= item_data.quantity
    
    # Update package status to sourcing if it was new
    if package.status == PackageStatus.NEW.value:
        package.status = PackageStatus.SOURCING.value
    
    db.commit()
    db.refresh(package_item)
    return package_item


@router.delete("/{package_id}/items/{package_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item_from_package(
    package_id: int,
    package_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Remove an item from a package (does NOT return to inventory)."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    package_item = db.query(PackageItem).filter(
        PackageItem.id == package_item_id,
        PackageItem.package_id == package_id
    ).first()
    
    if not package_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package item not found"
        )
    
    db.delete(package_item)
    
    # Update status back to new if no items left
    remaining = db.query(PackageItem).filter(PackageItem.package_id == package_id).count()
    if remaining <= 1:  # This one is being deleted
        package.status = PackageStatus.NEW.value
    
    db.commit()
    return None


@router.post("/{package_id}/pack", response_model=PackageResponse)
async def pack_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Mark package as packed (ACT:OK on package)."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    if package.status == PackageStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot pack a cancelled package"
        )
    
    package.status = PackageStatus.PACKED.value
    db.commit()
    db.refresh(package)
    return package


@router.post("/{package_id}/complete", response_model=PackageResponse)
async def complete_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Mark package as done/completed."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    package.status = PackageStatus.DONE.value
    db.commit()
    db.refresh(package)
    return package


@router.post("/{package_id}/cancel", response_model=PackageResponse)
async def cancel_package(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Cancel a package (does NOT return items to inventory automatically)."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    if package.status == PackageStatus.DONE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel a completed package"
        )
    
    package.status = PackageStatus.CANCELLED.value
    db.commit()
    db.refresh(package)
    return package


@router.post("/{package_id}/return-item/{package_item_id}", response_model=PackageItemResponse)
async def return_item_to_inventory(
    package_id: int,
    package_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Return an item from a cancelled package back to inventory."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    if package.status != PackageStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only return items from cancelled packages"
        )
    
    package_item = db.query(PackageItem).filter(
        PackageItem.id == package_item_id,
        PackageItem.package_id == package_id
    ).first()
    
    if not package_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package item not found"
        )
    
    # Check if source box still exists
    if not package_item.source_box_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source box information not available"
        )
    
    box = db.query(Box).filter(Box.id == package_item.source_box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source box no longer exists"
        )
    
    # Check if original item still exists
    existing_item = db.query(Item).filter(Item.barcode == package_item.item_barcode).first()
    
    if existing_item:
        # Add quantity back to existing item
        existing_item.quantity += package_item.quantity
    else:
        # Create new item
        new_item = Item(
            barcode=package_item.item_barcode,
            name=package_item.item_name,
            quantity=package_item.quantity,
            price=package_item.price,
            box_id=package_item.source_box_id
        )
        db.add(new_item)
    
    # Remove from package
    db.delete(package_item)
    db.commit()
    
    return package_item


@router.post("/{package_id}/return-all")
async def return_all_items_to_inventory(
    package_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Return all items from a cancelled package back to inventory."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    if package.status != PackageStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only return items from cancelled packages"
        )
    
    returned = 0
    errors = []
    
    for package_item in package.package_items[:]:  # Copy list to avoid modification during iteration
        try:
            if not package_item.source_box_id:
                errors.append(f"{package_item.item_name}: No source box info")
                continue
            
            box = db.query(Box).filter(Box.id == package_item.source_box_id).first()
            if not box:
                errors.append(f"{package_item.item_name}: Source box no longer exists")
                continue
            
            existing_item = db.query(Item).filter(Item.barcode == package_item.item_barcode).first()
            
            if existing_item:
                existing_item.quantity += package_item.quantity
            else:
                new_item = Item(
                    barcode=package_item.item_barcode,
                    name=package_item.item_name,
                    quantity=package_item.quantity,
                    price=package_item.price,
                    box_id=package_item.source_box_id
                )
                db.add(new_item)
            
            db.delete(package_item)
            returned += 1
        except Exception as e:
            errors.append(f"{package_item.item_name}: {str(e)}")
    
    db.commit()
    
    return {
        "returned": returned,
        "errors": errors
    }


@router.post("/{package_id}/convert-to-box")
async def convert_package_to_box(
    package_id: int,
    warehouse_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Convert a package to a box. Creates new box with same barcode/name, moves items to box, deletes package."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    # Check warehouse exists
    warehouse = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not warehouse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Warehouse not found"
        )
    
    # Check barcode not used by existing box
    existing_box = db.query(Box).filter(Box.barcode == package.barcode).first()
    if existing_box:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Box with barcode '{package.barcode}' already exists"
        )
    
    # Create new box with same barcode and name
    new_box = Box(
        barcode=package.barcode,
        name=package.name,
        description=package.description,
        warehouse_id=warehouse_id
    )
    db.add(new_box)
    db.flush()  # Get the box ID
    
    # Convert package items to real items in the box
    items_created = 0
    for package_item in package.package_items:
        # Check if item with this barcode already exists
        existing_item = db.query(Item).filter(Item.barcode == package_item.item_barcode).first()
        if existing_item:
            # Add quantity to existing item
            existing_item.quantity += package_item.quantity
        else:
            # Create new item in the new box
            new_item = Item(
                barcode=package_item.item_barcode,
                name=package_item.item_name,
                quantity=package_item.quantity,
                price=package_item.price,
                box_id=new_box.id
            )
            db.add(new_item)
        items_created += 1
    
    # Delete the package (cascade deletes package_items)
    db.delete(package)
    db.commit()
    db.refresh(new_box)
    
    return {
        "success": True,
        "box_id": new_box.id,
        "box_barcode": new_box.barcode,
        "box_name": new_box.name,
        "items_moved": items_created,
        "message": f"Package converted to box '{new_box.name}' with {items_created} items"
    }


@router.post("/{package_id}/convert-to-item")
async def convert_package_to_item(
    package_id: int,
    box_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Convert a package to an item. Packs the package and creates new item with package name/barcode."""
    package = db.query(Package).filter(Package.id == package_id).first()
    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found"
        )
    
    # Check box exists
    box = db.query(Box).filter(Box.id == box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Box not found"
        )
    
    # Check barcode not used by existing item
    existing_item = db.query(Item).filter(Item.barcode == package.barcode).first()
    if existing_item:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Item with barcode '{package.barcode}' already exists"
        )
    
    # Calculate total value from package items
    total_value = sum(
        (pi.price or 0) * pi.quantity 
        for pi in package.package_items
    )
    
    # Create new item with package barcode and name
    new_item = Item(
        barcode=package.barcode,
        name=package.name,
        description=package.description,
        quantity=1,  # The package becomes a single item
        price=total_value if total_value > 0 else None,
        box_id=box_id
    )
    db.add(new_item)
    
    # Mark package as packed/done (items already consumed)
    package.status = PackageStatus.PACKED.value
    
    db.commit()
    db.refresh(new_item)
    
    return {
        "success": True,
        "item_id": new_item.id,
        "item_barcode": new_item.barcode,
        "item_name": new_item.name,
        "message": f"Package converted to item '{new_item.name}' in box '{box.name}'"
    }
