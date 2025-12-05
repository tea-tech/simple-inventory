// API Client for Simple Inventory

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

    // Boxes
    async getBoxes(warehouseId = null) {
        const params = warehouseId ? `?warehouse_id=${warehouseId}` : '';
        return this.request(`/boxes/${params}`);
    }

    async getBox(id) {
        return this.request(`/boxes/${id}`);
    }

    async getBoxByBarcode(barcode) {
        return this.request(`/boxes/barcode/${barcode}`);
    }

    async createBox(data) {
        return this.request('/boxes/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateBox(id, data) {
        return this.request(`/boxes/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deleteBox(id) {
        return this.request(`/boxes/${id}`, {
            method: 'DELETE'
        });
    }

    async moveBox(id, targetWarehouseId) {
        return this.request(`/boxes/${id}/move/${targetWarehouseId}`, {
            method: 'POST'
        });
    }

    // Items
    async getItems(boxId = null, search = null) {
        const params = new URLSearchParams();
        if (boxId) params.append('box_id', boxId);
        if (search) params.append('search', search);
        const queryString = params.toString();
        return this.request(`/items/${queryString ? '?' + queryString : ''}`);
    }

    async getItem(id) {
        return this.request(`/items/${id}`);
    }

    async getItemByBarcode(barcode) {
        return this.request(`/items/barcode/${barcode}`);
    }

    async createItem(data) {
        return this.request('/items/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateItem(id, data) {
        return this.request(`/items/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deleteItem(id) {
        return this.request(`/items/${id}`, {
            method: 'DELETE'
        });
    }

    async moveItem(id, targetBoxId, quantity = null) {
        const data = { target_box_id: targetBoxId };
        if (quantity) data.quantity = quantity;
        return this.request(`/items/${id}/move`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async takeItem(id, quantity = 1) {
        return this.request(`/items/${id}/take?quantity=${quantity}`, {
            method: 'POST'
        });
    }

    async storeItem(id, quantity = 1) {
        return this.request(`/items/${id}/store?quantity=${quantity}`, {
            method: 'POST'
        });
    }

    // CSV Import/Export
    async exportItemsCSV() {
        const response = await fetch(`${API_BASE}/items/export/csv`, {
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        if (!response.ok) throw new Error('Export failed');
        return response.blob();
    }

    async exportBoxesCSV() {
        const response = await fetch(`${API_BASE}/boxes/export/csv`, {
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        if (!response.ok) throw new Error('Export failed');
        return response.blob();
    }

    async importItemsCSV(file) {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${API_BASE}/items/import/csv`, {
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

    async importBoxesCSV(file) {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${API_BASE}/boxes/import/csv`, {
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

    // Orders
    async getOrders(status = null) {
        const params = status ? `?status_filter=${status}` : '';
        return this.request(`/orders/${params}`);
    }

    async getOrder(id) {
        return this.request(`/orders/${id}`);
    }

    async getOrderByBarcode(barcode) {
        return this.request(`/orders/barcode/${barcode}`);
    }

    async createOrder(data) {
        return this.request('/orders/', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    async updateOrder(id, data) {
        return this.request(`/orders/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    async deleteOrder(id) {
        return this.request(`/orders/${id}`, {
            method: 'DELETE'
        });
    }

    async addItemToOrder(orderId, itemId, quantity) {
        return this.request(`/orders/${orderId}/items`, {
            method: 'POST',
            body: JSON.stringify({ item_id: itemId, quantity: quantity })
        });
    }

    async removeItemFromOrder(orderId, orderItemId) {
        return this.request(`/orders/${orderId}/items/${orderItemId}`, {
            method: 'DELETE'
        });
    }

    async packOrder(orderId) {
        return this.request(`/orders/${orderId}/pack`, {
            method: 'POST'
        });
    }

    async completeOrder(orderId) {
        return this.request(`/orders/${orderId}/complete`, {
            method: 'POST'
        });
    }

    async cancelOrder(orderId) {
        return this.request(`/orders/${orderId}/cancel`, {
            method: 'POST'
        });
    }

    async returnItemToInventory(orderId, orderItemId) {
        return this.request(`/orders/${orderId}/return-item/${orderItemId}`, {
            method: 'POST'
        });
    }

    async returnAllItemsToInventory(orderId) {
        return this.request(`/orders/${orderId}/return-all`, {
            method: 'POST'
        });
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

    async updateCheckItem(checkId, itemId, actualQuantity) {
        return this.request(`/checks/${checkId}/items/${itemId}`, {
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
