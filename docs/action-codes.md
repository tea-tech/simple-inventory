# Action Codes

Action codes are scannable barcodes that trigger operations in the inventory system. They follow a prefix-based naming convention for easy identification.

## Operations (`OP:`)

Used to perform actions on scanned entities.

| Code | Description |
|------|-------------|
| `OP:ADD` | Add quantity or items to something |
| `OP:TAKE` | Remove quantity or items from something |
| `OP:MOVE` | Move an entity to a different location |
| `OP:CHANGE` | Convert entity type (Package↔Box, Package→Item) |

## Actions (`ACT:`)

General control actions for the code chain.

| Code | Description |
|------|-------------|
| `ACT:OK` | Confirm / mark as completed |
| `ACT:CANCEL` | Cancel the current operation |

## Types (`TYPE:`)

Used when creating new entities from unknown barcodes.

| Code | Description |
|------|-------------|
| `TYPE:ITEM` | A physical object that can be tracked |
| `TYPE:BOX` | A container that holds items |
| `TYPE:PACKAGE` | An arrangement of items (e.g., order, kit) |