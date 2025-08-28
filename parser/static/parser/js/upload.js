// Upload functionality
document.addEventListener('DOMContentLoaded', function() {
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('id_file');
    const uploadForm = document.getElementById('upload-form');
    const progressContainer = document.getElementById('progress-container');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    
    // Drag and drop functionality
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            handleFileUpload(files[0]);
        }
    });
    
    // Click to upload
    uploadArea.addEventListener('click', function() {
        fileInput.click();
    });
    
    // File input change
    fileInput.addEventListener('change', function() {
        if (this.files.length > 0) {
            handleFileUpload(this.files[0]);
        }
    });
    
    function handleFileUpload(file) {
        // Validate file size
        const maxSize = 10 * 1024 * 1024; // 10MB
        if (file.size > maxSize) {
            showDetailedError('File too large', 
                `File size is ${(file.size / (1024*1024)).toFixed(1)}MB, maximum allowed is 10MB`,
                ['Compress your file', 'Use a smaller image resolution', 'Split large documents'],
                false);
            return;
        }
        
        // Validate file type
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'application/pdf', 'text/plain'];
        if (!allowedTypes.includes(file.type)) {
            showDetailedError('Unsupported file type', 
                `File type "${file.type}" is not supported`,
                ['Please upload JPG, PNG, PDF, or TXT files', 'Check your file format'],
                false);
            return;
        }
        
        // Show progress
        showProgress('Uploading...', 0);
        
        // Create FormData
        const formData = new FormData();
        formData.append('file', file);
        formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
        
        // Upload via AJAX
        const xhr = new XMLHttpRequest();
        
        xhr.upload.addEventListener('progress', function(e) {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                showProgress(`Uploading... ${Math.round(percentComplete)}%`, percentComplete);
            }
        });
        
        xhr.addEventListener('load', function() {
            if (xhr.status === 200) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    if (response.success) {
                        showProgress('Upload complete!', 100);
                        showMessage('success', response.message);
                        
                        // Reset form and reload page after delay
                        setTimeout(function() {
                            location.reload();
                        }, 1500);
                    } else {
                        hideProgress();
                        handleErrorResponse(response);
                    }
                } catch (e) {
                    hideProgress();
                    showDetailedError('Server Error', 
                        'Could not process server response',
                        ['Try again in a few minutes', 'Check your internet connection'],
                        true);
                }
            } else {
                hideProgress();
                showDetailedError('Upload Failed', 
                    `Server responded with status ${xhr.status}`,
                    ['Check your internet connection', 'Try again in a few minutes'],
                    true);
            }
        });
        
        xhr.addEventListener('error', function() {
            hideProgress();
            showDetailedError('Network Error', 
                'Could not connect to the server',
                ['Check your internet connection', 'Try again in a few minutes'],
                true);
        });
        
        xhr.addEventListener('timeout', function() {
            hideProgress();
            showDetailedError('Upload Timeout', 
                'The upload took too long to complete',
                ['Check your internet connection', 'Try uploading a smaller file'],
                true);
        });
        
        xhr.timeout = 60000; // 60 second timeout
        xhr.open('POST', uploadForm.dataset.uploadUrl || '/upload-ajax/');
        xhr.send(formData);
    }
    
    function showMessage(type, message) {
        const messagesContainer = document.querySelector('.messages') || createMessagesContainer();
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        messageDiv.textContent = message;
        
        messagesContainer.appendChild(messageDiv);
        
        // Auto-remove after 5 seconds
        setTimeout(function() {
            messageDiv.remove();
        }, 5000);
    }
    
    function createMessagesContainer() {
        const container = document.createElement('div');
        container.className = 'messages';
        document.querySelector('.container').insertBefore(container, document.querySelector('.session-info'));
        return container;
    }
    
    function showProgress(message, percentage) {
        progressContainer.style.display = 'block';
        progressFill.style.width = percentage + '%';
        progressText.textContent = message;
    }
    
    function hideProgress() {
        progressContainer.style.display = 'none';
    }
    
    function showDetailedError(title, details, suggestions, retryAllowed) {
        // Remove any existing error modals
        const existingModal = document.querySelector('.error-modal');
        if (existingModal) {
            existingModal.remove();
        }
        
        // Create error modal
        const modal = document.createElement('div');
        modal.className = 'error-modal';
        modal.innerHTML = `
            <div class="error-modal-content">
                <div class="error-modal-header">
                    <h3>${title}</h3>
                    <button class="error-modal-close">&times;</button>
                </div>
                <div class="error-modal-body">
                    <p class="error-details">${details}</p>
                    ${suggestions && suggestions.length > 0 ? `
                        <div class="error-suggestions">
                            <h4>Suggestions:</h4>
                            <ul>
                                ${suggestions.map(suggestion => `<li>${suggestion}</li>`).join('')}
                            </ul>
                        </div>
                    ` : ''}
                </div>
                <div class="error-modal-footer">
                    <button class="btn btn-secondary error-modal-close">Close</button>
                    ${retryAllowed ? '<button class="btn btn-primary" onclick="location.reload()">Try Again</button>' : ''}
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Add event listeners for close buttons
        modal.querySelectorAll('.error-modal-close').forEach(btn => {
            btn.addEventListener('click', () => modal.remove());
        });
        
        // Close on background click
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.remove();
            }
        });
    }
    
    function handleErrorResponse(response) {
        const title = response.error || 'Error';
        const details = response.details || response.message || 'An error occurred';
        const suggestions = response.suggestions || [];
        const retryAllowed = response.retry_allowed !== false;
        
        showDetailedError(title, details, suggestions, retryAllowed);
        
        // Also show a simple message
        showMessage('error', title);
    }
});

// Document processing functions
function processDocument(documentId) {
    const button = event.target;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Processing...';
    
    // Start status polling
    const statusInterval = startStatusPolling(documentId);
    
    fetch('/process-document/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ document_id: documentId })
    })
    .then(response => response.json())
    .then(data => {
        clearInterval(statusInterval);
        
        if (data.success) {
            showMessage('success', data.message);
            setTimeout(() => location.reload(), 1500);
        } else {
            handleProcessingError(data, button, originalText, documentId);
        }
    })
    .catch(error => {
        clearInterval(statusInterval);
        console.error('Error:', error);
        showDetailedError('Network Error', 
            'Could not connect to the server',
            ['Check your internet connection', 'Try again in a few minutes'],
            true);
        button.disabled = false;
        button.textContent = originalText;
    });
}

function handleProcessingError(errorData, button, originalText, documentId) {
    const title = errorData.error || 'Processing Failed';
    const details = errorData.details || 'An error occurred while processing the document';
    const suggestions = errorData.suggestions || [];
    const retryAllowed = errorData.retry_allowed !== false;
    
    // Show detailed error modal
    showDetailedError(title, details, suggestions, retryAllowed);
    
    // Update button based on retry availability
    if (retryAllowed) {
        button.textContent = 'Retry';
        button.onclick = () => retryProcessing(documentId, button);
    } else {
        button.textContent = 'Failed';
        button.classList.add('btn-danger');
    }
    
    button.disabled = false;
    
    // Show simple error message
    showMessage('error', title);
}

function retryProcessing(documentId, button) {
    button.disabled = true;
    button.textContent = 'Retrying...';
    
    fetch('/retry-processing/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ document_id: documentId })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showMessage('success', 'Processing completed successfully');
            setTimeout(() => location.reload(), 1500);
        } else {
            handleProcessingError(data, button, 'Retry', documentId);
        }
    })
    .catch(error => {
        console.error('Retry error:', error);
        showDetailedError('Retry Failed', 
            'Could not retry processing',
            ['Check your internet connection', 'Try refreshing the page'],
            true);
        button.disabled = false;
        button.textContent = 'Retry';
    });
}

function startStatusPolling(documentId) {
    return setInterval(() => {
        fetch(`/status/${documentId}/`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateProcessingStatus(documentId, data);
            }
        })
        .catch(error => {
            console.log('Status polling error:', error);
        });
    }, 2000); // Poll every 2 seconds
}

function updateProcessingStatus(documentId, statusData) {
    const statusElement = document.querySelector(`[data-document-id="${documentId}"] .processing-status`);
    if (statusElement) {
        const status = statusData.status;
        statusElement.textContent = status.charAt(0).toUpperCase() + status.slice(1);
        statusElement.className = `processing-status status-${status}`;
        
        // Add progress indicator for processing status
        if (status === 'processing') {
            statusElement.innerHTML = `
                <span class="status-text">Processing</span>
                <div class="processing-spinner"></div>
            `;
        }
    }
}

function viewResults(documentId) {
    fetch(`/results/${documentId}/`)
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            displayResults(data.results);
        } else {
            alert('Error loading results: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Network error occurred');
    });
}

function displayResults(results) {
    const resultsSection = document.getElementById('results-section');
    const dataTableBody = document.getElementById('data-table-body');
    
    // Clear existing data
    dataTableBody.innerHTML = '';
    
    // Populate table with results
    Object.entries(results).forEach(([field, data]) => {
        const row = document.createElement('tr');
        
        const fieldCell = document.createElement('td');
        fieldCell.textContent = field;
        
        const valueCell = document.createElement('td');
        valueCell.textContent = data.value || 'N/A';
        
        const confidenceCell = document.createElement('td');
        const confidenceSpan = document.createElement('span');
        confidenceSpan.className = `confidence-score confidence-${getConfidenceLevel(data.confidence)}`;
        confidenceSpan.textContent = `${Math.round(data.confidence * 100)}%`;
        confidenceCell.appendChild(confidenceSpan);
        
        row.appendChild(fieldCell);
        row.appendChild(valueCell);
        row.appendChild(confidenceCell);
        
        dataTableBody.appendChild(row);
    });
    
    // Show results section
    resultsSection.classList.add('show');
    
    // Enable download buttons
    document.getElementById('download-excel').disabled = false;
    document.getElementById('download-pdf').disabled = false;
    document.getElementById('download-doc').disabled = false;
}

function getConfidenceLevel(confidence) {
    if (confidence >= 0.8) return 'high';
    if (confidence >= 0.6) return 'medium';
    return 'low';
}