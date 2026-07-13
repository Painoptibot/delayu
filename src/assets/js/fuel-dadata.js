'use strict';

/** DaData party для портала жителя (ИНН → организация). */
(function () {
  var DEBOUNCE_MS = 300;
  var MIN_LEN = 3;

  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function fieldByName(form, name) {
    return form ? form.querySelector('[name="' + name + '"]') : null;
  }

  function hideDropdown(el) {
    if (el._fuelDadataDd) {
      el._fuelDadataDd.remove();
      el._fuelDadataDd = null;
    }
  }

  function showDropdown(input, items, onPick) {
    hideDropdown(input);
    if (!items.length) return;
    var dd = document.createElement('div');
    dd.className = 'fuel-dadata-dropdown';
    items.forEach(function (item) {
      var row = document.createElement('button');
      row.type = 'button';
      row.className = 'fuel-dadata-item';
      row.textContent = item.value || item.unrestricted_value || '';
      row.addEventListener('mousedown', function (e) {
        e.preventDefault();
        onPick(item);
        hideDropdown(input);
      });
      dd.appendChild(row);
    });
    var wrap = input.parentNode;
    wrap.classList.add('fuel-dadata-wrap');
    wrap.appendChild(dd);
    input._fuelDadataDd = dd;
  }

  function applyFill(input, item) {
    var raw = input.getAttribute('data-fuel-dadata-fill');
    if (!raw) return;
    var map;
    try {
      map = JSON.parse(raw);
    } catch (e) {
      return;
    }
    var form = input.form;
    var data = item.data || {};
    Object.keys(map).forEach(function (fieldName) {
      var key = map[fieldName];
      var target = fieldByName(form, fieldName);
      if (!target) return;
      var val = data[key];
      if (val !== undefined && val !== null) {
        target.value = String(val);
      }
    });
  }

  function bindInput(input, suggestUrl) {
    if (!input || input.dataset.fuelDadataBound) return;
    input.dataset.fuelDadataBound = '1';
    var timer = null;
    input.addEventListener('input', function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < MIN_LEN) {
        hideDropdown(input);
        return;
      }
      timer = setTimeout(function () {
        fetch(suggestUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
          },
          credentials: 'same-origin',
          body: JSON.stringify({ query: q }),
        })
          .then(function (r) { return r.json(); })
          .then(function (data) {
            var items = data.suggestions || [];
            showDropdown(input, items, function (item) {
              input.value = (item.data && item.data.inn) || item.value || input.value;
              applyFill(input, item);
            });
          })
          .catch(function () { hideDropdown(input); });
      }, DEBOUNCE_MS);
    });
    input.addEventListener('blur', function () {
      setTimeout(function () { hideDropdown(input); }, 150);
    });
  }

  window.initFuelDadata = function (formId, suggestUrl) {
    var form = document.getElementById(formId);
    if (!form) return;
    form.querySelectorAll('[data-fuel-dadata]').forEach(function (input) {
      bindInput(input, suggestUrl);
    });
  };
})();
