'use strict';

function csrfToken() {
  var el = document.querySelector('[name=csrfmiddlewaretoken]');
  return el ? el.value : '';
}

function postJson(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
      Accept: 'application/json',
    },
    body: JSON.stringify(body || {}),
    credentials: 'same-origin',
  }).then(function (r) {
    return r.json();
  });
}

function markButtonState(btn, state, message, resetMs) {
  if (!btn) return;
  if (!btn.dataset.studioOrigText) {
    btn.dataset.studioOrigText = btn.textContent.trim();
    btn.dataset.studioOrigClass = btn.className;
  }
  btn.disabled = state === 'pending' || state === 'success' || state === 'error';
  var map = {
    pending: { text: message || '…', cls: 'btn-outline-secondary' },
    success: { text: message || 'Готово', cls: 'btn-success' },
    error: { text: message || 'Ошибка', cls: 'btn-danger' },
    confirm: { text: message || 'Подтвердите', cls: 'btn-warning' },
    idle: { text: btn.dataset.studioOrigText, cls: '' },
  };
  var s = map[state] || map.success;
  btn.textContent = s.text;
  if (state === 'idle') {
    btn.className = btn.dataset.studioOrigClass;
    btn.disabled = false;
    return;
  }
  btn.className =
    btn.dataset.studioOrigClass.replace(/\bbtn-(primary|outline-primary|success|danger|warning|outline-secondary)\b/g, '').trim() +
    ' ' +
    s.cls;
  if (resetMs) {
    clearTimeout(btn._studioResetTimer);
    btn._studioResetTimer = setTimeout(function () {
      markButtonState(btn, 'idle');
    }, resetMs);
  }
}

document.addEventListener('DOMContentLoaded', function () {
  var publishBtn = document.getElementById('studioPublishBtn');
  var discardBtn = document.getElementById('studioDiscardBtn');
  var panel = document.getElementById('studioDraftBanner');
  var publishUrl = (panel && panel.getAttribute('data-publish-url')) || '/studio/api/publish/';
  var publishDryRunUrl =
    (panel && panel.getAttribute('data-publish-dry-run-url')) || '/studio/api/publish/dry-run/';
  var discardUrl = (panel && panel.getAttribute('data-discard-url')) || '/studio/api/discard-draft/';
  var commentEl = document.getElementById('studioPublishComment');
  var tagsEl = document.getElementById('studioPublishTags');
  var defaultTagsEl = document.getElementById('studioDefaultPublishTags');
  if (tagsEl && defaultTagsEl && !tagsEl.value.trim() && defaultTagsEl.value.trim()) {
    tagsEl.value = defaultTagsEl.value.trim();
  }
  var publishDryRunBtn = document.getElementById('studioPublishDryRunBtn');
  var publishDryRunResult = document.getElementById('studioPublishDryRunResult');

  var defaultTagsSaveBtn = document.getElementById('studioDefaultTagsSaveBtn');
  var defaultTagsPanel = document.getElementById('studioDefaultTagsPanel');
  if (defaultTagsSaveBtn && defaultTagsPanel) {
    defaultTagsSaveBtn.addEventListener('click', function () {
      var btn = this;
      var url =
        defaultTagsPanel.getAttribute('data-default-tags-url') ||
        '/studio/api/publish/default-tags/';
      var tags = (defaultTagsEl && defaultTagsEl.value ? defaultTagsEl.value : '')
        .split(',')
        .map(function (t) {
          return t.trim();
        })
        .filter(Boolean);
      markButtonState(btn, 'pending', '…');
      postJson(url, { tags: tags })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'Сохранено', 2000);
            if (tagsEl && !tagsEl.value.trim()) {
              tagsEl.value = tags.join(', ');
            }
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 2500);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  }

  var clearPendingBtn = document.getElementById('studioClearPendingTagsBtn');
  if (clearPendingBtn) {
    clearPendingBtn.addEventListener('click', function () {
      var btn = this;
      var url =
        clearPendingBtn.getAttribute('data-clear-pending-url') ||
        '/studio/api/publish/pending-tags/clear/';
      if (!window.confirm('Сбросить pending-теги?')) return;
      markButtonState(btn, 'pending', '…');
      postJson(url, {})
        .then(function (res) {
          if (res.ok) {
            var badge = document.getElementById('studioPendingTagsBadge');
            if (badge) badge.remove();
            btn.remove();
            markButtonState(btn, 'success', 'OK', 1500);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 2500);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  }

  if (publishDryRunBtn) {
    publishDryRunBtn.addEventListener('click', function () {
      var btn = this;
      markButtonState(btn, 'pending', 'Проверка…');
      var dryTags = (tagsEl && tagsEl.value ? tagsEl.value : '')
        .split(',')
        .map(function (t) {
          return t.trim();
        })
        .filter(Boolean);
      postJson(publishDryRunUrl, { tags: dryTags })
        .then(function (res) {
          if (!res.ok) {
            if (publishDryRunResult) {
              publishDryRunResult.classList.remove('d-none');
              publishDryRunResult.innerHTML =
                '<span class="text-danger">' + (res.error || 'Ошибка') + '</span>';
            }
            markButtonState(btn, 'error', 'Ошибка', 2500);
            return;
          }
          if (publishDryRunResult) {
            publishDryRunResult.classList.remove('d-none');
            var versionHint = res.next_version
              ? ' → версия <strong>' + res.next_version + '</strong>'
              : '';
            var tagsHint = '';
            if (res.publish_tags && res.publish_tags.length) {
              tagsHint =
                '<br>Теги публикации: <strong>' +
                res.publish_tags.join(', ') +
                '</strong>';
              var bd = res.publish_tags_breakdown || {};
              var parts = [];
              if (bd.explicit && bd.explicit.length) parts.push('явные: ' + bd.explicit.join(', '));
              if (bd.pending && bd.pending.length) parts.push('pending: ' + bd.pending.join(', '));
              if (bd.default && bd.default.length) parts.push('по умолчанию: ' + bd.default.join(', '));
              if (parts.length) tagsHint += ' <span class="text-muted">(' + parts.join('; ') + ')</span>';
            }
            if (!res.has_changes && !res.policies_drift) {
              publishDryRunResult.innerHTML =
                '<span class="text-success">Отличий от опубликованного нет.' +
                versionHint +
                tagsHint +
                '</span>';
            } else {
              if (res.has_changes) {
                renderDiffSections(res.diff, publishDryRunResult);
                publishDryRunResult.insertAdjacentHTML(
                  'afterbegin',
                  '<span class="text-muted">Черновик vs опубликованное' +
                    versionHint +
                    '<br>Секции: ' +
                    (res.draft_sections || []).join(', ') +
                    tagsHint +
                    '<br></span>'
                );
              } else {
                publishDryRunResult.innerHTML =
                  '<span class="text-muted">Меню/СЭД без изменений' + versionHint + tagsHint + '</span>';
              }
              if (res.policies_diff) {
                renderPoliciesDiff(res.policies_diff, publishDryRunResult);
              }
            }
          }
          markButtonState(btn, 'success', 'Готово', 2000);
        })
        .catch(function () {
          if (publishDryRunResult) {
            publishDryRunResult.classList.remove('d-none');
            publishDryRunResult.textContent = 'Ошибка сети';
          }
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  }

  if (publishBtn) {
    publishBtn.addEventListener('click', function () {
      var btn = this;
      var comment = commentEl ? commentEl.value.trim() : '';
      var tags = tagsEl
        ? tagsEl.value
            .split(',')
            .map(function (t) {
              return t.trim();
            })
            .filter(Boolean)
        : [];
      markButtonState(btn, 'pending', 'Публикация…');
      postJson(publishUrl, { comment: comment, tags: tags })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'Опубликовано: ' + res.version, 1800);
            window.setTimeout(function () {
              window.location.reload();
            }, 900);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка публикации', 3200);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка сети', 3200);
        });
    });
  }

  if (discardBtn) {
    discardBtn.addEventListener('click', function () {
      var btn = this;
      if (btn.dataset.confirming !== '1') {
        btn.dataset.confirming = '1';
        markButtonState(btn, 'confirm', 'Нажмите ещё раз для сброса');
        btn._studioConfirmTimer = window.setTimeout(function () {
          btn.dataset.confirming = '0';
          markButtonState(btn, 'idle');
        }, 4000);
        return;
      }
      window.clearTimeout(btn._studioConfirmTimer);
      btn.dataset.confirming = '0';
      markButtonState(btn, 'pending', 'Сброс…');
      postJson(discardUrl, {})
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'Черновик сброшен', 1600);
            window.setTimeout(function () {
              window.location.reload();
            }, 800);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 3200);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка сети', 3200);
        });
    });
  }

  var scheduleBtn = document.getElementById('studioScheduleBtn');
  var scheduleAtEl = document.getElementById('studioScheduleAt');
  var scheduleUrl = (panel && panel.getAttribute('data-schedule-url')) || '/studio/api/schedule-publish/';

  if (scheduleBtn && scheduleUrl) {
    scheduleBtn.addEventListener('click', function () {
      var btn = this;
      var atVal = scheduleAtEl ? scheduleAtEl.value : '';
      if (!atVal) {
        markButtonState(btn, 'error', 'Укажите дату и время', 2800);
        return;
      }
      var comment = commentEl ? commentEl.value.trim() : '';
      var scheduleTags = (tagsEl && tagsEl.value ? tagsEl.value : '')
        .split(',')
        .map(function (t) {
          return t.trim();
        })
        .filter(Boolean);
      markButtonState(btn, 'pending', 'Планирование…');
      postJson(scheduleUrl, { at: atVal, comment: comment, tags: scheduleTags })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'Запланировано', 1600);
            window.setTimeout(function () {
              window.location.reload();
            }, 800);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 3200);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка сети', 3200);
        });
    });
  }

  var scheduleDryRunBtn = document.getElementById('studioScheduleDryRunBtn');
  var scheduleDryRunUrl =
    (panel && panel.getAttribute('data-schedule-dry-run-url')) || '/studio/api/publish/schedule/dry-run/';
  var publishDryRunResult = document.getElementById('studioPublishDryRunResult');
  if (scheduleDryRunBtn && scheduleDryRunUrl) {
    scheduleDryRunBtn.addEventListener('click', function () {
      var btn = this;
      var atVal = scheduleAtEl ? scheduleAtEl.value : '';
      if (!atVal) {
        markButtonState(btn, 'error', 'Укажите дату', 2800);
        return;
      }
      var comment = commentEl ? commentEl.value.trim() : '';
      var scheduleTags = (tagsEl && tagsEl.value ? tagsEl.value : '')
        .split(',')
        .map(function (t) {
          return t.trim();
        })
        .filter(Boolean);
      markButtonState(btn, 'pending', 'Проверка…');
      postJson(scheduleDryRunUrl, { at: atVal, comment: comment, tags: scheduleTags })
        .then(function (res) {
          if (publishDryRunResult) {
            publishDryRunResult.classList.remove('d-none');
            if (!res.ok) {
              publishDryRunResult.innerHTML = '<span class="text-danger">' + (res.error || 'Ошибка') + '</span>';
              markButtonState(btn, 'error', 'Ошибка', 2800);
              return;
            }
            var tagsHint = '';
            if (res.schedule_publish_tags && res.schedule_publish_tags.length) {
              tagsHint =
                '<br>Теги публикации: <strong>' +
                res.schedule_publish_tags.join(', ') +
                '</strong>';
            } else if (res.publish_tags && res.publish_tags.length) {
              tagsHint =
                '<br>Теги публикации: <strong>' +
                res.publish_tags.join(', ') +
                '</strong>';
            }
            publishDryRunResult.innerHTML =
              '<span class="text-muted">План на ' +
              (res.scheduled_at || atVal).slice(0, 16) +
              ' · следующая версия ' +
              (res.next_version || '—') +
              tagsHint +
              '<br></span>';
            renderCompareDetails(res, publishDryRunResult);
            renderPoliciesDiff(res.policies_diff, publishDryRunResult);
          }
          markButtonState(btn, 'success', 'Готово', 2000);
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка сети', 2800);
        });
    });
  }

  var cancelScheduleBtn = document.getElementById('studioCancelScheduleBtn');
  var scheduledBanner = document.getElementById('studioScheduledBanner');
  var cancelScheduleUrl =
    (scheduledBanner && scheduledBanner.getAttribute('data-schedule-url')) || '/studio/api/schedule-publish/';
  if (cancelScheduleBtn) {
    cancelScheduleBtn.addEventListener('click', function () {
      var btn = this;
      markButtonState(btn, 'pending', 'Отмена…');
      fetch(cancelScheduleUrl, {
        method: 'DELETE',
        headers: { 'X-CSRFToken': csrfToken(), Accept: 'application/json' },
        credentials: 'same-origin',
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'Отменено', 1400);
            window.setTimeout(function () {
              window.location.reload();
            }, 700);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 3200);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка сети', 3200);
        });
    });
  }

  var clonePanel = document.getElementById('studioClonePanel');
  var cloneBtn = document.getElementById('studioCloneBtn');
  var cloneStatus = document.getElementById('studioCloneStatus');
  var cloneUrl = (clonePanel && clonePanel.getAttribute('data-clone-url')) || '/studio/api/clone/';
  if (cloneBtn) {
    cloneBtn.addEventListener('click', function () {
      var btn = this;
      var targetEl = document.getElementById('studioCloneTarget');
      var includeDraftEl = document.getElementById('studioCloneIncludeDraft');
      var targetCode = targetEl ? targetEl.value : '';
      if (!targetCode) {
        if (cloneStatus) cloneStatus.textContent = 'Выберите подсистему';
        return;
      }
      if (btn.dataset.confirming !== '1') {
        btn.dataset.confirming = '1';
        markButtonState(btn, 'confirm', 'Подтвердите клонирование');
        btn._studioConfirmTimer = window.setTimeout(function () {
          btn.dataset.confirming = '0';
          markButtonState(btn, 'idle');
        }, 5000);
        return;
      }
      window.clearTimeout(btn._studioConfirmTimer);
      btn.dataset.confirming = '0';
      markButtonState(btn, 'pending', 'Клонирование…');
      postJson(cloneUrl, {
        target_code: targetCode,
        to_draft: true,
        include_draft: includeDraftEl ? includeDraftEl.checked : false,
      })
        .then(function (res) {
          if (res.ok) {
            if (cloneStatus) {
              cloneStatus.textContent = 'Скопировано в ' + res.target + ' (меню/СЭД в черновик)';
            }
            markButtonState(btn, 'success', 'Готово', 2000);
          } else {
            if (cloneStatus) cloneStatus.textContent = res.error || 'Ошибка';
            markButtonState(btn, 'error', res.error || 'Ошибка', 3200);
          }
        })
        .catch(function () {
          if (cloneStatus) cloneStatus.textContent = 'Ошибка сети';
          markButtonState(btn, 'error', 'Ошибка сети', 3200);
        });
    });
  }

  var importFile = document.getElementById('studioImportFile');
  var importStatus = document.getElementById('studioImportStatus');
  var packagePanel = document.getElementById('studioPackagePanel');
  var importUrl = (packagePanel && packagePanel.getAttribute('data-import-url')) || '/studio/api/import/';
  var packageDiffUrl =
    (packagePanel && packagePanel.getAttribute('data-package-diff-url')) || '/studio/api/package/diff/';
  var packageValidateUrl =
    (packagePanel && packagePanel.getAttribute('data-package-validate-url')) ||
    '/studio/api/package/validate/';
  var packageDiffResult = document.getElementById('studioPackageDiffResult');
  var importRiskPanel = document.getElementById('studioImportRiskPanel');

  function renderImportRisk(risk, container) {
    if (!container) return;
    if (!risk || (!risk.critical || !risk.critical.length) && (!risk.warnings || !risk.warnings.length)) {
      container.classList.add('d-none');
      container.innerHTML = '';
      return;
    }
    var html = '';
    if (risk.blocked && risk.critical && risk.critical.length) {
      html +=
        '<div class="alert alert-danger py-2 mb-2"><strong>Критические изменения</strong> — импорт заблокирован без подтверждения.<ul class="mb-0 mt-1">' +
        risk.critical
          .map(function (r) {
            return '<li>' + r.message + '</li>';
          })
          .join('') +
        '</ul></div>';
    } else if (risk.critical && risk.critical.length) {
      html +=
        '<div class="alert alert-danger py-2 mb-2"><ul class="mb-0">' +
        risk.critical
          .map(function (r) {
            return '<li>' + r.message + '</li>';
          })
          .join('') +
        '</ul></div>';
    }
    if (risk.warnings && risk.warnings.length) {
      html +=
        '<div class="alert alert-warning py-2 mb-0"><strong>Предупреждения</strong><ul class="mb-0 mt-1">' +
        risk.warnings
          .map(function (r) {
            return '<li>' + r.message + '</li>';
          })
          .join('') +
        '</ul></div>';
    }
    container.innerHTML = html;
    container.classList.remove('d-none');
  }

  function renderEntityDiffs(entityDiffs, container) {
    if (!container || !entityDiffs) return;
    var labels = { added: 'добавится', removed: 'удалится', modified: 'изменится' };
    var html = '';
    if (entityDiffs.forms && entityDiffs.forms.length) {
      html +=
        '<div class="alert alert-info py-2 mt-2 mb-0"><strong>Формы</strong><ul class="mb-0 mt-1">' +
        entityDiffs.forms
          .map(function (f) {
            var line = '<li><code>' + f.code + '</code> — ' + (labels[f.change] || f.change);
            if (f.detail) {
              line +=
                ' (+' +
                (f.detail.added || []).length +
                ' / −' +
                (f.detail.removed || []).length +
                ' / ~' +
                (f.detail.changed || []).length +
                ' полей)';
            }
            return line + '</li>';
          })
          .join('') +
        '</ul></div>';
    }
    if (entityDiffs.bpm && entityDiffs.bpm.length) {
      html +=
        '<div class="alert alert-info py-2 mt-2 mb-0"><strong>BPM</strong><ul class="mb-0 mt-1">' +
        entityDiffs.bpm
          .map(function (b) {
            var line = '<li><code>' + b.code + '</code> — ' + (labels[b.change] || b.change);
            if (b.detail) {
              line +=
                ' (+' +
                (b.detail.added || []).length +
                ' / −' +
                (b.detail.removed || []).length +
                ' / ~' +
                (b.detail.changed || []).length +
                ' узлов)';
            }
            return line + '</li>';
          })
          .join('') +
        '</ul></div>';
    }
    if (html) container.insertAdjacentHTML('beforeend', html);
  }

  function renderPoliciesDiff(policiesDiff, container) {
    if (!container || !policiesDiff || !policiesDiff.changed || !policiesDiff.changed.length) return;
    container.insertAdjacentHTML(
      'beforeend',
      '<div class="alert alert-warning py-2 mt-2 mb-0"><strong>Политики</strong> (отличия от последней ревизии):<ul class="mb-0 mt-1">' +
        policiesDiff.changed
          .map(function (row) {
            return (
              '<li><code>' +
              row.attr +
              '</code>: ' +
              (row.before != null ? row.before : '—') +
              ' → ' +
              (row.after != null ? row.after : '—') +
              '</li>'
            );
          })
          .join('') +
        '</ul><span class="text-muted">Не входят в публикацию черновика, но изменены с момента последней ревизии.</span></div>'
    );
  }

  function renderCompareDetails(res, container) {
    if (!container) return;
    var data = res;
    if (res.diff && typeof res.diff === 'object' && res.sections == null) {
      data = Object.assign({}, res.diff, {
        entity_diffs: res.entity_diffs || res.diff.entity_diffs,
        policies_diff: res.policies_diff || res.diff.policies_diff,
      });
    }
    container.innerHTML = '';
    if (data.error) {
      container.innerHTML = '<span class="text-danger">' + data.error + '</span>';
      return;
    }
    var hasSections = data.sections && data.sections.length;
    var hasEntity =
      data.entity_diffs &&
      ((data.entity_diffs.forms && data.entity_diffs.forms.length) ||
        (data.entity_diffs.bpm && data.entity_diffs.bpm.length));
    var hasPolicies = data.policies_diff && data.policies_diff.changed && data.policies_diff.changed.length;
    if (!hasSections && !hasEntity && !hasPolicies) {
      container.innerHTML =
        '<span class="text-success">Отличий нет' +
        (data.unchanged != null ? ' (' + data.unchanged + ' блоков)' : '') +
        '.</span>';
      return;
    }
    renderDiffSections(data, container);
    renderEntityDiffs(data.entity_diffs, container);
    renderPoliciesDiff(data.policies_diff, container);
  }

  function updateCompareExportLink(exportBtn, exportBase, aVal, bVal) {
    if (!exportBtn || !exportBase || !aVal || !bVal) return;
    exportBtn.href =
      exportBase + '?a=' + encodeURIComponent(aVal) + '&b=' + encodeURIComponent(bVal);
    exportBtn.classList.remove('d-none');
  }

  function renderDiffSections(diff, container) {
    if (!container || !diff) return;
    var sections = diff.sections || (diff.diff && diff.diff.sections);
    var changed = diff.changed_sections != null ? diff.changed_sections : diff.diff && diff.diff.changed_sections;
    if (!sections || !sections.length) {
      container.innerHTML = '<span class="text-success">Отличий нет.</span>';
      return;
    }
    container.innerHTML =
      '<p class="mb-1">Изменено блоков: <strong>' +
      changed +
      '</strong></p><ul class="mb-0">' +
      sections
        .map(function (s) {
          return '<li><strong>' + s.label + '</strong> — ' + s.detail + '</li>';
        })
        .join('') +
      '</ul>';
  }

  var packageDiffBtn = document.getElementById('studioPackageDiffBtn');
  if (packageDiffBtn) {
    packageDiffBtn.addEventListener('click', function () {
      var revEl = document.getElementById('studioPackageDiffRevision');
      var revId = revEl && revEl.value;
      if (!revId) {
        if (packageDiffResult) packageDiffResult.textContent = 'Выберите ревизию';
        return;
      }
      markButtonState(packageDiffBtn, 'pending', 'Сравнение…');
      fetch(packageDiffUrl + '?revision_id=' + encodeURIComponent(revId), {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (res) {
          if (!res.ok) {
            if (packageDiffResult) packageDiffResult.innerHTML = '<span class="text-danger">' + (res.error || 'Ошибка') + '</span>';
            markButtonState(packageDiffBtn, 'error', 'Ошибка', 2500);
            return;
          }
          renderCompareDetails(res, packageDiffResult);
          if (packageDiffResult) {
            packageDiffResult.insertAdjacentHTML(
              'afterbegin',
              '<span class="text-muted">Текущее состояние vs ' + (res.revision_label || revId) + '<br></span>'
            );
          }
          markButtonState(packageDiffBtn, 'success', 'Готово', 2000);
        })
        .catch(function () {
          if (packageDiffResult) packageDiffResult.textContent = 'Ошибка сети';
          markButtonState(packageDiffBtn, 'error', 'Ошибка', 2500);
        });
    });
  }

  if (importFile) {
    importFile.addEventListener('change', function () {
      var file = importFile.files && importFile.files[0];
      if (!file) return;
      if (importStatus) importStatus.textContent = 'Загрузка ' + file.name + '…';
      if (importRiskPanel) {
        importRiskPanel.classList.add('d-none');
        importRiskPanel.innerHTML = '';
      }
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var data = JSON.parse(reader.result);
          var revEl = document.getElementById('studioPackageDiffRevision');
          var revId = revEl && revEl.value;
          var dryBody = { package: data, to_draft: true };
          if (revId) dryBody.revision_id = parseInt(revId, 10);
          postJson(packageValidateUrl, data)
            .then(function (validation) {
              if (!validation.ok) {
                if (importStatus) {
                  importStatus.innerHTML =
                    '<span class="text-danger">Пакет невалиден: ' +
                    (validation.errors || []).join('; ') +
                    '</span>';
                }
                throw new Error('validation failed');
              }
              if (validation.warnings && validation.warnings.length && packageDiffResult) {
                packageDiffResult.innerHTML =
                  '<span class="text-warning">Предупреждения: ' + validation.warnings.join('; ') + '</span>';
              }
              return postJson(packageDiffUrl, dryBody);
            })
            .then(function (dry) {
              if (dry && dry.ok) {
                if (packageDiffResult) {
                  renderCompareDetails(dry, packageDiffResult);
                }
                if (dry.risk) {
                  renderImportRisk(dry.risk, importRiskPanel);
                }
              }
              if (dry && dry.risk && dry.risk.blocked) {
                var criticalMsg = (dry.risk.critical || [])
                  .map(function (r) {
                    return r.message;
                  })
                  .join('\n');
                if (!window.confirm('Критические изменения:\n' + criticalMsg + '\n\nПродолжить импорт?')) {
                  if (importStatus) importStatus.textContent = 'Импорт отменён';
                  throw new Error('cancelled');
                }
                var forced = Object.assign({}, data, { force: true });
                return postJson(importUrl, forced);
              }
              return postJson(importUrl, data);
            })
            .then(function (res) {
              if (!res) return;
              if (res.ok) {
                if (importStatus) {
                  importStatus.textContent =
                    'Импортировано: меню ' +
                    (res.stats.menu ? 'да' : 'нет') +
                    ', СЭД ' +
                    (res.stats.correspondence ? 'да' : 'нет') +
                    ', шаблонов ролей ' +
                    res.stats.role_layouts;
                }
                window.setTimeout(function () {
                  window.location.reload();
                }, 1200);
              } else if (importStatus) {
                importStatus.textContent = res.error || 'Ошибка импорта';
              }
            })
            .catch(function (err) {
              if (err && (err.message === 'validation failed' || err.message === 'cancelled')) return;
              if (importStatus) importStatus.textContent = 'Ошибка сети';
            });
        } catch (e) {
          if (importStatus) importStatus.textContent = 'Некорректный JSON';
        }
        importFile.value = '';
      };
      reader.readAsText(file, 'utf-8');
    });
  }

  var comparePanel = document.getElementById('studioRevisionCompare');
  var compareBtn = document.getElementById('studioCompareBtn');
  var compareResult = document.getElementById('studioCompareResult');
  var compareExportBtn = document.getElementById('studioCompareExportBtn');
  if (compareBtn && comparePanel) {
    compareBtn.addEventListener('click', function () {
      var a = document.getElementById('studioCompareA').value;
      var b = document.getElementById('studioCompareB').value;
      var base = comparePanel.getAttribute('data-compare-url');
      var exportBase = comparePanel.getAttribute('data-compare-export-url');
      markButtonState(compareBtn, 'pending', 'Сравнение…');
      fetch(base + '?a=' + encodeURIComponent(a) + '&b=' + encodeURIComponent(b), {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (res) {
          if (!res.ok && res.error) {
            if (compareResult) compareResult.innerHTML = '<span class="text-danger">' + res.error + '</span>';
            markButtonState(compareBtn, 'error', 'Ошибка', 2500);
            return;
          }
          if (compareResult) renderCompareDetails(res, compareResult);
          updateCompareExportLink(compareExportBtn, exportBase, a, b);
          markButtonState(compareBtn, 'success', 'Готово', 2000);
        })
        .catch(function () {
          if (compareResult) compareResult.textContent = 'Ошибка сети';
          markButtonState(compareBtn, 'error', 'Ошибка', 2500);
        });
    });
  }

  var blueprintPanel = document.getElementById('studioBlueprintsPanel');
  var blueprintStatus = document.getElementById('studioBlueprintStatus');
  var blueprintPreviewBox = document.getElementById('studioBlueprintPreview');
  var blueprintUrl = (blueprintPanel && blueprintPanel.getAttribute('data-blueprint-url')) || '/studio/api/blueprints/apply/';
  var blueprintPreviewUrl =
    (blueprintPanel && blueprintPanel.getAttribute('data-blueprint-preview-url')) ||
    '/studio/api/blueprints/preview/';
  var blueprintDryRunUrl =
    (blueprintPanel && blueprintPanel.getAttribute('data-blueprint-dry-run-url')) ||
    '/studio/api/blueprints/dry-run/';
  var blueprintCompareUrl =
    (blueprintPanel && blueprintPanel.getAttribute('data-blueprint-compare-url')) ||
    '/studio/api/blueprints/compare/';
  var blueprintCompareLiveUrl =
    (blueprintPanel && blueprintPanel.getAttribute('data-blueprint-compare-live-url')) ||
    '/studio/api/blueprints/compare/live/';
  var blueprintPackageCompareUrl =
    (blueprintPanel && blueprintPanel.getAttribute('data-blueprint-package-compare-url')) ||
    '/studio/api/blueprints/compare/package/';

  function collectBlueprintRoleMap(blueprintId) {
    var roleMap = {};
    var panel = document.querySelector('.studioBpRoleMap[data-blueprint-id="' + blueprintId + '"]');
    if (!panel) return roleMap;
    panel.querySelectorAll('.studioBpRoleSelect').forEach(function (sel) {
      var from = sel.getAttribute('data-from');
      if (from) roleMap[from] = sel.value;
    });
    return roleMap;
  }

  function renderBlueprintPreview(data) {
    if (!blueprintPreviewBox) return;
    blueprintPreviewBox.classList.remove('d-none');
    var lines = [
      '<strong>' + (data.name || data.blueprint) + '</strong>',
      '<span class="text-muted">' + (data.description || '') + '</span>',
      'В черновик: ' + (data.draft_sections || []).join(', '),
      'Меню: ' + (data.menu_sections || 0) + ' секций, ' + (data.menu_items || 0) + ' пунктов',
      'СЭД: ' + (data.correspondence_steps || []).join(' → '),
    ];
    if (data.role_layouts && data.role_layouts.length) {
      lines.push(
        'Раскладки: ' +
          data.role_layouts_resolved +
          '/' +
          data.role_layouts.length +
          ' — ' +
          data.role_layouts
            .map(function (r) {
              return (
                r.role_code +
                '→' +
                r.mapped_to +
                (r.resolved ? ' (' + r.role_name + ')' : ' <span class="text-danger">не найдена</span>')
              );
            })
            .join(', ')
      );
    }
    blueprintPreviewBox.innerHTML = lines.join('<br>');
  }

  document.querySelectorAll('.studioBlueprintPreviewBtn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-blueprint-id');
      markButtonState(btn, 'pending', 'Загрузка…');
      postJson(blueprintPreviewUrl, { blueprint_id: id, role_map: collectBlueprintRoleMap(id) })
        .then(function (res) {
          if (res.ok) {
            renderBlueprintPreview(res);
            markButtonState(btn, 'success', 'Предпросмотр', 1800);
          } else {
            if (blueprintStatus) blueprintStatus.textContent = res.error || 'Ошибка';
            markButtonState(btn, 'error', 'Ошибка', 2500);
          }
        })
        .catch(function () {
          if (blueprintStatus) blueprintStatus.textContent = 'Ошибка сети';
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  });

  document.querySelectorAll('.studioBlueprintDryRunBtn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-blueprint-id');
      markButtonState(btn, 'pending', 'Dry-run…');
      postJson(blueprintDryRunUrl, { blueprint_id: id, role_map: collectBlueprintRoleMap(id) })
        .then(function (res) {
            if (res.ok) {
            renderBlueprintPreview(res);
            if (res.diff && blueprintPreviewBox) {
              renderCompareDetails(res, blueprintPreviewBox);
              if (res.overwrites_draft) {
                blueprintPreviewBox.insertAdjacentHTML(
                  'afterbegin',
                  '<span class="text-warning">Перезапишет существующий черновик.<br></span>'
                );
              }
            }
            markButtonState(btn, 'success', 'Dry-run', 1800);
          } else {
            if (blueprintStatus) blueprintStatus.textContent = res.error || 'Ошибка';
            markButtonState(btn, 'error', 'Ошибка', 2500);
          }
        })
        .catch(function () {
          if (blueprintStatus) blueprintStatus.textContent = 'Ошибка сети';
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  });

  document.querySelectorAll('.studioBlueprintCompareBtn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-blueprint-id');
      var revEl = document.getElementById('studioBlueprintCompareRev');
      var revId = revEl && revEl.value;
      if (!revId) {
        if (blueprintStatus) blueprintStatus.textContent = 'Выберите ревизию';
        return;
      }
      markButtonState(btn, 'pending', 'Сравнение…');
      var url =
        blueprintCompareUrl +
        '?blueprint_id=' +
        encodeURIComponent(id) +
        '&revision_id=' +
        encodeURIComponent(revId);
      fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (r) {
          return r.json();
        })
        .then(function (res) {
          if (res.ok) {
            renderBlueprintPreview(res);
            if (res.diff && blueprintPreviewBox) {
              renderCompareDetails(res, blueprintPreviewBox);
              blueprintPreviewBox.insertAdjacentHTML(
                'afterbegin',
                '<strong>Шаблон vs ' + (res.revision_label || revId) + '</strong><br>'
              );
            }
            if (blueprintStatus) blueprintStatus.textContent = 'Сравнение выполнено';
            markButtonState(btn, 'success', 'Готово', 2000);
          } else {
            if (blueprintStatus) blueprintStatus.textContent = res.error || 'Ошибка';
            markButtonState(btn, 'error', 'Ошибка', 2500);
          }
        })
        .catch(function () {
          if (blueprintStatus) blueprintStatus.textContent = 'Ошибка сети';
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  });

  document.querySelectorAll('.studioBlueprintCompareLiveBtn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-blueprint-id');
      markButtonState(btn, 'pending', 'Сравнение…');
      var url =
        blueprintCompareLiveUrl + '?blueprint_id=' + encodeURIComponent(id);
      fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (r) {
          return r.json();
        })
        .then(function (res) {
          if (res.ok) {
            renderBlueprintPreview(res);
            if (res.diff && blueprintPreviewBox) {
              renderCompareDetails(res, blueprintPreviewBox);
              blueprintPreviewBox.insertAdjacentHTML(
                'afterbegin',
                '<strong>Шаблон vs текущая (' + (res.live_version || 'live') + ')</strong><br>'
              );
            }
            if (blueprintStatus) blueprintStatus.textContent = 'Сравнение с текущей выполнено';
            markButtonState(btn, 'success', 'Готово', 2000);
          } else {
            if (blueprintStatus) blueprintStatus.textContent = res.error || 'Ошибка';
            markButtonState(btn, 'error', 'Ошибка', 2500);
          }
        })
        .catch(function () {
          if (blueprintStatus) blueprintStatus.textContent = 'Ошибка сети';
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  });

  document.querySelectorAll('.studioBlueprintBtn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = btn.getAttribute('data-blueprint-id');
      markButtonState(btn, 'pending', 'Применение…');
      postJson(blueprintUrl, { blueprint_id: id, role_map: collectBlueprintRoleMap(id) })
        .then(function (res) {
          if (res.ok) {
            if (blueprintStatus) {
              blueprintStatus.textContent =
                'Шаблон применён: ' +
                (res.applied || []).join(', ') +
                (res.role_layouts ? ' (' + res.role_layouts + ' раскладок)' : '');
            }
            markButtonState(btn, 'success', 'В черновике', 2000);
            window.setTimeout(function () {
              window.location.reload();
            }, 1000);
          } else {
            if (blueprintStatus) blueprintStatus.textContent = res.error || 'Ошибка';
            markButtonState(btn, 'error', 'Ошибка', 2500);
          }
        })
        .catch(function () {
          if (blueprintStatus) blueprintStatus.textContent = 'Ошибка сети';
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  });

  var revTable = document.getElementById('studioRevisionTable');
  var restoreUrl = (revTable && revTable.getAttribute('data-restore-url')) || '/studio/api/revisions/restore/';
  var restoreDryRunUrl =
    (revTable && revTable.getAttribute('data-restore-dry-run-url')) ||
    '/studio/api/revisions/restore/dry-run/';
  var restorePreviewResult = document.getElementById('studioRestorePreviewResult');

  document.querySelectorAll('.studioRestorePreviewBtn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var revId = btn.getAttribute('data-revision-id');
      var version = btn.getAttribute('data-version') || revId;
      markButtonState(btn, 'pending', '…');
      postJson(restoreDryRunUrl, { revision_id: parseInt(revId, 10), mode: 'apply' })
        .then(function (res) {
          if (!restorePreviewResult) return;
          restorePreviewResult.classList.remove('d-none');
          if (!res.ok) {
            restorePreviewResult.innerHTML =
              '<span class="text-danger">' + (res.error || 'Ошибка') + '</span>';
            markButtonState(btn, 'error', 'Ошибка', 2500);
            return;
          }
          restorePreviewResult.innerHTML = '';
          restorePreviewResult.insertAdjacentHTML(
            'afterbegin',
            '<span class="text-muted">Откат к <strong>' +
              version +
              '</strong>: текущее → снимок ревизии<br></span>'
          );
          if (res.has_changes) {
            renderDiffSections(res.diff, restorePreviewResult);
          } else {
            restorePreviewResult.insertAdjacentHTML(
              'beforeend',
              '<span class="text-success">Конфигурация совпадает со снимком.</span>'
            );
          }
          if (res.policies_diff) {
            var polBox = document.createElement('div');
            restorePreviewResult.appendChild(polBox);
            if (res.policies_diff.changed && res.policies_diff.changed.length) {
              polBox.innerHTML =
                '<div class="alert alert-warning py-2 mt-2 mb-0"><strong>Политики</strong><ul class="mb-0 mt-1">' +
                res.policies_diff.changed
                  .map(function (row) {
                    return (
                      '<li><code>' +
                      row.attr +
                      '</code>: ' +
                      row.before +
                      ' → ' +
                      row.after +
                      '</li>'
                    );
                  })
                  .join('') +
                '</ul></div>';
            }
          }
          if (res.risk) {
            renderImportRisk(res.risk, restorePreviewResult);
          }
          if (res.entity_diffs) {
            renderEntityDiffs(res.entity_diffs, restorePreviewResult);
          }
          markButtonState(btn, 'success', 'Готово', 2000);
        })
        .catch(function () {
          if (restorePreviewResult) {
            restorePreviewResult.classList.remove('d-none');
            restorePreviewResult.textContent = 'Ошибка сети';
          }
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  });

  function bindRestore(btn, mode) {
    if (!btn) return;
    btn.addEventListener('click', function () {
      var revId = btn.getAttribute('data-revision-id');
      var version = btn.getAttribute('data-version') || revId;
      if (mode === 'apply' && btn.dataset.confirming !== '1') {
        btn.dataset.confirming = '1';
        markButtonState(btn, 'confirm', 'Подтвердите откат');
        btn._studioConfirmTimer = window.setTimeout(function () {
          btn.dataset.confirming = '0';
          markButtonState(btn, 'idle');
        }, 5000);
        return;
      }
      if (mode === 'apply') {
        window.clearTimeout(btn._studioConfirmTimer);
        btn.dataset.confirming = '0';
      }
      markButtonState(btn, 'pending', mode === 'apply' ? 'Откат…' : 'Восстановление…');
      var body = { revision_id: parseInt(revId, 10), mode: mode };
      if (btn.dataset.forceRestore === '1') {
        body.force = true;
        btn.dataset.forceRestore = '0';
      }
      postJson(restoreUrl, body)
        .then(function (res) {
          if (res.ok) {
            markButtonState(
              btn,
              'success',
              mode === 'apply' ? 'Откат: ' + (res.version || version) : 'В черновике',
              2000
            );
            window.setTimeout(function () {
              window.location.reload();
            }, 1000);
          } else if (res.blocked && res.risk) {
            var criticalMsg = (res.risk.critical || [])
              .map(function (r) {
                return r.message;
              })
              .join('\n');
            if (
              window.confirm(
                'Критические изменения при откате:\n' + criticalMsg + '\n\nПродолжить с force?'
              )
            ) {
              btn.dataset.forceRestore = '1';
              btn.dataset.confirming = '1';
              btn.click();
            } else {
              markButtonState(btn, 'error', 'Отменено', 2500);
            }
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 3000);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка сети', 3000);
        });
    });
  }

  document.querySelectorAll('.studioRestoreDraftBtn').forEach(function (btn) {
    bindRestore(btn, 'draft');
  });
  document.querySelectorAll('.studioRestoreApplyBtn').forEach(function (btn) {
    bindRestore(btn, 'apply');
  });

  var revInlinePanel = document.getElementById('studioRevisionInlineCompare');
  var revInlineBtn = document.getElementById('studioRevInlineCompareBtn');
  var revInlineResult = document.getElementById('studioRevInlineCompareResult');
  var revInlineExportBtn = document.getElementById('studioRevInlineExportBtn');
  if (revInlineBtn && revInlinePanel) {
    revInlineBtn.addEventListener('click', function () {
      var a = document.getElementById('studioRevCompareA');
      var b = document.getElementById('studioRevCompareB');
      var base = revInlinePanel.getAttribute('data-compare-url');
      var exportBase = revInlinePanel.getAttribute('data-compare-export-url');
      if (!a || !b || !base) return;
      markButtonState(revInlineBtn, 'pending', '…');
      fetch(base + '?a=' + encodeURIComponent(a.value) + '&b=' + encodeURIComponent(b.value), {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (res) {
          if (!revInlineResult) return;
          revInlineResult.classList.remove('d-none');
          if (res.error) {
            revInlineResult.innerHTML = '<span class="text-danger">' + res.error + '</span>';
            markButtonState(revInlineBtn, 'error', 'Ошибка', 2500);
            return;
          }
          revInlineResult.innerHTML = '';
          renderCompareDetails(res, revInlineResult);
          revInlineResult.insertAdjacentHTML(
            'afterbegin',
            '<span class="text-muted">' +
              (a.options[a.selectedIndex] ? a.options[a.selectedIndex].text : a.value) +
              ' vs ' +
              (b.options[b.selectedIndex] ? b.options[b.selectedIndex].text : b.value) +
              '<br></span>'
          );
          updateCompareExportLink(revInlineExportBtn, exportBase, a.value, b.value);
          markButtonState(revInlineBtn, 'success', 'Готово', 2000);
        })
        .catch(function () {
          if (revInlineResult) {
            revInlineResult.classList.remove('d-none');
            revInlineResult.textContent = 'Ошибка сети';
          }
          markButtonState(revInlineBtn, 'error', 'Ошибка', 2500);
        });
    });
  }

  var pruneBtn = document.getElementById('studioPruneBtn');
  if (pruneBtn) {
    pruneBtn.addEventListener('click', function () {
      var keepEl = document.getElementById('studioPruneKeep');
      var keep = keepEl ? parseInt(keepEl.value, 10) || 50 : 50;
      var url = pruneBtn.getAttribute('data-prune-url');
      markButtonState(pruneBtn, 'pending', '…');
      postJson(url, { keep: keep, dry_run: true })
        .then(function (preview) {
          if (!preview.ok) {
            markButtonState(pruneBtn, 'error', preview.error || 'Ошибка', 3000);
            return null;
          }
          var msg =
            'Будет удалено ревизий: ' +
            preview.would_delete +
            (preview.sample_labels && preview.sample_labels.length
              ? '\nПримеры: ' + preview.sample_labels.join(', ')
              : '');
          if (!window.confirm(msg + '\n\nПродолжить?')) {
            markButtonState(pruneBtn, 'error', 'Отменено', 2000);
            return null;
          }
          return postJson(url, { keep: keep, dry_run: false });
        })
        .then(function (res) {
          if (!res) return;
          if (res.ok) {
            markButtonState(pruneBtn, 'success', '−' + res.deleted, 2000);
            window.setTimeout(function () {
              window.location.reload();
            }, 900);
          } else {
            markButtonState(pruneBtn, 'error', res.error || 'Ошибка', 3000);
          }
        })
        .catch(function () {
          markButtonState(pruneBtn, 'error', 'Ошибка', 3000);
        });
    });
  }

  document.querySelectorAll('.studioRevPinBtn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var revId = btn.getAttribute('data-revision-id');
      var pinned = btn.getAttribute('data-pinned') === '1';
      var pinUrl = (revTable && revTable.getAttribute('data-pin-url')) || '/studio/api/revisions/pin/';
      markButtonState(btn, 'pending', '…');
      postJson(pinUrl, { revision_id: parseInt(revId, 10), pinned: !pinned })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', pinned ? 'Откреплено' : 'Закреплено', 1200);
            window.setTimeout(function () {
              window.location.reload();
            }, 700);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 2500);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  });

  document.querySelectorAll('.studioRevMetaBtn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var revId = btn.getAttribute('data-revision-id');
      var metaUrl =
        (revTable && revTable.getAttribute('data-meta-url')) || '/studio/api/revisions/meta/';
      var comment = window.prompt('Комментарий к ревизии:', btn.getAttribute('data-comment') || '');
      if (comment === null) return;
      var tagsRaw = window.prompt(
        'Теги (через запятую):',
        btn.getAttribute('data-tags') || ''
      );
      if (tagsRaw === null) return;
      var tags = tagsRaw
        .split(',')
        .map(function (t) {
          return t.trim();
        })
        .filter(Boolean);
      markButtonState(btn, 'pending', '…');
      postJson(metaUrl, {
        revision_id: parseInt(revId, 10),
        comment: comment,
        tags: tags,
      })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'Сохранено', 1200);
            window.setTimeout(function () {
              window.location.reload();
            }, 700);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 2500);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  });

  var bulkTagsBtn = document.getElementById('studioRevisionBulkTagsBtn');
  if (bulkTagsBtn) {
    bulkTagsBtn.addEventListener('click', function () {
      var btn = this;
      var bulkUrl =
        (revTable && revTable.getAttribute('data-bulk-tags-url')) ||
        btn.getAttribute('data-bulk-tags-url') ||
        '/studio/api/revisions/tags/bulk/';
      var idsRaw = window.prompt(
        'ID ревизий через запятую (пусто = все на странице):',
        ''
      );
      if (idsRaw === null) return;
      var revisionIds = idsRaw
        ? idsRaw
            .split(',')
            .map(function (x) {
              return parseInt(x.trim(), 10);
            })
            .filter(function (n) {
              return !isNaN(n);
            })
        : Array.prototype.slice
            .call(document.querySelectorAll('.studioRevMetaBtn'))
            .map(function (el) {
              return parseInt(el.getAttribute('data-revision-id'), 10);
            });
      if (!revisionIds.length) {
        window.alert('Нет ревизий для обновления');
        return;
      }
      var tagsRaw = window.prompt('Теги (через запятую):', '');
      if (tagsRaw === null) return;
      var tags = tagsRaw
        .split(',')
        .map(function (t) {
          return t.trim();
        })
        .filter(Boolean);
      var mode = window.prompt('Режим: set | add | remove', 'add');
      if (mode === null) return;
      markButtonState(btn, 'pending', '…');
      postJson(bulkUrl, { revision_ids: revisionIds, tags: tags, mode: mode || 'add' })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'Обновлено: ' + (res.count || 0), 2000);
            window.setTimeout(function () {
              window.location.reload();
            }, 800);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 2500);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  }

  var complianceSchedulePanel = document.getElementById('studioComplianceSchedulePanel');
  var complianceScheduleSaveBtn = document.getElementById('studioComplianceScheduleSaveBtn');
  if (complianceScheduleSaveBtn && complianceSchedulePanel) {
    complianceScheduleSaveBtn.addEventListener('click', function () {
      var btn = this;
      var enabledEl = document.getElementById('studioComplianceScheduleEnabled');
      var intervalEl = document.getElementById('studioComplianceScheduleInterval');
      var tagEl = document.getElementById('studioComplianceScheduleTag');
      var scheduleUrl =
        complianceSchedulePanel.getAttribute('data-compliance-schedule-url') ||
        '/studio/api/compliance/schedule/';
      markButtonState(btn, 'pending', '…');
      postJson(scheduleUrl, {
        enabled: !!(enabledEl && enabledEl.checked),
        interval_days: parseInt((intervalEl && intervalEl.value) || '30', 10),
        mask_pii: false,
        revision_tag: tagEl && tagEl.value ? tagEl.value.trim() : '',
      })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'OK', 1500);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 2500);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  }

  var complianceExportBtn = document.getElementById('studioComplianceExportBtn');
  var complianceTagFilter = document.getElementById('studioComplianceTagFilter');
  if (complianceExportBtn && complianceTagFilter) {
    var baseComplianceUrl = complianceExportBtn.getAttribute('href') || '';
    function syncComplianceExportUrl() {
      var tag = complianceTagFilter.value.trim();
      complianceExportBtn.href = tag
        ? baseComplianceUrl + (baseComplianceUrl.indexOf('?') >= 0 ? '&' : '?') + 'tag=' + encodeURIComponent(tag)
        : baseComplianceUrl;
    }
    complianceTagFilter.addEventListener('change', syncComplianceExportUrl);
    syncComplianceExportUrl();
  }

  var setupPanel = document.getElementById('studioSetupWizard');
  var setupUrl = (setupPanel && setupPanel.getAttribute('data-setup-url')) || '/studio/api/setup/';
  var setupStatus = document.getElementById('studioSetupStatus');
  var setupDismiss = document.getElementById('studioSetupDismiss');

  function setupPost(body, btn) {
    if (btn) markButtonState(btn, 'pending', '…');
    return postJson(setupUrl, body).then(function (res) {
      if (!res.ok && res.error) {
        if (setupStatus) setupStatus.textContent = res.error;
        if (btn) markButtonState(btn, 'error', 'Ошибка', 2500);
        return res;
      }
      if (setupStatus && res.percent !== undefined) {
        setupStatus.textContent = 'Прогресс: ' + res.percent + '%';
      }
      if (btn) markButtonState(btn, 'success', 'Готово', 1500);
      window.setTimeout(function () {
        window.location.reload();
      }, 800);
      return res;
    });
  }

  document.querySelectorAll('.studioSetupActionBtn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var action = btn.getAttribute('data-action');
      var body = { action: action };
      if (action === 'blueprint') {
        var sel = document.querySelector('.studioSetupBlueprintSelect');
        body.blueprint_id = sel ? sel.value : 'operator_daily';
      }
      setupPost(body, btn);
    });
  });

  if (setupDismiss) {
    setupDismiss.addEventListener('click', function () {
      setupPost({ action: 'dismiss' }, setupDismiss);
    });
  }

  var blueprintImport = document.getElementById('studioBlueprintImportFile');
  if (blueprintImport) {
    blueprintImport.addEventListener('change', function () {
      var file = blueprintImport.files && blueprintImport.files[0];
      if (!file) return;
      var bpPanel = document.getElementById('studioBlueprintsPanel');
      var blueprintUrl =
        (bpPanel && bpPanel.getAttribute('data-blueprint-url')) || '/studio/api/blueprints/apply/';
      var blueprintValidateUrl =
        (bpPanel && bpPanel.getAttribute('data-blueprint-validate-url')) ||
        '/studio/api/blueprints/validate/';
      var blueprintDryRunUrl =
        (bpPanel && bpPanel.getAttribute('data-blueprint-dry-run-url')) ||
        '/studio/api/blueprints/dry-run/';
      var reader = new FileReader();
      reader.onload = function () {
        try {
          var data = JSON.parse(reader.result);
          var st = document.getElementById('studioBlueprintStatus');
          if (st) st.textContent = 'Проверка шаблона…';
          postJson(blueprintValidateUrl, data)
            .then(function (validation) {
              if (!validation.ok) {
                if (st) {
                  st.innerHTML =
                    '<span class="text-danger">Шаблон невалиден: ' +
                    (validation.errors || []).join('; ') +
                    '</span>';
                }
                throw new Error('validation failed');
              }
              return postJson(blueprintDryRunUrl, { package: data });
            })
            .then(function (dry) {
              if (dry && dry.ok && blueprintPreviewBox) {
                blueprintPreviewBox.classList.remove('d-none');
                renderCompareDetails(dry, blueprintPreviewBox);
              }
              if (!window.confirm('Применить шаблон в черновик?')) {
                if (st) st.textContent = 'Импорт отменён';
                throw new Error('cancelled');
              }
              return postJson(blueprintUrl, data);
            })
            .then(function (res) {
              if (res && res.ok) window.location.reload();
              else if (st) st.textContent = (res && res.error) || 'Ошибка импорта';
            })
            .catch(function (err) {
              if (err && (err.message === 'validation failed' || err.message === 'cancelled')) return;
              if (st) st.textContent = 'Ошибка сети';
            });
        } catch (e) {
          var st2 = document.getElementById('studioBlueprintStatus');
          if (st2) st2.textContent = 'Некорректный JSON';
        }
        blueprintImport.value = '';
      };
      reader.readAsText(file, 'utf-8');
    });
  }

  var activityNotifyBtn = document.getElementById('studioActivityNotifyBtn');
  if (activityNotifyBtn) {
    activityNotifyBtn.addEventListener('click', function () {
      var btn = this;
      var notifyUrl =
        activityNotifyBtn.getAttribute('data-notify-url') || '/studio/api/activity/notify/';
      markButtonState(btn, 'pending', 'Отправка…');
      postJson(notifyUrl, { days: 7 })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'Отправлено: ' + (res.notified || 0), 3000);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 2500);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  }

  var activityPanel = document.getElementById('studioActivityPanel');
  var activityScheduleSaveBtn = document.getElementById('studioActivityScheduleSaveBtn');
  if (activityScheduleSaveBtn && activityPanel) {
    activityScheduleSaveBtn.addEventListener('click', function () {
      var btn = this;
      var enabledEl = document.getElementById('studioActivityScheduleEnabled');
      var intervalEl = document.getElementById('studioActivityScheduleInterval');
      var scheduleUrl =
        activityPanel.getAttribute('data-activity-schedule-url') ||
        '/studio/api/activity/schedule/';
      markButtonState(btn, 'pending', 'Сохранение…');
      postJson(scheduleUrl, {
        enabled: !!(enabledEl && enabledEl.checked),
        interval_days: parseInt((intervalEl && intervalEl.value) || '7', 10),
        digest_days: 7,
      })
        .then(function (res) {
          if (res.ok) {
            markButtonState(btn, 'success', 'Сохранено', 2000);
          } else {
            markButtonState(btn, 'error', res.error || 'Ошибка', 2500);
          }
        })
        .catch(function () {
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  }

  var policiesDiffBtn = document.getElementById('studioPoliciesDiff');
  var policiesDiffResult = document.getElementById('studioPoliciesDiffResult');
  var policiesPanel = document.getElementById('studioPoliciesPanel');
  var policiesDiffUrl = policiesPanel && policiesPanel.getAttribute('data-diff-url');
  if (policiesDiffBtn && policiesDiffUrl) {
    policiesDiffBtn.addEventListener('click', function () {
      var btn = this;
      markButtonState(btn, 'pending', 'Сравнение…');
      var revEl = document.getElementById('studioPoliciesDiffRevision');
      var url = policiesDiffUrl;
      if (revEl && revEl.value) url += '?revision_id=' + encodeURIComponent(revEl.value);
      fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (r) {
          return r.json();
        })
        .then(function (res) {
          if (!res.ok && res.error) {
            if (policiesDiffResult) policiesDiffResult.textContent = res.error;
            markButtonState(btn, 'error', 'Ошибка', 2500);
            return;
          }
          if (!res.changed || !res.changed.length) {
            if (policiesDiffResult) {
              policiesDiffResult.innerHTML =
                '<span class="text-success">Совпадает с ' + (res.revision_label || 'ревизией') + '.</span>';
            }
          } else if (policiesDiffResult) {
            policiesDiffResult.innerHTML =
              '<span class="text-muted">База: ' +
              (res.revision_label || '—') +
              '</span><ul class="mb-0 mt-1">' +
              res.changed
                .map(function (c) {
                  return '<li>' + c.attr + ': ' + c.before + ' → ' + c.after + '</li>';
                })
                .join('') +
              '</ul>';
          }
          markButtonState(btn, 'success', 'Готово', 2000);
        })
        .catch(function () {
          if (policiesDiffResult) policiesDiffResult.textContent = 'Ошибка сети';
          markButtonState(btn, 'error', 'Ошибка', 2500);
        });
    });
  }

  var hubTabRoot = document.querySelector('.studio-hub-tabs');
  if (hubTabRoot && typeof bootstrap !== 'undefined' && bootstrap.Tab) {
    var hubParams = new URLSearchParams(window.location.search);
    var hubTabBtnId = null;
    if (hubParams.get('rev_tag') || hubParams.get('rev_q')) {
      hubTabBtnId = 'tab-revisions-btn';
    } else if (hubParams.get('audit_action') || hubParams.get('forced') || hubParams.get('audit_rev_tag')) {
      hubTabBtnId = 'tab-journal-btn';
    } else {
      var hubHash = (window.location.hash || '').replace('#', '');
      var hashMap = {
        revisions: 'tab-revisions-btn',
        export: 'tab-export-btn',
        blueprints: 'tab-blueprints-btn',
        journal: 'tab-journal-btn',
      };
      hubTabBtnId = hashMap[hubHash] || null;
    }
    if (hubTabBtnId) {
      var hubTabBtn = document.getElementById(hubTabBtnId);
      if (hubTabBtn) {
        bootstrap.Tab.getOrCreateInstance(hubTabBtn).show();
      }
    }
    hubTabRoot.querySelectorAll('[data-bs-toggle="tab"]').forEach(function (el) {
      el.addEventListener('shown.bs.tab', function () {
        var id = el.id || '';
        var slug = id.replace('tab-', '').replace('-btn', '');
        if (slug && window.history && window.history.replaceState) {
          var url = new URL(window.location.href);
          url.hash = slug;
          window.history.replaceState(null, '', url.pathname + url.search + url.hash);
        }
      });
    });
  }
});
