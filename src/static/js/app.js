/**
 * Budget App Main JavaScript
 */

// Initialize tooltips and popovers
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Initialize Bootstrap popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
    
    // Add event listeners for transaction category selection
    setupCategorySelectors();
    
    // Setup dynamic budget form fields
    setupDynamicFormFields();
    
    // Initialize categorization tools
    initCategorizationTools();
});

// Setup transaction category selectors
function setupCategorySelectors() {
    const categorySelects = document.querySelectorAll('.category-select');
    
    categorySelects.forEach(select => {
        select.addEventListener('change', function() {
            const transactionId = this.getAttribute('data-transaction-id');
            const categoryValue = this.value;
            
            if (transactionId && categoryValue) {
                updateTransactionCategory(transactionId, categoryValue);
            }
        });
    });
}

// Update transaction category via AJAX
function updateTransactionCategory(transactionId, category) {
    const formData = new FormData();
    formData.append('category', category);
    
    fetch(`/transaction/${transactionId}/update`, {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showAlert('Category updated successfully', 'success');
        } else {
            showAlert('Error updating category', 'danger');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showAlert('Error updating category', 'danger');
    });
}

// Show alert message
function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(alertDiv, container.firstChild);
    
    // Auto dismiss after 3 seconds
    setTimeout(() => {
        alertDiv.classList.remove('show');
        setTimeout(() => alertDiv.remove(), 150);
    }, 3000);
}

// Setup dynamic form fields for budget and other forms
function setupDynamicFormFields() {
    // Add category field in budget form
    const addCategoryBtn = document.getElementById('add-category-btn');
    if (addCategoryBtn) {
        addCategoryBtn.addEventListener('click', function() {
            const categoriesContainer = document.getElementById('categories-container');
            const categoryCount = categoriesContainer.children.length;
            
            const newRow = document.createElement('div');
            newRow.className = 'row mb-3 category-row';
            newRow.innerHTML = `
                <div class="col-md-6">
                    <input type="text" class="form-control" name="category_${categoryCount}" 
                           placeholder="Category Name" list="category-suggestions">
                </div>
                <div class="col-md-4">
                    <div class="input-group">
                        <span class="input-group-text">$</span>
                        <input type="number" step="0.01" class="form-control" name="amount_${categoryCount}" 
                               placeholder="Amount">
                    </div>
                </div>
                <div class="col-md-2">
                    <button type="button" class="btn btn-outline-danger remove-category-btn">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
            
            categoriesContainer.appendChild(newRow);
            
            // Add event listener to the remove button
            newRow.querySelector('.remove-category-btn').addEventListener('click', function() {
                newRow.remove();
            });
        });
    }
}

// Initialize categorization tools
function initCategorizationTools() {
    // Auto-categorize progress handling
    const categorizationProgress = document.getElementById('categorization-progress');
    if (categorizationProgress) {
        // Poll for categorization progress
        const limit = categorizationProgress.getAttribute('data-limit');
        
        function pollProgress() {
            fetch(`/categorize/auto/process?limit=${limit}`)
                .then(response => response.json())
                .then(data => {
                    const progress = Math.round((data.processed / data.total) * 100);
                    
                    // Update progress bar
                    document.getElementById('progress-bar').style.width = `${progress}%`;
                    document.getElementById('progress-bar').setAttribute('aria-valuenow', progress);
                    document.getElementById('progress-text').textContent = `${data.processed} of ${data.total} transactions processed`;
                    
                    // If complete, show results
                    if (data.processed >= data.total) {
                        document.getElementById('categorization-results').classList.remove('d-none');
                        document.getElementById('suggestion-count').textContent = data.suggestions.length;
                        
                        // Populate suggestions table
                        const suggestionsTable = document.getElementById('suggestions-table');
                        if (suggestionsTable && data.suggestions.length > 0) {
                            const tbody = suggestionsTable.querySelector('tbody');
                            tbody.innerHTML = '';
                            
                            data.suggestions.forEach(suggestion => {
                                const confidenceClass = suggestion.confidence > 0.8 ? 'high' : 
                                                       suggestion.confidence > 0.6 ? 'medium' : 'low';
                                
                                const row = document.createElement('tr');
                                row.className = `suggestion-item suggestion-confidence-${confidenceClass}`;
                                row.innerHTML = `
                                    <td>${suggestion.description}</td>
                                    <td>$${Math.abs(suggestion.amount).toFixed(2)}</td>
                                    <td>${suggestion.suggested_category}</td>
                                    <td>${(suggestion.confidence * 100).toFixed(0)}%</td>
                                    <td>
                                        <button class="btn btn-sm btn-success accept-btn" 
                                                data-transaction-id="${suggestion.id}" 
                                                data-category="${suggestion.suggested_category}">
                                            <i class="fas fa-check"></i> Accept
                                        </button>
                                    </td>
                                `;
                                
                                tbody.appendChild(row);
                                
                                // Add event listener to the accept button
                                row.querySelector('.accept-btn').addEventListener('click', function() {
                                    const txId = this.getAttribute('data-transaction-id');
                                    const category = this.getAttribute('data-category');
                                    
                                    updateTransactionCategory(txId, category);
                                    row.classList.add('bg-light');
                                    this.disabled = true;
                                    this.innerHTML = '<i class="fas fa-check"></i> Applied';
                                });
                            });
                        }
                    } else {
                        // Not complete, poll again after 1 second
                        setTimeout(pollProgress, 1000);
                    }
                })
                .catch(error => {
                    console.error('Error polling progress:', error);
                    document.getElementById('error-message').classList.remove('d-none');
                });
        }
        
        // Start polling
        pollProgress();
    }
}
