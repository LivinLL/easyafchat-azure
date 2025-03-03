(function() {
    // Check for configuration
    if (!window.davesEasyChatConfig || !window.davesEasyChatConfig.chatbotId) {
        console.error('DavesEasyChatConfig: Missing required configuration');
        return;
    }

    // Store current script reference and config
    const currentScript = document.currentScript;
    const config = window.davesEasyChatConfig;

    // Check if we should proceed with initialization or wait
    // This allows us to delay initialization until Pinecone processing is complete
    if (!config.readyToLoad && config.waitForProcessing) {
        console.log('Chatbot initialization delayed until processing completes');
        return;
    }

    // Load marked library
    const markedScript = document.createElement('script');
    markedScript.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
    markedScript.onload = function() {
        // Initialize marked
        marked.setOptions({
            headerIds: false,
            mangle: false
        });

        const chatbotId = config.chatbotId;
        const baseUrl = config.baseUrl || currentScript.src.split('/static/js/')[0];
        let isMobile = window.innerWidth <= 767;
        const desktopMountPoint = config.mountTo ? document.querySelector(config.mountTo) : document.body;
        let mountPoint = desktopMountPoint;

        // First inject any mount-specific styles
        if (config.mountTo && !isMobile) {
            const mountStyle = document.createElement('style');
            mountStyle.textContent = `
                ${config.mountTo} {
                    position: relative !important;
                }
            `;
            document.head.appendChild(mountStyle);
        }

        // Load main CSS
        const style = document.createElement('style');
        // Check if this is the demo page
        const isDemoPage = window.location.pathname.includes('/demo/');
        style.textContent = `
            .daves-chat-window {
                position: ${config.mountTo ? 'absolute' : 'fixed'};
                bottom: 100px;
                right: 20px;
                width: 400px;
                height: ${isDemoPage && config.mountTo ? '500px' : '80vh'}; 
                max-height: ${isDemoPage && config.mountTo ? '500px' : '800px'};
                border-radius: 12px;
                box-shadow: 0 0 20px rgba(0, 0, 0, 0.1);
                display: flex !important;
                flex-direction: column !important;
                transition: all 0.3s ease;
                z-index: ${isDemoPage ? '9999999' : '999999'};
                overflow: hidden;
                background-color: white !important;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
            }

            .daves-chat-window .card-header {
                background-color: #f3f5f7 !important;
                border-bottom: 1px solid #e9ecef !important;
                padding: 1rem !important;
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
            }

            /* Bottom align */
            .daves-chat-window .card-header > div:last-child {
                display: flex !important;
                align-items: flex-end !important; /* Change from center to flex-end */
                /* background-color: #e0f7fa !important; */ /* Light blue background */
                padding: 5px !important;
                border-radius: 4px !important;
            }

            .daves-chat-window .card-body {
                flex: 1 !important;
                overflow-y: auto !important;
                padding: 1rem !important;
                background-color: white !important;
            }

            .daves-chat-window .card-footer {
                background-color: #f3f5f7 !important;
                border-top: 1px solid #e9ecef !important;
                padding: 1rem !important;
            }

            @media (max-width: 767px) {
                .daves-chat-window {
                    width: 90%;
                    right: 5%;
                    height: 95vh;
                    max-height: 600px;
                    bottom: 20px;
                }

                .daves-chat-window #daves-close-chat {
                    font-size: 24px !important;
                }

                #daves-reset-chat svg {
                    width: 20px !important;
                    height: 20px !important;
                }
            }

            .daves-chat-bubble {
                position: ${config.mountTo ? 'absolute' : 'fixed'};
                bottom: 20px;
                right: 20px;
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background-color: #0d6efd !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                cursor: pointer;
                transition: transform 0.3s ease;
                z-index: 999999;
                box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
            }

            .daves-chat-bubble:hover {
                transform: scale(1.1);
            }

            .daves-chat-bubble.active {
                transform: scale(0.9);
            }

            #daves-chat-messages {
                display: flex !important;
                flex-direction: column !important;
                gap: 1rem !important;
            }

            .daves-chat-message {
                margin-bottom: 1rem !important;
                padding: 0.75rem 1rem !important;
                border-radius: 12px !important;
                max-width: 80% !important;
                position: relative !important;
                text-align: left !important;
            }

            .daves-chat-message.assistant {
                background-color: #e9ecef !important;
                margin-right: auto !important;
                margin-left: 0 !important;
                padding-left: 2.5rem !important;
                color: #212529 !important;
            }

            .daves-chat-message.assistant::before {
                content: '';
                position: absolute !important;
                left: 0.5rem !important;
                top: 0.5rem !important;
                width: 24px !important;
                height: 24px !important;
                background-image: url('https://res.cloudinary.com/dd19jhkar/image/upload/v1735504762/enfadxyhjtjkwdivbuw4.png');
                background-size: cover !important;
                background-position: center !important;
                border-radius: 50% !important;
            }

            .daves-chat-message.user {
                background-color: #0d6efd !important;
                margin-left: auto !important;
                margin-right: 0 !important;
                color: white !important;
            }

            .daves-chat-input {
                width: 85% !important;
                padding: 0.5rem 0.75rem !important;
                padding-right: 45px !important;
                border: 1px solid #dee2e6 !important;
                border-radius: 6px !important;
                background-color: white !important;
                color: #212529 !important;
                resize: none !important;
                min-height: 40px !important;
                line-height: 1.5 !important;
                font-size: 1rem !important;
            }

            .daves-chat-input:focus {
                border-color: #6c757d !important;
                box-shadow: none !important;
                outline: 0 !important;
                background-color: white !important;
            }

            .daves-chat-input::placeholder {
                font-size: 1.1rem !important;
            }

            .send-icon-btn {
                position: absolute !important;
                right: 0 !important;
                top: 50% !important;
                transform: translateY(-50%) !important;
                padding: 6px !important;
                background: none !important;
                border: none !important;
                color: #495057 !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                cursor: pointer !important;
            }

            .input-wrapper {
                position: relative !important;
                width: 100% !important;
            }

            .daves-button {
                background: none !important;
                border: none !important;
                padding: 0.375rem !important;
                cursor: pointer !important;
                color: #6c757d !important;
            }

            .daves-button:hover {
                color: #212529 !important;
            }

            #daves-close-chat {
                font-size: 16px !important;
            }

            .d-none {
                display: none !important;
            }

            /* Add markdown styling */
            .daves-chat-message h1,
            .daves-chat-message h2,
            .daves-chat-message h3,
            .daves-chat-message h4 {
                margin-top: 0.5rem !important;
                margin-bottom: 0.5rem !important;
                font-weight: 600 !important;
            }

            .daves-chat-message p {
                margin-bottom: 0.5rem !important;
            }

            .daves-chat-message ul,
            .daves-chat-message ol {
                margin: 0.5rem 0 !important;
                padding-left: 1.5rem !important;
            }

            .daves-chat-message li {
                margin-bottom: 0.25rem !important;
            }

            .daves-chat-message code {
                background: rgba(0, 0, 0, 0.1) !important;
                padding: 0.2rem 0.4rem !important;
                border-radius: 0.25rem !important;
                font-family: monospace !important;
            }

            .daves-chat-message pre {
                background: rgba(0, 0, 0, 0.1) !important;
                padding: 0.75rem !important;
                border-radius: 0.5rem !important;
                overflow-x: auto !important;
                margin: 0.5rem 0 !important;
            }

            /* Initial popup with delay */
            .daves-initial-popup {
                position: absolute;
                top: -10px;
                left: -240px;
                width: 240px;
                padding: 10px 15px;
                background-color: white;
                border: 1px solid #e9ecef;
                border-radius: 8px;
                box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1);
                transform: translateY(-100%);
                opacity: 0;
                transition: opacity 0.3s ease;
                z-index: 999998;
                font-size: 14px;
                text-align: left;
                color: #333;
            }

            .daves-initial-popup:after {
                content: "";
                position: absolute;
                bottom: -8px;
                right: 20px;
                width: 0;
                height: 0;
                border-left: 8px solid transparent;
                border-right: 8px solid transparent;
                border-top: 8px solid white;
            }

            @media (max-width: 767px) {
                .daves-initial-popup {
                    left: auto;
                    right: 10px;
                    width: 200px;
                }
            }
        `;

        document.head.appendChild(style);

        // Create chat elements
        const chatBubble = document.createElement('div');
        chatBubble.className = 'daves-chat-bubble';
        chatBubble.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; width: 100%; height: 100%;">
                <svg width="55" height="55" viewBox="0 0 1120 1120" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M252 434C252 372.144 302.144 322 364 322H770C831.856 322 882 372.144 882 434V614.459L804.595 585.816C802.551 585.06 800.94 583.449 800.184 581.405L763.003 480.924C760.597 474.424 751.403 474.424 748.997 480.924L711.816 581.405C711.06 583.449 709.449 585.06 707.405 585.816L606.924 622.997C600.424 625.403 600.424 634.597 606.924 637.003L707.405 674.184C709.449 674.94 711.06 676.551 711.816 678.595L740.459 756H629.927C629.648 756.476 629.337 756.945 628.993 757.404L578.197 825.082C572.597 832.543 561.403 832.543 555.803 825.082L505.007 757.404C504.663 756.945 504.352 756.476 504.073 756H364C302.144 756 252 705.856 252 644V434ZM633.501 471.462C632.299 468.212 627.701 468.212 626.499 471.462L619.252 491.046C618.874 492.068 618.068 492.874 617.046 493.252L597.462 500.499C594.212 501.701 594.212 506.299 597.462 507.501L617.046 514.748C618.068 515.126 618.874 515.932 619.252 516.954L626.499 536.538C627.701 539.788 632.299 539.788 633.501 536.538L640.748 516.954C641.126 515.932 641.932 515.126 642.954 514.748L662.538 507.501C665.788 506.299 665.788 501.701 662.538 500.499L642.954 493.252C641.932 492.874 641.126 492.068 640.748 491.046L633.501 471.462Z" fill="white"></path>
                    <path d="M771.545 755.99C832.175 755.17 881.17 706.175 881.99 645.545L804.595 674.184C802.551 674.94 800.94 676.551 800.184 678.595L771.545 755.99Z" fill="white"></path>
                </svg>            
            </div>
        `;

        const chatWindow = document.createElement('div');
        chatWindow.className = 'daves-chat-window d-none';
        chatWindow.innerHTML = `
            <div class="card-header">
                <div style="display: flex; align-items: center;">
                    <div style="width: 28px; height: 28px; margin-right: 8px;">
                        <img src="https://res.cloudinary.com/dd19jhkar/image/upload/v1735504762/enfadxyhjtjkwdivbuw4.png" 
                             alt="Agent d-A-v-I-d Avatar" 
                             style="width: 100%; height: 100%; border-radius: 50%;">
                    </div>
                    <span>Agent d-A-v-I-d</span>
                </div>
                <div style="border: 0px solid red;">
                    <button type="button" class="daves-button" id="daves-reset-chat" title="Start Fresh">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path>
                            <path d="M21 3v5h-5"></path>
                            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"></path>
                            <path d="M8 16H3v5"></path>
                        </svg>
                    </button>
                    <button type="button" class="daves-button" id="daves-close-chat">✕</button>
                </div>
            </div>
            <div class="card-body" id="daves-chat-messages"></div>
            <div class="card-footer">
                <form id="daves-chat-form">
                    <div class="input-wrapper">
                        <textarea class="daves-chat-input" 
                                id="daves-chat-input" 
                                placeholder="Your message..." 
                                required></textarea>
                                <button type="submit" class="daves-button send-icon-btn">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 20 20" fill="none" style="transform: rotate(0deg);">
                                        <title>Paper Plane</title>
                                        <path fill="currentColor" d="M15.44 1.68c.69-.05 1.47.08 2.13.74.66.67.8 1.45.75 2.14-.03.47-.15 1-.25 1.4l-.09.35a43.7 43.7 0 0 1-3.83 10.67A2.52 2.52 0 0 1 9.7 17l-1.65-3.03a.83.83 0 0 1 .14-1l3.1-3.1a.83.83 0 1 0-1.18-1.17l-3.1 3.1a.83.83 0 0 1-.99.14L2.98 10.3a2.52 2.52 0 0 1 .04-4.45 43.7 43.7 0 0 1 11.02-3.9c.4-.1.92-.23 1.4-.26Z"></path>
                                    </svg>
                                </button>
                    </div>
                </form>
            </div>
        `;

// Add elements to mount point
mountPoint.appendChild(chatBubble);
mountPoint.appendChild(chatWindow);

// Handle window resize for responsive mounting
window.addEventListener('resize', () => {
    const wasIsMobile = isMobile;
    isMobile = window.innerWidth <= 767;
    
    // Only remount if mobile state changed AND chat is open
    if (wasIsMobile !== isMobile && !chatWindow.classList.contains('d-none')) {
        mountPoint = isMobile ? document.body : desktopMountPoint;
        mountPoint.appendChild(chatWindow);
    }
});

// Initialize chat functionality
let messages = [];
const messagesContainer = chatWindow.querySelector('#daves-chat-messages');
const chatForm = chatWindow.querySelector('#daves-chat-form');
const chatInput = chatForm.querySelector('textarea');
const closeButton = chatWindow.querySelector('#daves-close-chat');
const resetButton = chatWindow.querySelector('#daves-reset-chat');

function addMessage(message, role) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `daves-chat-message ${role}`;
    messageDiv.innerHTML = role === 'assistant' ? marked.parse(message) : message;
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
    messages.push({ role, content: message });
}

// Function to show initial popup message with delay
function showInitialPopup(delay = 2000) {
    // Only show if enabled in config (default to true if not specified)
    if (config.showInitialMessage === false) return;
    
    // Default message or custom message from config
    const initialMessage = config.initialMessage || "Hi there! 👋 How can I help you?";
    
    // Create popup element
    const popup = document.createElement('div');
    popup.className = 'daves-initial-popup';
    popup.innerHTML = initialMessage;
    popup.id = 'daves-initial-popup'; // Add ID for easy reference
    
    // Add to DOM but hidden first
    chatBubble.appendChild(popup);
    
    // Show with delay and animation
    setTimeout(() => {
        popup.style.opacity = '1';
    }, delay);
}

// Add event listeners
chatBubble.addEventListener('click', () => {
    // Hide the popup if it exists
    const popup = document.getElementById('daves-initial-popup');
    if (popup) {
        popup.style.opacity = '0';
        setTimeout(() => {
            if (popup.parentNode === chatBubble) {
                chatBubble.removeChild(popup);
            }
        }, 300);
    }

    if (isMobile && chatWindow.classList.contains('d-none')) {
        // Move window to body before showing it on mobile
        document.body.appendChild(chatWindow);
        mountPoint = document.body;
    }
    chatWindow.classList.toggle('d-none');
    chatBubble.classList.toggle('active');
    if (messages.length === 0) {
        addMessage("Hi there! 👋 How can I help you?", 'assistant');
    }
});

closeButton.addEventListener('click', () => {
    chatWindow.classList.add('d-none');
    chatBubble.classList.remove('active');
});

// Updated submit handler for animated dots
// Updated submit handler with better dot positioning
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;

    addMessage(message, 'user');
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // Create a simple animated dots display
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'daves-chat-message assistant thinking';
    
    // Create dots with adjusted positioning to avoid overlapping with the agent icon
    thinkingDiv.innerHTML = `
        <div style="display: flex; align-items: center; justify-content: flex-end; padding: 0.5rem; margin-left: 0;">
            <span style="display: inline-block; width: 8px; height: 8px; margin: 0 4px; background-color: #6c757d; border-radius: 50%;"></span>
            <span style="display: inline-block; width: 8px; height: 8px; margin: 0 4px; background-color: #6c757d; border-radius: 50%;"></span>
            <span style="display: inline-block; width: 8px; height: 8px; margin: 0 4px; background-color: #6c757d; border-radius: 50%;"></span>
        </div>
    `;
    
    // Manually animate the dots with JavaScript for guaranteed compatibility
    const dots = thinkingDiv.querySelectorAll('span');
    let step = 0;
    
    const dotAnimation = setInterval(() => {
        // Reset all dots to normal
        dots.forEach(dot => {
            dot.style.opacity = '0.6';
            dot.style.transform = 'scale(1)';
        });
        
        // Highlight current dot
        dots[step].style.opacity = '1';
        dots[step].style.transform = 'scale(1.5)';
        
        // Move to next dot
        step = (step + 1) % 3;
    }, 400);
    
    messagesContainer.appendChild(thinkingDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    try {
        const response = await fetch(`${baseUrl}/embed-chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message,
                chatbot_id: chatbotId
            })
        });

        // Clear interval and remove thinking indicator
        clearInterval(dotAnimation);
        messagesContainer.removeChild(thinkingDiv);

        if (!response.ok) throw new Error('Failed to get response');

        const data = await response.json();
        addMessage(data.response, 'assistant');
    } catch (error) {
        // Clear interval and remove thinking indicator
        clearInterval(dotAnimation);
        if (thinkingDiv.parentNode === messagesContainer) {
            messagesContainer.removeChild(thinkingDiv);
        }
        console.error('Error:', error);
        addMessage('I apologize, but I encountered an error. Please try again.', 'assistant');
    }
});

// Enter key functionality
chatInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

// Fix for mobile input visibility when keyboard appears
chatInput.addEventListener('focus', function() {
    if (isMobile) {
        setTimeout(() => {
            window.scrollTo(0, 0);
            chatInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 100);
    }
});

// Auto-resize textarea
chatInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

// Reset chat functionality
resetButton.addEventListener('click', async () => {
    try {
        const response = await fetch(`${baseUrl}/embed-reset-chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                chatbot_id: chatbotId
            })
        });

        if (!response.ok) throw new Error('Failed to reset chat');

        messages = [];
        messagesContainer.innerHTML = '';
        addMessage("Hi there! 👋 How can I help you?", 'assistant');
    } catch (error) {
        console.error('Error resetting chat:', error);
    }
});

// Call the showInitialPopup function with a delay
setTimeout(() => {
    showInitialPopup();
}, 500); // Small initial delay to ensure everything is loaded
};

document.head.appendChild(markedScript);
})();