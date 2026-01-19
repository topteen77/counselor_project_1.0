function updatePartStatus(partId) {
    // Detect base path from current URL to handle production subdirectory
    const currentPath = window.location.pathname;
    let basePath = '';
    
    // Check if we're in a subdirectory (e.g., /counselor_project/)
    if (currentPath.includes('/counselor_project/')) {
        basePath = '/counselor_project';
    }
    
    // Use the URL pattern defined in the template if available, otherwise construct it
    const urlPattern = typeof UPDATE_PART_STATUS_URL !== 'undefined' 
        ? `${UPDATE_PART_STATUS_URL}${partId}/` 
        : `${basePath}/update_part_status/${partId}/`;
    
    fetch(urlPattern, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken() // Include CSRF token
        },
        body: JSON.stringify({})
    })
    .then(response => {
        // Check if response is OK before parsing JSON
        if (!response.ok) {
            // Try to parse error response, but handle empty responses
            return response.text().then(text => {
                try {
                    return { success: false, message: JSON.parse(text).message || `Server error: ${response.status}` };
                } catch (e) {
                    return { success: false, message: `Server error: ${response.status} ${response.statusText}` };
                }
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
          let progressContainer = document.querySelector(`.progress-container[data-video-id="video-${partId}"]`);

          if (progressContainer) {
              let progressCircle = progressContainer.querySelector('.progress-circle');
              let tickIcon = progressContainer.querySelector('.tick');
              let tooltip = progressContainer.querySelector('.tooltip');
              let quizButton = document.getElementById(`quiz-${partId}`); // Get the quiz button (may not exist for Introduction)
              
              if (progressCircle && tickIcon && tooltip) {
                  // Animate the progress circle
                  progressCircle.style.strokeDasharray = '66'; // Adjust the value as needed
                  progressCircle.style.transition = 'stroke-dasharray 0.5s ease-in-out';

                  // Show the tick mark
                  tickIcon.style.display = 'block';

                  // Update tooltip text
                  tooltip.textContent = 'Progress: 100%';
                  
                  // Enable quiz button if it exists (not for Introduction parts)
                  if (quizButton) {
                      quizButton.classList.add('enabled');
                  }
              }
          }

          // Check if this is an Introduction part (no quiz button means it's likely Introduction)
          let quizButton = document.getElementById(`quiz-${partId}`);
          let isIntroduction = !quizButton;
          
          if (!isIntroduction) {
              // For non-Introduction parts: Hide content and show quiz
              let contentElement = document.getElementById(`content-${partId}`);
              if (contentElement) {
                  contentElement.style.display = 'none';
              }
              
              // Show the quiz content
              let quizContent = document.getElementById(`contentquiz-${partId}`);
              if (quizContent) {
                  quizContent.style.display = 'block';
                  
                  // Scroll to the quiz content
                  quizContent.scrollIntoView({ behavior: 'smooth' });
                  
                  // Update active button in the sidebar if applicable
                  let quizButtonElement = document.querySelector(`[data-target="contentquiz-${partId}"]`);
                  if (quizButtonElement) {
                      const buttons = document.querySelectorAll('.t-button');
                      buttons.forEach(btn => btn.classList.remove('active'));
                      quizButtonElement.classList.add('active');
                  }
              }
          } else {
              // For Introduction parts: Reload page to show updated completion status and Next button
              // Get course name from global variable or current URL
              const currentPath = window.location.pathname;
              let courseName = '';
              
              // Try to get course name from global variable first
              if (typeof CURRENT_COURSE_NAME !== 'undefined' && CURRENT_COURSE_NAME) {
                  courseName = CURRENT_COURSE_NAME;
              } else {
                  // Extract course name from URL patterns
                  const courseMatch = currentPath.match(/counselor_enrolled_course\/([^\/]+)/) || 
                                     currentPath.match(/fetch_current_part\/([^\/]+)/);
                  if (courseMatch) {
                      courseName = courseMatch[1];
                  }
              }
              
              // Check if we're on a specific part URL or use the partId parameter
              const partMatch = currentPath.match(/fetch_current_part\/[^\/]+\/(\d+)\//);
              let reloadPartId = partId; // Use the partId parameter passed to the function
              
              if (partMatch) {
                  reloadPartId = partMatch[1];
              }
              
              // Reload to the same part URL to preserve context and show Next button
              if (courseName && reloadPartId) {
                  // Detect base path for production subdirectory
                  let basePath = '';
                  if (currentPath.includes('/counselor_project/')) {
                      basePath = '/counselor_project';
                  }
                  
                  const reloadUrl = `${basePath}/fetch_current_part/${courseName}/${reloadPartId}/1/`;
                  console.log('Introduction part marked as complete, reloading to:', reloadUrl);
                  window.location.href = reloadUrl;
              } else {
                  // Fallback to simple reload
                  console.log('Introduction part marked as complete, reloading page (fallback)');
                  window.location.reload();
              }
          }

            // alert("Marked as complete!");
        } else {
            alert("Failed to update status: " + (data.message || "Unknown error"));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert("An error occurred while updating status. Please try again.");
    });
}

function getCSRFToken() {
    let cookieValue = null;
    let cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
        let cookie = cookies[i].trim();
        if (cookie.startsWith('csrftoken=')) {
            cookieValue = cookie.substring('csrftoken='.length, cookie.length);
            break;
        }
    }
    return cookieValue;
}