"""Supplier pattern routes."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin, require_viewer
from app.database import get_db
from app.models.user import User
from app.models.supplier_pattern import SupplierPattern
from app.schemas.supplier_pattern import (
    SupplierPatternCreate,
    SupplierPatternUpdate,
    SupplierPatternResponse,
    SupplierPatternMatch
)

router = APIRouter(prefix="/supplier-patterns", tags=["Supplier Patterns"])


def barcode_matches_pattern(barcode: str, pattern: str) -> bool:
    """
    Check if a barcode matches the given pattern.
    
    Pattern syntax:
    - # : matches a single digit (0-9)
    - * : matches any single character
    - $ : matches any character or none (optional character)
    - Other characters: literal match (case-insensitive for letters)
    """
    if not pattern or not barcode:
        return False
    
    # Use recursive matching to handle $ (optional character)
    return _match_pattern(barcode.upper(), pattern.upper(), 0, 0)


def _match_pattern(barcode: str, pattern: str, b_idx: int, p_idx: int) -> bool:
    """Recursive pattern matching helper."""
    # If we've consumed the entire pattern
    if p_idx >= len(pattern):
        return b_idx >= len(barcode)
    
    pat_char = pattern[p_idx]
    
    if pat_char == '$':
        # $ matches zero or one character
        # Try matching zero characters
        if _match_pattern(barcode, pattern, b_idx, p_idx + 1):
            return True
        # Try matching one character
        if b_idx < len(barcode) and _match_pattern(barcode, pattern, b_idx + 1, p_idx + 1):
            return True
        return False
    
    # For non-$ characters, we need a barcode character to match
    if b_idx >= len(barcode):
        return False
    
    bc_char = barcode[b_idx]
    
    if pat_char == '#':
        if not bc_char.isdigit():
            return False
    elif pat_char == '*':
        pass  # Any character matches
    else:
        if bc_char != pat_char:
            return False
    
    return _match_pattern(barcode, pattern, b_idx + 1, p_idx + 1)


@router.get("/", response_model=List[SupplierPatternResponse])
async def list_supplier_patterns(
    enabled_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """List all supplier patterns."""
    query = db.query(SupplierPattern)
    if enabled_only:
        query = query.filter(SupplierPattern.enabled == True)
    return query.order_by(SupplierPattern.name).all()


@router.get("/match/{barcode}", response_model=SupplierPatternMatch)
async def match_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """
    Check if a barcode matches any supplier pattern.
    Returns the matching supplier and search URL if found.
    """
    patterns = db.query(SupplierPattern).filter(SupplierPattern.enabled == True).all()
    
    for pattern in patterns:
        if barcode_matches_pattern(barcode, pattern.pattern):
            # Substitute {barcode} placeholder in URL
            search_url = pattern.search_url.replace("{barcode}", barcode)
            return SupplierPatternMatch(
                barcode=barcode,
                matched=True,
                supplier=pattern,
                search_url=search_url
            )
    
    return SupplierPatternMatch(
        barcode=barcode,
        matched=False,
        supplier=None,
        search_url=None
    )


@router.get("/{pattern_id}", response_model=SupplierPatternResponse)
async def get_supplier_pattern(
    pattern_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get a specific supplier pattern by ID."""
    pattern = db.query(SupplierPattern).filter(SupplierPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier pattern not found"
        )
    return pattern


@router.post("/", response_model=SupplierPatternResponse, status_code=status.HTTP_201_CREATED)
async def create_supplier_pattern(
    pattern_data: SupplierPatternCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new supplier pattern (admin only)."""
    # Validate URL contains {barcode} placeholder
    if "{barcode}" not in pattern_data.search_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search URL must contain {barcode} placeholder"
        )
    
    pattern = SupplierPattern(**pattern_data.model_dump())
    db.add(pattern)
    db.commit()
    db.refresh(pattern)
    return pattern


@router.put("/{pattern_id}", response_model=SupplierPatternResponse)
async def update_supplier_pattern(
    pattern_id: int,
    pattern_update: SupplierPatternUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a supplier pattern (admin only)."""
    pattern = db.query(SupplierPattern).filter(SupplierPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier pattern not found"
        )
    
    update_data = pattern_update.model_dump(exclude_unset=True)
    
    # Validate URL contains {barcode} placeholder if being updated
    if "search_url" in update_data and "{barcode}" not in update_data["search_url"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search URL must contain {barcode} placeholder"
        )
    
    for field, value in update_data.items():
        setattr(pattern, field, value)
    
    db.commit()
    db.refresh(pattern)
    return pattern


@router.delete("/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier_pattern(
    pattern_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete a supplier pattern (admin only)."""
    pattern = db.query(SupplierPattern).filter(SupplierPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supplier pattern not found"
        )
    
    db.delete(pattern)
    db.commit()


@router.post("/test")
async def test_pattern(
    pattern: str,
    barcode: str,
    current_user: User = Depends(require_viewer)
):
    """Test if a barcode matches a pattern."""
    matches = barcode_matches_pattern(barcode, pattern)
    return {
        "pattern": pattern,
        "barcode": barcode,
        "matches": matches,
        "message": f"Barcode '{barcode}' {'matches' if matches else 'does NOT match'} pattern '{pattern}'"
    }
