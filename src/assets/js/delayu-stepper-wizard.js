'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var wizard = document.querySelector('.wizard-numbered');
  var form = wizard && wizard.closest('form');
  if (!wizard || !form || typeof Stepper === 'undefined') return;

  var stepper = new Stepper(wizard, { linear: false });

  function activePane() {
    return wizard.querySelector('.content.active');
  }

  function validatePane(pane) {
    if (!pane) return true;
    var invalid = [];
    pane.querySelectorAll('input, select, textarea').forEach(function (el) {
      if (el.disabled || el.type === 'hidden' || el.offsetParent === null) return;
      if (!el.checkValidity()) {
        invalid.push(el);
        el.classList.add('is-invalid');
      } else {
        el.classList.remove('is-invalid');
      }
    });
    if (invalid.length) {
      invalid[0].focus();
      invalid[0].reportValidity && invalid[0].reportValidity();
      return false;
    }
    return true;
  }

  wizard.querySelectorAll('.btn-next').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!validatePane(activePane())) return;
      stepper.next();
    });
  });
  wizard.querySelectorAll('.btn-prev').forEach(function (btn) {
    btn.addEventListener('click', function () {
      stepper.previous();
    });
  });

  form.addEventListener('submit', function (e) {
    var panes = wizard.querySelectorAll('.content');
    for (var i = 0; i < panes.length; i++) {
      if (!validatePane(panes[i])) {
        e.preventDefault();
        stepper.to(i + 1);
        return;
      }
    }
  });
});
