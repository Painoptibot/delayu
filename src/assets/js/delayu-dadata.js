/**
 * Автоподсказки DaData через серверный прокси (/api/v1/dadata/suggest/).
 * Поля: data-dadata="address|fio|party|..." [, data-dadata-fill, data-dadata-parts, data-dadata-geo]
 */
(function (global) {
  'use strict';

  var SUGGEST_URL = '/api/v1/dadata/suggest/';
  var DEBOUNCE_MS = 280;
  var MIN_LEN = 2;

  function csrfToken() {
    var el = document.querySelector('[name=csrfmiddlewaretoken]');
    return el ? el.value : '';
  }

  function fieldByName(form, name) {
    if (!form || !name) return null;
    return form.querySelector('[name="' + name + '"]');
  }

  function hideDropdown(el) {
    var dd = el._dadataDropdown;
    if (dd) dd.remove();
    el._dadataDropdown = null;
  }

  function showDropdown(input, items, onPick) {
    hideDropdown(input);
    if (!items.length) return;
    var dd = document.createElement('div');
    dd.className = 'delayu-dadata-dropdown';
    items.forEach(function (item) {
      var row = document.createElement('button');
      row.type = 'button';
      row.className = 'delayu-dadata-item';
      row.textContent = item.value || item.unrestricted_value || '';
      row.addEventListener('mousedown', function (e) {
        e.preventDefault();
        onPick(item);
        hideDropdown(input);
      });
      dd.appendChild(row);
    });
    input.parentNode.classList.add('delayu-dadata-wrap');
    input.parentNode.appendChild(dd);
    input._dadataDropdown = dd;
  }

  function applyFill(input, item) {
    var raw = input.getAttribute('data-dadata-fill');
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
        target.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  }

  function applyGeo(input, item) {
    if (input.getAttribute('data-dadata-geo') !== '1') return;
    var data = item.data || {};
    var form = input.form;
    if (!form) return;
    var lat = data.geo_lat;
    var lng = data.geo_lon;
    if (lat == null || lng == null) return;
    var latEl = form.querySelector('[name=latitude]');
    var lngEl = form.querySelector('[name=longitude]');
    if (latEl) latEl.value = lat;
    if (lngEl) lngEl.value = lng;
  }

  function formatSnils(value) {
    var d = (value || '').replace(/\D/g, '').slice(0, 11);
    if (d.length <= 3) return d;
    if (d.length <= 6) return d.slice(0, 3) + '-' + d.slice(3);
    if (d.length <= 9) return d.slice(0, 3) + '-' + d.slice(3, 6) + '-' + d.slice(6);
    return d.slice(0, 3) + '-' + d.slice(3, 6) + '-' + d.slice(6, 9) + ' ' + d.slice(9);
  }

  function bindSnilsMask(input) {
    input.addEventListener('input', function () {
      var pos = input.selectionStart;
      input.value = formatSnils(input.value);
      if (pos != null) input.setSelectionRange(input.value.length, input.value.length);
    });
  }

  function fetchSuggest(type, query, extra, cb) {
    fetch(SUGGEST_URL, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
      },
      body: JSON.stringify({
        type: type,
        query: query,
        count: 10,
        extra: extra || undefined,
      }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        cb((data && data.suggestions) || []);
      })
      .catch(function () {
        cb([]);
      });
  }

  function bindSuggest(input) {
    if (input._dadataBound) return;
    input._dadataBound = true;
    var type = input.getAttribute('data-dadata');
    if (!type) return;
    var timer = null;

    input.addEventListener('input', function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < MIN_LEN) {
        hideDropdown(input);
        return;
      }
      timer = setTimeout(function () {
        var extra = {};
        var parts = input.getAttribute('data-dadata-parts');
        if (parts) extra.parts = [parts];
        fetchSuggest(type, q, extra, function (items) {
          showDropdown(input, items, function (item) {
            var data = item.data || {};
            var parts = input.getAttribute('data-dadata-parts');
            if (type === 'fio' && parts) {
              if (parts === 'SURNAME') input.value = data.surname || '';
              else if (parts === 'NAME') input.value = data.name || '';
              else if (parts === 'PATRONYMIC') input.value = data.patronymic || '';
              else input.value = item.value || '';
            } else if (type === 'passport' && data.series != null) {
              input.value = data.series || '';
            } else {
              input.value = item.value || '';
            }
            applyFill(input, item);
            applyGeo(input, item);
            input.dispatchEvent(new Event('change', { bubbles: true }));
          });
        });
      }, DEBOUNCE_MS);
    });

    input.addEventListener('blur', function () {
      setTimeout(function () {
        hideDropdown(input);
      }, 180);
    });
  }

  function delayuDadataInit(root) {
    root = root || document;
    root.querySelectorAll('[data-dadata]').forEach(bindSuggest);
    root.querySelectorAll('[data-dadata-mask="snils"]').forEach(bindSnilsMask);
  }

  global.delayuDadataInit = delayuDadataInit;

  document.addEventListener('DOMContentLoaded', function () {
    if (document.querySelector('[data-dadata], [data-dadata-mask]')) {
      delayuDadataInit(document);
    }
  });
})(window);
