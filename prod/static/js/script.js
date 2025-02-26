// Form Processing
document.getElementById('urlForm').addEventListener('submit', function(event) {
    // Show the processing overlay
    document.getElementById('processingOverlay').style.display = 'flex';
});

// Hamburger Menu Functionality
function toggleMobileMenu() {
    const navContainer = document.querySelector('.nav-container');
    const navLinks = document.querySelector('.nav-links');
    
    navContainer.classList.toggle('mobile-active');
    
    // If menu is now active, show the links
    if (navContainer.classList.contains('mobile-active')) {
        navLinks.style.display = 'flex';
    } else {
        // Add a small delay to hide the links for smooth transition
        setTimeout(() => {
            navLinks.style.display = 'none';
        }, 300);
    }
}

// FAQ Accordion Functionality
document.addEventListener('DOMContentLoaded', () => {
    const faqItems = document.querySelectorAll('.faq-item');

    faqItems.forEach(item => {
        const question = item.querySelector('.faq-question');
        const answer = item.querySelector('.faq-answer');

        question.addEventListener('click', () => {
            const isOpen = question.classList.contains('active');

            // Close all FAQ items first
            faqItems.forEach(otherItem => {
                const otherQuestion = otherItem.querySelector('.faq-question');
                const otherAnswer = otherItem.querySelector('.faq-answer');
                
                otherQuestion.classList.remove('active');
                otherAnswer.style.display = 'none';
            });

            // If the clicked item wasn't open, open it
            if (!isOpen) {
                question.classList.add('active');
                answer.style.display = 'block';
            }
        });
    });
});

// Scroll to URL input function for "Create My Chatbot" button
function scrollToHeroInput() {
    const heroInput = document.querySelector('.hero-input');
    heroInput.scrollIntoView({ behavior: 'smooth' });
}