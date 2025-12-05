"""Settings routes."""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_admin, require_viewer
from app.database import get_db
from app.models.user import User
from app.models.settings import Settings, SETTINGS_KEYS
from app.schemas.settings import (
    SettingResponse, 
    SettingUpdate, 
    AllSettingsResponse,
    BarcodePatternTest,
    BarcodePatternTestResult
)

router = APIRouter(prefix="/settings", tags=["Settings"])


def get_setting(db: Session, key: str) -> Optional[Settings]:
    """Get a setting by key."""
    return db.query(Settings).filter(Settings.key == key).first()


def get_setting_value(db: Session, key: str) -> str:
    """Get a setting value, returning default if not set."""
    setting = get_setting(db, key)
    if setting and setting.value is not None:
        return setting.value
    return SETTINGS_KEYS.get(key, {}).get("default", "")


def set_setting(db: Session, key: str, value: str) -> Settings:
    """Set a setting value."""
    setting = get_setting(db, key)
    if setting:
        setting.value = value
    else:
        setting = Settings(
            key=key,
            value=value,
            description=SETTINGS_KEYS.get(key, {}).get("description", "")
        )
        db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def barcode_matches_pattern(barcode: str, pattern: str) -> bool:
    """
    Check if a barcode matches the given pattern.
    
    Pattern syntax:
    - # : matches a single digit (0-9)
    - * : matches any single character
    - $ : matches any character or none (optional character)
    - Other characters: literal match
    
    Examples:
    - "######" matches any 6-digit number (000000-999999)
    - "INV-####" matches INV-0000 to INV-9999
    - "A*###" matches A followed by any char and 3 digits
    - "LA######$" matches LA150177 or LA150177M
    """
    if not pattern:
        return True  # No pattern means all barcodes are valid
    
    # Use recursive matching to handle $ (optional character)
    return _match_pattern(barcode, pattern, 0, 0)


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


def pattern_to_regex(pattern: str) -> str:
    """Convert barcode pattern to regex for display/validation."""
    if not pattern:
        return ".*"
    
    regex_parts = []
    for char in pattern:
        if char == '#':
            regex_parts.append('[0-9]')
        elif char == '*':
            regex_parts.append('.')
        elif char == '$':
            regex_parts.append('.?')  # Optional any character
        else:
            regex_parts.append(re.escape(char))
    
    return '^' + ''.join(regex_parts) + '$'


def generate_example_barcodes(pattern: str, count: int = 3) -> list[str]:
    """Generate example barcodes that match the pattern."""
    if not pattern:
        return ["ABC123", "XYZ789"]
    
    examples = []
    for i in range(count):
        example = ""
        digit_counter = i
        for char in pattern:
            if char == '#':
                example += str(digit_counter % 10)
                digit_counter += 1
            elif char == '*':
                example += chr(65 + (i % 26))  # A, B, C...
            elif char == '$':
                # For examples, sometimes include char, sometimes not
                if i % 2 == 0:
                    example += chr(65 + (i % 26))
                # else: skip (optional)
            else:
                example += char
        examples.append(example)
    
    return examples


@router.get("/", response_model=AllSettingsResponse)
async def get_all_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get all application settings."""
    return AllSettingsResponse(
        barcode_pattern=get_setting_value(db, "barcode_pattern"),
        auto_lookup_external=get_setting_value(db, "auto_lookup_external").lower() == "true"
    )


@router.get("/{key}", response_model=SettingResponse)
async def get_setting_by_key(
    key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """Get a specific setting by key."""
    if key not in SETTINGS_KEYS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown setting key: {key}"
        )
    
    setting = get_setting(db, key)
    if not setting:
        # Return default
        return SettingResponse(
            id=0,
            key=key,
            value=SETTINGS_KEYS[key]["default"],
            description=SETTINGS_KEYS[key]["description"],
            updated_at=None
        )
    return setting


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    setting_update: SettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update a setting (admin only)."""
    if key not in SETTINGS_KEYS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown setting key: {key}"
        )
    
    setting = set_setting(db, key, setting_update.value or "")
    return setting


@router.post("/test-pattern", response_model=BarcodePatternTestResult)
async def test_barcode_pattern(
    test_data: BarcodePatternTest,
    current_user: User = Depends(require_viewer)
):
    """Test if a barcode matches a pattern."""
    matches = barcode_matches_pattern(test_data.barcode, test_data.pattern)
    
    if not test_data.pattern:
        message = "No pattern set - all barcodes are accepted as internal"
        is_internal = True
    elif matches:
        message = f"Barcode '{test_data.barcode}' matches pattern '{test_data.pattern}'"
        is_internal = True
    else:
        message = f"Barcode '{test_data.barcode}' does NOT match pattern - will trigger external lookup"
        is_internal = False
    
    return BarcodePatternTestResult(
        pattern=test_data.pattern,
        barcode=test_data.barcode,
        matches=matches,
        is_internal=is_internal,
        message=message
    )


@router.get("/pattern/examples")
async def get_pattern_examples(
    pattern: str = "",
    current_user: User = Depends(require_viewer)
):
    """Get example barcodes for a pattern."""
    examples = generate_example_barcodes(pattern, 5)
    regex = pattern_to_regex(pattern)
    
    return {
        "pattern": pattern,
        "regex": regex,
        "examples": examples,
        "description": f"Pattern '{pattern}' will match barcodes like: {', '.join(examples)}"
    }


@router.post("/validate-barcode")
async def validate_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_viewer)
):
    """
    Validate a barcode against the configured pattern.
    Returns whether it's an internal barcode or external (EAN/UPC/ISBN).
    """
    pattern = get_setting_value(db, "barcode_pattern")
    is_internal = barcode_matches_pattern(barcode, pattern)
    
    return {
        "barcode": barcode,
        "pattern": pattern,
        "is_internal": is_internal,
        "should_lookup": not is_internal and get_setting_value(db, "auto_lookup_external").lower() == "true"
    }
