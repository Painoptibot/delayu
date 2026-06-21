'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var calendarEl = document.getElementById('uzhvDeadlineCalendar');
  var modalEl = document.getElementById('uzhvModal');
  var bodyEl = document.getElementById('uzhvModalBody');
  var titleEl = document.getElementById('uzhvModalTitle');
  var raw = window.uzhvDeadlineEvents || [];

  function openModal(url, title) {
    if (!modalEl || !bodyEl || !url) return;
    var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    if (titleEl && title) titleEl.textContent = title;
    bodyEl.innerHTML = '<div class="text-center py-5 text-muted">Загрузка…</div>';
    modal.show();
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.ok ? r.text() : Promise.reject(); })
      .then(function (h) { bodyEl.innerHTML = h; })
      .catch(function () {
        bodyEl.innerHTML = '<div class="alert alert-danger mb-0">Ошибка загрузки карточки</div>';
      });
  }

  if (bodyEl) {
    bodyEl.addEventListener('click', function (e) {
      var link = e.target.closest('.uzhv-modal-link');
      if (!link) return;
      e.preventDefault();
      openModal(link.getAttribute('data-modal-url'), link.getAttribute('data-modal-title'));
    });
  }

  if (!calendarEl || typeof Calendar === 'undefined') return;

  var plugins = [];
  if (window.dayGridPlugin) plugins.push(window.dayGridPlugin);
  if (window.listPlugin) plugins.push(window.listPlugin);
  if (window.interactionPlugin) plugins.push(window.interactionPlugin);

  var calendar = new Calendar(calendarEl, {
    plugins: plugins,
    initialView: 'dayGridMonth',
    locale: 'ru',
    buttonText: { today: 'Сегодня', month: 'Месяц', list: 'Список' },
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,listMonth',
    },
    events: raw,
    height: 'auto',
    dayMaxEvents: 3,
    navLinks: true,
    eventClick: function (info) {
      info.jsEvent.preventDefault();
      var props = info.event.extendedProps || {};
      if (props.modal_url) {
        openModal(props.modal_url, props.modal_title || info.event.title);
      } else if (info.event.url) {
        window.location.href = info.event.url;
      }
    },
    eventDidMount: function (info) {
      if (info.event.extendedProps && info.event.extendedProps.overdue) {
        info.el.style.boxShadow = 'inset 0 0 0 2px #ff4c51';
      }
    },
  });
  calendar.render();
});
