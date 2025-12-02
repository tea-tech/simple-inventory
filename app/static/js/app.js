// Main Application Logic

let currentUser = null;
let warehouses = [];
let boxes = [];
let items = [];
let orders = [];
let inventoryChecks = [];
let activeCheck = null;
let currentCheckDetail = null;
let currentCheckItem = null;

// Barcode scanner buffer
let barcodeBuffer = '';
let barcodeTimeout = null;
const BARCODE_TIMEOUT = 100; // ms between keystrokes for barcode scanner

// Action mode state
const ACTION_CODES = {
    'ACTION:MOVE': 'move',
    'ACTION:ADD': 'add',
    'ACTION:TAKE': 'take',
    'ACTION:DONE': 'done',
    'ACTION:CANCEL': 'cancel',
    'ACTION:CLEAR': 'cancel',   // Alias
    'TYPE:BOX': 'type_box',
    'TYPE:ITEM': 'type_item',
    'TYPE:ORDER': 'type_order'
};

// Pending new barcode - when unknown barcode scanned, waiting for type
let pendingNewBarcode = null;

// Normalize action code - handle different separators (: or " due to keyboard layouts)
function normalizeActionCode(barcode) {
    if (!barcode) return '';
    // Replace " with : to handle scanner keyboard layout issues
    return barcode.toUpperCase().trim().replace(/"/g, ':');
}

// Check if a barcode is an action code
function isActionCode(barcode) {
    if (!barcode) return false;
    const normalized = normalizeActionCode(barcode);
    return ACTION_CODES.hasOwnProperty(normalized);
}

function getActionFromCode(barcode) {
    if (!barcode) return null;
    const normalized = normalizeActionCode(barcode);
    return ACTION_CODES[normalized];
}

// Code Chain state - tracks the 3-step workflow: Item/Order/Box > Action > Target
let codeChain = {
    item: null,      // { id, name, barcode, quantity, box_id }
    order: null,     // { id, name, barcode, status }
    box: null,       // { id, name, barcode, warehouse_id }
    action: null,    // 'move' | 'add' | 'take' | 'done' | 'cancel'
    target: null     // box object for move, item for order add, or quantity number
};

// Current order being viewed in detail modal
let currentOrderDetail = null;

// Legacy alias for backward compatibility
let pendingAction = null;  // Will be kept in sync with codeChain

// Initialize app
document.addEventListener('DOMContentLoaded', async () => {
    // Check if logged in
    if (!api.token) {
        window.location.href = '/static/login.html';
        return;
    }

    try {
        currentUser = await api.getMe();
        initializeApp();
    } catch (error) {
        console.error('Failed to get user:', error);
        api.logout();
    }
});

function initializeApp() {
    // Update user info in sidebar
    document.getElementById('userName').textContent = currentUser.full_name || currentUser.username;
    document.getElementById('userRole').textContent = currentUser.role;

    // Setup navigation
    setupNavigation();

    // Setup logout
    document.getElementById('logoutBtn').addEventListener('click', () => api.logout());

    // Setup barcode scanner listener
    setupBarcodeScanner();

    // Setup rolling hints
    setupRollingHints();
    
    // Setup item box input handler
    setupItemBoxInput();

    // Show/hide admin-only menu items
    if (currentUser.role !== 'administrator') {
        document.querySelectorAll('.admin-only').forEach(el => el.classList.add('hidden'));
    }
    
    // Show/hide manager-only menu items (managers and admins can see)
    if (!['administrator', 'manager'].includes(currentUser.role)) {
        document.querySelectorAll('.manager-only').forEach(el => el.classList.add('hidden'));
    }

    // Preload data for barcode lookups
    preloadData();

    // Load initial page
    navigateTo('dashboard');
}

async function preloadData() {
    try {
        warehouses = await api.getWarehouses();
        boxes = await api.getBoxes();
    } catch (error) {
        console.error('Failed to preload data:', error);
    }
}

// Item box input handler - handles barcode scanner input and Enter key
function setupItemBoxInput() {
    const boxInput = document.getElementById('itemBoxInput');
    const dropdown = document.getElementById('itemBoxDropdown');
    if (!boxInput || !dropdown) return;
    
    // Handle Enter key - resolve box and move to Name field
    boxInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const value = boxInput.value.trim();
            
            if (value) {
                // Try to find box by barcode or name
                const box = boxes.find(b => b.barcode === value || b.name.toLowerCase() === value.toLowerCase());
                if (box) {
                    document.getElementById('itemBoxId').value = box.id;
                    boxInput.value = `${box.name} (${box.barcode})`;
                    hideBoxDropdown();
                    // Move focus to Name field
                    document.getElementById('itemName').focus();
                } else {
                    showAlert('Box not found: ' + value, 'warning');
                    boxInput.select();
                }
            } else {
                // Empty value, just move to next field
                document.getElementById('itemName').focus();
            }
        } else if (e.key === 'Escape') {
            hideBoxDropdown();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            const firstItem = dropdown.querySelector('.dropdown-item');
            if (firstItem) firstItem.focus();
        }
    });
    
    // Handle input - filter dropdown
    boxInput.addEventListener('input', () => {
        const value = boxInput.value.trim().toLowerCase();
        updateBoxDropdown(value);
        if (value.length > 0) {
            showBoxDropdown();
        }
    });
    
    // Handle focus - show dropdown
    boxInput.addEventListener('focus', () => {
        updateBoxDropdown(boxInput.value.trim().toLowerCase());
    });
    
    // Handle click outside to close dropdown
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.input-with-dropdown')) {
            hideBoxDropdown();
        }
    });
}

function updateBoxDropdown(filter = '') {
    const dropdown = document.getElementById('itemBoxDropdown');
    if (!dropdown) return;
    
    const filteredBoxes = filter 
        ? boxes.filter(b => 
            b.name.toLowerCase().includes(filter) || 
            b.barcode.toLowerCase().includes(filter))
        : boxes;
    
    if (filteredBoxes.length === 0) {
        dropdown.innerHTML = '<div class="dropdown-item" style="color: var(--gray-color);">No boxes found</div>';
    } else {
        dropdown.innerHTML = filteredBoxes.map(b => `
            <div class="dropdown-item" data-id="${b.id}" data-barcode="${escapeHtml(b.barcode)}" data-name="${escapeHtml(b.name)}" tabindex="0">
                <div class="box-name">${escapeHtml(b.name)}</div>
                <div class="box-barcode">${escapeHtml(b.barcode)}</div>
            </div>
        `).join('');
        
        // Add click handlers to dropdown items
        dropdown.querySelectorAll('.dropdown-item[data-id]').forEach(item => {
            item.addEventListener('click', () => selectBox(item));
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    selectBox(item);
                } else if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    const next = item.nextElementSibling;
                    if (next) next.focus();
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    const prev = item.previousElementSibling;
                    if (prev) prev.focus();
                    else document.getElementById('itemBoxInput').focus();
                } else if (e.key === 'Escape') {
                    hideBoxDropdown();
                    document.getElementById('itemBoxInput').focus();
                }
            });
        });
    }
}

function selectBox(item) {
    const boxInput = document.getElementById('itemBoxInput');
    const boxId = item.dataset.id;
    const boxName = item.dataset.name;
    const boxBarcode = item.dataset.barcode;
    
    document.getElementById('itemBoxId').value = boxId;
    boxInput.value = `${boxName} (${boxBarcode})`;
    hideBoxDropdown();
    document.getElementById('itemName').focus();
}

function toggleBoxDropdown() {
    const dropdown = document.getElementById('itemBoxDropdown');
    if (dropdown.classList.contains('show')) {
        hideBoxDropdown();
    } else {
        updateBoxDropdown('');
        showBoxDropdown();
    }
}

function showBoxDropdown() {
    const dropdown = document.getElementById('itemBoxDropdown');
    if (dropdown) dropdown.classList.add('show');
}

function hideBoxDropdown() {
    const dropdown = document.getElementById('itemBoxDropdown');
    if (dropdown) dropdown.classList.remove('show');
}

// Rolling hints
function setupRollingHints() {
    const hints = document.querySelectorAll('.hints-container .hint');
    if (hints.length === 0) return;
    
    let currentHint = 0;
    
    setInterval(() => {
        hints[currentHint].classList.remove('active');
        currentHint = (currentHint + 1) % hints.length;
        hints[currentHint].classList.add('active');
    }, 4000); // Change hint every 4 seconds
}

// Barcode Scanner - captures keyboard input when not in an input field
function setupBarcodeScanner() {
    document.addEventListener('keydown', handleBarcodeInput);
}

function handleBarcodeInput(e) {
    // Ignore if typing in an input, textarea, or select (except quantity prompt)
    const activeElement = document.activeElement;
    const isInputField = activeElement.tagName === 'INPUT' || 
                         activeElement.tagName === 'TEXTAREA' || 
                         activeElement.tagName === 'SELECT' ||
                         activeElement.isContentEditable;
    
    // Allow scanning in quantity prompt input
    const isQuantityPrompt = activeElement.id === 'scannerQuantityInput';
    
    if (isInputField && !isQuantityPrompt) {
        return;
    }

    // Clear timeout and reset buffer if too much time passed
    if (barcodeTimeout) {
        clearTimeout(barcodeTimeout);
    }

    // Handle Escape - close modal, clear buffer, and cancel code chain
    if (e.key === 'Escape') {
        e.preventDefault();
        barcodeBuffer = '';
        hideBarcodeIndicator();
        closeBarcodeResultModal();
        closeQuantityPrompt();
        clearCodeChain();
        return;
    }

    // Handle Enter in quantity prompt
    if (e.key === 'Enter' && isQuantityPrompt) {
        e.preventDefault();
        submitQuantityPrompt();
        return;
    }

    // Handle Enter key - process the barcode
    if (e.key === 'Enter' && barcodeBuffer.length > 0) {
        e.preventDefault();
        const barcode = barcodeBuffer.trim();
        barcodeBuffer = '';
        hideBarcodeIndicator();
        // Close any existing result modal before searching
        closeBarcodeResultModal();
        processScan(barcode);
        return;
    }

    // Only capture printable characters
    if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
        // Don't capture if in quantity prompt (let them type numbers)
        if (isQuantityPrompt) {
            return;
        }
        
        e.preventDefault();
        // If modal is open and user starts typing, close it and start fresh scan
        const modalOpen = document.querySelector('#barcodeResultModal.active');
        if (modalOpen) {
            closeBarcodeResultModal();
        }
        
        barcodeBuffer += e.key;
        showBarcodeIndicator(barcodeBuffer);
        
        // Auto-clear buffer after timeout (in case Enter wasn't pressed)
        barcodeTimeout = setTimeout(() => {
            if (barcodeBuffer.length > 0) {
                const barcode = barcodeBuffer.trim();
                barcodeBuffer = '';
                hideBarcodeIndicator();
                // Auto-search if buffer has content after timeout (for scanners that don't send Enter)
                if (barcode.length >= 3) {
                    processScan(barcode);
                }
            }
        }, 500);
    }
}

// Process scanned barcode - handles action codes and regular barcodes
async function processScan(barcode) {
    if (!barcode || barcode.trim() === '') return;
    
    const trimmedBarcode = barcode.trim();
    
    // ALWAYS check if it's an action code FIRST - before any other logic
    if (isActionCode(trimmedBarcode)) {
        const action = getActionFromCode(trimmedBarcode);
        handleActionCode(action);
        return;
    }
    
    // Check if we're on the check detail page with an active check
    const checkDetailPage = document.getElementById('page-check-detail');
    if (checkDetailPage && !checkDetailPage.classList.contains('hidden') && activeCheck && activeCheck.status === 'in_progress') {
        // We're in check mode - handle as check item scan
        await handleCheckItemScan(trimmedBarcode);
        return;
    }
    
    // Regular barcode - behavior depends on Code Chain state
    if (codeChain.item && codeChain.action === 'move') {
        // Step 3: Expecting a target box barcode for MOVE
        await handleTargetScan(trimmedBarcode);
    } else if (codeChain.order && codeChain.action === 'add') {
        // Order flow: expecting item barcode to add to order
        await handleOrderItemScan(trimmedBarcode);
    } else {
        // Step 1: New item/box/order search (resets chain)
        await searchByBarcode(trimmedBarcode);
    }
}

function handleActionCode(action) {
    const isManager = ['administrator', 'manager'].includes(currentUser.role);
    
    // Handle TYPE:BOX, TYPE:ITEM, TYPE:ORDER for pending unknown barcode FIRST
    // These need to be checked before other actions to avoid clearing pendingNewBarcode
    if (action === 'type_box' || action === 'type_item' || action === 'type_order') {
        if (!isManager) {
            showAlert('You do not have permission to create items/boxes/orders', 'danger');
            return;
        }
        
        // pendingNewBarcode can be a string (from unknown barcode prompt) or an object (from createNewItem)
        const barcodeValue = typeof pendingNewBarcode === 'string' ? pendingNewBarcode : (pendingNewBarcode?.barcode || null);
        
        if (barcodeValue) {
            closeUnknownBarcodePrompt();
            if (action === 'type_box') {
                createNewBox(barcodeValue);
            } else if (action === 'type_item') {
                createNewItem(barcodeValue);
            } else {
                createNewOrder(barcodeValue);
            }
            return;
        } else {
            showAlert('Scan an unknown barcode first, then scan TYPE:BOX, TYPE:ITEM, or TYPE:ORDER', 'warning');
            return;
        }
    }
    
    if (action === 'cancel') {
        // Check if we have an order in the chain that should be cancelled
        if (codeChain.order && !codeChain.action) {
            if (isManager) {
                cancelOrderFromChain();
                return;
            }
        }
        clearCodeChain();
        pendingNewBarcode = null;
        closeUnknownBarcodePrompt();
        showAlert('Action cancelled', 'info');
        return;
    }
    
    // Handle DONE action
    if (action === 'done') {
        if (codeChain.order) {
            // Pack the order
            if (isManager) {
                packOrderFromChain();
            } else {
                showAlert('You do not have permission to pack orders', 'danger');
            }
            return;
        }
        // Mark returns as done (close modal)
        if (document.getElementById('returnItemsSection') && 
            !document.getElementById('returnItemsSection').classList.contains('hidden')) {
            markReturnsDone();
            return;
        }
        showAlert('Scan an order first, then ACTION:DONE to pack it', 'warning');
        return;
    }
    
    if (!isManager) {
        showAlert('You do not have permission to perform this action', 'danger');
        return;
    }
    
    // Handle ADD action - can work with items or orders
    if (action === 'add') {
        if (codeChain.order) {
            // Order flow: waiting for item to add
            codeChain.action = 'add';
            updateCodeChainUI();
            closeBarcodeResultModal();
            closeOrderDetailModal();
            showAlert('Scan an item barcode to add to this order', 'info');
            return;
        } else if (codeChain.item) {
            // Item flow: add/store quantity
            codeChain.action = 'add';
            pendingAction = { item: codeChain.item, action: 'add' };
            updateCodeChainUI();
            closeBarcodeResultModal();
            showQuantityPrompt('add', codeChain.item);
            return;
        }
        showAlert('Scan an item or order first, then ACTION:ADD', 'warning');
        return;
    }
    
    // Handle TAKE action - only for items
    if (action === 'take') {
        if (!codeChain.item) {
            showAlert('Scan an item first, then ACTION:TAKE', 'warning');
            return;
        }
        codeChain.action = 'take';
        pendingAction = { item: codeChain.item, action: 'take' };
        updateCodeChainUI();
        closeBarcodeResultModal();
        showQuantityPrompt('take', codeChain.item);
        return;
    }
    
    // Handle MOVE action - for items or boxes
    if (action === 'move') {
        if (codeChain.box) {
            // Box move - show warehouse selection modal
            codeChain.action = 'move';
            updateCodeChainUI();
            closeBarcodeResultModal();
            showMoveBoxModalFromChain(codeChain.box);
            return;
        }
        if (!codeChain.item) {
            showAlert('Scan an item or box first, then ACTION:MOVE', 'warning');
            return;
        }
        codeChain.action = 'move';
        pendingAction = { item: codeChain.item, action: 'move' };
        updateCodeChainUI();
        closeBarcodeResultModal();
        return;
    }
}

async function handleTargetScan(barcode) {
    // Safety check: if this is an action code, handle it as action
    if (isActionCode(barcode)) {
        handleActionCode(getActionFromCode(barcode));
        return;
    }
    
    if (!codeChain.item || !codeChain.action) {
        await searchByBarcode(barcode);
        return;
    }
    
    if (codeChain.action === 'move') {
        // Expecting a box barcode as target
        try {
            const box = await api.getBoxByBarcode(barcode);
            if (box) {
                codeChain.target = box;
                updateCodeChainUI();
                await executeMove(codeChain.item, box);
            }
        } catch (error) {
            showAlert(`Box not found with barcode: ${barcode}`, 'danger');
        }
    }
}

async function executeMove(item, targetBox) {
    try {
        await api.moveItem(item.id, targetBox.id);
        showCodeChainSuccess(`Moved "${item.name}" → "${targetBox.name}"`);
        // Refresh data
        await preloadData();
        if (document.getElementById('page-items').classList.contains('hidden') === false) {
            await loadItems();
        }
    } catch (error) {
        showAlert(`Failed to move item: ${error.message}`, 'danger');
        clearCodeChain();
    }
}

async function executeAdd(item, quantity) {
    try {
        await api.storeItem(item.id, quantity);
        codeChain.target = quantity;
        updateCodeChainUI();
        showCodeChainSuccess(`Added ${quantity} → "${item.name}"`);
        // Refresh data
        if (document.getElementById('page-items').classList.contains('hidden') === false) {
            await loadItems();
        }
    } catch (error) {
        showAlert(`Failed to add item: ${error.message}`, 'danger');
        clearCodeChain();
    }
}

async function executeTake(item, quantity) {
    try {
        await api.takeItem(item.id, quantity);
        codeChain.target = quantity;
        updateCodeChainUI();
        showCodeChainSuccess(`Took ${quantity} ← "${item.name}"`);
        // Refresh data
        if (document.getElementById('page-items').classList.contains('hidden') === false) {
            await loadItems();
        }
    } catch (error) {
        showAlert(`Failed to take item: ${error.message}`, 'danger');
        clearCodeChain();
    }
}

function cancelPendingAction() {
    clearCodeChain();
}

function clearCodeChain() {
    codeChain = { item: null, order: null, box: null, action: null, target: null };
    pendingAction = null;
    updateCodeChainUI();
    closeQuantityPrompt();
}

function updateCodeChainUI() {
    let chainBar = document.getElementById('codeChainBar');
    
    // If nothing in chain, hide the bar
    if (!codeChain.item && !codeChain.order && !codeChain.box && !codeChain.action && !codeChain.target) {
        if (chainBar) {
            chainBar.classList.remove('visible');
        }
        return;
    }
    
    // Create bar if doesn't exist
    if (!chainBar) {
        chainBar = document.createElement('div');
        chainBar.id = 'codeChainBar';
        chainBar.className = 'code-chain-bar';
        document.body.appendChild(chainBar);
    }
    
    // Determine if this is an order chain, box chain, or item chain
    const isOrderChain = codeChain.order !== null;
    const isBoxChain = codeChain.box !== null;
    
    // Build chain steps
    let step1Label = isOrderChain ? 'Order' : (isBoxChain ? 'Box' : 'Item');
    const firstItem = isOrderChain ? codeChain.order : (isBoxChain ? codeChain.box : codeChain.item);
    const itemStep = firstItem 
        ? `<span class="chain-value">${escapeHtml(firstItem.name || firstItem.barcode)}</span>` 
        : '<span class="chain-placeholder">?</span>';
    
    const actionStep = codeChain.action 
        ? `<span class="chain-value">${codeChain.action.toUpperCase()}</span>` 
        : '<span class="chain-placeholder">?</span>';
    
    let targetLabel = 'Target';
    let targetValue = '<span class="chain-placeholder">?</span>';
    if (codeChain.target) {
        if (typeof codeChain.target === 'object') {
            // Box object for move, or item for order
            targetValue = `<span class="chain-value">${escapeHtml(codeChain.target.name)}</span>`;
        } else {
            // Number for add/take
            targetValue = `<span class="chain-value">${codeChain.target}</span>`;
        }
    } else if (codeChain.action === 'add') {
        targetLabel = isOrderChain ? 'Item' : 'Qty';
    } else if (codeChain.action === 'take') {
        targetLabel = 'Qty';
    } else if (codeChain.action === 'move') {
        targetLabel = isBoxChain ? 'Warehouse' : 'Box';
    }
    
    // Determine which step is active
    let step1Class = firstItem ? 'completed' : 'active';
    let step2Class = firstItem && !codeChain.action ? 'active' : (codeChain.action ? 'completed' : '');
    let step3Class = codeChain.action && !codeChain.target ? 'active' : (codeChain.target ? 'completed' : '');
    
    chainBar.innerHTML = `
        <div class="chain-title"><i class="fas fa-link"></i> Code Chain</div>
        <div class="chain-steps">
            <div class="chain-step ${step1Class}">
                <span class="chain-label">${step1Label}</span>
                ${itemStep}
            </div>
            <div class="chain-arrow"><i class="fas fa-chevron-right"></i></div>
            <div class="chain-step ${step2Class}">
                <span class="chain-label">Action</span>
                ${actionStep}
            </div>
            <div class="chain-arrow"><i class="fas fa-chevron-right"></i></div>
            <div class="chain-step ${step3Class}">
                <span class="chain-label">${targetLabel}</span>
                ${targetValue}
            </div>
        </div>
        <button class="chain-cancel-btn" onclick="clearCodeChain()">
            <i class="fas fa-times"></i>
        </button>
    `;
    chainBar.classList.add('visible');
}

function showCodeChainSuccess(message) {
    const chainBar = document.getElementById('codeChainBar');
    if (chainBar) {
        chainBar.classList.add('success');
        
        // Add success message
        const successMsg = chainBar.querySelector('.chain-success-msg');
        if (!successMsg) {
            const msg = document.createElement('div');
            msg.className = 'chain-success-msg';
            msg.innerHTML = `<i class="fas fa-check-circle"></i> ${escapeHtml(message)}`;
            chainBar.appendChild(msg);
        }
    }
    
    // Auto-hide after 3 seconds
    setTimeout(() => {
        clearCodeChain();
    }, 3000);
}

// Legacy function for backward compatibility
function updateActionStatus() {
    updateCodeChainUI();
}

// Quantity Prompt for Add/Take
function showQuantityPrompt(action, item) {
    closeBarcodeResultModal();
    
    const modal = document.getElementById('quantityPromptModal');
    const title = document.getElementById('quantityPromptTitle');
    const itemName = document.getElementById('quantityPromptItem');
    const input = document.getElementById('scannerQuantityInput');
    const maxInfo = document.getElementById('quantityMaxInfo');
    
    title.innerHTML = action === 'add' 
        ? '<i class="fas fa-plus-circle"></i> Add Items'
        : '<i class="fas fa-minus-circle"></i> Take Items';
    
    itemName.textContent = item.name;
    input.value = ''; // Start empty so barcode scanner can input directly
    input.min = 1;
    
    if (action === 'take') {
        input.max = item.quantity;
        maxInfo.textContent = `Available: ${item.quantity}`;
        maxInfo.classList.remove('hidden');
    } else {
        input.removeAttribute('max');
        maxInfo.classList.add('hidden');
    }
    
    modal.dataset.action = action;
    modal.classList.add('active');
    
    // Focus the input after a short delay
    setTimeout(() => {
        input.focus();
        input.select();
    }, 100);
}

function closeQuantityPrompt() {
    const modal = document.getElementById('quantityPromptModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

async function submitQuantityPrompt() {
    const modal = document.getElementById('quantityPromptModal');
    const input = document.getElementById('scannerQuantityInput');
    const action = modal.dataset.action;
    const quantity = parseInt(input.value);
    
    if (!quantity || quantity < 1) {
        showAlert('Please enter a valid quantity', 'warning');
        return;
    }
    
    if (action === 'take' && quantity > codeChain.item.quantity) {
        showAlert(`Cannot take more than available (${codeChain.item.quantity})`, 'warning');
        return;
    }
    
    closeQuantityPrompt();
    
    if (action === 'add') {
        await executeAdd(codeChain.item, quantity);
    } else if (action === 'take') {
        await executeTake(codeChain.item, quantity);
    }
    
    // Clear the code chain after action
    clearCodeChain();
}

function incrementQuantity() {
    const input = document.getElementById('scannerQuantityInput');
    const max = input.max ? parseInt(input.max) : Infinity;
    const current = parseInt(input.value) || 0;
    if (current < max) {
        input.value = current + 1;
    }
}

function decrementQuantity() {
    const input = document.getElementById('scannerQuantityInput');
    const current = parseInt(input.value) || 0;
    if (current > 0) {
        input.value = current > 1 ? current - 1 : '';
    }
}

function showBarcodeIndicator(text) {
    let indicator = document.getElementById('barcodeIndicator');
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'barcodeIndicator';
        indicator.className = 'barcode-indicator';
        document.body.appendChild(indicator);
    }
    indicator.innerHTML = `<i class="fas fa-barcode"></i> Scanning: <strong>${escapeHtml(text)}</strong>`;
    indicator.classList.add('visible');
}

function hideBarcodeIndicator() {
    const indicator = document.getElementById('barcodeIndicator');
    if (indicator) {
        indicator.classList.remove('visible');
    }
}

async function searchByBarcode(barcode) {
    hideBarcodeIndicator();
    
    if (!barcode || barcode.length < 1) {
        return;
    }
    
    // Double-check: if this is an action code, handle it as action (safety net)
    if (isActionCode(barcode)) {
        handleActionCode(getActionFromCode(barcode));
        return;
    }

    showAlert(`Searching for barcode: ${barcode}...`, 'info');

    try {
        // Try to find an item first
        try {
            const item = await api.getItemByBarcode(barcode);
            if (item) {
                // Start new Code Chain with this item (Step 1)
                codeChain = { item: item, order: null, box: null, action: null, target: null };
                pendingAction = { item: item, action: null }; // Legacy sync
                updateCodeChainUI();
                showBarcodeResult('item', item);
                return;
            }
        } catch (e) {
            // Item not found, try box
        }

        // Try to find a box
        try {
            const box = await api.getBoxByBarcode(barcode);
            if (box) {
                // Check if we have a pending new item waiting for a box
                if (pendingNewBarcode && pendingNewBarcode.type === 'item') {
                    // Auto-fill the box in the item form
                    document.getElementById('itemBox').value = box.id;
                    pendingNewBarcode = null;
                    showAlert(`Box "${box.name}" selected for new item`, 'success');
                    return;
                }
                // Start new Code Chain with this box (Step 1)
                codeChain = { item: null, order: null, box: box, action: null, target: null };
                pendingAction = null;
                updateCodeChainUI();
                showBarcodeResult('box', box);
                return;
            }
        } catch (e) {
            // Box not found, try order
        }

        // Try to find an order
        try {
            const order = await api.getOrderByBarcode(barcode);
            if (order) {
                // Start new Code Chain with this order
                codeChain = { item: null, order: order, box: null, action: null, target: null };
                pendingAction = null;
                updateCodeChainUI();
                showBarcodeResult('order', order);
                return;
            }
        } catch (e) {
            // Order not found either
        }

        // Unknown barcode - prompt user for type (manager only)
        const isManager = ['administrator', 'manager'].includes(currentUser.role);
        if (isManager) {
            showUnknownBarcodePrompt(barcode);
        } else {
            showAlert(`No item, box, or order found with barcode: ${barcode}`, 'warning');
        }
    } catch (error) {
        showAlert(`Error searching for barcode: ${error.message}`, 'danger');
    }
}

// Unknown Barcode Prompt Functions
function showUnknownBarcodePrompt(barcode) {
    pendingNewBarcode = barcode;
    document.getElementById('unknownBarcodeValue').textContent = barcode;
    document.getElementById('unknownBarcodeModal').classList.add('active');
}

function closeUnknownBarcodePrompt() {
    document.getElementById('unknownBarcodeModal').classList.remove('active');
    // Only clear pendingNewBarcode if it's still a string (not yet used)
    // If it's an object with type 'item', we need to keep it for box selection
    if (typeof pendingNewBarcode === 'string') {
        pendingNewBarcode = null;
    }
}

async function createNewBox(barcode = null) {
    closeUnknownBarcodePrompt();
    const useBarcode = barcode || (typeof pendingNewBarcode === 'string' ? pendingNewBarcode : pendingNewBarcode?.barcode);
    pendingNewBarcode = null;
    
    // Ensure warehouses are loaded
    if (warehouses.length === 0) {
        try {
            warehouses = await api.getWarehouses();
        } catch (error) {
            console.error('Failed to load warehouses:', error);
        }
    }
    
    // Update warehouse dropdown options
    updateWarehouseSelects();
    
    // Open box modal with barcode prefilled
    const form = document.getElementById('boxForm');
    form.reset();
    form.dataset.id = '';  // Clear the edit ID to ensure we create a new box
    document.getElementById('boxModalTitle').textContent = 'Add Box';
    document.getElementById('boxBarcode').value = useBarcode || '';
    document.getElementById('boxWarehouse').value = warehouses.length > 0 ? warehouses[0].id : '';
    document.getElementById('boxModal').classList.add('active');
    
    // Focus on name field since barcode is prefilled
    setTimeout(() => document.getElementById('boxName').focus(), 100);
}

function createNewItem(barcode = null) {
    closeUnknownBarcodePrompt();
    const useBarcode = barcode || (typeof pendingNewBarcode === 'string' ? pendingNewBarcode : pendingNewBarcode?.barcode);
    
    // Store the barcode for when a box is scanned
    pendingNewBarcode = { type: 'item', barcode: useBarcode };
    
    // Update box datalist
    updateBoxSelects();
    
    // Open item modal with barcode prefilled
    document.getElementById('itemModalTitle').textContent = 'Add Item';
    document.getElementById('itemId').value = '';
    document.getElementById('itemBarcode').value = useBarcode || '';
    document.getElementById('itemBoxInput').value = '';
    document.getElementById('itemBoxId').value = '';
    document.getElementById('itemName').value = '';
    document.getElementById('itemDescription').value = '';
    document.getElementById('itemQuantity').value = 1;
    document.getElementById('itemPrice').value = '';
    document.getElementById('itemForm').dataset.id = '';
    document.getElementById('itemModal').classList.add('active');
    
    // Focus on box field so user can scan box barcode
    setTimeout(() => document.getElementById('itemBoxInput').focus(), 100);
    
    showAlert('Scan a box barcode or select from dropdown, then fill in item details', 'info');
}

function showBarcodeResult(type, data) {
    const modal = document.getElementById('barcodeResultModal');
    const title = document.getElementById('barcodeResultTitle');
    const content = document.getElementById('barcodeResultContent');
    const actions = document.getElementById('barcodeResultActions');

    if (type === 'item') {
        const box = boxes.find(b => b.id === data.box_id);
        title.innerHTML = `<i class="fas fa-cube"></i> Item Found`;
        content.innerHTML = `
            <div class="result-details">
                <div class="result-row">
                    <span class="label">Barcode:</span>
                    <span class="value"><code>${escapeHtml(data.barcode)}</code></span>
                </div>
                <div class="result-row">
                    <span class="label">Name:</span>
                    <span class="value"><strong>${escapeHtml(data.name)}</strong></span>
                </div>
                <div class="result-row">
                    <span class="label">Description:</span>
                    <span class="value">${escapeHtml(data.description || '-')}</span>
                </div>
                <div class="result-row">
                    <span class="label">Quantity:</span>
                    <span class="value"><strong>${data.quantity}</strong></span>
                </div>
                <div class="result-row">
                    <span class="label">Box:</span>
                    <span class="value">${box ? escapeHtml(box.name) : 'Unknown'}</span>
                </div>
            </div>
        `;
        
        const isManager = ['administrator', 'manager'].includes(currentUser.role);
        actions.innerHTML = isManager ? `
            <button class="btn btn-success" onclick="closeBarcodeResultModal(); showStoreItemModal(${data.id})">
                <i class="fas fa-plus"></i> Store
            </button>
            <button class="btn btn-warning" onclick="closeBarcodeResultModal(); showTakeItemModal(${data.id})">
                <i class="fas fa-minus"></i> Take
            </button>
            <button class="btn btn-primary" onclick="closeBarcodeResultModal(); showMoveItemModal(${data.id})">
                <i class="fas fa-arrows-alt"></i> Move
            </button>
        ` : '';
    } else if (type === 'box') {
        const warehouse = warehouses.find(w => w.id === data.warehouse_id);
        title.innerHTML = `<i class="fas fa-box"></i> Box Found`;
        content.innerHTML = `
            <div class="result-details">
                <div class="result-row">
                    <span class="label">Barcode:</span>
                    <span class="value"><code>${escapeHtml(data.barcode)}</code></span>
                </div>
                <div class="result-row">
                    <span class="label">Name:</span>
                    <span class="value"><strong>${escapeHtml(data.name)}</strong></span>
                </div>
                <div class="result-row">
                    <span class="label">Description:</span>
                    <span class="value">${escapeHtml(data.description || '-')}</span>
                </div>
                <div class="result-row">
                    <span class="label">Warehouse:</span>
                    <span class="value">${warehouse ? escapeHtml(warehouse.name) : 'Unknown'}</span>
                </div>
                <div class="result-row">
                    <span class="label">Items:</span>
                    <span class="value"><strong>${data.items ? data.items.length : 0}</strong> item(s)</span>
                </div>
            </div>
        `;
        
        actions.innerHTML = `
            <button class="btn btn-primary" onclick="closeBarcodeResultModal(); viewBoxItems(${data.id})">
                <i class="fas fa-eye"></i> View Items
            </button>
        `;
    } else if (type === 'order') {
        title.innerHTML = `<i class="fas fa-clipboard-list"></i> Order Found`;
        content.innerHTML = `
            <div class="result-details">
                <div class="result-row">
                    <span class="label">Barcode:</span>
                    <span class="value"><code>${escapeHtml(data.barcode)}</code></span>
                </div>
                <div class="result-row">
                    <span class="label">Name:</span>
                    <span class="value"><strong>${escapeHtml(data.name)}</strong></span>
                </div>
                <div class="result-row">
                    <span class="label">Status:</span>
                    <span class="value"><span class="status-badge ${data.status}">${data.status.toUpperCase()}</span></span>
                </div>
                <div class="result-row">
                    <span class="label">Items:</span>
                    <span class="value"><strong>${data.order_items ? data.order_items.length : 0}</strong> item(s)</span>
                </div>
            </div>
            <div class="order-scan-hint">
                <p><i class="fas fa-info-circle"></i> Scan <code>ACTION:ADD</code> then item barcode to add items</p>
            </div>
        `;
        
        const isManager = ['administrator', 'manager'].includes(currentUser.role);
        let actionButtons = `
            <button class="btn btn-primary" onclick="closeBarcodeResultModal(); showOrderDetail(${data.id})">
                <i class="fas fa-eye"></i> View Details
            </button>
        `;
        
        if (isManager && data.status !== 'done' && data.status !== 'cancelled') {
            actionButtons += `
                <button class="btn btn-success" onclick="closeBarcodeResultModal(); packOrder(${data.id})">
                    <i class="fas fa-box"></i> Pack
                </button>
            `;
        }
        
        actions.innerHTML = actionButtons;
    }

    modal.classList.add('active');
}

function closeBarcodeResultModal() {
    document.getElementById('barcodeResultModal').classList.remove('active');
}

function viewBoxItems(boxId) {
    document.getElementById('itemBoxFilter').value = boxId;
    navigateTo('items');
}

function setupNavigation() {
    document.querySelectorAll('.sidebar-nav a').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const page = link.dataset.page;
            navigateTo(page);
        });
    });
}

function navigateTo(page) {
    // Update active nav
    document.querySelectorAll('.sidebar-nav a').forEach(link => {
        link.classList.toggle('active', link.dataset.page === page);
    });

    // Hide all pages
    document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));

    // Show target page
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.classList.remove('hidden');
        loadPageData(page);
    }
}

async function loadPageData(page) {
    switch (page) {
        case 'dashboard':
            await loadDashboard();
            break;
        case 'warehouses':
            await loadWarehouses();
            break;
        case 'boxes':
            await loadBoxes();
            break;
        case 'items':
            await loadItems();
            break;
        case 'orders':
            await loadOrders();
            break;
        case 'checks':
            await loadChecks();
            break;
        case 'check-detail':
            // Handled separately by viewCheck
            break;
        case 'users':
            await loadUsers();
            break;
    }
}

// Dashboard
async function loadDashboard() {
    try {
        const [warehouseData, boxData, itemData, orderData] = await Promise.all([
            api.getWarehouses(),
            api.getBoxes(),
            api.getItems(),
            api.getOrders()
        ]);

        document.getElementById('stat-warehouses').textContent = warehouseData.length;
        document.getElementById('stat-boxes').textContent = boxData.length;
        document.getElementById('stat-items').textContent = itemData.reduce((sum, item) => sum + item.quantity, 0);
        
        // Count active orders (not done or cancelled)
        const activeOrders = orderData.filter(o => !['done', 'cancelled'].includes(o.status));
        document.getElementById('stat-orders').textContent = activeOrders.length;

        if (currentUser.role === 'administrator') {
            const userData = await api.getUsers();
            document.getElementById('stat-users').textContent = userData.length;
        }
    } catch (error) {
        showAlert('Failed to load dashboard data', 'danger');
    }
}

// Warehouses
async function loadWarehouses() {
    try {
        warehouses = await api.getWarehouses();
        renderWarehouses();
    } catch (error) {
        showAlert('Failed to load warehouses', 'danger');
    }
}

function renderWarehouses() {
    const tbody = document.getElementById('warehousesTable');
    const isManager = ['administrator', 'manager'].includes(currentUser.role);

    if (warehouses.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="empty-state">
                    <i class="fas fa-warehouse"></i>
                    <h3>No warehouses yet</h3>
                    <p>Create your first warehouse to get started</p>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = warehouses.map(w => `
        <tr>
            <td>${w.id}</td>
            <td><strong>${escapeHtml(w.name)}</strong></td>
            <td>${escapeHtml(w.description || '-')}</td>
            <td>${escapeHtml(w.location || '-')}</td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-sm btn-primary" onclick="viewWarehouse(${w.id})">
                        <i class="fas fa-eye"></i>
                    </button>
                    ${currentUser.role === 'administrator' ? `
                        <button class="btn btn-sm btn-warning" onclick="editWarehouse(${w.id})">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="deleteWarehouse(${w.id})">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : ''}
                </div>
            </td>
        </tr>
    `).join('');
}

async function viewWarehouse(id) {
    try {
        const warehouse = await api.getWarehouse(id);
        // Switch to boxes page filtered by this warehouse
        document.getElementById('boxWarehouseFilter').value = id;
        navigateTo('boxes');
    } catch (error) {
        showAlert('Failed to load warehouse', 'danger');
    }
}

function showWarehouseModal(warehouse = null) {
    const modal = document.getElementById('warehouseModal');
    const form = document.getElementById('warehouseForm');
    const title = document.getElementById('warehouseModalTitle');

    form.reset();
    form.dataset.id = warehouse ? warehouse.id : '';
    title.textContent = warehouse ? 'Edit Warehouse' : 'Add Warehouse';

    if (warehouse) {
        document.getElementById('warehouseName').value = warehouse.name;
        document.getElementById('warehouseDescription').value = warehouse.description || '';
        document.getElementById('warehouseLocation').value = warehouse.location || '';
    }

    modal.classList.add('active');
}

function closeWarehouseModal() {
    document.getElementById('warehouseModal').classList.remove('active');
}

async function saveWarehouse(e) {
    e.preventDefault();
    const form = e.target;
    const id = form.dataset.id;

    const data = {
        name: document.getElementById('warehouseName').value,
        description: document.getElementById('warehouseDescription').value || null,
        location: document.getElementById('warehouseLocation').value || null
    };

    try {
        if (id) {
            await api.updateWarehouse(id, data);
            showAlert('Warehouse updated successfully', 'success');
        } else {
            await api.createWarehouse(data);
            showAlert('Warehouse created successfully', 'success');
        }
        closeWarehouseModal();
        await loadWarehouses();
        // Refresh warehouse selects in box forms
        updateWarehouseSelects();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

function editWarehouse(id) {
    const warehouse = warehouses.find(w => w.id === id);
    if (warehouse) {
        showWarehouseModal(warehouse);
    }
}

async function deleteWarehouse(id) {
    if (!confirm('Are you sure you want to delete this warehouse?')) return;

    try {
        await api.deleteWarehouse(id);
        showAlert('Warehouse deleted successfully', 'success');
        await loadWarehouses();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

// Boxes
async function loadBoxes() {
    try {
        warehouses = await api.getWarehouses();
        updateWarehouseSelects();

        const warehouseId = document.getElementById('boxWarehouseFilter').value;
        boxes = await api.getBoxes(warehouseId || null);
        renderBoxes();
    } catch (error) {
        showAlert('Failed to load boxes', 'danger');
    }
}

function updateWarehouseSelects() {
    const selects = document.querySelectorAll('.warehouse-select');
    const options = `<option value="">All Warehouses</option>` +
        warehouses.map(w => `<option value="${w.id}">${escapeHtml(w.name)}</option>`).join('');

    selects.forEach(select => {
        const currentValue = select.value;
        select.innerHTML = options;
        if (currentValue) select.value = currentValue;
    });

    // Required selects (for forms)
    const requiredSelects = document.querySelectorAll('.warehouse-select-required');
    const requiredOptions = warehouses.map(w => 
        `<option value="${w.id}">${escapeHtml(w.name)}</option>`
    ).join('');

    requiredSelects.forEach(select => {
        select.innerHTML = `<option value="">Select Warehouse</option>` + requiredOptions;
    });
}

function renderBoxes() {
    const tbody = document.getElementById('boxesTable');
    const isManager = ['administrator', 'manager'].includes(currentUser.role);

    if (boxes.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="empty-state">
                    <i class="fas fa-box"></i>
                    <h3>No boxes found</h3>
                    <p>Create a new box to start organizing items</p>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = boxes.map(b => {
        const warehouse = warehouses.find(w => w.id === b.warehouse_id);
        return `
            <tr>
                <td><code>${escapeHtml(b.barcode)}</code></td>
                <td><strong>${escapeHtml(b.name)}</strong></td>
                <td>${escapeHtml(b.description || '-')}</td>
                <td>${warehouse ? escapeHtml(warehouse.name) : '-'}</td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-primary" onclick="viewBox(${b.id})">
                            <i class="fas fa-eye"></i>
                        </button>
                        ${isManager ? `
                            <button class="btn btn-sm btn-warning" onclick="editBox(${b.id})">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-success" onclick="showMoveBoxModal(${b.id})">
                                <i class="fas fa-truck"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteBox(${b.id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        ` : ''}
                    </div>
                </td>
                <td class="barcode-visual"><svg class="barcode" data-barcode="${escapeHtml(b.barcode)}"></svg></td>
            </tr>
        `;
    }).join('');
    
    // Render visual barcodes
    renderBarcodes();
}

async function viewBox(id) {
    document.getElementById('itemBoxFilter').value = id;
    navigateTo('items');
}

function showBoxModal(box = null) {
    const modal = document.getElementById('boxModal');
    const form = document.getElementById('boxForm');
    const title = document.getElementById('boxModalTitle');

    form.reset();
    form.dataset.id = box ? box.id : '';
    title.textContent = box ? 'Edit Box' : 'Add Box';

    if (box) {
        document.getElementById('boxBarcode').value = box.barcode;
        document.getElementById('boxName').value = box.name;
        document.getElementById('boxDescription').value = box.description || '';
        document.getElementById('boxWarehouse').value = box.warehouse_id;
    }

    modal.classList.add('active');
}

function closeBoxModal() {
    document.getElementById('boxModal').classList.remove('active');
    // Clear the form data ID to prevent stale edit state
    document.getElementById('boxForm').dataset.id = '';
}

async function saveBox(e) {
    e.preventDefault();
    const form = e.target;
    const id = form.dataset.id;

    const data = {
        barcode: document.getElementById('boxBarcode').value,
        name: document.getElementById('boxName').value,
        description: document.getElementById('boxDescription').value || null,
        warehouse_id: parseInt(document.getElementById('boxWarehouse').value)
    };

    try {
        if (id) {
            await api.updateBox(id, data);
            showAlert('Box updated successfully', 'success');
        } else {
            await api.createBox(data);
            showAlert('Box created successfully', 'success');
        }
        closeBoxModal();
        await loadBoxes();
        // Refresh box selects in item forms
        boxes = await api.getBoxes();
        updateBoxSelects();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

function editBox(id) {
    const box = boxes.find(b => b.id === id);
    if (box) {
        showBoxModal(box);
    }
}

async function deleteBox(id) {
    if (!confirm('Are you sure you want to delete this box?')) return;

    try {
        await api.deleteBox(id);
        showAlert('Box deleted successfully', 'success');
        await loadBoxes();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

function showMoveBoxModal(id) {
    const box = boxes.find(b => b.id === id);
    if (!box) return;

    document.getElementById('moveBoxId').value = id;
    document.getElementById('moveBoxName').textContent = box.name;
    document.getElementById('moveBoxTarget').value = '';
    document.getElementById('moveBoxModal').classList.add('active');
}

function showMoveBoxModalFromChain(box) {
    // Called from code chain (box scanned + ACTION:MOVE)
    document.getElementById('moveBoxId').value = box.id;
    document.getElementById('moveBoxName').textContent = box.name;
    document.getElementById('moveBoxTarget').value = '';
    document.getElementById('moveBoxModal').classList.add('active');
}

function closeMoveBoxModal() {
    document.getElementById('moveBoxModal').classList.remove('active');
    // Clear code chain if we were in a box move flow
    if (codeChain.box && codeChain.action === 'move') {
        clearCodeChain();
    }
}

async function moveBox(e) {
    e.preventDefault();
    const boxId = document.getElementById('moveBoxId').value;
    const targetId = document.getElementById('moveBoxTarget').value;

    try {
        const movedBox = await api.moveBox(boxId, targetId);
        const targetWarehouse = warehouses.find(w => w.id === parseInt(targetId));
        
        // Check if this was from code chain
        if (codeChain.box && codeChain.action === 'move') {
            showCodeChainSuccess(`Moved box "${codeChain.box.name}" → "${targetWarehouse?.name || 'warehouse'}"`); 
        } else {
            showAlert('Box moved successfully', 'success');
        }
        
        closeMoveBoxModal();
        
        // Refresh data
        await preloadData();
        if (!document.getElementById('page-boxes').classList.contains('hidden')) {
            await loadBoxes();
        }
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

// Items
async function loadItems() {
    try {
        boxes = await api.getBoxes();
        updateBoxSelects();

        const boxId = document.getElementById('itemBoxFilter').value;
        const search = document.getElementById('itemSearch').value;
        items = await api.getItems(boxId || null, search || null);
        renderItems();
    } catch (error) {
        showAlert('Failed to load items', 'danger');
    }
}

function updateBoxSelects() {
    const selects = document.querySelectorAll('.box-select');
    const options = `<option value="">All Boxes</option>` +
        boxes.map(b => `<option value="${b.id}">${escapeHtml(b.name)} (${escapeHtml(b.barcode)})</option>`).join('');

    selects.forEach(select => {
        const currentValue = select.value;
        select.innerHTML = options;
        if (currentValue) select.value = currentValue;
    });

    // Required selects
    const requiredSelects = document.querySelectorAll('.box-select-required');
    const requiredOptions = boxes.map(b => 
        `<option value="${b.id}">${escapeHtml(b.name)} (${escapeHtml(b.barcode)})</option>`
    ).join('');

    requiredSelects.forEach(select => {
        select.innerHTML = `<option value="">Select Box</option>` + requiredOptions;
    });
}

function renderItems() {
    const tbody = document.getElementById('itemsTable');
    const isManager = ['administrator', 'manager'].includes(currentUser.role);

    if (items.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="8" class="empty-state">
                    <i class="fas fa-cube"></i>
                    <h3>No items found</h3>
                    <p>Add items to your inventory</p>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = items.map(item => {
        const box = boxes.find(b => b.id === item.box_id);
        const priceDisplay = item.price !== null && item.price !== undefined 
            ? `$${item.price.toFixed(2)}` 
            : '-';
        return `
            <tr>
                <td><code>${escapeHtml(item.barcode)}</code></td>
                <td><strong>${escapeHtml(item.name)}</strong></td>
                <td>${escapeHtml(item.description || '-')}</td>
                <td>${item.quantity}</td>
                <td>${priceDisplay}</td>
                <td>${box ? escapeHtml(box.name) : '-'}</td>
                <td>
                    <div class="btn-group">
                        ${isManager ? `
                            <button class="btn btn-sm btn-success" onclick="showStoreItemModal(${item.id})" title="Store more">
                                <i class="fas fa-plus"></i>
                            </button>
                            <button class="btn btn-sm btn-warning" onclick="showTakeItemModal(${item.id})" title="Take items">
                                <i class="fas fa-minus"></i>
                            </button>
                            <button class="btn btn-sm btn-primary" onclick="showMoveItemModal(${item.id})" title="Move">
                                <i class="fas fa-arrows-alt"></i>
                            </button>
                            <button class="btn btn-sm btn-secondary" onclick="editItem(${item.id})" title="Edit">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteItem(${item.id})" title="Delete">
                                <i class="fas fa-trash"></i>
                            </button>
                        ` : ''}
                    </div>
                </td>
                <td class="barcode-visual"><svg class="barcode" data-barcode="${escapeHtml(item.barcode)}"></svg></td>
            </tr>
        `;
    }).join('');
    
    // Render visual barcodes
    renderBarcodes();
}

function showItemModal(item = null) {
    const modal = document.getElementById('itemModal');
    const form = document.getElementById('itemForm');
    const title = document.getElementById('itemModalTitle');

    form.reset();
    form.dataset.id = item ? item.id : '';
    title.textContent = item ? 'Edit Item' : 'Add Item';
    
    // Update box datalist
    updateBoxSelects();

    if (item) {
        document.getElementById('itemId').value = item.id;
        document.getElementById('itemBarcode').value = item.barcode;
        const box = boxes.find(b => b.id === item.box_id);
        document.getElementById('itemBoxInput').value = box ? box.barcode : '';
        document.getElementById('itemBoxId').value = item.box_id;
        document.getElementById('itemName').value = item.name;
        document.getElementById('itemDescription').value = item.description || '';
        document.getElementById('itemQuantity').value = item.quantity;
        document.getElementById('itemPrice').value = item.price || '';
    } else {
        document.getElementById('itemId').value = '';
        document.getElementById('itemBoxInput').value = '';
        document.getElementById('itemBoxId').value = '';
    }

    modal.classList.add('active');
}

function closeItemModal() {
    document.getElementById('itemModal').classList.remove('active');
}

async function saveItem(e) {
    e.preventDefault();
    const form = e.target;
    const id = form.dataset.id;
    
    // Resolve box ID from input
    const boxInput = document.getElementById('itemBoxInput').value.trim();
    let boxId = document.getElementById('itemBoxId').value;
    
    if (!boxId && boxInput) {
        // Try to find box by barcode or name
        const box = boxes.find(b => b.barcode === boxInput || b.name === boxInput);
        if (box) {
            boxId = box.id;
        } else {
            showAlert('Box not found. Please select a valid box.', 'danger');
            return;
        }
    }
    
    if (!boxId) {
        showAlert('Please select a box', 'danger');
        return;
    }

    const priceValue = document.getElementById('itemPrice').value;
    const data = {
        barcode: document.getElementById('itemBarcode').value,
        name: document.getElementById('itemName').value,
        description: document.getElementById('itemDescription').value || null,
        quantity: parseInt(document.getElementById('itemQuantity').value),
        price: priceValue ? parseFloat(priceValue) : null,
        box_id: parseInt(boxId)
    };

    try {
        if (id) {
            await api.updateItem(id, data);
            showAlert('Item updated successfully', 'success');
        } else {
            await api.createItem(data);
            showAlert('Item created successfully', 'success');
        }
        closeItemModal();
        await loadItems();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

function editItem(id) {
    const item = items.find(i => i.id === id);
    if (item) {
        showItemModal(item);
    }
}

async function deleteItem(id) {
    if (!confirm('Are you sure you want to delete this item?')) return;

    try {
        await api.deleteItem(id);
        showAlert('Item deleted successfully', 'success');
        await loadItems();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

function showStoreItemModal(id) {
    const item = items.find(i => i.id === id);
    if (!item) return;

    document.getElementById('storeItemId').value = id;
    document.getElementById('storeItemName').textContent = item.name;
    document.getElementById('storeItemQuantity').value = 1;
    document.getElementById('storeItemModal').classList.add('active');
}

function closeStoreItemModal() {
    document.getElementById('storeItemModal').classList.remove('active');
}

async function storeItem(e) {
    e.preventDefault();
    const id = document.getElementById('storeItemId').value;
    const quantity = parseInt(document.getElementById('storeItemQuantity').value);

    try {
        await api.storeItem(id, quantity);
        showAlert(`Added ${quantity} item(s) to inventory`, 'success');
        closeStoreItemModal();
        await loadItems();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

function showTakeItemModal(id) {
    const item = items.find(i => i.id === id);
    if (!item) return;

    document.getElementById('takeItemId').value = id;
    document.getElementById('takeItemName').textContent = item.name;
    document.getElementById('takeItemMax').textContent = item.quantity;
    document.getElementById('takeItemQuantity').value = 1;
    document.getElementById('takeItemQuantity').max = item.quantity;
    document.getElementById('takeItemModal').classList.add('active');
}

function closeTakeItemModal() {
    document.getElementById('takeItemModal').classList.remove('active');
}

async function takeItem(e) {
    e.preventDefault();
    const id = document.getElementById('takeItemId').value;
    const quantity = parseInt(document.getElementById('takeItemQuantity').value);

    try {
        await api.takeItem(id, quantity);
        showAlert(`Took ${quantity} item(s) from inventory`, 'success');
        closeTakeItemModal();
        await loadItems();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

function showMoveItemModal(id) {
    const item = items.find(i => i.id === id);
    if (!item) return;

    document.getElementById('moveItemId').value = id;
    document.getElementById('moveItemName').textContent = item.name;
    document.getElementById('moveItemTarget').value = '';
    document.getElementById('moveItemModal').classList.add('active');
}

function closeMoveItemModal() {
    document.getElementById('moveItemModal').classList.remove('active');
}

async function moveItem(e) {
    e.preventDefault();
    const id = document.getElementById('moveItemId').value;
    const targetId = document.getElementById('moveItemTarget').value;

    try {
        await api.moveItem(id, targetId);
        showAlert('Item moved successfully', 'success');
        closeMoveItemModal();
        await loadItems();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

// ==================== INVENTORY CHECKS ====================

async function loadChecks() {
    try {
        const statusFilter = document.getElementById('checkStatusFilter')?.value || '';
        inventoryChecks = await api.getChecks(statusFilter || null);
        
        // Also check for active check
        activeCheck = await api.getActiveCheck();
        updateActiveCheckBanner();
        
        renderChecks();
    } catch (error) {
        showAlert('Failed to load checks', 'danger');
    }
}

function filterChecks() {
    loadChecks();
}

function updateActiveCheckBanner() {
    const banner = document.getElementById('activeCheckBanner');
    if (!banner) return;
    
    if (activeCheck && activeCheck.status === 'in_progress') {
        banner.classList.remove('hidden');
        document.getElementById('activeCheckName').textContent = activeCheck.name;
        
        // Calculate progress
        let total = 0, checked = 0;
        activeCheck.boxes.forEach(box => {
            total += box.total_items;
            checked += box.checked_items;
        });
        document.getElementById('activeCheckProgress').textContent = `${checked}/${total} items`;
    } else {
        banner.classList.add('hidden');
    }
}

function renderChecks() {
    const tbody = document.getElementById('checksTable');
    const isManager = ['administrator', 'manager'].includes(currentUser.role);
    const isAdmin = currentUser.role === 'administrator';
    
    if (inventoryChecks.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="empty-state">
                    <i class="fas fa-clipboard-check"></i>
                    <h3>No inventory checks</h3>
                    <p>Start a new check to verify your inventory</p>
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = inventoryChecks.map(check => {
        const statusClass = {
            'in_progress': 'status-sourcing',
            'completed': 'status-done',
            'cancelled': 'status-cancelled'
        }[check.status] || '';
        
        const statusText = {
            'in_progress': 'In Progress',
            'completed': 'Completed',
            'cancelled': 'Cancelled'
        }[check.status] || check.status;
        
        const progress = check.total_items > 0 
            ? Math.round((check.checked_items / check.total_items) * 100) 
            : 0;
        
        return `
            <tr>
                <td><strong>${escapeHtml(check.name)}</strong></td>
                <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                <td>
                    <div class="progress-bar-small">
                        <div class="progress-fill" style="width: ${progress}%"></div>
                    </div>
                    <span class="progress-text">${check.checked_items}/${check.total_items}</span>
                </td>
                <td>
                    ${check.items_with_difference > 0 
                        ? `<span class="diff-badge">${check.items_with_difference}</span>` 
                        : '-'}
                </td>
                <td>${formatDate(check.started_at)}</td>
                <td>${check.completed_at ? formatDate(check.completed_at) : '-'}</td>
                <td>
                    <button class="btn btn-sm" onclick="viewCheck(${check.id})" title="View">
                        <i class="fas fa-eye"></i>
                    </button>
                    ${isAdmin ? `
                        <button class="btn btn-sm btn-danger" onclick="deleteCheck(${check.id})" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : ''}
                </td>
            </tr>
        `;
    }).join('');
}

function showNewCheckModal() {
    document.getElementById('checkName').value = '';
    document.getElementById('checkDescription').value = '';
    document.getElementById('newCheckModal').classList.add('active');
    setTimeout(() => document.getElementById('checkName').focus(), 100);
}

function closeNewCheckModal() {
    document.getElementById('newCheckModal').classList.remove('active');
}

async function createNewCheck(e) {
    e.preventDefault();
    
    try {
        const check = await api.createCheck({
            name: document.getElementById('checkName').value,
            description: document.getElementById('checkDescription').value || null
        });
        
        closeNewCheckModal();
        showAlert('Inventory check started!', 'success');
        
        // Navigate to the new check
        viewCheck(check.id);
    } catch (error) {
        showAlert(`Failed to create check: ${error.message}`, 'danger');
    }
}

async function viewCheck(checkId) {
    try {
        currentCheckDetail = await api.getCheckGrouped(checkId);
        activeCheck = currentCheckDetail; // Set as active for scanning
        
        renderCheckDetail();
        
        // Navigate to detail page
        document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
        document.getElementById('page-check-detail').classList.remove('hidden');
        
        // Update nav highlight
        document.querySelectorAll('.sidebar-nav a').forEach(a => a.classList.remove('active'));
        document.querySelector('[data-page="checks"]')?.classList.add('active');
        
        // Load previous checks for comparison dropdown
        await loadComparisonOptions();
        
    } catch (error) {
        showAlert(`Failed to load check: ${error.message}`, 'danger');
    }
}

function viewActiveCheck() {
    if (activeCheck) {
        viewCheck(activeCheck.id);
    }
}

function renderCheckDetail() {
    if (!currentCheckDetail) return;
    
    // Update title and action buttons
    document.getElementById('checkDetailTitle').textContent = currentCheckDetail.name;
    
    const isInProgress = currentCheckDetail.status === 'in_progress';
    document.getElementById('completeCheckBtn').classList.toggle('hidden', !isInProgress);
    document.getElementById('cancelCheckBtn').classList.toggle('hidden', !isInProgress);
    document.getElementById('checkModeHint').classList.toggle('hidden', !isInProgress);
    
    // Calculate totals
    let totalItems = 0, checkedItems = 0, differences = 0;
    currentCheckDetail.boxes.forEach(box => {
        totalItems += box.total_items;
        checkedItems += box.checked_items;
        box.items.forEach(item => {
            if (item.difference !== null && item.difference !== 0) {
                differences++;
            }
        });
    });
    
    document.getElementById('checkTotalItems').textContent = totalItems;
    document.getElementById('checkCheckedItems').textContent = checkedItems;
    document.getElementById('checkRemainingItems').textContent = totalItems - checkedItems;
    document.getElementById('checkDifferences').textContent = differences;
    
    // Render box groups
    const container = document.getElementById('checkBoxGroups');
    container.innerHTML = currentCheckDetail.boxes.map(box => `
        <div class="check-box-group">
            <div class="check-box-header" onclick="toggleCheckBoxGroup(this)">
                <span class="box-name">
                    <i class="fas fa-box"></i> ${escapeHtml(box.box_name)}
                </span>
                <span class="box-progress ${box.checked_items === box.total_items ? 'complete' : ''}">
                    ${box.checked_items}/${box.total_items}
                </span>
                <i class="fas fa-chevron-down toggle-icon"></i>
            </div>
            <div class="check-box-items">
                <table class="check-items-table">
                    <thead>
                        <tr>
                            <th>Barcode</th>
                            <th>Name</th>
                            <th>Expected</th>
                            <th>Actual</th>
                            <th>Diff</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${box.items.map(item => renderCheckItem(item)).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `).join('');
}

function renderCheckItem(item) {
    const isChecked = item.actual_quantity !== null;
    const diff = item.difference;
    const diffClass = diff === null ? '' : (diff === 0 ? 'diff-ok' : (diff > 0 ? 'diff-plus' : 'diff-minus'));
    const diffText = diff === null ? '-' : (diff > 0 ? `+${diff}` : diff);
    
    return `
        <tr class="${isChecked ? 'checked' : 'unchecked'}" onclick="showCheckQuantityModalForItem(${item.item_id})">
            <td><code>${escapeHtml(item.item_barcode)}</code></td>
            <td>${escapeHtml(item.item_name)}</td>
            <td class="qty">${item.expected_quantity}</td>
            <td class="qty">${item.actual_quantity !== null ? item.actual_quantity : '-'}</td>
            <td class="qty ${diffClass}">${diffText}</td>
            <td>
                ${isChecked 
                    ? '<i class="fas fa-check-circle text-success"></i>' 
                    : '<i class="fas fa-circle text-muted"></i>'}
            </td>
        </tr>
    `;
}

function toggleCheckBoxGroup(header) {
    const group = header.parentElement;
    group.classList.toggle('collapsed');
}

async function loadComparisonOptions() {
    try {
        const allChecks = await api.getChecks();
        const select = document.getElementById('compareCheckSelect');
        
        // Filter out current check and only show completed checks
        const otherChecks = allChecks.filter(c => 
            c.id !== currentCheckDetail.id && c.status === 'completed'
        );
        
        select.innerHTML = '<option value="">Compare with...</option>' + 
            otherChecks.map(c => 
                `<option value="${c.id}">${escapeHtml(c.name)} (${formatDate(c.completed_at)})</option>`
            ).join('');
    } catch (error) {
        console.error('Failed to load comparison options:', error);
    }
}

async function loadCheckComparison() {
    const previousCheckId = document.getElementById('compareCheckSelect').value;
    if (!previousCheckId || !currentCheckDetail) return;
    
    try {
        const comparisons = await api.compareChecks(currentCheckDetail.id, previousCheckId);
        renderCheckComparison(comparisons);
    } catch (error) {
        showAlert(`Failed to load comparison: ${error.message}`, 'danger');
    }
}

function renderCheckComparison(comparisons) {
    // Show items that have changes since last check
    const changedItems = comparisons.filter(c => c.change_since_last !== null && c.change_since_last !== 0);
    
    if (changedItems.length === 0) {
        showAlert('No changes detected since the previous check', 'info');
        return;
    }
    
    // Create a modal or section to show comparison
    const content = `
        <div class="comparison-list">
            <h4>Changes since previous check:</h4>
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Item</th>
                        <th>Box</th>
                        <th>Previous Count</th>
                        <th>Current Expected</th>
                        <th>Change</th>
                    </tr>
                </thead>
                <tbody>
                    ${changedItems.map(c => `
                        <tr>
                            <td>${escapeHtml(c.item_name)}</td>
                            <td>${escapeHtml(c.box_name || '-')}</td>
                            <td>${c.previous_actual !== null ? c.previous_actual : '-'}</td>
                            <td>${c.current_expected}</td>
                            <td class="${c.change_since_last > 0 ? 'diff-plus' : 'diff-minus'}">
                                ${c.change_since_last > 0 ? '+' : ''}${c.change_since_last}
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>
    `;
    
    // Show in alert or create a popup
    showComparisonModal(content);
}

function showComparisonModal(content) {
    // Create modal if doesn't exist
    let modal = document.getElementById('comparisonModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'comparisonModal';
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal modal-lg">
                <div class="modal-header">
                    <h3>Comparison with Previous Check</h3>
                    <button class="modal-close" onclick="closeComparisonModal()">&times;</button>
                </div>
                <div class="modal-body" id="comparisonContent"></div>
                <div class="modal-footer">
                    <button class="btn" onclick="closeComparisonModal()">Close</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    
    document.getElementById('comparisonContent').innerHTML = content;
    modal.classList.add('active');
}

function closeComparisonModal() {
    const modal = document.getElementById('comparisonModal');
    if (modal) modal.classList.remove('active');
}

// Handle scanning an item during check mode
async function handleCheckItemScan(barcode) {
    if (!activeCheck || !currentCheckDetail) return;
    
    // Find the item in the check
    let foundItem = null;
    for (const box of currentCheckDetail.boxes) {
        foundItem = box.items.find(i => i.item_barcode === barcode);
        if (foundItem) break;
    }
    
    if (!foundItem) {
        showAlert(`Item with barcode "${barcode}" not found in this check`, 'warning');
        return;
    }
    
    // Show quantity modal for this item
    showCheckQuantityModal(foundItem);
}

function showCheckQuantityModalForItem(itemId) {
    if (!currentCheckDetail) return;
    
    let foundItem = null;
    for (const box of currentCheckDetail.boxes) {
        foundItem = box.items.find(i => i.item_id === itemId);
        if (foundItem) break;
    }
    
    if (foundItem) {
        showCheckQuantityModal(foundItem);
    }
}

function showCheckQuantityModal(item) {
    currentCheckItem = item;
    
    document.getElementById('checkItemName').textContent = item.item_name;
    document.getElementById('checkItemBarcode').textContent = item.item_barcode;
    document.getElementById('checkItemBox').textContent = item.box_name || 'No box';
    document.getElementById('checkExpectedQty').textContent = item.expected_quantity;
    
    const input = document.getElementById('checkActualQty');
    input.value = item.actual_quantity !== null ? item.actual_quantity : '';
    
    document.getElementById('checkQuantityModal').classList.add('active');
    setTimeout(() => {
        input.focus();
        input.select();
    }, 100);
}

function closeCheckQuantityModal() {
    document.getElementById('checkQuantityModal').classList.remove('active');
    currentCheckItem = null;
}

function incrementCheckQuantity() {
    const input = document.getElementById('checkActualQty');
    const current = parseInt(input.value) || 0;
    input.value = current + 1;
}

function decrementCheckQuantity() {
    const input = document.getElementById('checkActualQty');
    const current = parseInt(input.value) || 0;
    if (current > 0) {
        input.value = current - 1;
    }
}

async function submitCheckQuantity() {
    if (!currentCheckItem || !activeCheck) return;
    
    const input = document.getElementById('checkActualQty');
    const quantity = parseInt(input.value);
    
    if (isNaN(quantity) || quantity < 0) {
        showAlert('Please enter a valid quantity', 'warning');
        return;
    }
    
    try {
        await api.updateCheckItem(activeCheck.id, currentCheckItem.item_id, quantity);
        
        const itemName = currentCheckItem.item_name;
        closeCheckQuantityModal();
        showAlert(`Counted: ${itemName} = ${quantity}`, 'success');
        
        // Refresh the check detail
        currentCheckDetail = await api.getCheckGrouped(activeCheck.id);
        activeCheck = currentCheckDetail;
        renderCheckDetail();
        updateActiveCheckBanner();
        
    } catch (error) {
        showAlert(`Failed to update count: ${error.message}`, 'danger');
    }
}

async function completeActiveCheck() {
    if (!activeCheck) return;
    await completeCheckById(activeCheck.id);
}

async function completeCurrentCheck() {
    if (!currentCheckDetail) return;
    await completeCheckById(currentCheckDetail.id);
}

async function completeCheckById(checkId) {
    if (!confirm('Complete this inventory check? Make sure all items have been counted.')) return;
    
    try {
        await api.completeCheck(checkId);
        showAlert('Inventory check completed!', 'success');
        
        activeCheck = null;
        await loadChecks();
        navigateTo('checks');
    } catch (error) {
        showAlert(`Failed to complete check: ${error.message}`, 'danger');
    }
}

async function cancelActiveCheck() {
    if (!activeCheck) return;
    await cancelCheckById(activeCheck.id);
}

async function cancelCurrentCheck() {
    if (!currentCheckDetail) return;
    await cancelCheckById(currentCheckDetail.id);
}

async function cancelCheckById(checkId) {
    if (!confirm('Cancel this inventory check? All progress will be lost.')) return;
    
    try {
        await api.cancelCheck(checkId);
        showAlert('Inventory check cancelled', 'info');
        
        activeCheck = null;
        await loadChecks();
        navigateTo('checks');
    } catch (error) {
        showAlert(`Failed to cancel check: ${error.message}`, 'danger');
    }
}

async function deleteCheck(checkId) {
    if (!confirm('Delete this inventory check? This cannot be undone.')) return;
    
    try {
        await api.deleteCheck(checkId);
        showAlert('Check deleted', 'success');
        await loadChecks();
    } catch (error) {
        showAlert(`Failed to delete check: ${error.message}`, 'danger');
    }
}

function exportCheckForPrint() {
    if (!currentCheckDetail) return;
    
    // Open the export URL in a new tab with token
    const token = localStorage.getItem('token');
    const url = `/api/checks/${currentCheckDetail.id}/export?token=${encodeURIComponent(token)}`;
    window.open(url, '_blank');
}

// ==================== END INVENTORY CHECKS ====================

// ==================== CHANGE PASSWORD ====================

let changePasswordTargetUser = null;

function showChangePasswordModal() {
    // Self password change - requires current password
    changePasswordTargetUser = null;
    document.getElementById('changePasswordUserId').value = '';
    document.getElementById('changePasswordTitle').innerHTML = '<i class="fas fa-key"></i> Change Password';
    document.getElementById('currentPasswordGroup').style.display = 'block';
    document.getElementById('currentPassword').required = true;
    document.getElementById('currentPassword').value = '';
    document.getElementById('newPassword').value = '';
    document.getElementById('confirmPassword').value = '';
    document.getElementById('changePasswordModal').classList.add('active');
    document.getElementById('currentPassword').focus();
}

function showChangePasswordModalForUser(userId) {
    // Admin changing another user's password - no current password needed
    const user = usersData.find(u => u.id === userId);
    changePasswordTargetUser = user;
    document.getElementById('changePasswordUserId').value = userId;
    document.getElementById('changePasswordTitle').innerHTML = `<i class="fas fa-key"></i> Set Password for ${user ? escapeHtml(user.username) : 'User'}`;
    document.getElementById('currentPasswordGroup').style.display = 'none';
    document.getElementById('currentPassword').required = false;
    document.getElementById('currentPassword').value = '';
    document.getElementById('newPassword').value = '';
    document.getElementById('confirmPassword').value = '';
    document.getElementById('changePasswordModal').classList.add('active');
    document.getElementById('newPassword').focus();
}

function closeChangePasswordModal() {
    document.getElementById('changePasswordModal').classList.remove('active');
    changePasswordTargetUser = null;
}

async function changePassword(e) {
    e.preventDefault();
    
    const userId = document.getElementById('changePasswordUserId').value;
    const currentPassword = document.getElementById('currentPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    
    if (newPassword !== confirmPassword) {
        showAlert('New passwords do not match', 'danger');
        return;
    }
    
    if (newPassword.length < 6) {
        showAlert('New password must be at least 6 characters', 'warning');
        return;
    }
    
    try {
        if (userId) {
            // Admin setting another user's password
            await api.setUserPassword(userId, newPassword);
            showAlert('Password updated successfully', 'success');
        } else {
            // Self password change
            await api.changePassword(currentPassword, newPassword);
            showAlert('Password changed successfully', 'success');
        }
        closeChangePasswordModal();
    } catch (error) {
        showAlert(error.message || 'Failed to change password', 'danger');
    }
}

// ==================== END CHANGE PASSWORD ====================

// Users
async function loadUsers() {
    if (currentUser.role !== 'administrator') {
        return;
    }

    try {
        const users = await api.getUsers();
        renderUsers(users);
    } catch (error) {
        showAlert('Failed to load users', 'danger');
    }
}

function renderUsers(users) {
    const tbody = document.getElementById('usersTable');

    tbody.innerHTML = users.map(u => `
        <tr>
            <td>${u.id}</td>
            <td><strong>${escapeHtml(u.username)}</strong></td>
            <td>${escapeHtml(u.email)}</td>
            <td>${escapeHtml(u.full_name || '-')}</td>
            <td><span class="badge badge-${u.role}">${u.role}</span></td>
            <td><span class="badge badge-${u.is_active ? 'active' : 'inactive'}">${u.is_active ? 'Active' : 'Inactive'}</span></td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-sm btn-secondary" onclick="showChangePasswordModalForUser(${u.id})" title="Change Password">
                        <i class="fas fa-key"></i>
                    </button>
                    <button class="btn btn-sm btn-warning" onclick="editUser(${u.id})" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                    ${u.id !== currentUser.id ? `
                        <button class="btn btn-sm btn-danger" onclick="deleteUser(${u.id})" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : ''}
                </div>
            </td>
        </tr>
    `).join('');
}

let usersData = [];

async function editUser(id) {
    try {
        usersData = await api.getUsers();
        const user = usersData.find(u => u.id === id);
        if (user) {
            showUserModal(user);
        }
    } catch (error) {
        showAlert('Failed to load user', 'danger');
    }
}

function showUserModal(user = null) {
    const modal = document.getElementById('userModal');
    const form = document.getElementById('userForm');
    const title = document.getElementById('userModalTitle');
    const passwordGroup = document.getElementById('userPasswordGroup');

    form.reset();
    form.dataset.id = user ? user.id : '';
    title.textContent = user ? 'Edit User' : 'Add User';
    passwordGroup.style.display = user ? 'none' : 'block';

    if (user) {
        document.getElementById('userUsername').value = user.username;
        document.getElementById('userEmail').value = user.email;
        document.getElementById('userFullName').value = user.full_name || '';
        document.getElementById('userRole').value = user.role;
        document.getElementById('userActive').checked = user.is_active;
    }

    modal.classList.add('active');
}

function closeUserModal() {
    document.getElementById('userModal').classList.remove('active');
}

async function saveUser(e) {
    e.preventDefault();
    const form = e.target;
    const id = form.dataset.id;

    const data = {
        username: document.getElementById('userUsername').value,
        email: document.getElementById('userEmail').value,
        full_name: document.getElementById('userFullName').value || null,
        role: document.getElementById('userRole').value,
        is_active: document.getElementById('userActive').checked
    };

    if (!id) {
        data.password = document.getElementById('userPassword').value;
    }

    try {
        if (id) {
            await api.updateUser(id, data);
            showAlert('User updated successfully', 'success');
        } else {
            await api.createUser(data);
            showAlert('User created successfully', 'success');
        }
        closeUserModal();
        await loadUsers();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

async function deleteUser(id) {
    if (!confirm('Are you sure you want to delete this user?')) return;

    try {
        await api.deleteUser(id);
        showAlert('User deleted successfully', 'success');
        await loadUsers();
    } catch (error) {
        showAlert(error.message, 'danger');
    }
}

// Utility functions
function showAlert(message, type = 'info') {
    const alertsContainer = document.getElementById('alerts');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'danger' ? 'exclamation-circle' : 'info-circle'}"></i>
        ${escapeHtml(message)}
    `;
    alertsContainer.appendChild(alert);

    setTimeout(() => {
        alert.remove();
    }, 5000);
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Render visual barcodes using JsBarcode
function renderBarcodes() {
    document.querySelectorAll('svg.barcode[data-barcode]').forEach(svg => {
        const value = svg.dataset.barcode;
        if (value && typeof JsBarcode !== 'undefined') {
            try {
                JsBarcode(svg, value, {
                    format: 'CODE128',
                    width: 1.5,
                    height: 30,
                    displayValue: false,
                    margin: 0,
                    background: 'transparent'
                });
            } catch (e) {
                // If barcode generation fails, hide the SVG
                svg.style.display = 'none';
            }
        }
    });
}

// Filter handlers
function filterBoxes() {
    loadBoxes();
}

function filterItems() {
    loadItems();
}

function searchItems() {
    loadItems();
}

// CSV Export Functions
async function exportItemsCSV() {
    try {
        showAlert('Exporting items...', 'info');
        const blob = await api.exportItemsCSV();
        downloadBlob(blob, 'items.csv');
        showAlert('Items exported successfully', 'success');
    } catch (error) {
        showAlert('Failed to export items: ' + error.message, 'danger');
    }
}

async function exportBoxesCSV() {
    try {
        showAlert('Exporting boxes...', 'info');
        const blob = await api.exportBoxesCSV();
        downloadBlob(blob, 'boxes.csv');
        showAlert('Boxes exported successfully', 'success');
    } catch (error) {
        showAlert('Failed to export boxes: ' + error.message, 'danger');
    }
}

function downloadBlob(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
}

// CSV Import Functions
async function importItemsCSV(input) {
    const file = input.files[0];
    if (!file) return;
    
    try {
        showAlert('Importing items...', 'info');
        const result = await api.importItemsCSV(file);
        showAlert(`Import complete: ${result.created} created, ${result.updated} updated${result.errors.length ? ', ' + result.errors.length + ' errors' : ''}`, 
            result.errors.length ? 'warning' : 'success');
        
        if (result.errors.length) {
            console.log('Import errors:', result.errors);
        }
        
        await loadItems();
    } catch (error) {
        showAlert('Failed to import items: ' + error.message, 'danger');
    }
    
    // Reset file input
    input.value = '';
}

async function importBoxesCSV(input) {
    const file = input.files[0];
    if (!file) return;
    
    try {
        showAlert('Importing boxes...', 'info');
        const result = await api.importBoxesCSV(file);
        showAlert(`Import complete: ${result.created} created, ${result.updated} updated${result.errors.length ? ', ' + result.errors.length + ' errors' : ''}`, 
            result.errors.length ? 'warning' : 'success');
        
        if (result.errors.length) {
            console.log('Import errors:', result.errors);
        }
        
        await loadBoxes();
    } catch (error) {
        showAlert('Failed to import boxes: ' + error.message, 'danger');
    }
    
    // Reset file input
    input.value = '';
}

// ==================== Orders ====================

async function loadOrders() {
    try {
        orders = await api.getOrders();
        renderOrders();
    } catch (error) {
        showAlert('Failed to load orders', 'danger');
    }
}

function filterOrders() {
    const status = document.getElementById('orderStatusFilter').value;
    renderOrders(status);
}

function renderOrders(statusFilter = null) {
    const tbody = document.getElementById('ordersTable');
    const isManager = ['administrator', 'manager'].includes(currentUser.role);
    
    let filteredOrders = orders;
    if (statusFilter) {
        filteredOrders = orders.filter(o => o.status === statusFilter);
    }

    if (filteredOrders.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="empty-state">
                    <i class="fas fa-clipboard-list"></i>
                    <h3>No orders found</h3>
                    <p>Create a new order or adjust filters</p>
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = filteredOrders.map(o => `
        <tr>
            <td><code>${escapeHtml(o.barcode)}</code></td>
            <td><strong>${escapeHtml(o.name)}</strong></td>
            <td><span class="status-badge ${o.status}">${o.status.toUpperCase()}</span></td>
            <td>${o.item_count} items (${o.total_quantity} pcs)</td>
            <td>${new Date(o.created_at).toLocaleDateString()}</td>
            <td>
                <div class="btn-group">
                    <button class="btn btn-sm btn-primary" onclick="showOrderDetail(${o.id})" title="View Details">
                        <i class="fas fa-eye"></i>
                    </button>
                    ${isManager && !['done', 'cancelled'].includes(o.status) ? `
                        <button class="btn btn-sm btn-success" onclick="packOrder(${o.id})" title="Pack Order">
                            <i class="fas fa-box"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="cancelOrder(${o.id})" title="Cancel Order">
                            <i class="fas fa-ban"></i>
                        </button>
                    ` : ''}
                    ${isManager && o.status === 'cancelled' ? `
                        <button class="btn btn-sm btn-warning" onclick="deleteOrder(${o.id})" title="Delete Order">
                            <i class="fas fa-trash"></i>
                        </button>
                    ` : ''}
                </div>
            </td>
            <td>
                <svg class="barcode-svg" data-barcode="${escapeHtml(o.barcode)}"></svg>
            </td>
        </tr>
    `).join('');
    
    // Generate barcodes
    setTimeout(() => {
        document.querySelectorAll('#ordersTable .barcode-svg').forEach(svg => {
            try {
                JsBarcode(svg, svg.dataset.barcode, {
                    format: "CODE128",
                    width: 1,
                    height: 30,
                    displayValue: false,
                    margin: 0
                });
            } catch (e) {
                console.warn('Failed to generate barcode:', e);
            }
        });
    }, 0);
}

function showOrderModal() {
    document.getElementById('orderModalTitle').textContent = 'New Order';
    document.getElementById('orderId').value = '';
    document.getElementById('orderBarcode').value = '';
    document.getElementById('orderName').value = '';
    document.getElementById('orderDescription').value = '';
    document.getElementById('orderModal').classList.add('active');
}

function closeOrderModal() {
    document.getElementById('orderModal').classList.remove('active');
}

async function saveOrder(event) {
    event.preventDefault();
    
    const data = {
        barcode: document.getElementById('orderBarcode').value.trim(),
        name: document.getElementById('orderName').value.trim(),
        description: document.getElementById('orderDescription').value.trim() || null
    };
    
    try {
        await api.createOrder(data);
        showAlert('Order created successfully', 'success');
        closeOrderModal();
        await loadOrders();
    } catch (error) {
        showAlert('Failed to create order: ' + error.message, 'danger');
    }
}

function createNewOrder(barcode) {
    closeUnknownBarcodePrompt();
    pendingNewBarcode = null;
    
    document.getElementById('orderModalTitle').textContent = 'New Order';
    document.getElementById('orderId').value = '';
    document.getElementById('orderBarcode').value = barcode || '';
    document.getElementById('orderName').value = '';
    document.getElementById('orderDescription').value = '';
    document.getElementById('orderModal').classList.add('active');
    
    setTimeout(() => document.getElementById('orderName').focus(), 100);
}

async function showOrderDetail(orderId) {
    try {
        const order = await api.getOrder(orderId);
        currentOrderDetail = order;
        
        // Fill in order details
        document.getElementById('orderDetailBarcode').textContent = order.barcode;
        document.getElementById('orderDetailName').textContent = order.name;
        document.getElementById('orderDetailDescription').textContent = order.description || '-';
        document.getElementById('orderDetailStatus').textContent = order.status.toUpperCase();
        document.getElementById('orderDetailStatus').className = 'status-badge ' + order.status;
        document.getElementById('orderDetailCreated').textContent = new Date(order.created_at).toLocaleString();
        
        // Generate barcode
        try {
            JsBarcode('#orderDetailBarcodeSvg', order.barcode, {
                format: "CODE128",
                width: 2,
                height: 50,
                displayValue: false
            });
        } catch (e) {
            console.warn('Failed to generate barcode:', e);
        }
        
        // Render order items
        renderOrderItems(order);
        
        // Show/hide action buttons based on status
        const isManager = ['administrator', 'manager'].includes(currentUser.role);
        const btnCancel = document.getElementById('btnCancelOrder');
        const btnPack = document.getElementById('btnPackOrder');
        const btnComplete = document.getElementById('btnCompleteOrder');
        
        btnCancel.style.display = isManager && !['done', 'cancelled'].includes(order.status) ? '' : 'none';
        btnPack.style.display = isManager && !['packed', 'done', 'cancelled'].includes(order.status) ? '' : 'none';
        btnComplete.style.display = isManager && order.status === 'packed' ? '' : 'none';
        
        // Show return section for cancelled orders
        const returnSection = document.getElementById('returnItemsSection');
        if (order.status === 'cancelled' && order.order_items && order.order_items.length > 0) {
            returnSection.classList.remove('hidden');
            renderReturnItems(order);
        } else {
            returnSection.classList.add('hidden');
        }
        
        document.getElementById('orderDetailModal').classList.add('active');
    } catch (error) {
        showAlert('Failed to load order details: ' + error.message, 'danger');
    }
}

function renderOrderItems(order) {
    const emptyState = document.getElementById('orderItemsEmpty');
    const table = document.getElementById('orderItemsTable');
    const tbody = document.getElementById('orderItemsTableBody');
    
    if (!order.order_items || order.order_items.length === 0) {
        emptyState.classList.remove('hidden');
        table.classList.add('hidden');
        return;
    }
    
    emptyState.classList.add('hidden');
    table.classList.remove('hidden');
    
    const isManager = ['administrator', 'manager'].includes(currentUser.role);
    const canRemove = isManager && !['done', 'cancelled'].includes(order.status);
    
    tbody.innerHTML = order.order_items.map(oi => `
        <tr>
            <td><strong>${escapeHtml(oi.item_name)}</strong></td>
            <td><code>${escapeHtml(oi.item_barcode)}</code></td>
            <td>${oi.source_box_name ? escapeHtml(oi.source_box_name) : '-'}</td>
            <td>${oi.quantity}</td>
            <td>${oi.price != null ? '$' + oi.price.toFixed(2) : '-'}</td>
            <td>
                ${canRemove ? `
                    <button class="btn btn-sm btn-danger" onclick="removeOrderItem(${order.id}, ${oi.id})" title="Remove">
                        <i class="fas fa-trash"></i>
                    </button>
                ` : ''}
            </td>
        </tr>
    `).join('');
}

function renderReturnItems(order) {
    const container = document.getElementById('returnItemsList');
    
    container.innerHTML = order.order_items.map(oi => `
        <div class="return-item-row" data-order-item-id="${oi.id}">
            <div class="return-item-info">
                <span class="return-item-name">${escapeHtml(oi.item_name)}</span>
                <span class="return-item-box">→ ${oi.source_box_name ? escapeHtml(oi.source_box_name) : 'Unknown box'}</span>
                <span class="return-item-qty">×${oi.quantity}</span>
            </div>
            <button class="btn btn-sm btn-success" onclick="returnSingleItem(${order.id}, ${oi.id})">
                <i class="fas fa-undo"></i> Return
            </button>
        </div>
    `).join('');
}

function closeOrderDetailModal() {
    document.getElementById('orderDetailModal').classList.remove('active');
    currentOrderDetail = null;
}

async function packOrder(orderId) {
    try {
        await api.packOrder(orderId);
        showAlert('Order packed successfully', 'success');
        clearCodeChain();
        await loadOrders();
        
        // Refresh detail if open
        if (currentOrderDetail && currentOrderDetail.id === orderId) {
            await showOrderDetail(orderId);
        }
    } catch (error) {
        showAlert('Failed to pack order: ' + error.message, 'danger');
    }
}

async function cancelOrder(orderId) {
    if (!confirm('Are you sure you want to cancel this order?')) return;
    
    try {
        await api.cancelOrder(orderId);
        showAlert('Order cancelled', 'warning');
        clearCodeChain();
        await loadOrders();
        
        // Refresh detail if open
        if (currentOrderDetail && currentOrderDetail.id === orderId) {
            await showOrderDetail(orderId);
        }
    } catch (error) {
        showAlert('Failed to cancel order: ' + error.message, 'danger');
    }
}

async function deleteOrder(orderId) {
    if (!confirm('Are you sure you want to delete this order?')) return;
    
    try {
        await api.deleteOrder(orderId);
        showAlert('Order deleted', 'success');
        await loadOrders();
        closeOrderDetailModal();
    } catch (error) {
        showAlert('Failed to delete order: ' + error.message, 'danger');
    }
}

async function removeOrderItem(orderId, orderItemId) {
    if (!confirm('Remove this item from the order? (Item will NOT be returned to inventory)')) return;
    
    try {
        await api.removeItemFromOrder(orderId, orderItemId);
        showAlert('Item removed from order', 'success');
        await showOrderDetail(orderId);
        await loadOrders();
    } catch (error) {
        showAlert('Failed to remove item: ' + error.message, 'danger');
    }
}

async function returnSingleItem(orderId, orderItemId) {
    try {
        await api.returnItemToInventory(orderId, orderItemId);
        showAlert('Item returned to inventory', 'success');
        await showOrderDetail(orderId);
    } catch (error) {
        showAlert('Failed to return item: ' + error.message, 'danger');
    }
}

async function returnAllItems() {
    if (!currentOrderDetail) return;
    
    try {
        const result = await api.returnAllItemsToInventory(currentOrderDetail.id);
        showAlert(`Returned ${result.returned} items to inventory`, 'success');
        
        if (result.errors.length) {
            console.log('Return errors:', result.errors);
        }
        
        await showOrderDetail(currentOrderDetail.id);
    } catch (error) {
        showAlert('Failed to return items: ' + error.message, 'danger');
    }
}

function markReturnsDone() {
    closeOrderDetailModal();
    clearCodeChain();
    showAlert('Returns completed', 'success');
}

// Order from Code Chain
async function cancelOrderFromChain() {
    if (!codeChain.order) return;
    await cancelOrder(codeChain.order.id);
}

async function packOrderFromChain() {
    if (!codeChain.order) return;
    await packOrder(codeChain.order.id);
}

async function cancelCurrentOrder() {
    if (!currentOrderDetail) return;
    await cancelOrder(currentOrderDetail.id);
}

async function packCurrentOrder() {
    if (!currentOrderDetail) return;
    await packOrder(currentOrderDetail.id);
}

async function completeCurrentOrder() {
    if (!currentOrderDetail) return;
    
    try {
        await api.completeOrder(currentOrderDetail.id);
        showAlert('Order completed!', 'success');
        await loadOrders();
        closeOrderDetailModal();
    } catch (error) {
        showAlert('Failed to complete order: ' + error.message, 'danger');
    }
}

// Handle scanning an item to add to an order
async function handleOrderItemScan(barcode) {
    if (!codeChain.order || codeChain.action !== 'add') {
        await searchByBarcode(barcode);
        return;
    }
    
    try {
        const item = await api.getItemByBarcode(barcode);
        if (item) {
            // Set as target in chain
            codeChain.target = item;
            updateCodeChainUI();
            
            // Show quantity prompt for adding to order
            showOrderQuantityPrompt(codeChain.order, item);
        } else {
            showAlert('Item not found', 'warning');
        }
    } catch (error) {
        showAlert('Item not found: ' + error.message, 'warning');
    }
}

function showOrderQuantityPrompt(order, item) {
    const title = document.getElementById('quantityPromptTitle');
    const itemLabel = document.getElementById('quantityPromptItem');
    const input = document.getElementById('scannerQuantityInput');
    const maxInfo = document.getElementById('quantityMaxInfo');
    
    title.textContent = `Add to Order: ${order.name}`;
    itemLabel.textContent = `${item.name} (${item.quantity} available)`;
    input.value = 1;
    input.max = item.quantity;
    maxInfo.textContent = `Max: ${item.quantity}`;
    maxInfo.classList.remove('hidden');
    
    // Store context for submission
    window.orderAddContext = { order, item };
    
    document.getElementById('quantityPromptModal').classList.add('active');
}

// Override submitQuantityPrompt to handle order adds
const originalSubmitQuantityPrompt = window.submitQuantityPrompt;
window.submitQuantityPrompt = async function() {
    // Check if this is an order add operation
    if (window.orderAddContext) {
        const { order, item } = window.orderAddContext;
        const quantity = parseInt(document.getElementById('scannerQuantityInput').value) || 1;
        
        try {
            await api.addItemToOrder(order.id, item.id, quantity);
            showAlert(`Added ${quantity}x ${item.name} to order`, 'success');
            
            // Show success in chain
            showCodeChainSuccess(`Added to ${order.name}`);
            
            // Refresh orders
            await loadOrders();
            
            // Clear context
            window.orderAddContext = null;
            closeQuantityPrompt();
            
            // Keep order in chain for more additions
            setTimeout(() => {
                codeChain.action = null;
                codeChain.target = null;
                updateCodeChainUI();
                showAlert('Scan ACTION:ADD then item barcode to add more, or ACTION:DONE to pack', 'info');
            }, 1500);
        } catch (error) {
            showAlert('Failed to add item: ' + error.message, 'danger');
        }
        return;
    }
    
    // Call original for item store/take operations
    if (typeof originalSubmitQuantityPrompt === 'function') {
        originalSubmitQuantityPrompt();
    } else {
        await submitQuantityPromptOriginal();
    }
};

// Store original submit function
async function submitQuantityPromptOriginal() {
    const quantity = parseInt(document.getElementById('scannerQuantityInput').value) || 1;
    
    if (!codeChain.item || !codeChain.action) {
        closeQuantityPrompt();
        return;
    }
    
    // Store quantity as target in chain
    codeChain.target = quantity;
    updateCodeChainUI();
    
    try {
        if (codeChain.action === 'add') {
            await api.storeItem(codeChain.item.id, quantity);
            showCodeChainSuccess(`+${quantity} stored`);
            showAlert(`Added ${quantity} to ${codeChain.item.name}`, 'success');
        } else if (codeChain.action === 'take') {
            await api.takeItem(codeChain.item.id, quantity);
            showCodeChainSuccess(`-${quantity} taken`);
            showAlert(`Took ${quantity} from ${codeChain.item.name}`, 'success');
        }
        
        // Reload items
        await loadItems();
        
        // Clear chain after delay
        setTimeout(() => {
            clearCodeChain();
        }, 2000);
    } catch (error) {
        showAlert(`Failed to ${codeChain.action} items: ${error.message}`, 'danger');
    }
    
    closeQuantityPrompt();
}
