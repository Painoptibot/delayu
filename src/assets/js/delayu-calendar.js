'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var calendarEl = document.getElementById('calendar');
  var raw = window.events || [];
  if (!calendarEl || typeof Calendar === 'undefined') return;

  var plugins = [];
  if (window.dayGridPlugin) plugins.push(window.dayGridPlugin);
  if (window.timeGridPlugin) plugins.push(window.timeGridPlugin);
  if (window.listPlugin) plugins.push(window.listPlugin);
  if (window.interactionPlugin) plugins.push(window.interactionPlugin);

  var calendar = new Calendar(calendarEl, {
    plugins: plugins,
    initialView: 'dayGridMonth',
    locale: 'ru',
    buttonText: {
      today: 'Сегодня',
      month: 'Месяц',
      week: 'Неделя',
      day: 'День',
      list: 'Список',
    },
    allDayText: 'Весь день',
    moreLinkText: function (n) {
      return 'ещё ' + n;
    },
    noEventsText: 'Нет событий',
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,timeGridWeek,listMonth',
    },
    events: raw,
    height: 'auto',
    eventDisplay: 'block',
    dayMaxEvents: 2,
    navLinks: true,
    eventClick: function (info) {
      if (info.event.url) {
        info.jsEvent.preventDefault();
        window.location.href = info.event.url;
      }
    },
    eventDidMount: function (info) {
      var bg = info.event.backgroundColor;
      if (bg) {
        info.el.style.backgroundColor = bg;
        info.el.style.borderColor = info.event.borderColor || bg;
      }
      var fg = info.event.textColor || '#fff';
      info.el.style.color = fg;
      var title = info.el.querySelector('.fc-event-title, .fc-event-title-container');
      if (title) title.style.color = fg;
      var time = info.el.querySelector('.fc-event-time');
      if (time) time.style.color = fg;
    },
  });
  calendar.render();

  var inline = document.querySelector('.inline-calendar');
  if (inline && typeof flatpickr !== 'undefined') {
    var fpRu = {
      weekdays: {
        shorthand: ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'],
        longhand: ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'],
      },
      months: {
        shorthand: ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'],
        longhand: [
          'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
          'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
        ],
      },
      firstDayOfWeek: 1,
    };
    flatpickr(inline, {
      inline: true,
      locale: fpRu,
      dateFormat: 'Y-m-d',
      onChange: function (selected) {
        if (selected[0]) calendar.gotoDate(selected[0]);
      }
    });
  }

  function applyFilters() {
    var allowed = [];
    var all = document.querySelector('.select-all');
    if (all && all.checked) {
      allowed = ['personal', 'business', 'family', 'holiday'];
    } else {
      document.querySelectorAll('.input-filter:checked').forEach(function (f) {
        allowed.push(f.getAttribute('data-value'));
      });
    }
    calendar.removeAllEvents();
    raw.forEach(function (ev) {
      var cal = (ev.extendedProps && ev.extendedProps.calendar) || 'business';
      if (allowed.indexOf(cal) >= 0) calendar.addEvent(ev);
    });
  }

  document.querySelectorAll('.input-filter, .select-all').forEach(function (cb) {
    cb.addEventListener('change', applyFilters);
  });
});
