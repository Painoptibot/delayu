/**
 * M03 — пошаговое создание пользователя (bs-stepper, без alert из шаблона).
 */
'use strict';

document.addEventListener('DOMContentLoaded', function () {
  const wizard = document.querySelector('.wizard-numbered');
  const form = document.getElementById('userWizardForm');
  if (!wizard || !form || typeof Stepper === 'undefined') return;

  const stepper = new Stepper(wizard, { linear: false });

  wizard.querySelectorAll('.btn-next').forEach(function (btn) {
    btn.addEventListener('click', function () {
      stepper.next();
    });
  });
  wizard.querySelectorAll('.btn-prev').forEach(function (btn) {
    btn.addEventListener('click', function () {
      stepper.previous();
    });
  });

  const submitBtn = wizard.querySelector('.btn-submit');
  if (submitBtn) {
    submitBtn.addEventListener('click', function (e) {
      e.preventDefault();
      form.submit();
    });
  }
});
