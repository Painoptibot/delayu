'use strict';

function delayuInitDatePickers(root) {
  if (typeof flatpickr === 'undefined') return;
  var scope = root || document;
  var ru = {
    weekdays: {
      shorthand: ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'],
      longhand: ['Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    },
    months: {
      shorthand: ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'],
      longhand: [
        'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
      ]
    },
    firstDayOfWeek: 1,
    rangeSeparator: ' — ',
    weekAbbreviation: 'Нед',
    scrollTitle: 'Прокрутите для выбора',
    toggleTitle: 'Нажмите для переключения'
  };

  scope.querySelectorAll('.delayu-date').forEach(function (el) {
    if (el._flatpickr) return;
    flatpickr(el, {
      locale: ru,
      dateFormat: 'Y-m-d',
      altInput: true,
      altFormat: 'd.m.Y',
      allowInput: true,
      monthSelectorType: 'static',
      static: true
    });
  });
}
window.delayuInitDatePickers = delayuInitDatePickers;

document.addEventListener('DOMContentLoaded', function () {
  delayuInitDatePickers(document);
});
