"""Barcode lookup service - queries free online databases for product information."""
import asyncio
import re
from typing import Optional
from dataclasses import dataclass
import httpx


@dataclass
class ProductInfo:
    """Product information from barcode lookup."""
    name: Optional[str] = None
    description: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    source: Optional[str] = None
    confidence: float = 0.0  # 0.0 to 1.0
    
    def to_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "brand": self.brand,
            "category": self.category,
            "image_url": self.image_url,
            "source": self.source,
            "confidence": self.confidence
        }


def is_isbn(barcode: str) -> bool:
    """Check if barcode is likely an ISBN (book)."""
    # ISBN-10 or ISBN-13
    clean = barcode.replace("-", "").replace(" ", "")
    if len(clean) == 10:
        # ISBN-10: 9 digits + check digit (digit or X)
        return clean[:9].isdigit() and (clean[9].isdigit() or clean[9].upper() == 'X')
    elif len(clean) == 13:
        # ISBN-13: starts with 978 or 979
        return clean.isdigit() and clean.startswith(('978', '979'))
    return False


def is_ean13(barcode: str) -> bool:
    """Check if barcode is EAN-13 format."""
    clean = barcode.replace("-", "").replace(" ", "")
    return len(clean) == 13 and clean.isdigit()


def is_upc(barcode: str) -> bool:
    """Check if barcode is UPC-A format (12 digits)."""
    clean = barcode.replace("-", "").replace(" ", "")
    return len(clean) == 12 and clean.isdigit()


async def lookup_open_food_facts(barcode: str) -> Optional[ProductInfo]:
    """
    Look up product in Open Food Facts database.
    Free, open source database for food products worldwide.
    https://world.openfoodfacts.org/
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            url = f"https://world.openfoodfacts.org/api/v2/product/{barcode}.json"
            response = await client.get(url, headers={
                "User-Agent": "SimpleInventory/1.0 (https://github.com/simple-inventory)"
            })
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if data.get("status") != 1:
                return None
            
            product = data.get("product", {})
            
            # Build name from available fields
            name = product.get("product_name") or product.get("product_name_en")
            brand = product.get("brands")
            
            if not name:
                return None
            
            # Build description
            desc_parts = []
            if product.get("quantity"):
                desc_parts.append(product.get("quantity"))
            if product.get("categories"):
                # Take first category
                cats = product.get("categories", "").split(",")
                if cats:
                    desc_parts.append(cats[0].strip())
            
            description = ", ".join(desc_parts) if desc_parts else None
            
            # Get image
            image_url = product.get("image_front_small_url") or product.get("image_url")
            
            return ProductInfo(
                name=name,
                description=description,
                brand=brand,
                category=product.get("categories", "").split(",")[0].strip() if product.get("categories") else None,
                image_url=image_url,
                source="Open Food Facts",
                confidence=0.9 if name else 0.5
            )
    except Exception as e:
        print(f"Open Food Facts lookup error: {e}")
        return None


async def lookup_open_library(barcode: str) -> Optional[ProductInfo]:
    """
    Look up book by ISBN in Open Library.
    Free, open source database for books.
    https://openlibrary.org/
    """
    if not is_isbn(barcode):
        return None
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try ISBN API
            clean_isbn = barcode.replace("-", "").replace(" ", "")
            url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&jscmd=data&format=json"
            
            response = await client.get(url, headers={
                "User-Agent": "SimpleInventory/1.0"
            })
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            key = f"ISBN:{clean_isbn}"
            if key not in data:
                return None
            
            book = data[key]
            
            title = book.get("title")
            if not title:
                return None
            
            # Get authors
            authors = book.get("authors", [])
            author_names = ", ".join([a.get("name", "") for a in authors if a.get("name")])
            
            # Get publisher
            publishers = book.get("publishers", [])
            publisher = publishers[0].get("name") if publishers else None
            
            # Build description
            desc_parts = []
            if author_names:
                desc_parts.append(f"by {author_names}")
            if publisher:
                desc_parts.append(f"({publisher})")
            if book.get("publish_date"):
                desc_parts.append(book.get("publish_date"))
            
            # Get cover image
            cover = book.get("cover", {})
            image_url = cover.get("small") or cover.get("medium")
            
            return ProductInfo(
                name=title,
                description=" ".join(desc_parts) if desc_parts else None,
                brand=author_names or None,
                category="Books",
                image_url=image_url,
                source="Open Library",
                confidence=0.95
            )
    except Exception as e:
        print(f"Open Library lookup error: {e}")
        return None


async def lookup_upc_database(barcode: str) -> Optional[ProductInfo]:
    """
    Look up product in UPC Database (free tier).
    https://www.upcdatabase.com/
    Note: Limited free lookups, no API key needed for basic queries.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try the free UPC Item DB API
            url = f"https://api.upcitemdb.com/prod/trial/lookup?upc={barcode}"
            
            response = await client.get(url, headers={
                "User-Agent": "SimpleInventory/1.0",
                "Accept": "application/json"
            })
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            
            if data.get("code") != "OK":
                return None
            
            items = data.get("items", [])
            if not items:
                return None
            
            item = items[0]
            
            title = item.get("title")
            if not title:
                return None
            
            return ProductInfo(
                name=title,
                description=item.get("description"),
                brand=item.get("brand"),
                category=item.get("category"),
                image_url=item.get("images", [None])[0] if item.get("images") else None,
                source="UPC Database",
                confidence=0.85
            )
    except Exception as e:
        print(f"UPC Database lookup error: {e}")
        return None


async def lookup_ean_search(barcode: str) -> Optional[ProductInfo]:
    """
    Look up product using ean-search.org free tier.
    Limited to 10 lookups/day on free tier.
    """
    # This is a backup option - requires registration for API key
    # For now, we skip this as it requires an API key
    return None


async def lookup_barcode(barcode: str) -> Optional[ProductInfo]:
    """
    Look up a barcode in multiple free databases.
    Tries multiple sources in parallel and returns the best match.
    """
    if not barcode:
        return None
    
    # Clean the barcode
    clean_barcode = barcode.strip().replace("-", "").replace(" ", "")
    
    # Validate barcode format
    if not clean_barcode.isdigit() and not is_isbn(barcode):
        return None
    
    # For ISBN, prioritize Open Library
    if is_isbn(barcode):
        tasks = [
            lookup_open_library(barcode),
            lookup_open_food_facts(clean_barcode),  # Fallback
        ]
    else:
        # For EAN/UPC, try product databases
        tasks = [
            lookup_open_food_facts(clean_barcode),
            lookup_upc_database(clean_barcode),
        ]
    
    # Run lookups in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out errors and None results
    valid_results = [r for r in results if isinstance(r, ProductInfo) and r.name]
    
    if not valid_results:
        return None
    
    # Return the result with highest confidence
    return max(valid_results, key=lambda x: x.confidence)


async def lookup_barcode_all(barcode: str) -> list[ProductInfo]:
    """
    Look up a barcode in all available databases.
    Returns all found results sorted by confidence.
    """
    if not barcode:
        return []
    
    clean_barcode = barcode.strip().replace("-", "").replace(" ", "")
    
    tasks = [
        lookup_open_library(barcode),
        lookup_open_food_facts(clean_barcode),
        lookup_upc_database(clean_barcode),
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out errors and None results
    valid_results = [r for r in results if isinstance(r, ProductInfo) and r.name]
    
    # Sort by confidence descending
    valid_results.sort(key=lambda x: x.confidence, reverse=True)
    
    return valid_results
