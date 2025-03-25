(function() {
    // Check for configuration - note the SUPPORT-specific config object name
    if (!window.davesEasySupportChatConfig || !window.davesEasySupportChatConfig.chatbotId) {
        console.error('DavesEasySupportChatConfig: Missing required configuration');
        return;
    }

    // Store current script reference and config
    const currentScript = document.currentScript;
    const config = window.davesEasySupportChatConfig;

    // Check if we should proceed with initialization or wait
    if (!config.readyToLoad && config.waitForProcessing) {
        console.log('Support chatbot initialization delayed until processing completes');
        return;
    }

    // Get the base URL where the script is hosted
    const baseUrl = config.baseUrl || currentScript.src.split('/static/js/')[0];
        
    // Domain verification - First verify this site is authorized to use the support chatbot
    const verifyDomain = async function() {
        try {
            // Get current hostname
            const currentHostname = window.location.hostname;
            
            // Skip verification for localhost during development
            if (currentHostname === 'localhost' || 
                currentHostname === '127.0.0.1' || 
                currentHostname.endsWith('.local')) {
                console.log('DavesEasyChat Support: Running on localhost, skipping domain verification');
                return true;
            }
            
            // Skip verification for the app's own domain (allowing the demo page to work)
            const scriptHostname = new URL(baseUrl).hostname;
            if (currentHostname === scriptHostname) {
                console.log('DavesEasyChat Support: Running on app domain, skipping domain verification');
                return true;
            }
            
            // Verify with the server
            const response = await fetch(`${baseUrl}/verify-support-domain`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    domain: currentHostname
                })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                console.error(`DavesEasyChat Support: Domain verification failed - ${errorData.error}`);
                return false;
            }
            
            const result = await response.json();
            return result.authorized === true;
            
        } catch (error) {
            console.error('DavesEasyChat Support: Domain verification error -', error);
            return false;
        }
    };

    // Begin initialization by first verifying domain
    verifyDomain().then(isAuthorized => {
        if (!isAuthorized) {
            console.error('DavesEasyChat Support: This domain is not authorized to use this chatbot');
            
            // Optional: Show a small error message instead of the chat
            const errorDiv = document.createElement('div');
            errorDiv.style.cssText = 'position:fixed; bottom:20px; right:20px; background-color:#f8d7da; color:#721c24; padding:10px; border-radius:4px; font-family:sans-serif; font-size:12px; z-index:9999; max-width:300px;';
            errorDiv.textContent = 'This domain is not authorized to use the GoEasyChat support bot.';
            document.body.appendChild(errorDiv);
            
            // Remove error after 10 seconds
            setTimeout(() => {
                if (errorDiv.parentNode) {
                    errorDiv.parentNode.removeChild(errorDiv);
                }
            }, 10000);
            
            return;
        }
        
        // Domain is authorized - continue with normal initialization
        initializeMarkedAndChatbot();
    });

// Function to initialize marked library and chatbot
function initializeMarkedAndChatbot() {
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

        // Load main CSS - All classes prefixed with "support-" to avoid conflicts
        const style = document.createElement('style');
        // Check if this is the demo page
        const isDemoPage = window.location.pathname.includes('/demo/');
        style.textContent = `
            .support-chat-window {
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

            .support-chat-window .support-card-header {
                background-color: #f3f5f7 !important;
                border-bottom: 1px solid #e9ecef !important;
                padding: 1rem !important;
                display: flex !important;
                justify-content: space-between !important;
                align-items: center !important;
            }

            /* Bottom align */
            .support-chat-window .support-card-header > div:last-child {
                display: flex !important;
                align-items: flex-end !important; /* Change from center to flex-end */
                /* background-color: #e0f7fa !important; */ /* Light blue background */
                padding: 5px !important;
                border-radius: 4px !important;
            }

            .support-chat-window .support-card-body {
                flex: 1 !important;
                overflow-y: auto !important;
                padding: 1rem !important;
                background-color: white !important;
            }

            .support-chat-window .support-card-footer {
                background-color: #f3f5f7 !important;
                border-top: 1px solid #e9ecef !important;
                padding: 1rem !important;
            }

            @media (max-width: 767px) {
                .support-chat-window {
                    width: 90%;
                    right: 5%;
                    height: 95vh;
                    max-height: 600px;
                    bottom: 20px;
                }

                .support-chat-window #support-close-chat {
                    font-size: 24px !important;
                }

                #support-reset-chat svg {
                    width: 20px !important;
                    height: 20px !important;
                }
            }

            .support-chat-bubble {
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

            .support-chat-bubble:hover {
                transform: scale(1.1);
            }

            .support-chat-bubble.active {
                transform: scale(0.9);
            }

            #support-chat-messages {
                display: flex !important;
                flex-direction: column !important;
                gap: 1rem !important;
            }

            .support-chat-message {
                margin-bottom: 1rem !important;
                padding: 0.75rem 1rem !important;
                border-radius: 12px !important;
                max-width: 80% !important;
                position: relative !important;
                text-align: left !important;
            }

            .support-chat-message.assistant {
                background-color: #e9ecef !important;
                margin-right: auto !important;
                margin-left: 0 !important;
                padding-left: 2.5rem !important;
                color: #212529 !important;
            }

            .support-chat-message.assistant::before {
                content: '';
                position: absolute !important;
                left: 0.5rem !important;
                top: 0.5rem !important;
                width: 24px !important;
                height: 24px !important;
                background-image: url('https://res.cloudinary.com/dd19jhkar/image/upload/v1741958811/gtmxjoyfymndnxepoubl.png');
                background-size: cover !important;
                background-position: center !important;
                border-radius: 50% !important;
            }

            .support-chat-message.user {
                background-color: #0d6efd !important;
                margin-left: auto !important;
                margin-right: 0 !important;
                color: white !important;
            }

            .support-chat-input {
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

            .support-chat-input:focus {
                border-color: #6c757d !important;
                box-shadow: none !important;
                outline: 0 !important;
                background-color: white !important;
            }

            .support-chat-input::placeholder {
                font-size: 1.1rem !important;
            }

            .support-send-icon-btn {
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

            .support-input-wrapper {
                position: relative !important;
                width: 100% !important;
            }

            .support-button {
                background: none !important;
                border: none !important;
                padding: 0.375rem !important;
                cursor: pointer !important;
                color: #6c757d !important;
            }

            .support-button:hover {
                color: #212529 !important;
            }

            #support-close-chat {
                font-size: 16px !important;
            }

            .support-d-none {
                display: none !important;
            }

            /* Add markdown styling */
            .support-chat-message h1,
            .support-chat-message h2,
            .support-chat-message h3,
            .support-chat-message h4 {
                margin-top: 0.5rem !important;
                margin-bottom: 0.5rem !important;
                font-weight: 600 !important;
            }

            .support-chat-message p {
                margin-bottom: 0.5rem !important;
            }

            .support-chat-message ul,
            .support-chat-message ol {
                margin: 0.5rem 0 !important;
                padding-left: 1.5rem !important;
            }

            .support-chat-message li {
                margin-bottom: 0.25rem !important;
            }

            .support-chat-message code {
                background: rgba(0, 0, 0, 0.1) !important;
                padding: 0.2rem 0.4rem !important;
                border-radius: 0.25rem !important;
                font-family: monospace !important;
            }

            .support-chat-message pre {
                background: rgba(0, 0, 0, 0.1) !important;
                padding: 0.75rem !important;
                border-radius: 0.5rem !important;
                overflow-x: auto !important;
                margin: 0.5rem 0 !important;
            }

            /* Lead Form Styles */
            .support-lead-form {
                background-color: #f8f9fa !important;
                padding: 1rem !important;
                border-radius: 8px !important;
                margin: 0.5rem 0 !important;
                border: 1px solid #dee2e6 !important;
                max-width: 100% !important;
            }

            .support-lead-form h3 {
                margin-top: 0 !important;
                margin-bottom: 0.75rem !important;
                font-size: 1.1rem !important;
                color: #212529 !important;
            }

            .support-lead-form-field {
                margin-bottom: 0.75rem !important;
            }

            .support-lead-form-field input {
                width: 100% !important;
                padding: 0.5rem !important;
                border: 1px solid #ced4da !important;
                border-radius: 4px !important;
                font-size: 0.9rem !important;
            }

            .support-lead-form-field input:focus {
                outline: none !important;
                border-color: #80bdff !important;
                box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25) !important;
            }

            .support-lead-form-submit {
                background-color: #0d6efd !important;
                color: white !important;
                border: none !important;
                border-radius: 4px !important;
                padding: 0.5rem 1rem !important;
                cursor: pointer !important;
                font-size: 0.9rem !important;
                font-weight: 500 !important;
                transition: background-color 0.2s !important;
            }

            .support-lead-form-submit:hover {
                background-color: #0b5ed7 !important;
            }

            .support-lead-form-submit:disabled {
                background-color: #6c757d !important;
                cursor: not-allowed !important;
            }

            .support-lead-form-close {
                background: none !important;
                border: none !important;
                color: #6c757d !important;
                font-size: 0.8rem !important;
                margin-left: 0.5rem !important;
                cursor: pointer !important;
                text-decoration: underline !important;
            }

            .support-lead-form-close:hover {
                color: #495057 !important;
            }

            .support-lead-form-thanks {
                padding: 1rem !important;
                background-color: #d4edda !important;
                color: #155724 !important;
                border-radius: 4px !important;
                margin: 0.5rem 0 !important;
                text-align: center !important;
            }

            /* Initial popup with delay */
            .support-initial-popup {
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

            .support-initial-popup:after {
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
                .support-initial-popup {
                    left: auto;
                    right: 10px;
                    width: 200px;
                }
            }
        `;

        document.head.appendChild(style);

        // Create chat elements - all IDs and classes prefixed with "support-"
        const chatBubble = document.createElement('div');
        chatBubble.className = 'support-chat-bubble';
        chatBubble.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; width: 100%; height: 100%;">
                <svg width="55" height="55" viewBox="0 0 1120 1120" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path fill-rule="evenodd" clip-rule="evenodd" d="M252 434C252 372.144 302.144 322 364 322H770C831.856 322 882 372.144 882 434V614.459L804.595 585.816C802.551 585.06 800.94 583.449 800.184 581.405L763.003 480.924C760.597 474.424 751.403 474.424 748.997 480.924L711.816 581.405C711.06 583.449 709.449 585.06 707.405 585.816L606.924 622.997C600.424 625.403 600.424 634.597 606.924 637.003L707.405 674.184C709.449 674.94 711.06 676.551 711.816 678.595L740.459 756H629.927C629.648 756.476 629.337 756.945 628.993 757.404L578.197 825.082C572.597 832.543 561.403 832.543 555.803 825.082L505.007 757.404C504.663 756.945 504.352 756.476 504.073 756H364C302.144 756 252 705.856 252 644V434ZM633.501 471.462C632.299 468.212 627.701 468.212 626.499 471.462L619.252 491.046C618.874 492.068 618.068 492.874 617.046 493.252L597.462 500.499C594.212 501.701 594.212 506.299 597.462 507.501L617.046 514.748C618.068 515.126 618.874 515.932 619.252 516.954L626.499 536.538C627.701 539.788 632.299 539.788 633.501 536.538L640.748 516.954C641.126 515.932 641.932 515.126 642.954 514.748L662.538 507.501C665.788 506.299 665.788 501.701 662.538 500.499L642.954 493.252C641.932 492.874 641.126 492.068 640.748 491.046L633.501 471.462Z" fill="white"></path>
                    <path d="M771.545 755.99C832.175 755.17 881.17 706.175 881.99 645.545L804.595 674.184C802.551 674.94 800.94 676.551 800.184 678.595L771.545 755.99Z" fill="white"></path>
                </svg>            
            </div>
        `;

        const chatWindow = document.createElement('div');
        chatWindow.className = 'support-chat-window support-d-none';
        chatWindow.innerHTML = `
            <div class="support-card-header">
                <div style="display: flex; align-items: center;">
                    <div style="width: 28px; height: 28px; margin-right: 8px;">
                        <img src="https://res.cloudinary.com/dd19jhkar/image/upload/v1741958811/gtmxjoyfymndnxepoubl.png" 
                             alt="Agent d-A-v-I-d Avatar" 
                             style="width: 100%; height: 100%; border-radius: 50%;">
                    </div>
                    <span>GoEasyChat Support</span>
                </div>
                <div style="border: 0px solid red;">
                    <button type="button" class="support-button" id="support-reset-chat" title="Start Fresh">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"></path>
                            <path d="M21 3v5h-5"></path>
                            <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"></path>
                            <path d="M8 16H3v5"></path>
                        </svg>
                    </button>
                    <button type="button" class="support-button" id="support-close-chat">✕</button>
                </div>
            </div>
            <div class="support-card-body" id="support-chat-messages"></div>
            <div class="support-card-footer">
                <form id="support-chat-form">
                    <div class="support-input-wrapper">
                        <textarea class="support-chat-input" 
                                id="support-chat-input" 
                                placeholder="Your message..." 
                                required></textarea>
                                <button type="submit" class="support-button support-send-icon-btn">
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
            if (wasIsMobile !== isMobile && !chatWindow.classList.contains('support-d-none')) {
                mountPoint = isMobile ? document.body : desktopMountPoint;
                mountPoint.appendChild(chatWindow);
            }
        });

        // Initialize chat functionality
        let messages = [];
        let threadId = null;
        let hasShownLeadForm = false;
        let hasSubmittedLead = false;
        let initialQuestion = null;
        const messagesContainer = chatWindow.querySelector('#support-chat-messages');
        const chatForm = chatWindow.querySelector('#support-chat-form');
        const chatInput = chatForm.querySelector('textarea');
        const closeButton = chatWindow.querySelector('#support-close-chat');
        const resetButton = chatWindow.querySelector('#support-reset-chat');

        async function fetchLeadFormConfig() {
            try {
                console.log('Fetching lead form config for chatbot ID:', chatbotId);
                const response = await fetch(`${baseUrl}/config/lead-form/${chatbotId}`);
                if (!response.ok) {
                    console.log('Lead form config not found, using default');
                    return {
                        lead_form_title: 'Want us to reach out? Need to keep this chat going? Just fill out the info below.'
                    };
                }
                const config = await response.json();
                console.log('Lead form config received:', config);
                return config;
            } catch (error) {
                console.error('Error fetching lead form config:', error);
                return {
                    lead_form_title: 'Want us to reach out? Need to keep this chat going? Just fill out the info below.'
                };
            }
        }

        function createLeadForm() {
            console.log('createLeadForm called - fetching lead form config');
            
            // Disable the chat form while lead form is active
            const chatForm = document.getElementById('support-chat-form');
            chatForm.classList.add('support-d-none');
            
            // Fetch the lead form title from config
            fetchLeadFormConfig().then(config => {
                console.log('Lead form config received:', config);
                
                // Check if we should show the lead form at all
                if (config.show_lead_form === 'No') {
                    console.log('Lead form disabled by configuration');
                    hasShownLeadForm = true;
                    hasSubmittedLead = true; // Prevent showing the form later
                    return; // Exit without creating form
                }
                
                const leadFormDiv = document.createElement('div');
                leadFormDiv.className = 'support-lead-form';
                leadFormDiv.innerHTML = `
                    <h3>${config.lead_form_title}</h3>
                    <form id="support-lead-form">
                        <div class="support-lead-form-field">
                            <input type="text" id="support-lead-name" placeholder="Name" />
                        </div>
                        <div class="support-lead-form-field">
                            <input type="email" id="support-lead-email" placeholder="Email" />
                        </div>
                        <div class="support-lead-form-field">
                            <input type="tel" id="support-lead-phone" placeholder="Phone Number" />
                        </div>
                        <div style="display: flex; margin-top: 1rem;">
                            <button type="button" class="support-lead-form-submit">Submit</button>
                            <!-- Skip button commented out but kept for future use 
                            <button type="button" class="support-lead-form-close">Skip</button>
                            -->
                        </div>
                    </form>
                `;
                
                // Add the lead form to the chat
                messagesContainer.appendChild(leadFormDiv);
                // messagesContainer.scrollTop = messagesContainer.scrollHeight;
                console.log('Lead form added to messages container');
                
                // Handle form submission
                const leadFormSubmit = leadFormDiv.querySelector('.support-lead-form-submit');
                leadFormSubmit.addEventListener('click', handleLeadFormSubmit);
                
                // Handle skip button (commented out but kept for reference)
                /* 
                const skipButton = leadFormDiv.querySelector('.support-lead-form-close');
                skipButton.addEventListener('click', () => {
                    leadFormDiv.remove();
                    hasSubmittedLead = true; // Prevent showing the form again
                    chatForm.classList.remove('support-d-none'); // Re-enable chat input
                    console.log('Lead form skipped');
                });
                */
                
                hasShownLeadForm = true;
                console.log('hasShownLeadForm set to true');
            }).catch(error => {
                console.error('Error in fetchLeadFormConfig:', error);
                // Re-enable chat form in case of error
                chatForm.classList.remove('support-d-none');
            });
        }

        async function handleLeadFormSubmit(e) {
            e.preventDefault();
            console.log('Lead form submit handler called');
            
            const nameInput = document.getElementById('support-lead-name');
            const emailInput = document.getElementById('support-lead-email');
            const phoneInput = document.getElementById('support-lead-phone');
            
            const name = nameInput.value.trim();
            const email = emailInput.value.trim();
            const phone = phoneInput.value.trim();
            
            console.log('Lead form data:', { name, email, phone });
            
            // Validate name (not empty and at least 2 characters)
            if (!name || name.length < 2) {
                alert('Please enter a valid name (at least 2 characters)');
                nameInput.focus();
                return;
            }
            
            // Validate email (simple pattern check)
            if (email) {
                const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
                if (!emailPattern.test(email)) {
                    alert('Please enter a valid email address');
                    emailInput.focus();
                    return;
                }
            } else {
                alert('Please enter your email address');
                emailInput.focus();
                return;
            }
            
            // Validate phone (optional, but if provided must be at least 7 digits)
            if (phone) {
                // Remove non-digit characters to count actual digits
                const digits = phone.replace(/\D/g, '');
                if (digits.length < 7) {
                    alert('Please enter a valid phone number (at least 7 digits)');
                    phoneInput.focus();
                    return;
                }
            }
            
            try {
                console.log('Submitting lead data with thread ID:', threadId);
                const leadData = {
                    chatbot_id: chatbotId,
                    thread_id: threadId,
                    name,
                    email,
                    phone,
                    initial_question: initialQuestion
                };
                console.log('Sending lead form data:', leadData);
                
                const response = await fetch(`${baseUrl}/embed-save-lead`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(leadData)
                });
                
                if (!response.ok) throw new Error('Failed to save lead');
                
                const result = await response.json();
                console.log('Lead submission response:', result);
                
                // Replace form with thank you message
                const leadForm = document.querySelector('.support-lead-form');
                const thankYouDiv = document.createElement('div');
                thankYouDiv.className = 'support-lead-form-thanks';
                thankYouDiv.textContent = 'Thank you! We have received your information.';
                
                if (leadForm) {
                    leadForm.parentNode.replaceChild(thankYouDiv, leadForm);
                    console.log('Lead form replaced with thank you message');
                    
                    // Re-enable chat form after successful submission
                    const chatForm = document.getElementById('support-chat-form');
                    chatForm.classList.remove('support-d-none');
                    
                    // Remove the thank you message after a few seconds
                    setTimeout(() => {
                        if (thankYouDiv.parentNode) {
                            thankYouDiv.parentNode.removeChild(thankYouDiv);
                            console.log('Thank you message removed');
                        }
                    }, 5000);
                }
                
                hasSubmittedLead = true;
                console.log('hasSubmittedLead set to true');
                
            } catch (error) {
                console.error('Error saving lead:', error);
                alert('Sorry, there was an error saving your information. Please try again.');
                
                // Re-enable chat form even on error to prevent users from being stuck
                const chatForm = document.getElementById('support-chat-form');
                chatForm.classList.remove('support-d-none');
            }
        }

        function addMessage(message, role) {
            console.log(`Adding ${role} message:`, message.substring(0, 50) + (message.length > 50 ? '...' : ''));
            const messageDiv = document.createElement('div');
            messageDiv.className = `support-chat-message ${role}`;
            
            // Sanitize HTML if it's from the assistant and using markdown
            if (role === 'assistant') {
                // Load DOMPurify if it's not already loaded
                if (typeof DOMPurify === 'undefined') {
                    const script = document.createElement('script');
                    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.5/purify.min.js';
                    document.head.appendChild(script);
                    
                    // Set content after DOMPurify loads
                    script.onload = function() {
                        const sanitizedHTML = DOMPurify.sanitize(marked.parse(message));
                        messageDiv.innerHTML = sanitizedHTML;
                    };
                    
                    // Fallback in case DOMPurify fails to load
                    script.onerror = function() {
                        console.warn('Failed to load DOMPurify, falling back to basic escaping');
                        messageDiv.innerHTML = marked.parse(message);
                    };
                } else {
                    // DOMPurify is already loaded
                    const sanitizedHTML = DOMPurify.sanitize(marked.parse(message));
                    messageDiv.innerHTML = sanitizedHTML;
                }
            } else {
                // User messages don't use markdown
                messageDiv.innerHTML = message;
            }
            
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            messages.push({ role, content: message });
            
            // If this is the first exchange (one user message and one assistant message)
            // and we haven't shown the lead form, show it now
            if (
                messages.length === 3 && 
                role === 'assistant' && 
                !hasShownLeadForm && 
                !hasSubmittedLead
            ) {
                console.log('Showing lead form after first exchange - local message count =', messages.length);
                createLeadForm();
            } else {
                console.log('Lead form conditions not met:', {
                    'local messages.length': messages.length,
                    'hasShownLeadForm': hasShownLeadForm,
                    'hasSubmittedLead': hasSubmittedLead
                });
            }
            
            console.log(`Total messages in conversation: ${messages.length}`);
        }

        // Function to show initial popup message with delay
        function showInitialPopup(delay = 2000) {
            // Only show if enabled in config (default to true if not specified)
            if (config.showInitialMessage === false) return;
            
            // Default message or custom message from config
            const initialMessage = config.initialMessage || "GoEasyChat here! 👋 How can I help you?";
            
            // Create popup element
            const popup = document.createElement('div');
            popup.className = 'support-initial-popup';
            popup.innerHTML = initialMessage;
            popup.id = 'support-initial-popup'; // Add ID for easy reference
            
            // Add to DOM but hidden first
            chatBubble.appendChild(popup);
            
            // Show with delay and animation
            setTimeout(() => {
                popup.style.opacity = '1';
            }, delay);
        }

        // Add event listeners
        chatBubble.addEventListener('click', () => {
            console.log('Chat bubble clicked');
            
            // Hide the popup if it exists
            const popup = document.getElementById('support-initial-popup');
            if (popup) {
                popup.style.opacity = '0';
                setTimeout(() => {
                    if (popup.parentNode === chatBubble) {
                        chatBubble.removeChild(popup);
                    }
                }, 300);
            }

            if (isMobile && chatWindow.classList.contains('support-d-none')) {
                // Move window to body before showing it on mobile
                document.body.appendChild(chatWindow);
                mountPoint = document.body;
                console.log('Chat window moved to body for mobile');
            }
            
            // Toggle visibility
            if (chatWindow.classList.contains('support-d-none')) {
                chatWindow.classList.remove('support-d-none');
                chatBubble.classList.add('active');
                console.log('Chat window opened');
            } else {
                chatWindow.classList.add('support-d-none');
                chatBubble.classList.remove('active');
                console.log('Chat window closed');
            }
            
            if (messages.length === 0) {
                addMessage("GoEasyChat here! 👋 How can I help you?", 'assistant');
                console.log('Added initial assistant greeting');
            }
        });

        closeButton.addEventListener('click', () => {
            chatWindow.classList.add('support-d-none');
            chatBubble.classList.remove('active');
        });

        // Fixed chat submit handler with proper user message anchoring
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const message = chatInput.value.trim();
            if (!message) return;

            // If this is the first user message, store it and create a thread ID
            if (messages.length <= 1) {
                initialQuestion = message;
                threadId = `support_thread_${Date.now()}`;
                console.log('First user message. Thread ID:', threadId, 'Initial question:', initialQuestion);
            }

            // Clear any previous markers to avoid conflicts
            const previousMarkers = messagesContainer.querySelectorAll('[data-current-question="true"]');
            previousMarkers.forEach(el => el.removeAttribute('data-current-question'));
            
            addMessage(message, 'user');
            chatInput.value = '';
            chatInput.style.height = 'auto';

            // Find and mark the latest user message with a specific attribute
            const userMessages = messagesContainer.querySelectorAll('.support-chat-message.user');
            const lastUserMessage = userMessages[userMessages.length - 1];
            lastUserMessage.setAttribute('data-current-question', 'true');

            // Create a simple animated dots display
            const thinkingDiv = document.createElement('div');
            thinkingDiv.className = 'support-chat-message assistant thinking';
            
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
                console.log('Sending chat request:', {
                    message,
                    chatbot_id: chatbotId,
                    thread_id: threadId
                });
                
                const response = await fetch(`${baseUrl}/embed-chat`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message,
                        chatbot_id: chatbotId,
                        thread_id: threadId
                    })
                });

                // Clear interval and remove thinking indicator
                clearInterval(dotAnimation);
                messagesContainer.removeChild(thinkingDiv);

                if (!response.ok) throw new Error('Failed to get response');

                const data = await response.json();
                console.log('Received chat response:', data);
                
                // Update thread ID if provided in the response
                if (data.thread_id) {
                    threadId = data.thread_id;
                    console.log('Updated thread ID:', threadId);
                }
                
                // Create assistant message container
                const assistantMessageDiv = document.createElement('div');
                assistantMessageDiv.className = 'support-chat-message assistant';
                messagesContainer.appendChild(assistantMessageDiv);
                
                // Calculate a fixed top padding to position the container
                const cardBodyPadding = 16; // Standard padding value in the card-body
                
                // Function to ensure the user message is fixed at top
                function ensureUserMessageAtTop() {
                    // Find the marked user message (latest question)
                    const currentUserMessage = messagesContainer.querySelector('.support-chat-message.user[data-current-question="true"]');
                    
                    if (currentUserMessage) {
                        // Calculate top offset (accounting for card-body padding)
                        const desiredTop = cardBodyPadding;
                        
                        // Get current position
                        const rect = currentUserMessage.getBoundingClientRect();
                        const containerRect = messagesContainer.getBoundingClientRect();
                        
                        // Calculate the difference from desired position
                        const currentTopOffset = rect.top - containerRect.top;
                        
                        // Calculate how much we need to scroll to position message at top with padding
                        const scrollAdjustment = currentTopOffset - desiredTop;
                        
                        // Apply the scroll adjustment
                        messagesContainer.scrollTop += scrollAdjustment;
                    }
                }
                
                // Get the full response text
                const fullText = data.response;

                // Add to messages array right away
                messages.push({ role: 'assistant', content: fullText });

                // Make sure we display the user message at the top
                const ensureUserMessageVisible = () => {
                    // Find the marked user message (latest question)
                    const currentUserMessage = messagesContainer.querySelector('.support-chat-message.user[data-current-question="true"]');
                    
                    if (currentUserMessage) {
                        // Calculate top offset (accounting for card-body padding)
                        const desiredTop = cardBodyPadding;
                        
                        // Get current position
                        const rect = currentUserMessage.getBoundingClientRect();
                        const containerRect = messagesContainer.getBoundingClientRect();
                        
                        // Calculate the difference from desired position
                        const currentTopOffset = rect.top - containerRect.top;
                        
                        // Calculate how much we need to scroll to position message at top with padding
                        const scrollAdjustment = currentTopOffset - desiredTop;
                        
                        // Apply the scroll adjustment
                        messagesContainer.scrollTop += scrollAdjustment;
                    }
                };

                // Create a reference for our interval so we can clear it later
                let typeInterval = null;

                // Display the full response at once instead of typing it out
                const typeNextChunk = () => {
                    // Add the full text immediately
                    displayedText = fullText;
                    
                    // Handle markdown rendering with sanitization
                    if (typeof DOMPurify !== 'undefined') {
                        // DOMPurify is already loaded, use it
                        assistantMessageDiv.innerHTML = DOMPurify.sanitize(marked.parse(displayedText));
                    } else {
                        // Load DOMPurify if not available
                        const script = document.createElement('script');
                        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.5/purify.min.js';
                        document.head.appendChild(script);
                        
                        script.onload = function() {
                            assistantMessageDiv.innerHTML = DOMPurify.sanitize(marked.parse(displayedText));
                            // Make sure the user message stays at the top
                            ensureUserMessageVisible();
                        };
                        
                        script.onerror = function() {
                            // Fallback if DOMPurify fails to load
                            console.warn('Failed to load DOMPurify, falling back to basic parsing');
                            assistantMessageDiv.innerHTML = marked.parse(displayedText);
                            // Make sure the user message stays at the top
                            ensureUserMessageVisible();
                        };
                    }
                    
                    // Make sure the user message stays at the top
                    ensureUserMessageVisible();
                    
                    // Start a short interval to maintain position during any markdown rendering or image loading
                    typeInterval = setInterval(ensureUserMessageVisible, 100);
                    
                    // Clear the interval after a short time once everything is stable
                    setTimeout(() => {
                        if (typeInterval) {
                            clearInterval(typeInterval);
                        }
                        
                        // Final position adjustment to ensure user message is at top
                        ensureUserMessageVisible();
                        
                        // Check if we should show lead form
                        if (messages.length === 3 && !hasShownLeadForm && !hasSubmittedLead) {
                            console.log('Showing lead form after first exchange - local message count =', messages.length);
                            createLeadForm();
                        }
                    }, 500); // Short delay to ensure everything is rendered properly
                };
               
                // Start the typing simulation
                typeNextChunk();
                
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

        // Restore Enter key functionality
        chatInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                chatForm.dispatchEvent(new Event('submit'));
            }
        });

        // Fix for mobile input visibility when keyboard appears
        chatInput.addEventListener('focus', function(event) {
            console.log('Input field focused - applying fixed lift amount');
            if (isMobile) {
                // Prevent the underlying page from scrolling
                if (event) event.preventDefault();
                
                // Reset any existing transform first to prevent stacking
                chatWindow.style.transform = '';
                
                // Small delay to ensure the reset is processed before applying new transform
                setTimeout(() => {
                    // Then apply a fixed transformation to lift the chat window
                    chatWindow.style.transform = 'translateY(-200px)';
                    
                    // Still do a gentle scroll to ensure input is visible
                    chatInput.scrollIntoView({ behavior: 'smooth', block: 'end' });
                }, 50);
                
                // Reset position after blur
                chatInput.addEventListener('blur', function onBlur() {
                    chatWindow.style.transform = '';
                    chatInput.removeEventListener('blur', onBlur);
                }, { once: true });
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
                console.log('Resetting chat for chatbot ID:', chatbotId);
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
                console.log('Chat reset successful');

                messages = [];
                threadId = `support_thread_${Date.now()}`; // Generate new thread ID
                console.log('New thread ID generated:', threadId);
                hasShownLeadForm = false;
                hasSubmittedLead = false;
                initialQuestion = null;
                console.log('Lead form state reset');
                messagesContainer.innerHTML = '';
                addMessage("GoEasyChat here! 👋 How can I help you?", 'assistant');
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
}
})();