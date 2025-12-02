from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.inventory_check import InventoryCheck, CheckItem, CheckStatus
from app.models.item import Item
from app.models.box import Box
from app.schemas.inventory_check import (
    InventoryCheckCreate, InventoryCheckUpdate, InventoryCheckResponse,
    InventoryCheckSummary, InventoryCheckGrouped, BoxCheckGroup,
    CheckItemResponse, CheckItemUpdate, CheckComparison
)
from app.auth import get_current_user, require_role, get_user_from_token
from app.models.user import User, UserRole

router = APIRouter(prefix="/checks", tags=["inventory-checks"])


@router.get("/", response_model=List[InventoryCheckSummary])
async def list_checks(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all inventory checks with summary info."""
    query = db.query(InventoryCheck)
    
    if status:
        query = query.filter(InventoryCheck.status == status)
    
    checks = query.order_by(InventoryCheck.started_at.desc()).all()
    
    result = []
    for check in checks:
        total_items = len(check.check_items)
        checked_items = sum(1 for item in check.check_items if item.actual_quantity is not None)
        items_with_diff = sum(
            1 for item in check.check_items 
            if item.actual_quantity is not None and item.actual_quantity != item.expected_quantity
        )
        
        result.append(InventoryCheckSummary(
            id=check.id,
            name=check.name,
            description=check.description,
            status=check.status,
            started_at=check.started_at,
            completed_at=check.completed_at,
            total_items=total_items,
            checked_items=checked_items,
            items_with_difference=items_with_diff
        ))
    
    return result


@router.post("/", response_model=InventoryCheckResponse)
async def create_check(
    check_data: InventoryCheckCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMINISTRATOR, UserRole.MANAGER]))
):
    """Create a new inventory check and populate with current items."""
    # Create the check
    check = InventoryCheck(
        name=check_data.name,
        description=check_data.description,
        status=CheckStatus.in_progress,
        created_by=current_user.id
    )
    db.add(check)
    db.flush()  # Get the ID
    
    # Get all items and add them to the check
    items = db.query(Item).all()
    for item in items:
        box = db.query(Box).filter(Box.id == item.box_id).first()
        check_item = CheckItem(
            check_id=check.id,
            item_id=item.id,
            item_barcode=item.barcode,
            item_name=item.name,
            box_id=item.box_id,
            box_name=box.name if box else None,
            expected_quantity=item.quantity,
            price=item.price
        )
        db.add(check_item)
    
    db.commit()
    db.refresh(check)
    return check


@router.get("/active", response_model=Optional[InventoryCheckGrouped])
async def get_active_check(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the currently active (in_progress) check, grouped by box."""
    check = db.query(InventoryCheck).filter(
        InventoryCheck.status == CheckStatus.in_progress
    ).first()
    
    if not check:
        return None
    
    return _group_check_by_box(check)


@router.get("/{check_id}", response_model=InventoryCheckResponse)
async def get_check(
    check_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific inventory check."""
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    return check


@router.get("/{check_id}/grouped", response_model=InventoryCheckGrouped)
async def get_check_grouped(
    check_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a check with items grouped by box."""
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    return _group_check_by_box(check)


def _group_check_by_box(check: InventoryCheck) -> InventoryCheckGrouped:
    """Helper to group check items by box."""
    box_groups = {}
    
    for item in check.check_items:
        box_key = item.box_id or 0  # Use 0 for items without box
        box_name = item.box_name or "No Box"
        
        if box_key not in box_groups:
            box_groups[box_key] = {
                "box_id": item.box_id,
                "box_name": box_name,
                "items": [],
                "total_items": 0,
                "checked_items": 0
            }
        
        box_groups[box_key]["items"].append(CheckItemResponse(
            id=item.id,
            check_id=item.check_id,
            item_id=item.item_id,
            item_barcode=item.item_barcode,
            item_name=item.item_name,
            box_id=item.box_id,
            box_name=item.box_name,
            expected_quantity=item.expected_quantity,
            actual_quantity=item.actual_quantity,
            price=item.price,
            checked_at=item.checked_at,
            difference=item.actual_quantity - item.expected_quantity if item.actual_quantity is not None else None
        ))
        box_groups[box_key]["total_items"] += 1
        if item.actual_quantity is not None:
            box_groups[box_key]["checked_items"] += 1
    
    boxes = [
        BoxCheckGroup(
            box_id=data["box_id"],
            box_name=data["box_name"],
            total_items=data["total_items"],
            checked_items=data["checked_items"],
            items=sorted(data["items"], key=lambda x: x.item_name)
        )
        for data in sorted(box_groups.values(), key=lambda x: x["box_name"])
    ]
    
    return InventoryCheckGrouped(
        id=check.id,
        name=check.name,
        description=check.description,
        status=check.status,
        started_at=check.started_at,
        completed_at=check.completed_at,
        boxes=boxes
    )


@router.put("/{check_id}", response_model=InventoryCheckResponse)
async def update_check(
    check_id: int,
    check_data: InventoryCheckUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMINISTRATOR, UserRole.MANAGER]))
):
    """Update check metadata."""
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    if check_data.name is not None:
        check.name = check_data.name
    if check_data.description is not None:
        check.description = check_data.description
    
    db.commit()
    db.refresh(check)
    return check


@router.post("/{check_id}/complete", response_model=InventoryCheckResponse)
async def complete_check(
    check_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMINISTRATOR, UserRole.MANAGER]))
):
    """Mark a check as completed."""
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    if check.status != CheckStatus.in_progress:
        raise HTTPException(status_code=400, detail="Check is not in progress")
    
    check.status = CheckStatus.completed
    check.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(check)
    return check


@router.post("/{check_id}/cancel", response_model=InventoryCheckResponse)
async def cancel_check(
    check_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMINISTRATOR, UserRole.MANAGER]))
):
    """Cancel a check."""
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    if check.status != CheckStatus.in_progress:
        raise HTTPException(status_code=400, detail="Check is not in progress")
    
    check.status = CheckStatus.cancelled
    check.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(check)
    return check


@router.delete("/{check_id}")
async def delete_check(
    check_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMINISTRATOR]))
):
    """Delete a check (admin only)."""
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    db.delete(check)
    db.commit()
    return {"message": "Check deleted"}


# Check Item endpoints
@router.put("/{check_id}/items/{item_id}", response_model=CheckItemResponse)
async def update_check_item(
    check_id: int,
    item_id: int,
    item_data: CheckItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMINISTRATOR, UserRole.MANAGER]))
):
    """Update the actual quantity for an item in a check."""
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    if check.status != CheckStatus.in_progress:
        raise HTTPException(status_code=400, detail="Check is not in progress")
    
    check_item = db.query(CheckItem).filter(
        CheckItem.check_id == check_id,
        CheckItem.item_id == item_id
    ).first()
    
    if not check_item:
        raise HTTPException(status_code=404, detail="Item not in this check")
    
    check_item.actual_quantity = item_data.actual_quantity
    check_item.checked_at = datetime.utcnow()
    
    db.commit()
    db.refresh(check_item)
    
    response = CheckItemResponse(
        id=check_item.id,
        check_id=check_item.check_id,
        item_id=check_item.item_id,
        item_barcode=check_item.item_barcode,
        item_name=check_item.item_name,
        box_id=check_item.box_id,
        box_name=check_item.box_name,
        expected_quantity=check_item.expected_quantity,
        actual_quantity=check_item.actual_quantity,
        price=check_item.price,
        checked_at=check_item.checked_at,
        difference=check_item.actual_quantity - check_item.expected_quantity if check_item.actual_quantity is not None else None
    )
    return response


@router.post("/{check_id}/items/barcode/{barcode}", response_model=CheckItemResponse)
async def check_item_by_barcode(
    check_id: int,
    barcode: str,
    item_data: CheckItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMINISTRATOR, UserRole.MANAGER]))
):
    """Update an item in a check by barcode."""
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    if check.status != CheckStatus.in_progress:
        raise HTTPException(status_code=400, detail="Check is not in progress")
    
    check_item = db.query(CheckItem).filter(
        CheckItem.check_id == check_id,
        CheckItem.item_barcode == barcode
    ).first()
    
    if not check_item:
        raise HTTPException(status_code=404, detail="Item not in this check")
    
    check_item.actual_quantity = item_data.actual_quantity
    check_item.checked_at = datetime.utcnow()
    
    db.commit()
    db.refresh(check_item)
    
    response = CheckItemResponse(
        id=check_item.id,
        check_id=check_item.check_id,
        item_id=check_item.item_id,
        item_barcode=check_item.item_barcode,
        item_name=check_item.item_name,
        box_id=check_item.box_id,
        box_name=check_item.box_name,
        expected_quantity=check_item.expected_quantity,
        actual_quantity=check_item.actual_quantity,
        price=check_item.price,
        checked_at=check_item.checked_at,
        difference=check_item.actual_quantity - check_item.expected_quantity if check_item.actual_quantity is not None else None
    )
    return response


@router.get("/{check_id}/compare/{previous_check_id}", response_model=List[CheckComparison])
async def compare_checks(
    check_id: int,
    previous_check_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compare two checks to see differences."""
    current_check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    previous_check = db.query(InventoryCheck).filter(InventoryCheck.id == previous_check_id).first()
    
    if not current_check or not previous_check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    # Build lookup for previous check items
    previous_items = {item.item_id: item for item in previous_check.check_items}
    
    comparisons = []
    for current_item in current_check.check_items:
        prev_item = previous_items.get(current_item.item_id)
        
        change_since_last = None
        if prev_item and prev_item.actual_quantity is not None:
            # Change = what system says now vs what we counted last time
            change_since_last = current_item.expected_quantity - prev_item.actual_quantity
        
        comparisons.append(CheckComparison(
            item_id=current_item.item_id,
            item_barcode=current_item.item_barcode,
            item_name=current_item.item_name,
            box_name=current_item.box_name,
            previous_expected=prev_item.expected_quantity if prev_item else None,
            previous_actual=prev_item.actual_quantity if prev_item else None,
            current_expected=current_item.expected_quantity,
            current_actual=current_item.actual_quantity,
            change_since_last=change_since_last
        ))
    
    return comparisons


@router.post("/{check_id}/apply-corrections")
async def apply_corrections(
    check_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMINISTRATOR]))
):
    """Apply the actual quantities from the check to update inventory (admin only)."""
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    if check.status != CheckStatus.completed:
        raise HTTPException(status_code=400, detail="Check must be completed before applying corrections")
    
    corrections_made = 0
    for check_item in check.check_items:
        if check_item.actual_quantity is not None and check_item.actual_quantity != check_item.expected_quantity:
            item = db.query(Item).filter(Item.id == check_item.item_id).first()
            if item:
                item.quantity = check_item.actual_quantity
                corrections_made += 1
    
    db.commit()
    return {"message": f"Applied {corrections_made} corrections to inventory"}


@router.get("/{check_id}/export", response_class=HTMLResponse)
async def export_check_for_print(
    check_id: int,
    token: str,
    db: Session = Depends(get_db)
):
    """Export inventory check as printable HTML with barcodes."""
    # Authenticate via query parameter token
    current_user = await get_user_from_token(token, db)
    
    check = db.query(InventoryCheck).filter(InventoryCheck.id == check_id).first()
    if not check:
        raise HTTPException(status_code=404, detail="Check not found")
    
    # Group items by box
    box_groups = {}
    for item in check.check_items:
        box_key = item.box_id or 0
        box_name = item.box_name or "No Box"
        if box_key not in box_groups:
            # Get box barcode
            box_barcode = ""
            if item.box_id:
                box = db.query(Box).filter(Box.id == item.box_id).first()
                if box:
                    box_barcode = box.barcode
            box_groups[box_key] = {
                "name": box_name,
                "barcode": box_barcode,
                "items": []
            }
        box_groups[box_key]["items"].append(item)
    
    # Sort items within each box by name
    for box in box_groups.values():
        box["items"].sort(key=lambda x: x.item_name)
    
    # Build HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Inventory Check: {check.name}</title>
    <script src="https://cdn.jsdelivr.net/npm/jsbarcode@3.11.6/dist/JsBarcode.all.min.js"></script>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: Arial, sans-serif;
            font-size: 11pt;
            margin: 0;
            padding: 20px;
        }}
        h1 {{
            font-size: 18pt;
            margin-bottom: 5px;
        }}
        .meta {{
            color: #666;
            margin-bottom: 20px;
            font-size: 10pt;
        }}
        .box-section {{
            margin-bottom: 30px;
            page-break-inside: avoid;
        }}
        .box-header {{
            background: #f0f0f0;
            padding: 10px;
            border: 1px solid #ccc;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .box-title {{
            font-weight: bold;
            font-size: 14pt;
        }}
        .box-barcode svg {{
            height: 40px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 0;
        }}
        th, td {{
            border: 1px solid #ccc;
            padding: 6px 8px;
            text-align: left;
        }}
        th {{
            background: #f8f8f8;
            font-weight: bold;
        }}
        .item-name {{
            width: 35%;
        }}
        .item-expected {{
            width: 10%;
            text-align: center;
        }}
        .item-actual {{
            width: 15%;
            text-align: center;
        }}
        .item-actual-input {{
            border: 1px solid #999;
            min-height: 20px;
        }}
        .item-barcode {{
            width: 30%;
            text-align: right;
        }}
        .item-barcode svg {{
            height: 35px;
        }}
        .no-barcode {{
            color: #999;
            font-style: italic;
        }}
        @media print {{
            body {{
                padding: 10px;
            }}
            .box-section {{
                page-break-inside: avoid;
            }}
            .no-print {{
                display: none;
            }}
        }}
        .print-btn {{
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 20px;
            background: #3498db;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }}
        .print-btn:hover {{
            background: #2980b9;
        }}
    </style>
</head>
<body>
    <button class="print-btn no-print" onclick="window.print()">🖨️ Print</button>
    
    <h1>Inventory Check: {check.name}</h1>
    <div class="meta">
        Started: {check.started_at.strftime('%Y-%m-%d %H:%M') if check.started_at else 'N/A'} | 
        Status: {check.status.value if hasattr(check.status, 'value') else check.status} |
        Total Items: {len(check.check_items)}
    </div>
"""
    
    # Add each box section
    for box_key in sorted(box_groups.keys()):
        box = box_groups[box_key]
        box_barcode_html = ""
        if box["barcode"]:
            box_barcode_html = f'<div class="box-barcode"><svg class="barcode-box" data-barcode="{box["barcode"]}"></svg></div>'
        
        html += f"""
    <div class="box-section">
        <div class="box-header">
            <span class="box-title">📦 {box["name"]}</span>
            {box_barcode_html}
        </div>
        <table>
            <thead>
                <tr>
                    <th class="item-name">Item</th>
                    <th class="item-expected">Expected</th>
                    <th class="item-actual">Actual</th>
                    <th class="item-barcode">Barcode</th>
                </tr>
            </thead>
            <tbody>
"""
        
        for item in box["items"]:
            barcode_html = f'<svg class="barcode-item" data-barcode="{item.item_barcode}"></svg>' if item.item_barcode else '<span class="no-barcode">No barcode</span>'
            
            html += f"""
                <tr>
                    <td class="item-name">{item.item_name}</td>
                    <td class="item-expected">{item.expected_quantity}</td>
                    <td class="item-actual item-actual-input"></td>
                    <td class="item-barcode">{barcode_html}</td>
                </tr>
"""
        
        html += """
            </tbody>
        </table>
    </div>
"""
    
    # Add barcode generation script
    html += """
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Generate box barcodes
            document.querySelectorAll('.barcode-box').forEach(function(svg) {
                const code = svg.getAttribute('data-barcode');
                if (code) {
                    try {
                        JsBarcode(svg, code, {
                            format: "CODE128",
                            width: 1.5,
                            height: 40,
                            displayValue: true,
                            fontSize: 10,
                            margin: 0
                        });
                    } catch (e) {
                        svg.outerHTML = '<span class="no-barcode">' + code + '</span>';
                    }
                }
            });
            
            // Generate item barcodes
            document.querySelectorAll('.barcode-item').forEach(function(svg) {
                const code = svg.getAttribute('data-barcode');
                if (code) {
                    try {
                        JsBarcode(svg, code, {
                            format: "CODE128",
                            width: 1.2,
                            height: 35,
                            displayValue: true,
                            fontSize: 9,
                            margin: 0
                        });
                    } catch (e) {
                        svg.outerHTML = '<span class="no-barcode">' + code + '</span>';
                    }
                }
            });
        });
    </script>
</body>
</html>
"""
    
    return HTMLResponse(content=html)
