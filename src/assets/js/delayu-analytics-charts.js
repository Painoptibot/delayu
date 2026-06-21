'use strict';

document.addEventListener('DOMContentLoaded', function () {
  if (typeof ApexCharts === 'undefined' || !window.DELAYU_CHARTS) return;

  function barChart(elId, data, horizontal) {
    var el = document.querySelector(elId);
    if (!el || !data || !data.labels) return;
    new ApexCharts(el, {
      chart: { type: horizontal ? 'bar' : 'area', height: elId === '#chartCases' ? 280 : 260, toolbar: { show: false } },
      series: [{ name: data.title || '', data: data.series || [] }],
      xaxis: { categories: data.labels },
      plotOptions: { bar: { horizontal: horizontal } },
      dataLabels: { enabled: false },
      stroke: { curve: 'smooth' }
    }).render();
  }

  var c = window.DELAYU_CHARTS;
  if (c.cases) barChart('#chartCases', c.cases, false);
  if (c.tasks) barChart('#chartTasks', c.tasks, true);
  if (c.corr) {
    var el = document.querySelector('#chartCorr');
    if (el && c.corr.labels) {
      new ApexCharts(el, {
        chart: { type: 'donut', height: 260 },
        series: c.corr.series,
        labels: c.corr.labels
      }).render();
    }
  }
});
