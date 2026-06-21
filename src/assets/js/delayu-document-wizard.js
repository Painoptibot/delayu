'use strict';

document.addEventListener('DOMContentLoaded', function () {
  const wizard = document.querySelector('.wizard-numbered');
  const form = document.getElementById('docWizardForm');
  if (!wizard || !form || typeof Stepper === 'undefined') return;
  const stepper = new Stepper(wizard, { linear: false });
  wizard.querySelectorAll('.btn-next').forEach(function (b) {
    b.addEventListener('click', function () { stepper.next(); });
  });
  wizard.querySelectorAll('.btn-prev').forEach(function (b) {
    b.addEventListener('click', function () { stepper.previous(); });
  });
});
