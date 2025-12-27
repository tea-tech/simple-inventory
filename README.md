# Simple Inventory

## A simple story

Look, I was really tired when I wrote this (well, more "vibe-coded" than wrote), and I was looking for an inventory system for me & little company to track stuff. I have bought an old barcode reader and sticker printer in a discount store. 
I have tried many platforms, but everything was either too complex, too expensive, or without barcode support. So I have decided to write my own simple inventory system.
I have my room with a shelf. On the shelf, I have boxes with a lot of stuff to track. So this was going to be backbone of the system - Places, boxes & items. Also, i have started to print barcodes. A lot of them.
While writing this, I have realized that i will ned to quickly move items between boxes and I don't want to interact with computer since my scanner is wireless. So, action codes were born - scan item, then what to do and the third depends on the action. Even thought a catchy name - "Code chain".

## Code Chaining

> To be honest, the chaining is most definitely a deformation from playing Factorio too much. But Factory must grow.

The system uses **code chains** - sequences of barcode scans that perform operations without touching the computer. Scan an item, then an action code, then follow the prompts.

For detailed documentation on the code chain system, see:
- [Action Codes](docs/action-codes.md) - Available operation and type codes
- [Code Chains](docs/code-chains.md) - All supported scan sequences

### Quick Example

```
Scan Item → OP:MOVE → Scan Box → Item moved!
```

## Core Concepts

### Entities

- **Items** - Physical objects you track (screws, cables, etc.)
- **Boxes** - Containers that hold items
- **Packages** - Arrangements of items (orders, kits, project parts)
- **Warehouses** - Logical groupings for boxes (rooms, shelves, locations)

### Inventory Checks

Inventory checks help with stocktaking. Create a check, scan boxes and items, then compare results with current inventory. You can print checks with barcodes for manual counting without a scanner.


## Installation & setup

### Prerequisites

- Python 3.10 or higher
- A barcode scanner (optional, but recommended - any USB/wireless scanner that acts as keyboard input)
- A label printer for printing barcodes (optional and no, the app itself cannot print the barcodes... yet)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/bublinak/simple-inventory.git
   cd simple-inventory
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv .venv
   
   # Windows
   .venv\Scripts\activate
   
   # Linux/Mac
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create the admin user**
   ```bash
   python scripts/create_admin.py
   ```
   This creates the database and an initial admin account:
   - Username: `admin`
   - Password: `admin123`
   
    **Please change this password after first login!**

5. **Run the server**
   ```bash
   uvicorn app.main:app --reload
   ```
   
   The application will be available at `http://localhost:8000`

### Configuration

The application uses SQLite by default (`inventory.db`). No additional database setup is required.

Environment variables can be set in a `.env` file:
- `SECRET_KEY` - JWT secret key (auto-generated if not set)
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiration time (default: 480 minutes)

### User Roles

- **Administrator** - Full access, can manage users and all data
- **Manager** - Can manage inventory, run inventory checks
- **Viewer** - Read-only access to inventory


## Contributing

GitHub Copilot (Claude Opus 4.5) & Me

## License

From rework of the code chain system, the license has been changed to Open Community License (OCL v1), slightly modified (removed 3D printing, line 23).
Use this system as you wish, but YOU MUST NOT:
 - Create a commercial product based on this code without a proper license.
 - Patent or license any part of this code or its derivatives.
See the LICENSE file for more details.
