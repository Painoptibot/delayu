'use strict';

/** Подсказки марки/модели ТС (RU/EN). */
(function () {
  var DEBOUNCE_MS = 250;
  var MIN_LEN = 3;

  function hideDropdown(input) {
    if (input._fuelVehicleDd) {
      input._fuelVehicleDd.remove();
      input._fuelVehicleDd = null;
    }
  }

  function showDropdown(input, items, onPick) {
    hideDropdown(input);
    if (!items.length) return;
    var dd = document.createElement('div');
    dd.className = 'fuel-dadata-dropdown';
    items.forEach(function (label) {
      var row = document.createElement('button');
      row.type = 'button';
      row.className = 'fuel-dadata-item';
      row.textContent = label;
      row.addEventListener('mousedown', function (e) {
        e.preventDefault();
        onPick(label);
        hideDropdown(input);
      });
      dd.appendChild(row);
    });
    var wrap = input.parentNode;
    wrap.classList.add('fuel-dadata-wrap');
    wrap.appendChild(dd);
    input._fuelVehicleDd = dd;
  }

  function bindInput(input, suggestUrl) {
    if (!input || input.dataset.fuelVehicleBound) return;
    input.dataset.fuelVehicleBound = '1';
    var timer = null;
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < MIN_LEN) {
        hideDropdown(input);
        return;
      }
      timer = setTimeout(function () {
        fetch(suggestUrl + '?q=' + encodeURIComponent(q), {
          headers: { Accept: 'application/json' },
          credentials: 'same-origin',
        })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            showDropdown(input, data.suggestions || [], function (label) {
              input.value = label;
            });
          })
          .catch(function () {
            hideDropdown(input);
          });
      }, DEBOUNCE_MS);
    });
    input.addEventListener('blur', function () {
      setTimeout(function () {
        hideDropdown(input);
      }, 150);
    });
  }

  window.initFuelVehicleSuggest = function (formId, suggestUrl) {
    var form = document.getElementById(formId);
    if (!form) return;
    form.querySelectorAll('[data-fuel-vehicle-suggest]').forEach(function (input) {
      bindInput(input, suggestUrl);
    });
  };
})();
