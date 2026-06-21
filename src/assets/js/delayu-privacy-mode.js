'use strict';

/** Режим скрытия персональных данных — размытие на всех страницах контента. */
document.addEventListener('DOMContentLoaded', function () {
  var btn = document.getElementById('delayu-privacy-toggle');
  if (!btn) return;
  var icon = document.getElementById('delayu-privacy-icon');
  var key = 'delayuPrivacyMode';
  var auditUrl = document.body.getAttribute('data-privacy-audit-url');

  var PII_NAME = /first_name|last_name|middle_name|email|phone|snils|inn|passport|address|telegram|counterparty|username|birth|employee|tab_number|manager|position|assignee|full_name|counterparty|subject|title|body|description|comment|transcript|name/i;

  function markDynamicPii(root) {
    if (!document.body.classList.contains('delayu-privacy-mode')) return;
    var scope = root || document.querySelector('.layout-page');
    if (!scope) return;
    scope.querySelectorAll('input, textarea, select, .form-control-plaintext').forEach(function (el) {
      if (el.type === 'checkbox' || el.type === 'radio' || el.type === 'hidden' || el.type === 'file') return;
      if (el.classList.contains('email-search-input') || el.classList.contains('chat-search-input')) return;
      var keyStr = (el.name || '') + (el.id || '') + (el.getAttribute('autocomplete') || '');
      if (PII_NAME.test(keyStr) || el.getAttribute('data-pii') === '1') {
        el.classList.add('delayu-privacy-blur');
      }
    });
    scope.querySelectorAll('h5, h6, .fw-medium, .fw-semibold').forEach(function (el) {
      if (el.closest('.delayu-module-hint') || el.closest('#layout-menu') || el.closest('.btn')) return;
      if (el.closest('.card-header') && el.textContent && el.textContent.length < 80) {
        el.classList.add('delayu-privacy-blur');
      }
    });
  }

  function apply(on) {
    document.body.classList.toggle('delayu-privacy-mode', on);
    if (icon) {
      icon.classList.toggle('ri-eye-off-line', on);
      icon.classList.toggle('ri-eye-line', !on);
    }
    btn.setAttribute('title', on ? 'Показать персональные данные' : 'Скрыть персональные данные');
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    if (on) markDynamicPii();
  }

  apply(localStorage.getItem(key) === '1');

  if (localStorage.getItem(key) === '1' && auditUrl && window.fetch) {
    var fd0 = new FormData();
    fd0.append('enabled', '1');
    var csrf0 = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrf0) fd0.append('csrfmiddlewaretoken', csrf0.value);
    fetch(auditUrl, { method: 'POST', body: fd0, credentials: 'same-origin' }).catch(function () {});
  }

  btn.addEventListener('click', function (e) {
    e.preventDefault();
    var on = !document.body.classList.contains('delayu-privacy-mode');
    localStorage.setItem(key, on ? '1' : '0');
    apply(on);
    if (auditUrl && window.fetch) {
      var fd = new FormData();
      fd.append('enabled', on ? '1' : '0');
      var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
      if (csrf) fd.append('csrfmiddlewaretoken', csrf.value);
      fetch(auditUrl, { method: 'POST', body: fd, credentials: 'same-origin' }).catch(function () {});
    }
  });

  if (typeof MutationObserver !== 'undefined') {
    var page = document.querySelector('.layout-page');
    if (page) {
      var obs = new MutationObserver(function () {
        if (document.body.classList.contains('delayu-privacy-mode')) markDynamicPii(page);
      });
      obs.observe(page, { childList: true, subtree: true });
    }
  }
});
