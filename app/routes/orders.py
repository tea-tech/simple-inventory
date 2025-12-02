"""Order routes."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.auth import require_manager, require_viewer
from app.database import get_db
from app.models.user import User
from app.models.order import Order, OrderItem, OrderStatus
from app.models.item import Item
from app.models.box import Box
from app.schemas.order import (
    OrderCreate, OrderResponse, OrderUpdate, OrderSummary,
    OrderItemCreate, OrderItemResponse
)

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("/", response_model=List[OrderSummary])
async def list_orders(
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """List all orders with summary info."""
    query = db.query(Order)
    
    if status_filter:
        query = query.filter(Order.status == status_filter)
    
    orders = query.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for order in orders:
        item_count = len(order.order_items)
        total_quantity = sum(oi.quantity for oi in order.order_items)
        result.append(OrderSummary(
            id=order.id,
            barcode=order.barcode,
            name=order.name,
            status=order.status,
            item_count=item_count,
            total_quantity=total_quantity,
            created_at=order.created_at
        ))
    
    return result


@router.post("/", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Create a new order."""
    # Check if barcode is unique
    existing = db.query(Order).filter(Order.barcode == order_data.barcode).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order barcode already exists"
        )
    
    db_order = Order(**order_data.model_dump())
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    return db_order


@router.get("/barcode/{barcode}", response_model=OrderResponse)
async def get_order_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get an order by its barcode."""
    order = db.query(Order).filter(Order.barcode == barcode).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    return order


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get a specific order with all items."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    return order


@router.put("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: int,
    order_update: OrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Update an order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    update_data = order_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(order, field, value)
    
    db.commit()
    db.refresh(order)
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Delete an order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    db.delete(order)
    db.commit()
    return None


@router.post("/{order_id}/items", response_model=OrderItemResponse)
async def add_item_to_order(
    order_id: int,
    item_data: OrderItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Add an item to an order (removes from inventory)."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    if order.status in [OrderStatus.PACKED.value, OrderStatus.DONE.value, OrderStatus.CANCELLED.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot add items to order with status '{order.status}'"
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
    
    # Create order item
    order_item = OrderItem(
        order_id=order_id,
        item_id=item.id,
        item_barcode=item.barcode,
        item_name=item.name,
        source_box_id=item.box_id,
        source_box_name=box.name if box else None,
        quantity=item_data.quantity,
        price=item.price
    )
    db.add(order_item)
    
    # Remove from inventory
    if item_data.quantity >= item.quantity:
        db.delete(item)
    else:
        item.quantity -= item_data.quantity
    
    # Update order status to sourcing if it was new
    if order.status == OrderStatus.NEW.value:
        order.status = OrderStatus.SOURCING.value
    
    db.commit()
    db.refresh(order_item)
    return order_item


@router.delete("/{order_id}/items/{order_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item_from_order(
    order_id: int,
    order_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Remove an item from an order (does NOT return to inventory)."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    order_item = db.query(OrderItem).filter(
        OrderItem.id == order_item_id,
        OrderItem.order_id == order_id
    ).first()
    
    if not order_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order item not found"
        )
    
    db.delete(order_item)
    
    # Update status back to new if no items left
    remaining = db.query(OrderItem).filter(OrderItem.order_id == order_id).count()
    if remaining <= 1:  # This one is being deleted
        order.status = OrderStatus.NEW.value
    
    db.commit()
    return None


@router.post("/{order_id}/pack", response_model=OrderResponse)
async def pack_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Mark order as packed (ACTION:DONE on order)."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    if order.status == OrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot pack a cancelled order"
        )
    
    order.status = OrderStatus.PACKED.value
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/complete", response_model=OrderResponse)
async def complete_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Mark order as done/completed."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    order.status = OrderStatus.DONE.value
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Cancel an order (does NOT return items to inventory automatically)."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    if order.status == OrderStatus.DONE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel a completed order"
        )
    
    order.status = OrderStatus.CANCELLED.value
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/return-item/{order_item_id}", response_model=OrderItemResponse)
async def return_item_to_inventory(
    order_id: int,
    order_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Return an item from a cancelled order back to inventory."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    if order.status != OrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only return items from cancelled orders"
        )
    
    order_item = db.query(OrderItem).filter(
        OrderItem.id == order_item_id,
        OrderItem.order_id == order_id
    ).first()
    
    if not order_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order item not found"
        )
    
    # Check if source box still exists
    if not order_item.source_box_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source box information not available"
        )
    
    box = db.query(Box).filter(Box.id == order_item.source_box_id).first()
    if not box:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source box no longer exists"
        )
    
    # Check if original item still exists
    existing_item = db.query(Item).filter(Item.barcode == order_item.item_barcode).first()
    
    if existing_item:
        # Add quantity back to existing item
        existing_item.quantity += order_item.quantity
    else:
        # Create new item
        new_item = Item(
            barcode=order_item.item_barcode,
            name=order_item.item_name,
            quantity=order_item.quantity,
            price=order_item.price,
            box_id=order_item.source_box_id
        )
        db.add(new_item)
    
    # Remove from order
    db.delete(order_item)
    db.commit()
    
    return order_item


@router.post("/{order_id}/return-all")
async def return_all_items_to_inventory(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager)
):
    """Return all items from a cancelled order back to inventory."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    if order.status != OrderStatus.CANCELLED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only return items from cancelled orders"
        )
    
    returned = 0
    errors = []
    
    for order_item in order.order_items[:]:  # Copy list to avoid modification during iteration
        try:
            if not order_item.source_box_id:
                errors.append(f"{order_item.item_name}: No source box info")
                continue
            
            box = db.query(Box).filter(Box.id == order_item.source_box_id).first()
            if not box:
                errors.append(f"{order_item.item_name}: Source box no longer exists")
                continue
            
            existing_item = db.query(Item).filter(Item.barcode == order_item.item_barcode).first()
            
            if existing_item:
                existing_item.quantity += order_item.quantity
            else:
                new_item = Item(
                    barcode=order_item.item_barcode,
                    name=order_item.item_name,
                    quantity=order_item.quantity,
                    price=order_item.price,
                    box_id=order_item.source_box_id
                )
                db.add(new_item)
            
            db.delete(order_item)
            returned += 1
        except Exception as e:
            errors.append(f"{order_item.item_name}: {str(e)}")
    
    db.commit()
    
    return {
        "returned": returned,
        "errors": errors
    }
