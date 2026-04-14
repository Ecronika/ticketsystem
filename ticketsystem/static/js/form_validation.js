/* form_validation.js — Bootstrap-native inline validation + dirty-form guard.
 *
 * Usage:
 *   <form data-validate data-dirty-warn> … </form>
 *   <input required> <div class="invalid-feedback">Pflichtfeld</div>
 */
(function () {
  "use strict";

  // Opens every .collapse inside the form that contains a field the user has
  // already filled in — prevents hidden "unsaved" fields from surprising users.
  function openCollapsesWithDirtyFields(form) {
    if (!form || typeof bootstrap === "undefined" || !bootstrap.Collapse) return;
    form.querySelectorAll(".collapse").forEach(function (collapse) {
      var hasValue = Array.from(collapse.querySelectorAll("input, select, textarea"))
        .some(function (el) {
          if (el.type === "checkbox" || el.type === "radio") return el.checked;
          return el.value && String(el.value).trim().length > 0;
        });
      if (hasValue) {
        bootstrap.Collapse.getOrCreateInstance(collapse).show();
      }
    });
  }

  function attachValidation(form) {
    form.addEventListener(
      "submit",
      function (e) {
        if (!form.checkValidity()) {
          openCollapsesWithDirtyFields(form);
          e.preventDefault();
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
    form.querySelectorAll("input:not([readonly]), select, textarea").forEach(function (el) {
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
