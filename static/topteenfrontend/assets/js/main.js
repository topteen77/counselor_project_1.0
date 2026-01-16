document.addEventListener('DOMContentLoaded', function () {
    const messages = document.querySelector('.django-messages');
    if (messages) {
        setTimeout(() => {
            messages.style.display = 'none';
        }, 5000); // Hide after 5 seconds
    }
});