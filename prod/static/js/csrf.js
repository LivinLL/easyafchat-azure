// Add this JavaScript function to your main JavaScript file or where you handle AJAX requests
// This sets up CSRF protection for all AJAX requests

function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]').getAttribute('content');
}

// Add a global AJAX setup for jQuery if you're using it
if (typeof $ !== 'undefined') {
    $.ajaxSetup({
        beforeSend: function(xhr, settings) {
            if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(settings.type) && !this.crossDomain) {
                xhr.setRequestHeader("X-CSRFToken", getCsrfToken());
            }
        }
    });
}

// For fetch API requests (if not using jQuery)
async function fetchWithCsrf(url, options = {}) {
    // Default to POST if method not specified
    const method = options.method || 'POST';
    
    // Only add CSRF token for state-changing requests
    if (!/^(GET|HEAD|OPTIONS|TRACE)$/i.test(method)) {
        options.headers = {
            ...options.headers,
            'X-CSRFToken': getCsrfToken()
        };
    }
    
    return fetch(url, options);
}
