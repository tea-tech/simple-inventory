# Code Chains

A code chain is a sequence of barcode scans that performs an operation. The system interprets scans in order and guides the user through the flow.

> **Extensibility**: Each chain is defined independently. New chains can be added without modifying existing ones. See [action-codes.md](action-codes.md) for available codes.

---

## Entity Creation

When an unknown barcode is scanned, the system waits for a type code to determine what to create.

| Chain | Result |
|-------|--------|
| `Unknown` → `TYPE:BOX` | New Box created |
| `Unknown` → `TYPE:PACKAGE` | New Package created |
| `Unknown` → `TYPE:ITEM` → `Box Code` | New Item created in Box |
| `Unknown` → `ACT:CANCEL` | Action cancelled |

---

## Item Chains

Operations available after scanning an item barcode.

| Chain | Result |
|-------|--------|
| `Item` → `OP:MOVE` → `Box Code` | Item moved to target Box |
| `Item` → `OP:ADD` → `Quantity` | Quantity added to Item |
| `Item` → `OP:TAKE` → `Quantity` | Quantity removed from Item |
| `Item` → `ACT:CANCEL` | Action cancelled |

---

## Box Chains

Operations available after scanning a box barcode.

| Chain | Result |
|-------|--------|
| `Box` → `OP:MOVE` → `Warehouse` | Box moved to Warehouse |
| `Box` → `OP:CHANGE` → `TYPE:PACKAGE` | Box converted to Package (items moved) |
| `Box` → `ACT:CANCEL` | Action cancelled |

---

## Package Chains

Operations available after scanning a package barcode.

### Adding to Package

| Chain | Result |
|-------|--------|
| `Package` → `OP:ADD` → `Item Code` → `Quantity` | Items added to Package |
| `Package` → `OP:ADD` → `Box Code` | All items from Box added to Package |

### Removing from Package

| Chain | Result |
|-------|--------|
| `Package` → `OP:TAKE` → `Item Code` → `Quantity` | Items removed from Package |
| `Package` → `OP:TAKE` → `Box Code` | All items from Box removed from Package |

### Changing Package Type

| Chain | Result |
|-------|--------|
| `Package` → `OP:CHANGE` → `TYPE:ITEM` | Package converted to Item |
| `Package` → `OP:CHANGE` → `TYPE:BOX` | Package converted to Box |

### Packing

| Chain | Result |
|-------|--------|
| `Package` → `ACT:OK` | Package marked as packed |

---

## Adding New Chains

To add a new chain:

1. Define any new action codes in [action-codes.md](action-codes.md)
2. Add the chain definition to the appropriate section above
3. Implement the chain handler in the application