/**
 * Settings.js - Handles the UI for the settings tab in the dashboard
 */

// Store current chatbot ID and config
let currentChatbotId = '';
let currentSettings = {};
let currentSettingSection = '';

// Initialize settings page
document.addEventListener('DOMContentLoaded', function() {
    // If settings tab is initially active, load settings
    if (document.getElementById('settings').classList.contains('active')) {
        loadSettings();
    }

    // Add listener for tab clicks
    document.querySelector('a[onclick="openPage(\'settings\')"]')?.addEventListener('click', function() {
        setTimeout(loadSettings, 100); // Short delay to ensure tab is active
    });

    // Initialize settings navigation event handlers
    document.querySelectorAll('.settings-nav-item').forEach(item => {
        item.addEventListener('click', function(e) {
            e.preventDefault();
            const settingType = this.getAttribute('data-setting');
            switchSettingSection(settingType);
        });
    });
});

// Load settings for the current chatbot
function loadSettings() {
    // Get the currently selected chatbot ID
    const selectedBotElement = document.getElementById('selected-bot-name');
    let chatbotId = '';
    
    if (selectedBotElement) {
        const botDropdownOptions = document.querySelectorAll('.bot-dropdown-content a');
        for (let option of botDropdownOptions) {
            if (option.textContent.trim() === selectedBotElement.textContent.trim()) {
                const match = option.getAttribute('onclick').match(/selectBot\('([^']+)'/);
                if (match && match[1]) {
                    chatbotId = match[1];
                    break;
                }
            }
        }
    }
    
    if (!chatbotId) {
        showError('No chatbot selected. Please select a chatbot first.');
        return;
    }
    
    // Update current chatbot ID
    currentChatbotId = chatbotId;
    
    // Show loading state
    const contentArea = document.querySelector('.settings-content-area');
    if (contentArea) {
        contentArea.innerHTML = `
            <div class="settings-loading">
                <div class="spinner"></div>
                <p>Loading settings...</p>
            </div>
        `;
    }
    
    // Fetch settings from server
    fetch(`/settings/get-config/${chatbotId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                // Store settings
                currentSettings = data.config;
                
                // Load the UI with the first setting or the previously selected one
                if (!currentSettingSection) {
                    currentSettingSection = 'system-prompt';
                }
                
                // Highlight the active setting in the navigation
                document.querySelectorAll('.settings-nav-item').forEach(item => {
                    if (item.getAttribute('data-setting') === currentSettingSection) {
                        item.classList.add('active');
                    } else {
                        item.classList.remove('active');
                    }
                });
                
                // Load the content for the active setting
                loadSettingContent(currentSettingSection);
            } else {
                showError('Failed to load settings: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(error => {
            console.error('Error loading settings:', error);
            showError('Failed to load settings: ' + error.message);
        });
}

// Switch to a different setting section
function switchSettingSection(sectionId) {
    // Update current setting section
    currentSettingSection = sectionId;
    
    // Highlight the active setting in the navigation
    document.querySelectorAll('.settings-nav-item').forEach(item => {
        if (item.getAttribute('data-setting') === sectionId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
    
    // Load the content for the selected setting
    loadSettingContent(sectionId);
}

// Load content for a specific setting
function loadSettingContent(settingId) {
    const contentArea = document.querySelector('.settings-content-area');
    if (!contentArea) return;
    
    // Clear any previous form
    contentArea.innerHTML = '';
    
    // Create the appropriate form based on setting type
    switch (settingId) {
        case 'system-prompt':
            renderSystemPromptForm(contentArea);
            break;
        case 'chat-title':
            renderTextInputForm(contentArea, 'chat-title', 'Chat Title', 'The title shown at the top of your chatbot', 100);
            break;
        case 'chat-subtitle':
            renderTextInputForm(contentArea, 'chat-subtitle', 'Chat Subtitle', 'The subtitle text shown below the chat title', 100);
            break;
        case 'lead-form-title':
            renderTextInputForm(contentArea, 'lead-form-title', 'Lead Form Title', 'The title shown at the top of the lead generation form', 100);
            break;
        case 'primary-color':
            renderColorForm(contentArea, 'primary-color', 'Primary Color', 'The main color used for buttons and accents', 
                ['#0084ff', '#28a745', '#dc3545']);
            break;
        case 'accent-color':
            renderColorForm(contentArea, 'accent-color', 'Accent Color', 'The secondary color used for highlights', 
                ['#ffffff', '#f8f9fa', '#e9ecef']);
            break;
        case 'icon-image':
            renderIconImageForm(contentArea);
            break;
        case 'show-lead-form':
            renderRadioForm(contentArea, 'show-lead-form', 'Show Lead Form', 'Enable or disable the lead generation form', 
                [
                    { value: 'Yes', label: 'Yes - Show lead form to collect contact information' },
                    { value: 'No', label: 'No - Hide the lead form' }
                ]);
            break;
        case 'webhook-url':
            renderWebhookUrlForm(contentArea);
            break;
        case 'webhook-triggers':
            renderRadioForm(contentArea, 'webhook-triggers', 'Webhook Triggers', 'Select which events trigger your webhook', 
                [
                    { value: 'new_lead', label: 'New Lead - Send webhook when a new lead is generated' },
                    { value: '', label: 'No Trigger - Disable webhook triggers' }
                ]);
            break;
        default:
            contentArea.innerHTML = '<div class="settings-error">Unknown setting type</div>';
    }
}

// Render system prompt form
function renderSystemPromptForm(container) {
    const formHtml = `
        <div class="settings-form">
            <h3>System Prompt</h3>
            <p class="settings-description">The system prompt controls how your chatbot responds to user questions. It defines its personality, knowledge limitations, and behavior.</p>
            
            <div class="form-group">
                <textarea id="system-prompt-input" class="settings-textarea" rows="15">${currentSettings['system_prompt'] || ''}</textarea>
            </div>
            
            <div class="settings-message" id="settings-message-system-prompt"></div>
            
            <div class="settings-actions">
                <button id="save-system-prompt" class="settings-save-btn">Save Changes</button>
            </div>
        </div>
    `;
    
    container.innerHTML = formHtml;
    
    // Add event listener for save button
    document.getElementById('save-system-prompt').addEventListener('click', function() {
        const value = document.getElementById('system-prompt-input').value;
        saveSettingValue('system_prompt', value);
    });
}

// Render text input form with character limit
function renderTextInputForm(container, settingId, title, description, charLimit) {
    const dbFieldName = settingId.replace(/-/g, '_'); // Convert hyphen to underscore for DB field
    const currentValue = currentSettings[dbFieldName] || '';
    
    const formHtml = `
        <div class="settings-form">
            <h3>${title}</h3>
            <p class="settings-description">${description}</p>
            
            <div class="form-group">
                <input type="text" id="${settingId}-input" class="settings-text-input" 
                    value="${currentValue}" maxlength="${charLimit}">
                <div class="char-counter">
                    <span id="${settingId}-counter">${currentValue.length}</span>/${charLimit}
                </div>
            </div>
            
            <div class="settings-message" id="settings-message-${settingId}"></div>
            
            <div class="settings-actions">
                <button id="save-${settingId}" class="settings-save-btn">Save Changes</button>
            </div>
        </div>
    `;
    
    container.innerHTML = formHtml;
    
    // Add event listeners
    const inputField = document.getElementById(`${settingId}-input`);
    const counter = document.getElementById(`${settingId}-counter`);
    
    inputField.addEventListener('input', function() {
        counter.textContent = this.value.length;
    });
    
    document.getElementById(`save-${settingId}`).addEventListener('click', function() {
        const value = inputField.value;
        saveSettingValue(dbFieldName, value);
    });
}

// Render color picker form
function renderColorForm(container, settingId, title, description, presetColors) {
    const dbFieldName = settingId.replace(/-/g, '_'); // Convert hyphen to underscore for DB field
    const currentValue = currentSettings[dbFieldName] || '#0084ff';
    
    const formHtml = `
        <div class="settings-form">
            <h3>${title}</h3>
            <p class="settings-description">${description}</p>
            
            <div class="form-group">
                <label>Hex Color Code:</label>
                <div class="color-input-container">
                    <input type="text" id="${settingId}-input" class="settings-text-input" 
                        value="${currentValue}">
                    <div class="color-preview" id="${settingId}-preview" style="background-color: ${currentValue}"></div>
                </div>
                
                <div class="color-presets">
                    ${presetColors.map(color => 
                        `<div class="color-preset" data-color="${color}" style="background-color: ${color}" title="${color}"></div>`
                    ).join('')}
                </div>
            </div>
            
            <div class="settings-message" id="settings-message-${settingId}"></div>
            
            <div class="settings-actions">
                <button id="save-${settingId}" class="settings-save-btn">Save Changes</button>
            </div>
        </div>
    `;
    
    container.innerHTML = formHtml;
    
    // Add event listeners
    const inputField = document.getElementById(`${settingId}-input`);
    const colorPreview = document.getElementById(`${settingId}-preview`);
    
    inputField.addEventListener('input', function() {
        colorPreview.style.backgroundColor = this.value;
    });
    
    // Add preset color click handlers
    document.querySelectorAll('.color-preset').forEach(preset => {
        preset.addEventListener('click', function() {
            const color = this.getAttribute('data-color');
            inputField.value = color;
            colorPreview.style.backgroundColor = color;
        });
    });
    
    document.getElementById(`save-${settingId}`).addEventListener('click', function() {
        const value = inputField.value;
        // Basic hex color validation
        if (!/^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$/.test(value)) {
            showSettingMessage(`settings-message-${settingId}`, 'Please enter a valid hex color code (e.g. #0084ff)', 'error');
            return;
        }
        saveSettingValue(dbFieldName, value);
    });
}

// Render icon image form with Cloudinary upload
function renderIconImageForm(container) {
    const currentImage = currentSettings['icon_image_url'] || '';
    
    const formHtml = `
        <div class="settings-form">
            <h3>Chatbot Icon</h3>
            <p class="settings-description">Upload an image to personalize your chatbot. This will appear in the chat interface. For best results, use a square image.</p>
            
            <div class="form-group">
                <div class="icon-preview-container">
                    ${currentImage ? 
                        `<img src="${currentImage}" alt="Chatbot Icon" class="icon-preview" id="icon-preview">` :
                        `<div class="icon-placeholder">No image uploaded</div>`
                    }
                </div>
                
                <div class="icon-upload-container">
                    <input type="file" id="icon-image-file" accept="image/*" style="display: none;">
                    <button type="button" id="select-icon-btn" class="settings-upload-btn">
                        <span id="camera-icon">📸</span> Upload Image
                    </button>
                    <div id="image-preview-container"></div>
                    <div class="spinner-container" style="display: none;">
                        <div class="spinner"></div>
                        <p>Uploading image...</p>
                    </div>
                    <p class="settings-note">
                        Maximum file size: 10MB. Recommended size: 300x300 pixels.
                    </p>
                </div>
                
                <label>Or enter image URL:</label>
                <input type="text" id="icon-image-input" class="settings-text-input" 
                    value="${currentImage}" placeholder="Enter image URL">
            </div>
            
            <div class="settings-message" id="settings-message-icon-image"></div>
            
            <div class="settings-actions">
                <button id="save-icon-image" class="settings-save-btn">Save Changes</button>
            </div>
        </div>
    `;
    
    container.innerHTML = formHtml;
    
    // Add event listeners
    const inputField = document.getElementById('icon-image-input');
    const fileInput = document.getElementById('icon-image-file');
    const selectButton = document.getElementById('select-icon-btn');
    
    // Click on upload button triggers file input
    selectButton.addEventListener('click', function() {
        fileInput.click();
    });
    
    // File input change handler
    fileInput.addEventListener('change', handleIconImageUpload);
    
    // Save button handler
    document.getElementById('save-icon-image').addEventListener('click', function() {
        const value = inputField.value.trim();
        saveSettingValue('icon_image_url', value);
    });
}

// Handle icon image upload to Cloudinary
async function handleIconImageUpload(event) {
    const file = event.target.files[0];
    if (!file) {
        alert("Please select a file to upload.");
        return;
    }
    
    const spinnerContainer = document.querySelector('.spinner-container');
    const imagePreviewContainer = document.getElementById('image-preview-container');
    
    try {
        // Show spinner
        spinnerContainer.style.display = 'flex';
        
        // Validate file size (10MB limit)
        const maxSizeInMB = 10;
        const maxSizeInBytes = maxSizeInMB * 1024 * 1024;
        if (file.size > maxSizeInBytes) {
            spinnerContainer.style.display = 'none';
            alert(`File size exceeds ${maxSizeInMB}MB! Please choose a smaller file.`);
            return;
        }
        
        // Validate image dimensions
        const dimensionsValid = await validateImageDimensions(file);
        if (!dimensionsValid) {
            spinnerContainer.style.display = 'none';
            alert('Image dimensions are too large. Maximum dimensions are 2000x2000 pixels.');
            return;
        }
        
        // Step 1: Fetch signature from our server
        const signatureResponse = await fetch('/settings/generate-cloudinary-signature');
        const signatureData = await signatureResponse.json();
        
        if (!signatureData.success) {
            throw new Error(signatureData.error || "Failed to get upload signature");
        }
        
        console.log('Cloudinary signature data:', signatureData);
        console.log('Folder being sent to Cloudinary:', signatureData.folder);

        // Step 2: Upload to Cloudinary
        const formData = new FormData();
        formData.append('file', file);
        formData.append('api_key', signatureData.api_key);
        formData.append('timestamp', signatureData.timestamp);
        formData.append('signature', signatureData.signature);
        formData.append('folder', signatureData.folder);
        formData.append('transformation', signatureData.transformation);
        
        const uploadResponse = await fetch(`https://api.cloudinary.com/v1_1/${signatureData.cloud_name}/image/upload`, {
            method: 'POST',
            body: formData
        });
        
        const uploadResult = await uploadResponse.json();
        
        if (!uploadResponse.ok) {
            throw new Error(uploadResult.error?.message || "Image upload failed");
        }
        
        // Add transformation to the uploaded URL for preview
        const transformedUrl = uploadResult.secure_url.replace(
            '/upload/',
            '/upload/c_limit,w_300/'
        );
        
        // Update the input field with the URL
        document.getElementById('icon-image-input').value = uploadResult.secure_url;
        
        // Update the preview
        const iconPreview = document.getElementById('icon-preview');
        if (iconPreview) {
            iconPreview.src = transformedUrl;
        } else {
            const previewContainer = document.querySelector('.icon-preview-container');
            previewContainer.innerHTML = `<img src="${transformedUrl}" alt="Chatbot Icon" class="icon-preview" id="icon-preview">`;
        }
        
        // Hide placeholder if it exists
        const placeholder = document.querySelector('.icon-placeholder');
        if (placeholder) {
            placeholder.style.display = 'none';
        }
        
    } catch (error) {
        console.error('Error uploading image:', error);
        alert('Error uploading image: ' + error.message);
    } finally {
        // Hide spinner
        spinnerContainer.style.display = 'none';
    }
}

// Validate image dimensions
function validateImageDimensions(file) {
    return new Promise((resolve) => {
        const reader = new FileReader();
        
        reader.onload = (e) => {
            const img = new Image();
            
            img.onload = () => {
                const maxWidth = 5000;
                const maxHeight = 5000;
                
                if (img.width > maxWidth || img.height > maxHeight) {
                    resolve(false);
                } else {
                    resolve(true);
                }
            };
            
            img.src = e.target.result;
        };
        
        reader.readAsDataURL(file);
    });
}

// Render radio button form
function renderRadioForm(container, settingId, title, description, options) {
    const dbFieldName = settingId.replace(/-/g, '_'); // Convert hyphen to underscore for DB field
    const currentValue = currentSettings[dbFieldName] || '';
    
    const formHtml = `
        <div class="settings-form">
            <h3>${title}</h3>
            <p class="settings-description">${description}</p>
            
            <div class="form-group">
                ${options.map((option, index) => `
                    <div class="radio-option">
                        <input type="radio" id="${settingId}-${index}" name="${settingId}" 
                            value="${option.value}" ${currentValue === option.value ? 'checked' : ''}>
                        <label for="${settingId}-${index}">${option.label}</label>
                    </div>
                `).join('')}
            </div>
            
            <div class="settings-message" id="settings-message-${settingId}"></div>
            
            <div class="settings-actions">
                <button id="save-${settingId}" class="settings-save-btn">Save Changes</button>
            </div>
        </div>
    `;
    
    container.innerHTML = formHtml;
    
    // Add event listener for save button
    document.getElementById(`save-${settingId}`).addEventListener('click', function() {
        const selectedOption = document.querySelector(`input[name="${settingId}"]:checked`);
        if (selectedOption) {
            const value = selectedOption.value;
            saveSettingValue(dbFieldName, value);
        } else {
            showSettingMessage(`settings-message-${settingId}`, 'Please select an option', 'error');
        }
    });
}

// Render webhook URL form with validation and testing
function renderWebhookUrlForm(container) {
    const currentUrl = currentSettings['webhook_url'] || '';
    
    const formHtml = `
        <div class="settings-form">
            <h3>Webhook URL</h3>
            <p class="settings-description">Enter a webhook URL to receive notifications when events occur (e.g., when a new lead is generated).</p>
            
            <div class="form-group">
                <input type="text" id="webhook-url-input" class="settings-text-input" 
                    value="${currentUrl}" placeholder="https://hooks.yourservice.com/path">
                    
                <p class="settings-note">
                    Note: Only URLs from supported integration providers (e.g., Zapier, Make.com, n8n, IFTTT) are allowed.
                </p>
            </div>
            
            <div class="settings-message" id="settings-message-webhook-url"></div>
            
            <div class="settings-actions">
                <button id="save-webhook-url" class="settings-save-btn">Save Changes</button>
                ${currentUrl ? `<button id="test-webhook" class="settings-test-btn">Test Webhook</button>` : ''}
            </div>
            
            <div id="webhook-test-results" class="webhook-test-results" style="display: none;">
                <h4>Test Results</h4>
                <div id="webhook-status"></div>
                <div class="webhook-payload">
                    <h5>Payload</h5>
                    <pre id="webhook-payload-content"></pre>
                </div>
            </div>
        </div>
    `;
    
    container.innerHTML = formHtml;
    
    // Add event listeners
    const inputField = document.getElementById('webhook-url-input');
    
    document.getElementById('save-webhook-url').addEventListener('click', function() {
        const value = inputField.value.trim();
        
        // Basic URL validation
        if (value && !value.match(/^https?:\/\/.+/)) {
            showSettingMessage('settings-message-webhook-url', 'Please enter a valid URL (must start with http:// or https://)', 'error');
            return;
        }
        
        saveSettingValue('webhook_url', value, function() {
            // Show/hide test button based on whether a URL is now saved
            if (value) {
                if (!document.getElementById('test-webhook')) {
                    const actionsDiv = document.querySelector('.settings-actions');
                    const testButton = document.createElement('button');
                    testButton.id = 'test-webhook';
                    testButton.className = 'settings-test-btn';
                    testButton.textContent = 'Test Webhook';
                    testButton.addEventListener('click', testWebhook);
                    actionsDiv.appendChild(testButton);
                }
            } else {
                const testButton = document.getElementById('test-webhook');
                if (testButton) testButton.remove();
                
                // Hide test results if they were shown
                document.getElementById('webhook-test-results').style.display = 'none';
            }
        });
    });
    
    // Add test webhook handler if button exists
    const testButton = document.getElementById('test-webhook');
    if (testButton) {
        testButton.addEventListener('click', testWebhook);
    }
}

// Test webhook functionality
function testWebhook() {
    // Show loading state
    const statusDiv = document.getElementById('webhook-status');
    const resultsContainer = document.getElementById('webhook-test-results');
    const payloadContent = document.getElementById('webhook-payload-content');
    
    resultsContainer.style.display = 'block';
    statusDiv.innerHTML = `
        <div class="webhook-testing">
            <div class="spinner" style="width: 20px; height: 20px;"></div>
            <span>Testing webhook...</span>
        </div>
    `;
    payloadContent.textContent = '';
    
    // Get CSRF token
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    
    // Send test webhook request
    fetch(`/settings/test-webhook/${currentChatbotId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            statusDiv.innerHTML = `
                <div class="webhook-success">
                    <span class="webhook-icon">✓</span>
                    <span>Webhook sent successfully!</span>
                </div>
            `;
            
            // Show payload
            if (data.payload) {
                payloadContent.textContent = JSON.stringify(data.payload, null, 2);
            }
        } else {
            statusDiv.innerHTML = `
                <div class="webhook-error">
                    <span class="webhook-icon">✗</span>
                    <span>Webhook test failed: ${data.error || 'Unknown error'}</span>
                </div>
            `;
            
            // Show payload and details if available
            if (data.payload) {
                payloadContent.textContent = JSON.stringify(data.payload, null, 2);
            }
        }
    })
    .catch(error => {
        console.error('Error testing webhook:', error);
        statusDiv.innerHTML = `
            <div class="webhook-error">
                <span class="webhook-icon">✗</span>
                <span>Webhook test failed: ${error.message}</span>
            </div>
        `;
    });
}

// Save a setting value to the server
function saveSettingValue(settingName, value, callback) {
    // Show loading state
    const messageId = `settings-message-${settingName.replace(/_/g, '-')}`;
    showSettingMessage(messageId, 'Saving...', 'info');
    
    // Get CSRF token
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
    
    // Send update request
    fetch(`/settings/update/${currentChatbotId}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({
            setting: settingName,
            value: value
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Update local settings
            currentSettings[settingName] = value;
            
            // Show success message
            showSettingMessage(messageId, 'Saved successfully!', 'success');
            
            // Call callback if provided
            if (typeof callback === 'function') {
                callback();
            }
        } else {
            showSettingMessage(messageId, 'Error: ' + (data.error || 'Unknown error'), 'error');
        }
    })
    .catch(error => {
        console.error('Error saving setting:', error);
        showSettingMessage(messageId, 'Error: ' + error.message, 'error');
    });
}

// Show a message in the settings form
function showSettingMessage(elementId, message, type = 'info') {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    element.className = 'settings-message ' + type;
    element.textContent = message;
    
    // Clear success/info messages after 3 seconds
    if (type === 'success' || type === 'info') {
        setTimeout(() => {
            element.textContent = '';
            element.className = 'settings-message';
        }, 3000);
    }
}

// Show error message
function showError(message) {
    const contentArea = document.querySelector('.settings-content-area');
    if (contentArea) {
        contentArea.innerHTML = `
            <div class="settings-error">
                <p>${message}</p>
            </div>
        `;
    }
}
