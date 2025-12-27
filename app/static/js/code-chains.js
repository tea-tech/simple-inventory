/**
 * Code Chains Module
 * 
 * A modular system for handling barcode scan sequences.
 * Each chain defines a workflow triggered by scanning specific codes.
 * 
 * Prefixes:
 *   OP:   - Operations (ADD, TAKE, MOVE, CHANGE)
 *   ACT:  - Actions (OK, CANCEL)
 *   TYPE: - Entity types (ITEM, BOX, PACKAGE)
 * 
 * See docs/action-codes.md and docs/code-chains.md for documentation.
 */

// ==================== ACTION CODE DEFINITIONS ====================

/**
 * Map of recognized action codes to their internal action names.
 * Add new codes here to extend the system.
 */
const ACTION_CODES = {
    // Operations
    'OP:MOVE': 'move',
    'OP:ADD': 'add',
    'OP:TAKE': 'take',
    'OP:CHANGE': 'change',
    
    // Actions
    'ACT:OK': 'ok',
    'ACT:CANCEL': 'cancel',
    
    // Type codes for entity creation
    'TYPE:BOX': 'type_box',
    'TYPE:ITEM': 'type_item',
    'TYPE:PACKAGE': 'type_package'
};

// ==================== CODE CHAIN STATE ====================

/**
 * Current state of the code chain workflow.
 * Tracks what entity is selected and what action is pending.
 */
let chainState = {
    entity: null,      // The selected entity { type: 'item'|'box'|'package', data: {...} }
    action: null,      // Current action: 'move'|'add'|'take'|'ok'|'cancel'|'change'
    target: null,      // Target for the action (box for move, quantity for add/take, etc.)
    pendingBarcode: null  // Unknown barcode waiting for type assignment
};

// ==================== UTILITY FUNCTIONS ====================

/**
 * Normalize a barcode to handle keyboard layout issues.
 * Some scanners produce " instead of : depending on keyboard layout.
 */
function normalizeCode(barcode) {
    if (!barcode) return '';
    return barcode.toUpperCase().trim().replace(/"/g, ':');
}

/**
 * Check if a barcode is a recognized action code.
 */
function isActionCode(barcode) {
    if (!barcode) return false;
    return ACTION_CODES.hasOwnProperty(normalizeCode(barcode));
}

/**
 * Get the internal action name for a barcode.
 */
function getAction(barcode) {
    if (!barcode) return null;
    return ACTION_CODES[normalizeCode(barcode)] || null;
}

/**
 * Check if an action is a type assignment code.
 */
function isTypeAction(action) {
    return ['type_box', 'type_item', 'type_package'].includes(action);
}

/**
 * Check if an action is an operation code.
 */
function isOperationAction(action) {
    return ['move', 'add', 'take', 'change'].includes(action);
}

// ==================== CHAIN STATE MANAGEMENT ====================

/**
 * Get the current chain state (read-only copy).
 */
function getChainState() {
    return { ...chainState };
}

/**
 * Set the selected entity in the chain.
 */
function setEntity(type, data) {
    chainState.entity = { type, data };
    chainState.action = null;
    chainState.target = null;
}

/**
 * Set the pending action in the chain.
 */
function setAction(action) {
    chainState.action = action;
    chainState.target = null;
}

/**
 * Set the target for the current action.
 */
function setTarget(target) {
    chainState.target = target;
}

/**
 * Set a pending unknown barcode waiting for type.
 */
function setPendingBarcode(barcode) {
    chainState.pendingBarcode = barcode;
}

/**
 * Get and clear the pending barcode.
 */
function consumePendingBarcode() {
    const barcode = chainState.pendingBarcode;
    chainState.pendingBarcode = null;
    return barcode;
}

/**
 * Clear the entire chain state.
 */
function clearChain() {
    chainState = {
        entity: null,
        action: null,
        target: null,
        pendingBarcode: null
    };
}

/**
 * Clear just the action and target, keeping the entity.
 */
function clearAction() {
    chainState.action = null;
    chainState.target = null;
}

// ==================== CHAIN FLOW DETERMINATION ====================

/**
 * Determine what step the chain is currently at.
 * Returns: 'empty' | 'entity_selected' | 'action_pending' | 'awaiting_target' | 'complete'
 */
function getChainStep() {
    if (!chainState.entity && !chainState.pendingBarcode) {
        return 'empty';
    }
    if (chainState.pendingBarcode && !chainState.entity) {
        return 'awaiting_type';
    }
    if (chainState.entity && !chainState.action) {
        return 'entity_selected';
    }
    if (chainState.entity && chainState.action && !chainState.target) {
        return 'awaiting_target';
    }
    if (chainState.entity && chainState.action && chainState.target) {
        return 'complete';
    }
    return 'unknown';
}

/**
 * Get human-readable status message for UI display.
 */
function getChainStatusMessage() {
    const step = getChainStep();
    const entity = chainState.entity;
    const action = chainState.action;
    
    switch (step) {
        case 'empty':
            return 'Scan a barcode to begin';
        case 'awaiting_type':
            return `Unknown barcode. Scan TYPE:BOX, TYPE:ITEM, or TYPE:PACKAGE`;
        case 'entity_selected':
            const typeName = entity.type.charAt(0).toUpperCase() + entity.type.slice(1);
            return `${typeName} selected: ${entity.data.name || entity.data.barcode}`;
        case 'awaiting_target':
            return getAwaitingTargetMessage(entity.type, action);
        case 'complete':
            return 'Chain complete';
        default:
            return '';
    }
}

function getAwaitingTargetMessage(entityType, action) {
    if (entityType === 'item') {
        switch (action) {
            case 'move': return 'Scan target box';
            case 'add': return 'Enter quantity to add';
            case 'take': return 'Enter quantity to take';
            default: return `Action: ${action}`;
        }
    }
    if (entityType === 'box') {
        switch (action) {
            case 'move': return 'Select target warehouse';
            default: return `Action: ${action}`;
        }
    }
    if (entityType === 'package') {
        switch (action) {
            case 'add': return 'Scan item to add, then enter quantity';
            case 'take': return 'Scan item to remove';
            case 'change': return 'Scan TYPE:BOX or TYPE:ITEM to convert';
            default: return `Action: ${action}`;
        }
    }
    return '';
}

// ==================== CHAIN VALIDATION ====================

/**
 * Check if an action is valid for the current entity type.
 */
function isValidActionForEntity(action) {
    if (!chainState.entity) return false;
    
    const entityType = chainState.entity.type;
    const validActions = getValidActionsForEntity(entityType);
    
    return validActions.includes(action);
}

/**
 * Get list of valid actions for an entity type.
 */
function getValidActionsForEntity(entityType) {
    switch (entityType) {
        case 'item':
            return ['move', 'add', 'take', 'cancel'];
        case 'box':
            return ['move', 'cancel'];
        case 'package':
            return ['add', 'take', 'change', 'ok', 'cancel'];
        default:
            return ['cancel'];
    }
}

// ==================== EXPORTS ====================

// Export everything as a module object for use in app.js
const CodeChains = {
    // Constants
    ACTION_CODES,
    
    // Utility functions
    normalizeCode,
    isActionCode,
    getAction,
    isTypeAction,
    isOperationAction,
    
    // State management
    getChainState,
    setEntity,
    setAction,
    setTarget,
    setPendingBarcode,
    consumePendingBarcode,
    clearChain,
    clearAction,
    
    // Flow determination
    getChainStep,
    getChainStatusMessage,
    
    // Validation
    isValidActionForEntity,
    getValidActionsForEntity
};

// Also expose individual functions globally for backward compatibility
window.CodeChains = CodeChains;
