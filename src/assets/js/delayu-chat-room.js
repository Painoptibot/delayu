'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var box = document.getElementById('chatMessages');
  if (box) box.scrollTop = box.scrollHeight;
  var input = document.querySelector('#chatMessages + .border-top textarea, .border-top textarea');
  if (input) input.classList.add('form-control');
});
