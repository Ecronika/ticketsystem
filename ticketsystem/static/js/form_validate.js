// Inline field-validation for forms opted in via data-validate.
// - onblur: render native HTML5 validity message below input, add aria-invalid.
// - oninput: clear error when valid again.
// - submit: prevent default if invalid; focus first error.
// - window.applyServerErrors(formEl, [{field, message}]) for server-side errors
//   returned as JSON from @api_endpoint.

(function () {
    'use strict';

    function errorId(input) {
        return (input.id || input.name || 'field') + '-error';
    }

    function renderFieldError(input, message) {
        clearFieldError(input);
        const div = document.createElement('div');
        div.className = 'field-error';
        div.id = errorId(input);
        div.setAttribute('role', 'alert');
        div.textContent = message;
        input.setAttribute('aria-invalid', 'true');
        input.setAttribute('aria-describedby', div.id);
        input.insertAdjacentElement('afterend', div);
    }

    function clearFieldError(input) {
        input.removeAttribute('aria-invalid');
        input.removeAttribute('aria-describedby');
        const existing = document.getElementById(errorId(input));
        if (existing) existing.remove();
    }

    function validateInput(input) {
        // Skip hidden inputs, disabled inputs, and those without validation constraints
        if (input.disabled || input.type === 'hidden') return true;
        if (typeof input.checkValidity !== 'function') return true;
        if (input.checkValidity()) {
            clearFieldError(input);
            return true;
        }
        renderFieldError(input, input.validationMessage);
        return false;
    }

    function initForm(form) {
        const fields = form.querySelectorAll('input, textarea, select');
        fields.forEach(input => {
            input.addEventListener('blur', () => validateInput(input));
            input.addEventListener('input', () => {
                if (input.hasAttribute('aria-invalid') && input.checkValidity()) {
                    clearFieldError(input);
                }
            });
        });

        form.addEventListener('submit', (ev) => {
            let firstInvalid = null;
            fields.forEach(input => {
                if (!validateInput(input) && !firstInvalid) firstInvalid = input;
            });
            if (firstInvalid) {
                ev.preventDefault();
                firstInvalid.focus();
            }
        });
    }

    // Apply server-side field errors returned from @api_endpoint.
    // Payload shape: [{field: '<name>', message: '<human-readable>'}, ...]
    window.applyServerErrors = function (form, errors) {
        if (!form || !Array.isArray(errors)) return;
        errors.forEach(({field, message}) => {
            const input = form.querySelector(`[name="${field}"]`);
            if (input) renderFieldError(input, message);
        });
        const firstErrorInput = form.querySelector('[aria-invalid="true"]');
        if (firstErrorInput) firstErrorInput.focus();
    };

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form[data-validate]').forEach(initForm);
    });
})();
