document.addEventListener('DOMContentLoaded', function() {
    console.log("DOM fully loaded and parsed");
    
    // Find all buttons with the required data attributes
    const buttons = document.querySelectorAll('[data-window-closed-time][data-part-id]');
    
    buttons.forEach(function(button) {
        console.log("Processing button for part");
        
        const windowClosedTime = button.getAttribute('data-window-closed-time');
        if (!windowClosedTime) return; // Skip if no window closed time
        
        const partId = button.getAttribute('data-part-id');
        const closedTime = new Date(windowClosedTime);
        const unlockTime = new Date(closedTime.getTime() + (5*60 * 1000)); // Add 5 minutes
        
        function updateCountdown() {
            const now = new Date();
            const timeRemaining = unlockTime - now;
            
            if (timeRemaining <= 0) {
                // Time has passed, enable the button
                button.disabled = false;
                button.classList.remove('disabled');
                button.textContent = 'Last attempt';
                // Stop the interval once time is up
                clearInterval(countdownInterval);
            } else {
                // Still waiting, update countdown
                const hours = Math.floor(timeRemaining / (1000 * 60 * 60));
                const minutes = Math.floor((timeRemaining % (1000 * 60 * 60)) / (1000 * 60));
                const seconds = Math.floor((timeRemaining % (1000 * 60)) / 1000);
                
                const countdownElement = document.getElementById('countdown-' + partId);
                if (countdownElement) {
                    countdownElement.textContent = `${hours}h ${minutes}m ${seconds}s`;
                }
            }
        }
        
        // Update immediately and then every second
        updateCountdown();
        const countdownInterval = setInterval(updateCountdown, 1000);
    });
});