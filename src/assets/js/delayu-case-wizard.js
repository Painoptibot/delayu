'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var wizard = document.querySelector('.wizard-numbered');
  var form = document.getElementById('caseWizardForm');
  if (!wizard || !form || typeof Stepper === 'undefined') return;
  var stepper = new Stepper(wizard, { linear: false });
  wizard.querySelectorAll('.btn-next').forEach(function (b) {
    b.addEventListener('click', function () { stepper.next(); });
  });
  wizard.querySelectorAll('.btn-prev').forEach(function (b) {
    b.addEventListener('click', function () { stepper.previous(); });
  });
});
