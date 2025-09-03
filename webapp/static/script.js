/**
 * Prediction League Web App - Client-side JavaScript
 * 
 * Simple, vanilla JavaScript for enhanced user experience.
 * Following hobbyist philosophy: minimal dependencies, clear functions.
 */

// Global utilities
const PredictionLeague = {
    
    // Initialize app
    init() {
        this.setupFlashMessages();
        this.setupKeyboardShortcuts();
        this.setupTooltips();
        this.setupConfirmDialogs();
    },
    
    // Auto-hide flash messages
    setupFlashMessages() {
        const flashMessages = document.querySelectorAll('.flash-message');
        flashMessages.forEach(message => {
            // Add close button
            const closeBtn = document.createElement('button');
            closeBtn.innerHTML = '&times;';
            closeBtn.className = 'float-right text-xl leading-none hover:opacity-75';
            closeBtn.onclick = () => this.hideFlashMessage(message);
            message.querySelector('div').appendChild(closeBtn);
            
            // Auto-hide after 5 seconds
            setTimeout(() => this.hideFlashMessage(message), 5000);
        });
    },
    
    hideFlashMessage(message) {
        message.style.opacity = '0';
        message.style.transform = 'translateY(-10px)';
        setTimeout(() => message.remove(), 300);
    },
    
    // Keyboard shortcuts
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Only trigger if not typing in input
            if (e.target.tagName.toLowerCase() === 'input' || 
                e.target.tagName.toLowerCase() === 'textarea') {
                return;
            }
            
            // Alt + D for Dashboard
            if (e.altKey && e.key === 'd') {
                e.preventDefault();
                this.navigateTo('/dashboard');
            }
            
            // Alt + A for Admin
            if (e.altKey && e.key === 'a') {
                e.preventDefault();
                this.navigateTo('/admin');
            }
            
            // Alt + S for Scripts
            if (e.altKey && e.key === 's') {
                e.preventDefault();
                this.navigateTo('/scripts');
            }
            
            // Alt + F for FPL
            if (e.altKey && e.key === 'f') {
                e.preventDefault();
                this.navigateTo('/fpl');
            }
            
            // F5 for refresh (allow default)
            if (e.key === 'F5') {
                this.showLoading('Refreshing page...');
            }
        });
    },
    
    // Simple tooltips
    setupTooltips() {
        const elements = document.querySelectorAll('[data-tooltip]');
        elements.forEach(element => {
            element.addEventListener('mouseenter', (e) => {
                this.showTooltip(e.target, e.target.dataset.tooltip);
            });
            
            element.addEventListener('mouseleave', () => {
                this.hideTooltip();
            });
        });
    },
    
    showTooltip(element, text) {
        const tooltip = document.createElement('div');
        tooltip.className = 'absolute bg-gray-800 text-white text-sm px-2 py-1 rounded shadow-lg z-50';
        tooltip.textContent = text;
        tooltip.id = 'app-tooltip';
        
        document.body.appendChild(tooltip);
        
        const rect = element.getBoundingClientRect();
        tooltip.style.left = rect.left + 'px';
        tooltip.style.top = (rect.top - tooltip.offsetHeight - 5) + 'px';
    },
    
    hideTooltip() {
        const tooltip = document.getElementById('app-tooltip');
        if (tooltip) tooltip.remove();
    },
    
    // Confirm dangerous actions
    setupConfirmDialogs() {
        const dangerousActions = document.querySelectorAll('[data-confirm]');
        dangerousActions.forEach(element => {
            element.addEventListener('click', (e) => {
                const message = e.target.dataset.confirm || 'Are you sure?';
                if (!confirm(message)) {
                    e.preventDefault();
                    return false;
                }
            });
        });
    },
    
    // Navigation helper
    navigateTo(path) {
        this.showLoading('Loading...');
        window.location.href = path;
    },
    
    // Loading indicator
    showLoading(message = 'Loading...') {
        let loader = document.getElementById('app-loader');
        if (!loader) {
            loader = document.createElement('div');
            loader.id = 'app-loader';
            loader.className = 'fixed top-4 right-4 bg-blue-600 text-white px-4 py-2 rounded shadow-lg z-50';
            document.body.appendChild(loader);
        }
        loader.innerHTML = `
            <div class="flex items-center">
                <div class="loading-spinner"></div>
                ${message}
            </div>
        `;
        loader.style.display = 'block';
    },
    
    hideLoading() {
        const loader = document.getElementById('app-loader');
        if (loader) loader.style.display = 'none';
    },
    
    // API helper
    async fetchJson(url, options = {}) {
        try {
            this.showLoading('Loading data...');
            const response = await fetch(url, {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                },
                ...options
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.hideLoading();
            return data;
        } catch (error) {
            this.hideLoading();
            this.showError(`API Error: ${error.message}`);
            throw error;
        }
    },
    
    // Error handling
    showError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'fixed top-4 right-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded shadow-lg z-50';
        errorDiv.innerHTML = `
            <div class="flex items-center">
                <span class="mr-2">❌</span>
                <span>${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-red-500 hover:text-red-700">&times;</button>
            </div>
        `;
        document.body.appendChild(errorDiv);
        
        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (errorDiv.parentNode) {
                errorDiv.remove();
            }
        }, 5000);
    },
    
    // Success message
    showSuccess(message) {
        const successDiv = document.createElement('div');
        successDiv.className = 'fixed top-4 right-4 bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded shadow-lg z-50';
        successDiv.innerHTML = `
            <div class="flex items-center">
                <span class="mr-2">✅</span>
                <span>${message}</span>
                <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-green-500 hover:text-green-700">&times;</button>
            </div>
        `;
        document.body.appendChild(successDiv);
        
        setTimeout(() => {
            if (successDiv.parentNode) {
                successDiv.remove();
            }
        }, 3000);
    },
    
    // Form helpers
    serializeForm(form) {
        const formData = new FormData(form);
        return Object.fromEntries(formData.entries());
    },
    
    validateForm(form) {
        const requiredFields = form.querySelectorAll('[required]');
        let isValid = true;
        
        requiredFields.forEach(field => {
            if (!field.value.trim()) {
                field.classList.add('border-red-500');
                isValid = false;
            } else {
                field.classList.remove('border-red-500');
            }
        });
        
        return isValid;
    },
    
    // Local storage helpers
    saveToStorage(key, value) {
        try {
            localStorage.setItem(`pl_${key}`, JSON.stringify(value));
        } catch (error) {
            console.warn('Could not save to localStorage:', error);
        }
    },
    
    loadFromStorage(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(`pl_${key}`);
            return item ? JSON.parse(item) : defaultValue;
        } catch (error) {
            console.warn('Could not load from localStorage:', error);
            return defaultValue;
        }
    },
    
    // Chart helpers (for Chart.js integration)
    createChart(canvasId, config) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === 'undefined') {
            console.warn(`Cannot create chart: canvas '${canvasId}' not found or Chart.js not loaded`);
            return null;
        }
        
        return new Chart(canvas.getContext('2d'), config);
    },
    
    // Date/time helpers
    formatDateTime(timestamp, format = 'short') {
        if (!timestamp) return 'Unknown';
        
        const date = new Date(timestamp * 1000);
        
        if (format === 'short') {
            return date.toLocaleString('en-GB', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
        
        return date.toLocaleString();
    },
    
    timeAgo(timestamp) {
        if (!timestamp) return 'Unknown';
        
        const now = Date.now();
        const diff = now - (timestamp * 1000);
        const seconds = Math.floor(diff / 1000);
        
        if (seconds < 60) return 'Just now';
        if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
        if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
        return `${Math.floor(seconds / 86400)} days ago`;
    },
    
    // Number formatting
    formatNumber(num, decimals = 0) {
        if (typeof num !== 'number') return num;
        return num.toLocaleString('en-GB', { 
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals 
        });
    },
    
    // Theme helpers (future enhancement)
    toggleTheme() {
        const currentTheme = this.loadFromStorage('theme', 'light');
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        
        document.documentElement.setAttribute('data-theme', newTheme);
        this.saveToStorage('theme', newTheme);
        
        this.showSuccess(`Switched to ${newTheme} theme`);
    }
};

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    PredictionLeague.init();
    
    // Load saved theme
    const savedTheme = PredictionLeague.loadFromStorage('theme', 'light');
    document.documentElement.setAttribute('data-theme', savedTheme);
});

// Global error handler
window.addEventListener('error', (e) => {
    console.error('JavaScript error:', e.error);
    PredictionLeague.showError('An unexpected error occurred. Please refresh the page.');
});

// Make PredictionLeague available globally
window.PL = PredictionLeague;