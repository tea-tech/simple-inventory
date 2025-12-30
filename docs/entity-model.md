# Unified Entity Model

This document describes the unified entity model used for inventory management.

## Overview

The inventory system uses a single unified `Entity` model to represent all types of inventory objects:
- **Items**: Basic inventory items (products, components, materials)
- **Containers**: Storage containers (boxes, bins, shelves, racks)
- **Packages**: Collections of items for orders or production

This unified approach allows:
- Seamless conversion between types
- Hierarchical nesting (containers within containers)
- Consistent operations across all entity types
- Full history tracking for all operations

## Database Schema

### Entity Table

```
entities
├── id (PK)
├── barcode (unique) - Global unique identifier
├── origin_barcode - Original EAN/UPC/ISBN if applicable
├── name
├── description
├── entity_type - References entity_types.code
├── quantity - Quantity of this entity
├── price - Price per unit
├── warehouse_id (FK) - Direct warehouse location
├── parent_id (FK, self) - Parent entity (for nesting)
├── custom_fields (JSON) - Extensible custom data
├── status - Workflow status
├── created_at
└── updated_at
```

### Entity Relation Table

For tracking "how many of entity X are in entity Y" (e.g., package contents):

```
entity_relations
├── id (PK)
├── parent_id (FK) - The containing entity
├── child_id (FK) - The contained entity
├── quantity - How many of the child are in this relation
├── price_snapshot - Price at time of relation
├── notes
└── created_at
```

### Entity History Table

```
entity_history
├── id (PK)
├── entity_id (FK)
├── operation - Operation type (create, update, move, convert, etc.)
├── related_entity_id - Related entity if applicable
├── details (JSON) - Operation details
├── user_id (FK) - Who performed the operation
└── created_at
```

### Entity Type Table

```
entity_types
├── id (PK)
├── code (unique) - Type identifier (item, container, package)
├── name - Display name
├── description
├── icon - Emoji or icon code
├── color - Hex color for UI
├── can_contain_children - Whether this type can have children
├── can_be_child - Whether this type can be nested
├── allowed_parent_types (JSON) - Types this can be child of
├── allowed_child_types (JSON) - Types this can contain
├── visible_fields (JSON) - Fields shown in UI
├── required_fields (JSON) - Required fields for creation
├── available_statuses (JSON) - Valid status values
├── default_status - Default status on creation
├── sort_order - UI ordering
├── is_active - Can create new entities
├── is_builtin - System type (cannot delete)
├── created_at
└── updated_at
```

## Default Entity Types

### Item (`item`)
- **Purpose**: Basic inventory item (leaf node)
- **Can contain children**: No
- **Can be child**: Yes
- **Visible fields**: barcode, origin_barcode, name, description, quantity, price
- **Statuses**: None (items don't have workflow status)

### Container (`container`)
- **Purpose**: Storage container (box, bin, shelf, rack)
- **Can contain children**: Yes
- **Can be child**: Yes (for nesting containers)
- **Visible fields**: barcode, name, description
- **Statuses**: None

### Package (`package`)
- **Purpose**: Collection of items for orders or production
- **Can contain children**: Yes
- **Can be child**: No
- **Visible fields**: barcode, name, description, status
- **Statuses**: new, sourcing, packed, done, cancelled

## Hierarchy

Entities can be organized in a hierarchy:

```
Warehouse
├── Container (box)
│   ├── Item
│   ├── Item
│   └── Container (inner box)
│       └── Item
├── Container (shelf)
│   ├── Container (bin)
│   │   └── Item
│   └── Item
└── Package
    └── [Items via relations]
```

### Location Rules

1. An entity is either:
   - In a warehouse directly (`warehouse_id` set, `parent_id` null)
   - Inside another entity (`parent_id` set, `warehouse_id` null)
   - Neither (for packages or unassigned entities)

2. Packages typically don't have a physical location (they reference items via relations)

## Operations

### CRUD Operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/entities` | GET | List entities (with filters) |
| `/api/entities` | POST | Create entity |
| `/api/entities/{id}` | GET | Get entity with children |
| `/api/entities/{id}` | PUT | Update entity |
| `/api/entities/{id}` | DELETE | Delete entity |
| `/api/entities/barcode/{barcode}` | GET | Get by barcode |

### Movement & Transformation

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/entities/{id}/move` | POST | Move to different location |
| `/api/entities/{id}/convert` | POST | Convert to different type |
| `/api/entities/{id}/split` | POST | Split quantity into new entity |
| `/api/entities/{id}/merge` | POST | Merge other entities into this |
| `/api/entities/{id}/quantity` | POST | Adjust quantity |

### Child Management (Relations)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/entities/{id}/children` | GET | List children (via relations) |
| `/api/entities/{id}/children` | POST | Add child with quantity |
| `/api/entities/{id}/children/{relation_id}` | PUT | Update relation |
| `/api/entities/{id}/children/{relation_id}` | DELETE | Remove child |

### History

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/entities/{id}/history` | GET | Get operation history |

## Workflow Examples

### 1. Product Production Workflow

```
1. Source items and sort to containers
   POST /api/entities {"entity_type": "item", "parent_id": <container_id>, ...}

2. Create package with needed items
   POST /api/entities {"entity_type": "package", "name": "Order #123", ...}
   POST /api/entities/{package_id}/children {"child_barcode": "...", "quantity": 5}

3. Convert package to item (finished product)
   POST /api/entities/{package_id}/convert {"new_type": "item"}

4. Create shipping package
   POST /api/entities {"entity_type": "package", "name": "Shipment #456", ...}
   POST /api/entities/{shipment_id}/children {"child_id": <product_id>, ...}

5. Mark as done (sold/shipped)
   PUT /api/entities/{shipment_id} {"status": "done"}
```

### 2. Revert/Modify Workflow

```
1. Convert product back to package
   POST /api/entities/{product_id}/convert {"new_type": "package"}

2. Modify contents
   DELETE /api/entities/{package_id}/children/{relation_id}?return_quantity=true
   POST /api/entities/{package_id}/children {"child_barcode": "...", "quantity": 3}

3. Convert back to product
   POST /api/entities/{package_id}/convert {"new_type": "item"}
```

### 3. Container Reorganization

```
1. Move item to different container
   POST /api/entities/{item_id}/move {"target_parent_id": <new_container_id>}

2. Split item quantity
   POST /api/entities/{item_id}/split {"quantity": 10, "new_barcode": "...", "target_parent_id": <other_container>}

3. Merge items
   POST /api/entities/{target_id}/merge {"source_entity_ids": [1, 2, 3]}
```

## Entity Type Management

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/entity-types` | GET | List all types |
| `/api/entity-types` | POST | Create new type (admin) |
| `/api/entity-types/{code}` | GET | Get type details |
| `/api/entity-types/{code}` | PUT | Update type (admin) |
| `/api/entity-types/{code}` | DELETE | Delete type (admin) |
| `/api/entity-types/{code}/activate` | POST | Activate type |
| `/api/entity-types/{code}/deactivate` | POST | Deactivate type |

### Creating Custom Types

```json
POST /api/entity-types
{
  "code": "rack",
  "name": "Storage Rack",
  "description": "Large storage rack",
  "icon": "🗄️",
  "color": "#9C27B0",
  "can_contain_children": true,
  "can_be_child": false,
  "allowed_child_types": ["container"],
  "visible_fields": ["barcode", "name", "description"],
  "required_fields": ["barcode", "name"]
}
```

## History Operations

The following operations are tracked:

| Operation | Description |
|-----------|-------------|
| `create` | Entity created |
| `update` | Entity properties modified |
| `delete` | Entity deleted |
| `move` | Entity moved to different parent/warehouse |
| `convert` | Entity type changed |
| `add_child` | Child entity added |
| `remove_child` | Child entity removed |
| `split` | Entity split into two |
| `merge` | Entities merged |
| `quantity_change` | Quantity adjusted |

## Barcode Uniqueness

All barcodes in the system are globally unique across all entity types. This ensures:
- Any barcode scan returns a single, unambiguous result
- No confusion between items, containers, and packages
- Simple lookups via `/api/entities/barcode/{barcode}`

## Migration from Old Model

The old model with separate `items`, `boxes`, and `packages` tables has been replaced by the unified `entities` table.

### Mapping

| Old Model | New Entity Type |
|-----------|-----------------|
| `Item` | `entity_type = "item"` |
| `Box` | `entity_type = "container"` |
| `Package` | `entity_type = "package"` |
| `PackageItem` | `EntityRelation` |

### Key Differences

1. **Single table**: All entities in one table with `entity_type` field
2. **Flexible nesting**: Containers can contain other containers
3. **Type conversion**: Entities can be converted between types
4. **Configurable types**: New types can be added without code changes
5. **Full history**: All operations are logged
