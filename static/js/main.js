/**
 * Main JavaScript file for Badgey Quiz Dashboard
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Auto-dismiss alerts after 5 seconds
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert:not(.alert-persistent)');
        alerts.forEach(function(alert) {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Add confirm dialog to delete buttons
    const deleteButtons = document.querySelectorAll('.btn-delete');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to delete this item? This action cannot be undone.')) {
                e.preventDefault();
            }
        });
    });

    // Dynamic option handling for question forms
    setupQuestionForm();

    // Quiz preview functionality
    setupQuizPreview();
});

/**
 * Setup question form with dynamic option fields
 */
function setupQuestionForm() {
    const addOptionBtn = document.getElementById('add-option-btn');
    const optionsContainer = document.getElementById('options-container');

    if (addOptionBtn && optionsContainer) {
        // Add new option field
        addOptionBtn.addEventListener('click', function() {
            const optionCount = optionsContainer.children.length;
            const newOption = document.createElement('div');
            newOption.className = 'option-row row mb-3';
            newOption.innerHTML = `
                <div class="col-md-2">
                    <input type="text" class="form-control" name="option_key_${optionCount}" placeholder="Key" maxlength="5" required>
                </div>
                <div class="col-md-9">
                    <input type="text" class="form-control" name="option_value_${optionCount}" placeholder="Option text" required>
                </div>
                <div class="col-md-1">
                    <button type="button" class="btn btn-danger remove-option-btn">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            `;
            optionsContainer.appendChild(newOption);

            // Setup remove button
            const removeBtn = newOption.querySelector('.remove-option-btn');
            removeBtn.addEventListener('click', function() {
                optionsContainer.removeChild(newOption);
                updateCorrectAnswerOptions();
            });

            // Update correct answer dropdown
            updateCorrectAnswerOptions();
        });

        // Handle removing options
        optionsContainer.addEventListener('click', function(e) {
            if (e.target.classList.contains('remove-option-btn') || e.target.closest('.remove-option-btn')) {
                const button = e.target.closest('.remove-option-btn');
                const optionRow = button.closest('.option-row');
                optionsContainer.removeChild(optionRow);
                updateCorrectAnswerOptions();
            }
        });
    }
}

/**
 * Update correct answer dropdown options
 */
function updateCorrectAnswerOptions() {
    const optionsContainer = document.getElementById('options-container');
    const correctAnswerSelect = document.getElementById('correct_answer');

    if (optionsContainer && correctAnswerSelect) {
        // Clear current options
        correctAnswerSelect.innerHTML = '';
        
        // Add a default empty option
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = 'Select correct answer';
        correctAnswerSelect.appendChild(defaultOption);
        
        // Add option for each key
        const keyInputs = optionsContainer.querySelectorAll('input[name^="option_key_"]');
        keyInputs.forEach(function(input) {
            if (input.value.trim()) {
                const option = document.createElement('option');
                option.value = input.value.trim();
                option.textContent = input.value.trim();
                correctAnswerSelect.appendChild(option);
            }
        });
    }
}

/**
 * Setup quiz preview functionality
 */
function setupQuizPreview() {
    const previewContainer = document.getElementById('quiz-preview');
    if (!previewContainer) return;

    const questions = JSON.parse(previewContainer.dataset.questions || '[]');
    let currentIndex = 0;

    const questionDisplay = document.getElementById('preview-question');
    const optionsDisplay = document.getElementById('preview-options');
    const nextBtn = document.getElementById('preview-next-btn');
    const prevBtn = document.getElementById('preview-prev-btn');
    const progressDisplay = document.getElementById('preview-progress');

    // Initialize
    if (questions.length > 0) {
        showQuestion(currentIndex);
    }

    // Next button
    if (nextBtn) {
        nextBtn.addEventListener('click', function() {
            if (currentIndex < questions.length - 1) {
                currentIndex++;
                showQuestion(currentIndex);
            }
        });
    }

    // Previous button
    if (prevBtn) {
        prevBtn.addEventListener('click', function() {
            if (currentIndex > 0) {
                currentIndex--;
                showQuestion(currentIndex);
            }
        });
    }

    // Show question at index
    function showQuestion(index) {
        if (!questions[index]) return;
        
        const question = questions[index];
        
        // Update question text
        if (questionDisplay) {
            questionDisplay.textContent = question.text;
        }
        
        // Update options
        if (optionsDisplay) {
            optionsDisplay.innerHTML = '';
            
            for (const [key, value] of Object.entries(question.options)) {
                const optionEl = document.createElement('div');
                optionEl.className = 'form-check';
                optionEl.innerHTML = `
                    <input class="form-check-input" type="radio" name="preview-option" id="preview-option-${key}" ${key === question.correct_answer ? 'data-correct="true"' : ''}>
                    <label class="form-check-label" for="preview-option-${key}">
                        ${key}: ${value}
                    </label>
                `;
                optionsDisplay.appendChild(optionEl);
                
                // Add click handler
                const input = optionEl.querySelector('input');
                input.addEventListener('click', function() {
                    // Highlight correct/incorrect
                    const options = optionsDisplay.querySelectorAll('.form-check');
                    options.forEach(opt => {
                        const radio = opt.querySelector('input');
                        if (radio.dataset.correct === 'true') {
                            opt.classList.add('text-success');
                        } else if (radio.checked && radio.dataset.correct !== 'true') {
                            opt.classList.add('text-danger');
                        }
                    });
                    
                    // Show explanation if wrong
                    if (question.explanation && input.dataset.correct !== 'true') {
                        const explanationEl = document.createElement('div');
                        explanationEl.className = 'alert alert-info mt-3';
                        explanationEl.textContent = question.explanation;
                        optionsDisplay.appendChild(explanationEl);
                    }
                });
            }
        }
        
        // Update progress
        if (progressDisplay) {
            progressDisplay.textContent = `Question ${index + 1} of ${questions.length}`;
        }
        
        // Update button states
        if (prevBtn) {
            prevBtn.disabled = index === 0;
        }
        if (nextBtn) {
            nextBtn.disabled = index === questions.length - 1;
        }
    }
}

/**
 * Format a date string to a readable format
 * @param {string} dateString - The date string to format
 * @returns {string} Formatted date string
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

/**
 * Format a number with commas as thousands separators
 * @param {number} number - The number to format
 * @returns {string} Formatted number string
 */
function formatNumber(number) {
    return number.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * Show a toast notification
 * @param {string} message - The message to display
 * @param {string} type - The type of notification (success, error, warning, info)
 */
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        // Create toast container if it doesn't exist
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(container);
    }

    // Create toast element
    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-white bg-${type} border-0`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    document.getElementById('toast-container').appendChild(toastEl);
    
    // Initialize and show toast
    const toast = new bootstrap.Toast(toastEl, {
        autohide: true,
        delay: 5000
    });
    toast.show();
    
    // Remove from DOM after hiding
    toastEl.addEventListener('hidden.bs.toast', function() {
        toastEl.remove();
    });
} 