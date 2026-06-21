'use strict';

/** Русские подписи для демо-графиков главной (после dashboards-analytics.js). */
document.addEventListener('DOMContentLoaded', function () {
  var map = {
    Jan: 'Янв',
    Feb: 'Фев',
    Mar: 'Мар',
    Apr: 'Апр',
    May: 'Май',
    Jun: 'Июн',
    Jul: 'Июл',
    Aug: 'Авг',
    Sep: 'Сен',
    Oct: 'Окт',
    Nov: 'Ноя',
    Dec: 'Дек',
    Mon: 'Пн',
    Tue: 'Вт',
    Wed: 'Ср',
    Thu: 'Чт',
    Fri: 'Пт',
    Sat: 'Сб',
    Sun: 'Вс',
    S: 'В',
    M: 'П',
    T: 'В',
    W: 'С',
    F: 'П',
    Income: 'Доход',
    'Net Worth': 'Оборот',
    Earning: 'Поступления',
    Expense: 'Расходы',
    Sales: 'Дела',
    Progress: 'Выполнение',
    'Last Week': 'Прошлая нед.',
    'This Week': 'Текущая нед.',
    US: 'РФ',
    IN: 'СНГ',
    JA: 'Европа',
    CA: 'Сибирь',
    AU: 'Урал',
  };

  function ruLabel(val) {
    return map[val] || val;
  }

  if (typeof ApexCharts !== 'undefined' && ApexCharts.exec) {
    document.querySelectorAll('.apexcharts-legend-text, .apexcharts-xaxis-label, .apexcharts-yaxis-label').forEach(function (el) {
      var t = (el.textContent || '').trim();
      if (map[t]) el.textContent = ruLabel(t);
    });
  }
});
