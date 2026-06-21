'use strict';

/** Корреспонденция: панель просмотра + действия (удаление, прочитано, метки). */
document.addEventListener('DOMContentLoaded', function () {
  var root = document.querySelector('.app-email');
  if (!root) return;

  var actionsUrl = root.getAttribute('data-actions-url');
  var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
  var csrfToken = csrf ? csrf.value : '';

  var view = document.getElementById('app-email-view');
  var titleEl = document.getElementById('delayuEmailViewTitle');
  var badgeEl = document.getElementById('delayuEmailViewBadge');
  var contentEl = document.getElementById('delayuEmailViewContent');

  function selectedIds() {
    return Array.prototype.slice
      .call(document.querySelectorAll('.email-list-item-input:checked'))
      .map(function (inp) {
        var li = inp.closest('.email-list-item');
        return li ? li.getAttribute('data-corr-pk') : null;
      })
      .filter(Boolean);
  }

  function postAction(action, ids, extra) {
    if (!actionsUrl || !ids.length) return Promise.reject();
    var body = new URLSearchParams();
    body.append('action', action);
    ids.forEach(function (id) {
      body.append('ids', id);
    });
    if (extra && extra.label) body.append('label', extra.label);
    return fetch(actionsUrl, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrfToken,
        'X-Requested-With': 'XMLHttpRequest',
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: body.toString(),
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok || !data.ok) throw new Error(data.error || 'Ошибка');
        return data;
      });
    });
  }

  function reloadList() {
    window.location.reload();
  }

  function bindToolbar() {
    var delBtn = document.querySelector('.email-list-delete');
    var readBtn = document.querySelector('.email-list-read');
    if (delBtn) {
      delBtn.addEventListener('click', function () {
        var ids = selectedIds();
        if (!ids.length) return;
        if (!confirm('Переместить выбранные письма в корзину?')) return;
        postAction('delete', ids).then(reloadList).catch(alertError);
      });
    }
    if (readBtn) {
      readBtn.addEventListener('click', function () {
        var ids = selectedIds();
        if (!ids.length) return;
        postAction('mark_read', ids).then(reloadList).catch(alertError);
      });
    }
    document.querySelectorAll('.dropdown-menu [data-mail-action]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        var ids = selectedIds();
        if (!ids.length && el.getAttribute('data-mail-action') !== 'refresh') {
          alert('Выберите письма в списке');
          return;
        }
        var act = el.getAttribute('data-mail-action');
        if (act === 'refresh') {
          reloadList();
          return;
        }
        var label = el.getAttribute('data-mail-label') || '';
        postAction(act, ids, { label: label }).then(reloadList).catch(alertError);
      });
    });
    var refresh = document.querySelector('.email-refresh');
    if (refresh) {
      refresh.addEventListener('click', function () {
        reloadList();
      });
    }
  }

  function alertError(err) {
    alert(err && err.message ? err.message : 'Не удалось выполнить действие');
  }

  function loadPanel(url, li) {
    if (!url || !contentEl) return;
    contentEl.innerHTML =
      '<div class="text-center py-5 text-muted"><div class="spinner-border text-primary" role="status"></div></div>';
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {
        return r.ok ? r.json() : Promise.reject();
      })
      .then(function (data) {
        if (titleEl) titleEl.textContent = data.title || 'Письмо';
        if (badgeEl) {
          badgeEl.textContent = data.status || '';
          badgeEl.className = 'badge bg-label-secondary rounded-pill';
          badgeEl.classList.toggle('d-none', !data.status);
        }
        contentEl.innerHTML = data.html || '';
        if (li) {
          li.classList.add('email-marked-read');
          var icon = li.querySelector('.email-list-item-actions .email-unread i');
          if (icon) {
            icon.classList.remove('ri-mail-line');
            icon.classList.add('ri-mail-open-line');
          }
        }
        if (typeof PerfectScrollbar !== 'undefined') {
          if (contentEl._delayuPs) contentEl._delayuPs.update();
          else
            contentEl._delayuPs = new PerfectScrollbar(contentEl, {
              wheelPropagation: false,
              suppressScrollX: true,
            });
        }
      })
      .catch(function () {
        contentEl.innerHTML =
          '<div class="alert alert-danger m-4">Не удалось загрузить письмо</div>';
      });
  }

  document.querySelectorAll('.email-list-item[data-panel-url]').forEach(function (item) {
    item.addEventListener('click', function (e) {
      if (e.target.closest('.form-check') || e.target.closest('.email-list-item-actions')) return;
      document.querySelectorAll('.email-list-item').forEach(function (li) {
        li.classList.remove('active');
      });
      item.classList.add('active');
      loadPanel(item.getAttribute('data-panel-url'), item);
    });
    var bookmark = item.querySelector('.email-list-item-bookmark');
    if (bookmark) {
      bookmark.addEventListener('click', function (e) {
        e.stopPropagation();
        var pk = item.getAttribute('data-corr-pk');
        var starred = item.getAttribute('data-starred') === 'true';
        postAction(starred ? 'unstar' : 'star', [pk])
          .then(function () {
            item.setAttribute('data-starred', starred ? 'false' : 'true');
            bookmark.classList.toggle('ri-star-fill', !starred);
            bookmark.classList.toggle('ri-star-line', starred);
          })
          .catch(alertError);
      });
    }
    item.querySelectorAll('.email-list-item-actions li').forEach(function (act) {
      act.addEventListener('click', function (e) {
        e.stopPropagation();
        var pk = item.getAttribute('data-corr-pk');
        if (act.classList.contains('email-delete')) {
          if (!confirm('Удалить письмо?')) return;
          postAction('delete', [pk]).then(function () {
            item.remove();
          }).catch(alertError);
        } else if (act.classList.contains('email-read') || act.classList.contains('email-unread')) {
          var read = item.classList.contains('email-marked-read');
          postAction(read ? 'mark_unread' : 'mark_read', [pk]).then(function () {
            item.classList.toggle('email-marked-read', !read);
          }).catch(alertError);
        }
      });
    });
  });

  if (view) {
    var openPk = view.getAttribute('data-open-pk');
    if (openPk) {
      var first = document.querySelector('.email-list-item[data-corr-pk="' + openPk + '"]');
      if (first) {
        first.classList.add('active');
        loadPanel(first.getAttribute('data-panel-url'), first);
      }
    }
  }

  bindToolbar();
});
