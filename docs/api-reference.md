# API Reference

This document provides a complete reference for the Simple Inventory API.

## Authentication

All API endpoints (except `/api/auth/login`) require authentication via JWT token.

Include the token in the `Authorization` header:
```
Authorization: Bearer <token>
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Login and get token |
| `/api/auth/me` | GET | Get current user info |

## Entities

The core of the inventory system. See [Entity Model](entity-model.md) for details.

### List Entities

```
GET /api/entities
```

Query Parameters:
- `skip` (int): Pagination offset
- `limit` (int): Max results (default 100)
- `entity_type` (string): Filter by type (item, container, package)
- `warehouse_id` (int): Filter by warehouse
- `parent_id` (int): Filter by parent entity
- `root_only` (bool): Only entities without parent
- `search` (string): Search name, barcode, description
- `status_filter` (string): Filter by status

### Create Entity

```
POST /api/entities
```

Body:
```json
{
  "barcode": "string (required, unique)",
  "name": "string (required)",
  "description": "string (optional)",
  "entity_type": "string (required: item, container, package)",
  "quantity": 1,
  "price": null,
  "status": "string (optional)",
  "warehouse_id": null,
  "parent_id": null,
  "origin_barcode": null,
  "custom_fields": {}
}
```

### Get Entity

```
GET /api/entities/{entity_id}
GET /api/entities/barcode/{barcode}
```

Returns entity with children and relations.

### Update Entity

```
PUT /api/entities/{entity_id}
```

Body: Same as create (all fields optional).

### Delete Entity

```
DELETE /api/entities/{entity_id}?force=false
```

Parameters:
- `force` (bool): Delete even if has children

### Move Entity

```
POST /api/entities/{entity_id}/move
```

Body:
```json
{
  "target_warehouse_id": null,
  "target_parent_id": null,
  "quantity": null  // Split if less than total
}
```

### Convert Entity Type

```
POST /api/entities/{entity_id}/convert
```

Body:
```json
{
  "new_type": "string (required)",
  "new_status": "string (optional)"
}
```

### Split Entity

```
POST /api/entities/{entity_id}/split
```

Body:
```json
{
  "quantity": 10,
  "new_barcode": "string (required, unique)",
  "target_warehouse_id": null,
  "target_parent_id": null
}
```

### Merge Entities

```
POST /api/entities/{entity_id}/merge
```

Body:
```json
{
  "source_entity_ids": [1, 2, 3]
}
```

### Adjust Quantity

```
POST /api/entities/{entity_id}/quantity?adjustment=5
```

Parameters:
- `adjustment` (int, required): Positive to add, negative to remove

### Child Management

```
GET /api/entities/{entity_id}/children
POST /api/entities/{entity_id}/children
PUT /api/entities/{entity_id}/children/{relation_id}
DELETE /api/entities/{entity_id}/children/{relation_id}?return_quantity=false
```

Add child body:
```json
{
  "child_barcode": "string",
  "child_id": null,
  "quantity": 1,
  "remove_from_source": true,
  "price_snapshot": null,
  "notes": null
}
```

### History

```
GET /api/entities/{entity_id}/history?skip=0&limit=50
```

### Export/Import

```
GET /api/entities/export/csv?entity_type=item
POST /api/entities/import/csv
```

## Entity Types

### List Types

```
GET /api/entity-types?include_inactive=false
```

### Create Type (Admin)

```
POST /api/entity-types
```

Body:
```json
{
  "code": "string (required, unique)",
  "name": "string (required)",
  "description": null,
  "icon": "📦",
  "color": "#808080",
  "can_contain_children": false,
  "can_be_child": true,
  "allowed_parent_types": [],
  "allowed_child_types": [],
  "visible_fields": [],
  "required_fields": [],
  "available_statuses": [],
  "default_status": null,
  "sort_order": 0,
  "is_active": true
}
```

### Get/Update/Delete Type

```
GET /api/entity-types/{type_code}
PUT /api/entity-types/{type_code}
DELETE /api/entity-types/{type_code}
```

### Activate/Deactivate

```
POST /api/entity-types/{type_code}/activate
POST /api/entity-types/{type_code}/deactivate
```

## Warehouses

### List Warehouses

```
GET /api/warehouses
```

### Create Warehouse (Admin)

```
POST /api/warehouses
```

Body:
```json
{
  "name": "string (required)",
  "description": null,
  "location": null
}
```

### Get/Update/Delete Warehouse

```
GET /api/warehouses/{warehouse_id}
PUT /api/warehouses/{warehouse_id}
DELETE /api/warehouses/{warehouse_id}
```

## Inventory Checks

### List Checks

```
GET /api/checks?status=in_progress
```

### Create Check (Manager+)

```
POST /api/checks
```

Body:
```json
{
  "name": "string (required)",
  "description": null
}
```

Creates check populated with all item-type entities.

### Get Check

```
GET /api/checks/{check_id}
GET /api/checks/{check_id}/grouped
GET /api/checks/active
```

### Update Check

```
PUT /api/checks/{check_id}
```

### Check Actions

```
POST /api/checks/{check_id}/complete
POST /api/checks/{check_id}/cancel
DELETE /api/checks/{check_id}  (Admin only)
```

### Check Items

```
PUT /api/checks/{check_id}/items/{item_id}
POST /api/checks/{check_id}/items/barcode/{barcode}
```

Body:
```json
{
  "actual_quantity": 10
}
```

### Compare Checks

```
GET /api/checks/{check_id}/compare/{previous_check_id}
```

### Apply Corrections (Admin)

```
POST /api/checks/{check_id}/apply-corrections
```

### Export for Print

```
GET /api/checks/{check_id}/export?token={jwt_token}
```

## Users

### List Users (Admin)

```
GET /api/users
```

### Create User (Admin)

```
POST /api/users
```

Body:
```json
{
  "username": "string (required)",
  "email": "string (required)",
  "password": "string (required)",
  "role": "viewer|manager|administrator"
}
```

### Get/Update/Delete User

```
GET /api/users/{user_id}
PUT /api/users/{user_id}
DELETE /api/users/{user_id}
```

## Settings

### Get Setting

```
GET /api/settings/{key}
```

### Update Setting (Admin)

```
PUT /api/settings/{key}
```

Body:
```json
{
  "value": "string"
}
```

### List Settings

```
GET /api/settings
```

## Barcode Lookup

```
GET /api/barcode/lookup/{barcode}
```

Looks up product info from external databases.

## Supplier Patterns

### List Patterns

```
GET /api/supplier-patterns
```

### CRUD Operations

```
POST /api/supplier-patterns
GET /api/supplier-patterns/{pattern_id}
PUT /api/supplier-patterns/{pattern_id}
DELETE /api/supplier-patterns/{pattern_id}
```

### Match Barcode

```
GET /api/supplier-patterns/match/{barcode}
```

## Role Permissions

| Role | Permissions |
|------|-------------|
| `viewer` | Read-only access |
| `manager` | Create, update, delete entities and checks |
| `administrator` | Full access including users, settings, entity types |

## Error Responses

All errors return JSON:

```json
{
  "detail": "Error message"
}
```

Common status codes:
- `400`: Bad request (validation error)
- `401`: Unauthorized (missing/invalid token)
- `403`: Forbidden (insufficient permissions)
- `404`: Not found
- `500`: Internal server error
