// static/js/scripts.js

function validateForm() {
    var questionGroups = document.querySelectorAll('.question-container');
    var unanswered = false;

    questionGroups.forEach(function(group) {
        var isChecked = false;
        group.querySelectorAll('input[type="radio"]').forEach(function(radio) {
            if (radio.checked) {
                isChecked = true;
            }
        });

        console.log('Question group:', group.id, 'isChecked:', isChecked);

        if (!isChecked) {
            unanswered = true;
            group.classList.add('unchecked');
        } else {
            group.classList.remove('unchecked');
        }
    });

    if (unanswered) {
        alert("Please select an option for all questions before submitting.");
        return false;
    }

    return true;
}

