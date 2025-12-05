"""Barcode lookup routes."""
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth import require_viewer
from app.models.user import User
from app.services.barcode_lookup import lookup_barcode, lookup_barcode_all, ProductInfo

router = APIRouter(prefix="/barcode-lookup", tags=["Barcode Lookup"])


class ProductInfoResponse(BaseModel):
    """Response schema for product info."""
    name: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    source: Optional[str] = None
    confidence: float = 0.0


class BarcodeLookupResponse(BaseModel):
    """Response schema for barcode lookup."""
    barcode: str
    found: bool
    product: Optional[ProductInfoResponse] = None
    alternatives: List[ProductInfoResponse] = []


@router.get("/{barcode}", response_model=BarcodeLookupResponse)
async def lookup_product_barcode(
    barcode: str,
    current_user: User = Depends(require_viewer)
):
    """
    Look up product information from free online databases.
    
    Searches multiple free databases:
    - Open Food Facts (food/consumer products)
    - Open Library (books by ISBN)
    - UPC Database (general products)
    
    Returns the best match and alternative results.
    """
    if not barcode or len(barcode) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Barcode must be at least 8 characters"
        )
    
    # Get all results
    all_results = await lookup_barcode_all(barcode)
    
    if not all_results:
        return BarcodeLookupResponse(
            barcode=barcode,
            found=False,
            product=None,
            alternatives=[]
        )
    
    # Best match is first (highest confidence)
    best_match = all_results[0]
    alternatives = all_results[1:] if len(all_results) > 1 else []
    
    return BarcodeLookupResponse(
        barcode=barcode,
        found=True,
        product=ProductInfoResponse(
            name=best_match.name,
            description=best_match.description,
            brand=best_match.brand,
            category=best_match.category,
            image_url=best_match.image_url,
            source=best_match.source,
            confidence=best_match.confidence
        ),
        alternatives=[
            ProductInfoResponse(
                name=p.name,
                description=p.description,
                brand=p.brand,
                category=p.category,
                image_url=p.image_url,
                source=p.source,
                confidence=p.confidence
            )
            for p in alternatives
        ]
    )


@router.get("/quick/{barcode}")
async def quick_lookup(
    barcode: str,
    current_user: User = Depends(require_viewer)
):
    """
    Quick lookup - returns just the best match for faster response.
    Useful for auto-fill suggestions.
    """
    if not barcode or len(barcode) < 8:
        return {"found": False, "barcode": barcode}
    
    result = await lookup_barcode(barcode)
    
    if not result:
        return {"found": False, "barcode": barcode}
    
    return {
        "found": True,
        "barcode": barcode,
        "name": result.name,
        "description": result.description,
        "brand": result.brand,
        "source": result.source
    }
