'use strict';

(function () {
  var delegated = false;

  function initFuelAzsActions(options) {
    options = options || {};
    var mapContainerId = options.mapContainerId || 'fuel-citizen-map';
    var routePanelId = options.routePanelId || 'fuel-route-panel';

    if (!delegated) {
      delegated = true;
      document.addEventListener('click', function (e) {
        var routeBtn = e.target.closest('.fuel-route-btn');
        if (routeBtn) {
          e.stopPropagation();
          if (typeof window.buildRouteToAzs !== 'function') return;
          window.buildRouteToAzs(
            mapContainerId,
            parseFloat(routeBtn.dataset.lat),
            parseFloat(routeBtn.dataset.lng),
            {
              title: routeBtn.dataset.title || 'АЗС',
              address: routeBtn.dataset.address || '',
              routePanelId: routePanelId,
            }
          );
          return;
        }
        var item = e.target.closest('.fuel-azs-item--actionable');
        if (item) {
          var url = item.getAttribute('data-apply-url');
          if (url) window.location.href = url;
        }
      });
    }

    var panel = document.getElementById(routePanelId);
    if (panel && !panel.dataset.fuelRouteCloseBound) {
      panel.dataset.fuelRouteCloseBound = '1';
      var closeBtn = panel.querySelector('[data-fuel-route-close]');
      if (closeBtn) {
        closeBtn.addEventListener('click', function () {
          if (typeof window.clearFuelRoute === 'function') {
            window.clearFuelRoute(mapContainerId, routePanelId);
          }
        });
      }
    }
  }

  window.initFuelAzsActions = initFuelAzsActions;
})();
