'use strict';

/** Входящие: открытие письма в боковой панели как в Materialize app-email. */
document.addEventListener('DOMContentLoaded', function () {
  var view = document.getElementById('app-email-view');
  var titleEl = document.getElementById('delayuEmailViewTitle');
  var badgeEl = document.getElementById('delayuEmailViewBadge');
  var contentEl = document.getElementById('delayuEmailViewContent');
  if (!view || !contentEl) return;

  function loadPanel(url) {
    if (!url) return;
    contentEl.innerHTML =
      '<div class="text-center py-5 text-muted"><div class="spinner-border text-primary" role="status"></div></div>';
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {
        return r.ok ? r.json() : Promise.reject();
      })
      .then(function (data) {
        if (titleEl) titleEl.textContent = data.title || 'Письмо';
        if (badgeEl) {
          badgeEl.textContent = data.status || '';
          badgeEl.className = 'badge bg-label-secondary rounded-pill';
          badgeEl.classList.toggle('d-none', !data.status);
        }
        contentEl.innerHTML = data.html || '';
        if (typeof PerfectScrollbar !== 'undefined') {
          var ps = contentEl._delayuPs;
          if (ps) ps.update();
          else contentEl._delayuPs = new PerfectScrollbar(contentEl, { wheelPropagation: false, suppressScrollX: true });
        }
      })
      .catch(function () {
        contentEl.innerHTML =
          '<div class="alert alert-danger m-4">Не удалось загрузить письмо</div>';
      });
  }

  document.querySelectorAll('.email-list-item[data-panel-url]').forEach(function (item) {
    item.addEventListener('click', function (e) {
      if (e.target.closest('.form-check') || e.target.closest('.email-list-item-actions')) return;
      document.querySelectorAll('.email-list-item').forEach(function (li) {
        li.classList.remove('active');
      });
      item.classList.add('active');
      item.classList.add('email-marked-read');
      loadPanel(item.getAttribute('data-panel-url'));
    });
  });

  var openPk = view.getAttribute('data-open-pk');
  if (openPk) {
    var first = document.querySelector('.email-list-item[data-corr-pk="' + openPk + '"]');
    if (first) {
      first.classList.add('active', 'email-marked-read');
      loadPanel(first.getAttribute('data-panel-url'));
      if (typeof bootstrap !== 'undefined') {
        setTimeout(function () {
          var toggle = first.querySelector('[data-bs-toggle="sidebar"]') || first;
          toggle.click();
        }, 100);
      }
    }
  }
});
