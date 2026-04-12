/* form_validation.js — Bootstrap-native inline validation + dirty-form guard.
 *
 * Usage:
 *   <form data-validate data-dirty-warn> … </form>
 *   <input required> <div class="invalid-feedback">Pflichtfeld</div>
 */
(function () {
  "use strict";

  function attachValidation(form) {
    form.addEventListener(
      "submit",
      function (e) {
        if (!form.checkValidity()) {
          e.preventDefault();
          e.stopPropagation();
          const firstInvalid = form.querySelector(":invalid");
          if (firstInvalid && typeof firstInvalid.focus === "function") {
            firstInvalid.focus({ preventScroll: false });
          }
        }
        form.classList.add("was-validated");
      },
      false
    );

    // Blur-level validation: mark individual fields as touched so the user
    // sees feedback before hitting submit.
    form.querySelectorAll("input, select, textarea").forEach(function (el) {
      el.addEventListener("blur", function () {
        if (el.value !== "" || el.required) {
          el.classList.toggle("is-invalid", !el.checkValidity());
          el.classList.toggle("is-valid", el.checkValidity() && el.value !== "");
        }
      });
    });
  }

  function attachDirtyGuard(form) {
    let dirty = false;
    let submitting = false;

    form.addEventListener("input", function () {
      dirty = true;
    });
    form.addEventListener("submit", function () {
      submitting = true;
    });

    window.addEventListener("beforeunload", function (e) {
      if (dirty && !submitting) {
        e.preventDefault();
        e.returnValue = "";
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form[data-validate]").forEach(attachValidation);
    document.querySelectorAll("form[data-dirty-warn]").forEach(attachDirtyGuard);
  });
})();
