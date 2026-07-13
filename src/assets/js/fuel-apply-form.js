'use strict';

/** Маски полей заявки и выбор АЗС с поиском. */
(function () {
  var PLATE_ALLOWED = /[^АВЕКМНОРСТУХA-Z0-9]/g;
  var VISIBLE_LIMIT = 5;

  function bindPlateMask(input) {
    input.addEventListener('input', function () {
      var v = input.value.toUpperCase().replace(PLATE_ALLOWED, '');
      if (v.length > 9) v = v.slice(0, 9);
      input.value = v;
    });
  }

  function bindInnMask(input) {
    input.addEventListener('input', function () {
      input.value = input.value.replace(/\D/g, '').slice(0, 12);
    });
  }

  function normalizeSearch(s) {
    return (s || '').toLowerCase().replace(/\s+/g, ' ').trim();
  }

  function bindAzsPicker(root) {
    var list = root.querySelector('[data-fuel-azs-list]');
    var search = root.querySelector('[data-fuel-azs-search]');
    var moreBtn = root.querySelector('[data-fuel-azs-more]');
    if (!list) return;

    var items = Array.prototype.slice.call(list.querySelectorAll('[data-fuel-azs-item]'));
    var expanded = false;

    function hasSearchQuery() {
      return normalizeSearch(search ? search.value : '').length > 0;
    }

    function matchedItems() {
      return items.filter(function (el) {
        return !el.hidden;
      });
    }

    function isShown(el) {
      if (el.hidden) return false;
      if (!hasSearchQuery() && !expanded && el.classList.contains('fuel-azs-item--extra')) {
        return false;
      }
      return true;
    }

    function visibleItems() {
      return items.filter(isShown);
    }

    function ensureSelection() {
      var visible = visibleItems();
      var checked = visible.find(function (el) {
        var radio = el.querySelector('input[type=radio]');
        return radio && radio.checked;
      });
      if (!checked && visible[0]) {
        var radio = visible[0].querySelector('input[type=radio]');
        if (radio) radio.checked = true;
      }
      items.forEach(function (el) {
        var radio = el.querySelector('input[type=radio]');
        el.classList.toggle('fuel-azs-item--selected', !!(radio && radio.checked));
      });
    }

    function updateMoreButton() {
      if (!moreBtn) return;
      if (hasSearchQuery() || expanded) {
        moreBtn.hidden = true;
        moreBtn.classList.add('fuel-azs-more--hidden');
        return;
      }
      var matched = matchedItems();
      var extra = Math.max(0, matched.length - VISIBLE_LIMIT);
      if (extra === 0) {
        moreBtn.hidden = true;
        moreBtn.classList.add('fuel-azs-more--hidden');
        return;
      }
      moreBtn.hidden = false;
      moreBtn.classList.remove('fuel-azs-more--hidden');
      moreBtn.textContent = 'Показать ещё (' + extra + ')';
    }

    function applyFilter() {
      var q = normalizeSearch(search ? search.value : '');
      items.forEach(function (el) {
        var hay = normalizeSearch(el.getAttribute('data-search') || el.textContent);
        var match = !q || hay.indexOf(q) >= 0;
        el.hidden = !match;
        el.classList.remove('fuel-azs-item--extra');
      });
      applyCollapse();
      ensureSelection();
      updateMoreButton();
    }

    function applyCollapse() {
      if (hasSearchQuery()) {
        updateMoreButton();
        return;
      }
      var shown = 0;
      items.forEach(function (el) {
        if (el.hidden) {
          el.classList.remove('fuel-azs-item--extra');
          return;
        }
        shown += 1;
        if (!expanded && shown > VISIBLE_LIMIT) {
          el.classList.add('fuel-azs-item--extra');
        } else {
          el.classList.remove('fuel-azs-item--extra');
        }
      });
      updateMoreButton();
    }

    if (search) {
      search.addEventListener('input', function () {
        if (hasSearchQuery()) {
          expanded = false;
        }
        applyFilter();
      });
    }

    if (moreBtn) {
      moreBtn.addEventListener('click', function () {
        expanded = true;
        applyCollapse();
        ensureSelection();
        updateMoreButton();
      });
    }

    items.forEach(function (el) {
      el.addEventListener('click', function () {
        items.forEach(function (other) {
          other.classList.toggle('fuel-azs-item--selected', other === el);
        });
      });
    });

    applyFilter();

    var checked = list.querySelector('input[name=preferred_azs]:checked');
    if (checked) {
      var checkedItem = checked.closest('[data-fuel-azs-item]');
      if (checkedItem && checkedItem.classList.contains('fuel-azs-item--extra')) {
        expanded = true;
        applyCollapse();
        ensureSelection();
        updateMoreButton();
      }
    }
  }

  function init() {
    var form = document.getElementById('fuel-apply-form');
    if (!form) return;

    var plate = form.querySelector('input[name="plate"]');
    if (plate) bindPlateMask(plate);

    var inn = form.querySelector('input[name="inn"]');
    if (inn) bindInnMask(inn);

    var picker = form.querySelector('[data-fuel-azs-picker]');
    if (picker) bindAzsPicker(picker);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
