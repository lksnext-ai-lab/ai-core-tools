// Agent Playground JavaScript functionality

// Global variables
var cont = 0;
var attachedFiles = new Map(); // Store file references: {fileReference: {filename, contentType, uploadedAt}}

// File Upload Functionality
const fileUploadArea = document.getElementById('fileUploadArea');
const fileInput = document.getElementById('fileInput');
const attachedFilesSection = document.getElementById('attachedFilesSection');
const attachedFilesList = document.getElementById('attachedFilesList');

// === Playground Config from data-* attributes ===
const conversationContainer = document.querySelector('.conversation-container');
const appId = conversationContainer.dataset.appId;
const agentId = conversationContainer.dataset.agentId;
const agentName = conversationContainer.dataset.agentName;

// === Metadata Filter Collapse Animation ===
document.addEventListener('DOMContentLoaded', function() {
    const metadataFilterCollapse = document.getElementById('metadataFilterCollapse');
    const chevronIcon = document.querySelector('[data-bs-target="#metadataFilterCollapse"] .fas.fa-chevron-down');
    if (metadataFilterCollapse && chevronIcon) {
        metadataFilterCollapse.addEventListener('show.bs.collapse', function() {
            chevronIcon.style.transform = 'rotate(180deg)';
            chevronIcon.style.transition = 'transform 0.3s ease';
        });
        metadataFilterCollapse.addEventListener('hide.bs.collapse', function() {
            chevronIcon.style.transform = 'rotate(0deg)';
            chevronIcon.style.transition = 'transform 0.3s ease';
        });
    }
});

// === Prompt Editing Logic ===
window.saveSystemPrompt = function() {
    const newPrompt = document.getElementById('systemPromptEditor').value;
    const saveBtn = event.target;
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    saveBtn.disabled = true;
    fetch(`/agents/${agentId}/update-prompt`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        },
        body: JSON.stringify({ type: 'system', prompt: newPrompt })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('systemPromptPreview').textContent = newPrompt;
            bootstrap.Modal.getInstance(document.getElementById('systemPromptModal')).hide();
            showToast('System prompt updated successfully!', 'success');
            resetConversation();
        } else {
            showToast(data.error || 'Failed to update system prompt', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('An error occurred while saving the prompt', 'error');
    })
    .finally(() => {
        saveBtn.innerHTML = originalText;
        saveBtn.disabled = false;
    });
}

window.savePromptTemplate = function() {
    const newTemplate = document.getElementById('promptTemplateEditor').value;
    const saveBtn = event.target;
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    saveBtn.disabled = true;
    fetch(`/agents/${agentId}/update-prompt`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        },
        body: JSON.stringify({ type: 'template', prompt: newTemplate })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('promptTemplatePreview').textContent = newTemplate;
            bootstrap.Modal.getInstance(document.getElementById('promptTemplateModal')).hide();
            showToast('Prompt template updated successfully!', 'success');
            resetConversation();
        } else {
            showToast(data.error || 'Failed to update prompt template', 'error');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showToast('An error occurred while saving the template', 'error');
    })
    .finally(() => {
        saveBtn.innerHTML = originalText;
        saveBtn.disabled = false;
    });
}

// === Toast Notification Logic ===
function showToast(message, type = 'info') {
    const toastHtml = `
        <div class="toast align-items-center text-white bg-${type === 'error' ? 'danger' : type === 'success' ? 'success' : 'info'} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    toastContainer.insertAdjacentHTML('beforeend', toastHtml);
    const toastElement = toastContainer.lastElementChild;
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed top-0 end-0 p-3';
    container.style.zIndex = '9999';
    document.body.appendChild(container);
    return container;
}

// === Reset Conversation Logic ===
function resetConversation() {
    const resetBtn = document.getElementById('reset-btn');
    if (resetBtn) resetBtn.disabled = true;
    fetch('/api/app/' + appId + '/reset/' + agentId, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' }
    })
    .then(response => {
        if (!response.ok) throw new Error('Failed to reset conversation');
        return response.json();
    })
    .then(data => {
        // Remove all conversation messages
        document.querySelectorAll('.conversation-message').forEach(el => el.remove());
        // Clear attached files if the function exists
        if (typeof attachedFiles !== 'undefined') {
            attachedFiles.clear();
            const attachedFilesList = document.getElementById('attachedFilesList');
            if (attachedFilesList) attachedFilesList.innerHTML = '';
            if (typeof updateAttachedFilesVisibility === 'function') updateAttachedFilesVisibility();
        }
        // Show success message
        const successDiv = createMessageElement('agent', 'System', '<div class="text-success">Conversation reset due to prompt changes</div>');
        successDiv.attr('id', 'success-reset');
        document.querySelector('.conversation-container').appendChild(successDiv[0]);
        var container = document.querySelector('.conversation-container');
        if (container) container.scrollTop = container.scrollHeight;
        setTimeout(() => {
            if (successDiv[0].parentNode) successDiv[0].parentNode.removeChild(successDiv[0]);
        }, 3000);
    })
    .catch(error => {
        console.error('Error resetting conversation:', error);
        showToast('Failed to reset conversation. Please try again.', 'error');
    })
    .finally(() => {
        if (resetBtn) resetBtn.disabled = false;
    });
}

// Drag and drop functionality
fileUploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileUploadArea.classList.add('border-primary');
    fileUploadArea.style.backgroundColor = '#f8f9fa';
});

fileUploadArea.addEventListener('dragleave', (e) => {
    e.preventDefault();
    fileUploadArea.classList.remove('border-primary');
    fileUploadArea.style.backgroundColor = '';
});

fileUploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    fileUploadArea.classList.remove('border-primary');
    fileUploadArea.style.backgroundColor = '';
    
    const files = Array.from(e.dataTransfer.files);
    handleFiles(files);
});

fileInput.addEventListener('change', (e) => {
    const files = Array.from(e.target.files);
    handleFiles(files);
});

function handleFiles(files) {
    files.forEach(file => {
        uploadFile(file);
    });
}

function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    // Show loading state
    const fileItem = createFileItem(file, 'uploading');
    attachedFilesList.appendChild(fileItem);
    updateAttachedFilesVisibility();
    
    fetch('/api/app/' + appId + '/attach-file/' + agentId, {
        method: 'POST',
        credentials: 'include',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Upload failed: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        // Update file item with success state
        updateFileItem(fileItem, file.name, data.file_reference, 'success');
        attachedFiles.set(data.file_reference, {
            filename: file.name,
            contentType: data.content_type,
            uploadedAt: new Date().toISOString()
        });
    })
    .catch(error => {
        console.error('Upload error:', error);
        updateFileItem(fileItem, file.name, null, 'error', error.message);
    });
}

function createFileItem(file, status) {
    const fileItem = document.createElement('div');
    fileItem.className = 'list-group-item d-flex align-items-center p-2';
    fileItem.innerHTML = `
        <div class="flex-grow-1">
            <div class="d-flex align-items-center">
                <i class="fas fa-file me-2"></i>
                <span class="filename small">${file.name}</span>
            </div>
            <div class="status-text text-muted small"></div>
        </div>
        <div class="file-actions">
            <button type="button" class="btn btn-sm btn-outline-danger remove-file" style="display: none;">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;
    return fileItem;
}

function updateFileItem(fileItem, filename, fileReference, status, errorMessage = '') {
    const statusText = fileItem.querySelector('.status-text');
    const removeBtn = fileItem.querySelector('.remove-file');
    
    switch(status) {
        case 'uploading':
            statusText.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Uploading...';
            break;
        case 'success':
            statusText.innerHTML = '<i class="fas fa-check text-success"></i> Ready';
            removeBtn.style.display = 'block';
            removeBtn.onclick = () => removeFile(fileReference, fileItem);
            fileItem.dataset.fileReference = fileReference;
            break;
        case 'error':
            statusText.innerHTML = `<i class="fas fa-exclamation-triangle text-danger"></i> ${errorMessage}`;
            removeBtn.style.display = 'block';
            removeBtn.onclick = () => fileItem.remove();
            break;
    }
}

function removeFile(fileReference, fileItem) {
    fetch('/api/app/' + appId + '/detach-file/' + agentId + '/' + fileReference, {
        method: 'DELETE',
        credentials: 'include'
    })
    .then(response => {
        if (response.ok) {
            attachedFiles.delete(fileReference);
            fileItem.remove();
            updateAttachedFilesVisibility();
        } else {
            throw new Error('Failed to remove file');
        }
    })
    .catch(error => {
        console.error('Remove file error:', error);
        alert('Failed to remove file. Please try again.');
    });
}

function updateAttachedFilesVisibility() {
    if (attachedFilesList.children.length > 0) {
        attachedFilesSection.style.display = 'block';
    } else {
        attachedFilesSection.style.display = 'none';
    }
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Clear all files
document.getElementById('clearAllFiles').addEventListener('click', () => {
    if (confirm('Are you sure you want to remove all attached files?')) {
        const promises = Array.from(attachedFiles.keys()).map(fileReference => 
            fetch('/api/app/' + appId + '/detach-file/' + agentId + '/' + fileReference, {
                method: 'DELETE',
                credentials: 'include'
            })
        );
        
        Promise.all(promises)
            .then(() => {
                attachedFiles.clear();
                attachedFilesList.innerHTML = '';
                updateAttachedFilesVisibility();
            })
            .catch(error => {
                console.error('Clear files error:', error);
                alert('Failed to clear some files. Please try again.');
            });
    }
});

// Load existing attached files on page load
function loadAttachedFiles() {
    fetch('/api/app/' + appId + '/attached-files/' + agentId, {
        method: 'GET',
        credentials: 'include'
    })
    .then(response => response.json())
    .then(data => {
        if (data.files && Object.keys(data.files).length > 0) {
            Object.entries(data.files).forEach(([fileReference, fileInfo]) => {
                attachedFiles.set(fileReference, fileInfo);
                const fileItem = createFileItem({name: fileInfo.filename, size: 0}, 'success');
                updateFileItem(fileItem, fileInfo.filename, fileReference, 'success');
                attachedFilesList.appendChild(fileItem);
            });
            updateAttachedFilesVisibility();
        }
    })
    .catch(error => {
        console.error('Load attached files error:', error);
    });
}

// Function to create message elements with new styling
function createMessageElement(type, sender, content, fileCount = 0) {
    var messageClass = type + '-message';
    var bubbleClass = type + '-bubble';
    var avatarSrc = type === 'user' ? '/static/img/user-avatar.png' : '/static/img/mattin-small.png';
    
    // Default avatar if user avatar doesn't exist
    if (type === 'user') {
        avatarSrc = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHZpZXdCb3g9IjAgMCA0MCA0MCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPGNpcmNsZSBjeD0iMjAiIGN5PSIyMCIgcj0iMjAiIGZpbGw9IiMyOGE3NDUiLz4KPHN2ZyB4PSIxMCIgeT0iMTAiIHdpZHRoPSIyMCIgaGVpZ2h0PSIyMCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJ3aGl0ZSI+CjxwYXRoIGQ9Ik0xMiAxMmMyLjIxIDAgNC0xLjc5IDQtNHMtMS43OS00LTQtNC00IDEuNzktNCA0IDEuNzkgNCA0IDR6bTAgMmMtMi42NyAwLTggMS4zNC04IDR2MmgxNnYtMmMwLTIuNjYtNS4zMy00LTgtNHoiLz4KPC9zdmc+Cjwvc3ZnPgo=';
    }
    
    var fileAttachment = '';
    if (fileCount > 0) {
        fileAttachment = '<div class="file-attachment"><i class="fas fa-paperclip"></i> ' + fileCount + ' file(s) attached</div>';
    }
    
    var messageHtml = `
        <div class="conversation-message ${messageClass}">
            <div class="d-flex align-items-start">
                <div class="message-avatar me-3">
                    <img class="rounded-circle" src="${avatarSrc}" alt="avatar" style="width: 40px; height: 40px; object-fit: cover;">
                </div>
                <div class="message-bubble ${bubbleClass}">
                    <div class="message-header">
                        <span class="message-sender">${sender}</span>
                        <small class="message-time">${new Date().toLocaleTimeString()}</small>
                    </div>
                    <div class="message-content">
                        ${content}
                        ${fileAttachment}
                    </div>
                </div>
            </div>
        </div>
    `;
    
    return $(messageHtml);
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Load files on page load
    loadAttachedFiles();
    
    // Add reset functionality
    $('#reset-btn').click(function() {
        // Disable button while processing
        $('#reset-btn').prop('disabled', true);
        
        fetch('/api/app/' + appId + '/reset/' + agentId, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to reset conversation');
            }
            return response.json();
        })
        .then(data => {
            // Remove all conversation divs except the initial one
            $('[id^="referenece-"]').remove();
            $('[id^="loading-"]').remove();
            $('[id^="error-"]').remove();
            cont = 0;
            
            // Clear attached files
            attachedFiles.clear();
            attachedFilesList.innerHTML = '';
            updateAttachedFilesVisibility();
            
            // Show success message
            var successDiv = createMessageElement('agent', 'System', '<div class="text-success">Conversation reset successfully</div>');
            successDiv.attr('id', 'success-' + cont);
            $('.conversation-container').append(successDiv);
            var container = document.querySelector('.conversation-container');
            if (container) container.scrollTop = container.scrollHeight;
            
            // Remove success message after 3 seconds
            setTimeout(() => {
                $('#success-' + cont).remove();
            }, 3000);
        })
        .catch(error => {
            console.error('Error resetting conversation:', error);
            alert('Failed to reset conversation. Please try again.');
        })
        .finally(() => {
            $('#reset-btn').prop('disabled', false);
        });
    });

    // Function to send message
    function sendMessage() {
        // Deshabilitar el botón mientras se procesa
        $('#send-btn').prop('disabled', true);
        
        var question = $('#question').val();
        console.log('Sending question:', question);
        
        // Limpiar el input inmediatamente después de obtener su valor
        $('#question').val('');

        // Collect filter values if they exist
        var search_params = null;
        if (typeof filterFields !== 'undefined' && filterFields.length > 0) {
            var filter = {};
            filterFields.forEach(function(field) {
                var value = $('#filter_' + field.name).val();
                if (value) {
                    filter[field.name] = value;
                }
            });
            if (Object.keys(filter).length > 0) {
                search_params = { filter: filter };
            }
        }
        
        // Collect file references
        var file_references = Array.from(attachedFiles.keys());
        
        // Create user message
        var qDiv = createMessageElement('user', 'You', question, file_references.length);
        qDiv.attr('id', 'referenece-' + cont);
        cont++;
        $('.conversation-container').append(qDiv);
        var container = document.querySelector('.conversation-container');
        if (container) container.scrollTop = container.scrollHeight;

        // Create loading message
        var loadingDiv = createMessageElement('loading', agentName, '<div class="d-flex align-items-center"><div class="spinner-border spinner-border-sm me-2" role="status"></div>Thinking...</div>');
        loadingDiv.attr('id', 'loading-' + cont);
        $('.conversation-container').append(loadingDiv);
        var container = document.querySelector('.conversation-container');
        if (container) container.scrollTop = container.scrollHeight;

        $("html, body").animate({
            scrollTop: $(document).height() - $(window).height()
        }, 'slow');

        // Hacer la petición con timeout
        const timeoutDuration = 600000; // 10 minutos
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutDuration);

        fetch('/api/app/' + appId + '/call/' + agentId, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                question: question,
                search_params: search_params,
                file_references: file_references
            }),
            signal: controller.signal
        })
        .then(async response => {
            clearTimeout(timeoutId);
            if (!response.ok) {
                // Intentar obtener el mensaje de error del servidor
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `Error del servidor: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Remove loading message
            loadingDiv.remove();
            
            // Create response message
            var responseText = data["generated_text"];
            if (data.metadata && data.metadata.attachments_processed) {
                responseText += '\n\n<small class="text-muted"><i class="fas fa-check"></i> ' + 
                               data.metadata.attachment_count + ' file(s) processed</small>';
            }
            
            // If it's an object, convert to JSON string, otherwise try markdown
            var htmlContent;
            var textToProcess;
            
            if (responseText && typeof responseText === 'object') {
                textToProcess = JSON.stringify(responseText, null, 2);
            } else {
                textToProcess = String(responseText || '');
            }
            
            try {
                htmlContent = marked.parse(textToProcess);
            } catch (error) {
                console.warn('Markdown parsing failed, using plain text:', error);
                // Escape HTML to prevent XSS and preserve formatting
                htmlContent = textToProcess
                    .replace(/&/g, '&amp;')
                    .replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;')
                    .replace(/"/g, '&quot;')
                    .replace(/'/g, '&#39;')
                    .replace(/\n/g, '<br>');
            }
            var respDiv = createMessageElement('agent', agentName, htmlContent);
            respDiv.attr('id', 'referenece-' + cont);
            cont++;
            $('.conversation-container').append(respDiv);
            var container = document.querySelector('.conversation-container');
            if (container) container.scrollTop = container.scrollHeight;
        })
        .catch(error => {
            // Remove loading message
            loadingDiv.remove();
            
            // Show error message
            var errorDiv = createMessageElement('error', 'Error', `
                <div class="text-danger">
                    <p><strong>Error:</strong> ${error.message}</p>
                    <p><small>Si el problema persiste, por favor contacte al administrador.</small></p>
                </div>
            `);
            errorDiv.attr('id', 'error-' + cont);
            $('.conversation-container').append(errorDiv);
            var container = document.querySelector('.conversation-container');
            if (container) container.scrollTop = container.scrollHeight;
            
            console.error('Error detallado:', error);
        })
        .finally(() => {
            // Solo habilitar el botón ya que el input se limpió antes
            $('#send-btn').prop('disabled', false);
        });
    }

    // Add click handler for send button
    $('#send-btn').click(sendMessage);

    // Add keyboard event handler for textarea
    $('#question').keydown(function(e) {
        if (e.key === 'Enter' && !e.ctrlKey && !e.shiftKey) {
            e.preventDefault(); // Prevent default Enter behavior
            sendMessage();
        }
        // Ctrl+Enter or Shift+Enter will add new line (default behavior)
    });
}); 