// API Client for Simple Inventory (Unified Entity Model)

const API_BASE = '/api';

class ApiClient {
    constructor() {
        this.token = localStorage.getItem('token');
    }

    setToken(token) {
        this.token = token;
        localStorage.setItem('token', token);
    }

    clearToken() {
        this.token = null;
        localStorage.removeItem('token');
    }

    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers
            });

            if (response.status === 401) {
                this.clearToken();
                window.location.href = '/static/login.html';
                throw new Error('Unauthorized');
            }

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Request failed');
            }

            if (response.status === 204) {
                return null;
            }

            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }

    // Auth
    async login(username, password) {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Login failed');
        }

        const data = await response.json();
        this.setToken(data.access_token);
        return data;
    }

    async getMe() {
        return this.request('/auth/me');
    }

    async changePassword(currentPassword, newPassword) {
        return this.request('/auth/me/password', {
            method: 'POST',
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });
    }

    logout() {
        this.clearToken();
        window.location.href = '/static/login.html';
    }

    // Users
    async getUsers() {
        return this.request('/users/');
    }

    async createUser(data) {
        return this.request('/users/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateUser(id, data) {
        return this.request(`/users/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deleteUser(id) {
        return this.request(`/users/${id}`, {
            method: 'DELETE'
        });
    }

    async setUserPassword(id, newPassword) {
        return this.request(`/users/${id}/password`, {
            method: 'POST',
            body: JSON.stringify({ new_password: newPassword })
        });
    }

    // Warehouses
    async getWarehouses() {
        return this.request('/warehouses/');
    }

    async getWarehouse(id) {
        return this.request(`/warehouses/${id}`);
    }

    async createWarehouse(data) {
        return this.request('/warehouses/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateWarehouse(id, data) {
        return this.request(`/warehouses/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deleteWarehouse(id) {
        return this.request(`/warehouses/${id}`, {
            method: 'DELETE'
        });
    }

    // ============================================================================
    // ENTITIES (Unified Model - replaces items, boxes, packages)
    // ============================================================================

    async getEntities(params = {}) {
        const queryParams = new URLSearchParams();
        if (params.entity_type) queryParams.append('entity_type', params.entity_type);
        if (params.warehouse_id) queryParams.append('warehouse_id', params.warehouse_id);
        if (params.parent_id) queryParams.append('parent_id', params.parent_id);
        if (params.root_only) queryParams.append('root_only', 'true');
        if (params.search) queryParams.append('search', params.search);
        if (params.status_filter) queryParams.append('status_filter', params.status_filter);
        const queryString = queryParams.toString();
        return this.request(`/entities/${queryString ? '?' + queryString : ''}`);
    }

    async getEntity(id) {
        return this.request(`/entities/${id}`);
    }

    async getEntityByBarcode(barcode) {
        return this.request(`/entities/barcode/${encodeURIComponent(barcode)}`);
    }

    async createEntity(data) {
        return this.request('/entities/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateEntity(id, data) {
        return this.request(`/entities/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deleteEntity(id, force = false) {
        const query = force ? '?force=true' : '';
        return this.request(`/entities/${id}${query}`, {
            method: 'DELETE'
        });
    }

    // Entity Operations
    async moveEntity(id, data) {
        // data: { target_warehouse_id, target_parent_id, quantity }
        return this.request(`/entities/${id}/move`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async convertEntity(id, newType, newStatus = null) {
        return this.request(`/entities/${id}/convert`, {
            method: 'POST',
            body: JSON.stringify({ new_type: newType, new_status: newStatus })
        });
    }

    async splitEntity(id, data) {
        // data: { quantity, new_barcode, target_warehouse_id, target_parent_id }
        return this.request(`/entities/${id}/split`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async mergeEntities(targetId, sourceIds) {
        return this.request(`/entities/${targetId}/merge`, {
            method: 'POST',
            body: JSON.stringify({ source_entity_ids: sourceIds })
        });
    }

    async adjustQuantity(id, adjustment) {
        return this.request(`/entities/${id}/quantity?adjustment=${adjustment}`, {
            method: 'POST'
        });
    }

    // Entity Children (Relations)
    async getEntityChildren(id) {
        return this.request(`/entities/${id}/children`);
    }

    async addChildToEntity(parentId, data) {
        // data: { child_id, child_barcode, quantity, remove_from_source, price_snapshot, notes }
        return this.request(`/entities/${parentId}/children`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async removeChildFromEntity(parentId, relationId, returnQuantity = false) {
        const query = returnQuantity ? '?return_quantity=true' : '';
        return this.request(`/entities/${parentId}/children/${relationId}${query}`, {
            method: 'DELETE'
        });
    }

    async updateChildRelation(parentId, relationId, data) {
        return this.request(`/entities/${parentId}/children/${relationId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    // Entity History
    async getEntityHistory(id) {
        return this.request(`/entities/${id}/history`);
    }

    // Entity Types
    async getEntityTypes(activeOnly = true) {
        const query = activeOnly ? '' : '?include_inactive=true';
        return this.request(`/entity-types/${query}`);
    }

    async getEntityType(code) {
        return this.request(`/entity-types/${code}`);
    }

    async createEntityType(data) {
        return this.request('/entity-types/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateEntityType(code, data) {
        return this.request(`/entity-types/${code}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deleteEntityType(code) {
        return this.request(`/entity-types/${code}`, {
            method: 'DELETE'
        });
    }

    // ============================================================================
    // Backward-compatible aliases (for old code that uses items/boxes/packages)
    // These all use the unified entity API
    // ============================================================================

    // Boxes = entities with type 'container'
    async getBoxes(warehouseId = null) {
        const params = { entity_type: 'container' };
        if (warehouseId) params.warehouse_id = warehouseId;
        return this.getEntities(params);
    }

    async getBox(id) {
        return this.getEntity(id);
    }

    async getBoxByBarcode(barcode) {
        return this.getEntityByBarcode(barcode);
    }

    async createBox(data) {
        return this.createEntity({
            ...data,
            entity_type: 'container'
        });
    }

    async updateBox(id, data) {
        return this.updateEntity(id, data);
    }

    async deleteBox(id) {
        return this.deleteEntity(id);
    }

    async moveBox(id, targetWarehouseId) {
        return this.moveEntity(id, { target_warehouse_id: targetWarehouseId });
    }

    // Items = entities with type 'item'
    async getItems(parentId = null, search = null) {
        const params = { entity_type: 'item' };
        if (parentId) params.parent_id = parentId;
        if (search) params.search = search;
        return this.getEntities(params);
    }

    async getItem(id) {
        return this.getEntity(id);
    }

    async getItemByBarcode(barcode) {
        return this.getEntityByBarcode(barcode);
    }

    async createItem(data) {
        return this.createEntity({
            ...data,
            entity_type: 'item',
            parent_id: data.box_id || data.parent_id  // Map box_id to parent_id
        });
    }

    async updateItem(id, data) {
        const updateData = { ...data };
        if (data.box_id) {
            updateData.parent_id = data.box_id;
            delete updateData.box_id;
        }
        return this.updateEntity(id, updateData);
    }

    async deleteItem(id) {
        return this.deleteEntity(id);
    }

    async moveItem(id, targetParentId, quantity = null) {
        const data = { target_parent_id: targetParentId };
        if (quantity) data.quantity = quantity;
        return this.moveEntity(id, data);
    }

    async takeItem(id, quantity = 1) {
        return this.adjustQuantity(id, -quantity);
    }

    async storeItem(id, quantity = 1) {
        return this.adjustQuantity(id, quantity);
    }

    // Packages = entities with type 'package'
    async getPackages(status = null) {
        const params = { entity_type: 'package' };
        if (status) params.status_filter = status;
        return this.getEntities(params);
    }

    async getPackage(id) {
        return this.getEntity(id);
    }

    async getPackageByBarcode(barcode) {
        return this.getEntityByBarcode(barcode);
    }

    async createPackage(data) {
        return this.createEntity({
            ...data,
            entity_type: 'package',
            status: data.status || 'new'
        });
    }

    async updatePackage(id, data) {
        return this.updateEntity(id, data);
    }

    async deletePackage(id) {
        return this.deleteEntity(id, true); // Force delete for packages
    }

    async addItemToPackage(packageId, itemId, quantity) {
        return this.addChildToEntity(packageId, {
            child_id: itemId,
            quantity: quantity,
            remove_from_source: true
        });
    }

    async removeItemFromPackage(packageId, relationId) {
        return this.removeChildFromEntity(packageId, relationId, false);
    }

    async packPackage(packageId) {
        return this.updateEntity(packageId, { status: 'packed' });
    }

    async completePackage(packageId) {
        return this.updateEntity(packageId, { status: 'done' });
    }

    async cancelPackage(packageId) {
        return this.updateEntity(packageId, { status: 'cancelled' });
    }

    async returnItemToInventory(packageId, relationId) {
        return this.removeChildFromEntity(packageId, relationId, true);
    }

    async returnAllItemsToInventory(packageId) {
        const children = await this.getEntityChildren(packageId);
        let returned = 0;
        const errors = [];
        for (const relation of children) {
            try {
                await this.removeChildFromEntity(packageId, relation.id, true);
                returned++;
            } catch (e) {
                errors.push(e.message);
            }
        }
        return { returned, errors };
    }

    async convertPackageToBox(packageId, warehouseId) {
        await this.convertEntity(packageId, 'container');
        await this.updateEntity(packageId, { warehouse_id: warehouseId, parent_id: null });
        return { message: 'Package converted to container' };
    }

    async convertPackageToItem(packageId, parentId) {
        await this.convertEntity(packageId, 'item');
        await this.updateEntity(packageId, { parent_id: parentId, warehouse_id: null });
        return { message: 'Package converted to item' };
    }

    async convertBoxToPackage(boxId) {
        await this.convertEntity(boxId, 'package', 'new');
        return { message: 'Container converted to package' };
    }

    // CSV Import/Export
    async exportEntitiesCSV(entityType = null) {
        const query = entityType ? `?entity_type=${entityType}` : '';
        const response = await fetch(`${API_BASE}/entities/export/csv${query}`, {
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        if (!response.ok) throw new Error('Export failed');
        return response.blob();
    }

    async exportItemsCSV() {
        return this.exportEntitiesCSV('item');
    }

    async exportBoxesCSV() {
        return this.exportEntitiesCSV('container');
    }

    async importEntitiesCSV(file) {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${API_BASE}/entities/import/csv`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`
            },
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Import failed');
        }
        return response.json();
    }

    async importItemsCSV(file) {
        return this.importEntitiesCSV(file);
    }

    async importBoxesCSV(file) {
        return this.importEntitiesCSV(file);
    }

    // Inventory Checks
    async getChecks(status = null) {
        const params = status ? `?status=${status}` : '';
        return this.request(`/checks/${params}`);
    }

    async getCheck(id) {
        return this.request(`/checks/${id}`);
    }

    async getCheckGrouped(id) {
        return this.request(`/checks/${id}/grouped`);
    }

    async getActiveCheck() {
        return this.request('/checks/active');
    }

    async createCheck(data) {
        return this.request('/checks/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateCheck(id, data) {
        return this.request(`/checks/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async completeCheck(id) {
        return this.request(`/checks/${id}/complete`, {
            method: 'POST'
        });
    }

    async cancelCheck(id) {
        return this.request(`/checks/${id}/cancel`, {
            method: 'POST'
        });
    }

    async deleteCheck(id) {
        return this.request(`/checks/${id}`, {
            method: 'DELETE'
        });
    }

    async updateCheckItem(checkId, entityId, actualQuantity) {
        return this.request(`/checks/${checkId}/items/${entityId}`, {
            method: 'PUT',
            body: JSON.stringify({ actual_quantity: actualQuantity })
        });
    }

    async checkItemByBarcode(checkId, barcode, actualQuantity) {
        return this.request(`/checks/${checkId}/items/barcode/${barcode}`, {
            method: 'POST',
            body: JSON.stringify({ actual_quantity: actualQuantity })
        });
    }

    async compareChecks(checkId, previousCheckId) {
        return this.request(`/checks/${checkId}/compare/${previousCheckId}`);
    }

    async applyCheckCorrections(checkId) {
        return this.request(`/checks/${checkId}/apply-corrections`, {
            method: 'POST'
        });
    }

    // Barcode Lookup - lookup product info from online databases
    async lookupBarcode(barcode) {
        return this.request(`/barcode-lookup/${barcode}`);
    }

    async quickLookupBarcode(barcode) {
        return this.request(`/barcode-lookup/quick/${barcode}`);
    }

    // Settings
    async getSettings() {
        return this.request('/settings/');
    }

    async getSetting(key) {
        return this.request(`/settings/${key}`);
    }

    async updateSetting(key, value) {
        return this.request(`/settings/${key}`, {
            method: 'PUT',
            body: JSON.stringify({ value: value })
        });
    }

    async testBarcodePattern(pattern, barcode) {
        return this.request('/settings/test-pattern', {
            method: 'POST',
            body: JSON.stringify({ pattern: pattern, barcode: barcode })
        });
    }

    async getPatternExamples(pattern) {
        return this.request(`/settings/pattern/examples?pattern=${encodeURIComponent(pattern)}`);
    }

    async validateBarcode(barcode) {
        return this.request(`/settings/validate-barcode?barcode=${encodeURIComponent(barcode)}`, {
            method: 'POST'
        });
    }

    // Supplier Patterns
    async getSupplierPatterns(enabledOnly = false) {
        const query = enabledOnly ? '?enabled_only=true' : '';
        return this.request(`/supplier-patterns/${query}`);
    }

    async getSupplierPattern(id) {
        return this.request(`/supplier-patterns/${id}`);
    }

    async matchSupplierBarcode(barcode) {
        return this.request(`/supplier-patterns/match/${encodeURIComponent(barcode)}`);
    }

    async createSupplierPattern(data) {
        return this.request('/supplier-patterns/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateSupplierPattern(id, data) {
        return this.request(`/supplier-patterns/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deleteSupplierPattern(id) {
        return this.request(`/supplier-patterns/${id}`, {
            method: 'DELETE'
        });
    }

    async testSupplierPattern(pattern, barcode) {
        return this.request(`/supplier-patterns/test?pattern=${encodeURIComponent(pattern)}&barcode=${encodeURIComponent(barcode)}`, {
            method: 'POST'
        });
    }
}

// Global API instance
const api = new ApiClient();
