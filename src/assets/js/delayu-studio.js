'use strict';

document.addEventListener('DOMContentLoaded', function () {
  var root = document.querySelector('[data-studio]');
  if (!root) return;
  var kind = root.getAttribute('data-studio');
  if (kind === 'forms') initFormBuilder(root);
  else if (kind === 'bpm') initBpmEditor(root);
  else if (kind === 'menu') initMenuEditor(root);
  else if (kind === 'dashboard') initDashboardEditor(root);
  else if (kind === 'correspondence') initCorrEditor(root);
  else if (kind === 'print') initPrintEditor(root);
  else if (kind === 'permissions') initPermEditor(root);
  else if (kind === 'nsi') initNsiEditor(root);
  else if (kind === 'integration') initPipeEditor(root);
  else if (kind === 'cabinet') initCabinetEditor(root);
  else if (kind === 'today') initTodayEditor(root);
});

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
    body: JSON.stringify(body),
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
  btn.disabled = state !== 'idle';
  var map = {
    success: { text: message || 'Сохранено', cls: 'btn-success' },
    draft: { text: message || 'Сохранено в черновик', cls: 'btn-success' },
    error: { text: message || 'Ошибка', cls: 'btn-danger' },
    hint: { text: message || '', cls: 'btn-outline-secondary' },
  };
  var s = map[state] || map.success;
  btn.textContent = s.text;
  btn.className =
    btn.dataset.studioOrigClass.replace(/\bbtn-(primary|outline-primary|success|danger|outline-secondary)\b/g, '').trim() +
    ' ' +
    s.cls;
  if (resetMs) {
    clearTimeout(btn._studioResetTimer);
    btn._studioResetTimer = setTimeout(function () {
      btn.textContent = btn.dataset.studioOrigText;
      btn.className = btn.dataset.studioOrigClass;
      btn.disabled = false;
    }, resetMs);
  }
}

function handleStudioSave(btn, res, options) {
  options = options || {};
  if (res.ok) {
    if (res.draft) {
      markButtonState(btn, 'draft', options.draftMsg || 'Сохранено в черновик', 2800);
    } else {
      markButtonState(btn, 'success', options.okMsg || 'Сохранено', 2200);
    }
  } else {
    markButtonState(btn, 'error', res.error || 'Ошибка', 3200);
  }
}

function readJson(id, fallback) {
  var el = document.getElementById(id);
  if (!el) return fallback;
  try {
    return JSON.parse(el.textContent || '[]');
  } catch (e) {
    return fallback;
  }
}

function uid() {
  return 'n' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

/* --- Form builder --- */
function initFormBuilder(root) {
  var canvas = document.getElementById('studioFormCanvas');
  var preview = document.getElementById('studioFormPreview');
  var schema = readJson('studioFormSchemaJson', []);
  var nsiList = readJson('studioNsiJson', []);
  var regList = readJson('studioRegistriesJson', []);
  var libBlocks = readJson('studioFieldLibraryJson', []);
  var fields = Array.isArray(schema) ? schema.slice() : [];
  var libSel = document.getElementById('studioFieldLibrary');
  if (libSel) {
    libBlocks.forEach(function (b) {
      var opt = document.createElement('option');
      opt.value = b.name;
      opt.textContent = b.name;
      libSel.appendChild(opt);
    });
    document.getElementById('studioFieldLibraryAdd').onclick = function () {
      var name = libSel.value;
      if (!name) return;
      var block = libBlocks.find(function (b) {
        return b.name === name;
      });
      if (!block || !block.fields) return;
      block.fields.forEach(function (f) {
        fields.push(JSON.parse(JSON.stringify(f)));
      });
      render();
    };
  }

  function renderPreview() {
    if (!preview) return;
    preview.innerHTML = '';
    if (!fields.length) {
      preview.innerHTML = '<p class="text-muted small mb-0">Добавьте поля для предпросмотра</p>';
      return;
    }
    var sample = {};
    fields.forEach(function (f) {
      if (f.type === 'section') return;
      sample[f.key] = f.type === 'number' ? '10' : 'пример';
    });
    var currentSec = null;
    fields.forEach(function (f) {
      if (f.type === 'section') {
        currentSec = document.createElement('div');
        currentSec.className = 'mb-2';
        currentSec.innerHTML = '<div class="fw-medium small border-bottom pb-1 mb-2">' + (f.label || 'Секция') + '</div>';
        preview.appendChild(currentSec);
        return;
      }
      var visible = true;
      if (f.visible_when && f.visible_when.field) {
        var sv = sample[f.visible_when.field] || '';
        if (f.visible_when.filled) visible = !!String(sv).trim();
        else if (f.visible_when.equals !== undefined) visible = String(sv) === String(f.visible_when.equals);
      }
      var wrap = document.createElement('div');
      wrap.className = 'mb-2' + (visible ? '' : ' opacity-50');
      var hint = f.type === 'lookup' ? ' (реестр)' : f.type || 'text';
      wrap.innerHTML =
        '<label class="form-label small mb-0">' +
        (f.label || f.key) +
        (f.required ? ' *' : '') +
        '</label><input class="form-control form-control-sm" disabled placeholder="' +
        hint +
        '">';
      (currentSec || preview).appendChild(wrap);
    });
  }

  function render() {
    canvas.innerHTML = '';
    if (!fields.length) {
      canvas.innerHTML = '<p class="text-muted small studio-canvas-empty">Перетащите поля сюда</p>';
      renderPreview();
      return;
    }
    fields.forEach(function (f, idx) {
      var chip = document.createElement('div');
      chip.className = 'studio-field-chip flex-wrap';
      chip.dataset.idx = idx;
      if (f.type === 'section') {
        chip.innerHTML =
          '<i class="ri-layout-row-line text-primary"></i>' +
          '<input type="text" class="form-control form-control-sm" value="' +
          (f.label || 'Секция') +
          '" data-f="label" placeholder="Название секции">' +
          '<button type="button" class="btn btn-sm btn-icon btn-text-danger ms-auto" data-del>&times;</button>';
        canvas.appendChild(chip);
        chip.querySelector('[data-del]').onclick = function () {
          fields.splice(idx, 1);
          render();
        };
        chip.querySelector('[data-f]').oninput = function (e) {
          f.label = e.target.value;
          f.key = 'sec_' + idx;
          renderPreview();
        };
        return;
      }
      var nsiOpts =
        '<option value="">— без НСИ —</option>' +
        nsiList
          .map(function (n) {
            return (
              '<option value="' +
              n.code +
              '"' +
              (f.nsi_classifier === n.code ? ' selected' : '') +
              '>' +
              n.name +
              '</option>'
            );
          })
          .join('');
      var regOpts =
        '<option value="">— реестр —</option>' +
        regList
          .map(function (r) {
            return (
              '<option value="' +
              r.code +
              '"' +
              (f.registry_code === r.code ? ' selected' : '') +
              '>' +
              r.name +
              '</option>'
            );
          })
          .join('');
      var vw = f.visible_when || {};
      chip.innerHTML =
        '<i class="ri-drag-move-2-line text-muted"></i>' +
        '<input type="text" class="form-control form-control-sm" value="' +
        (f.label || f.key || '') +
        '" data-f="label" placeholder="Подпись">' +
        '<select class="form-select form-select-sm" data-f="type">' +
        ['text', 'textarea', 'date', 'select', 'lookup', 'number', 'section']
          .map(function (t) {
            return '<option value="' + t + '"' + (f.type === t ? ' selected' : '') + '>' + t + '</option>';
          })
          .join('') +
        '</select>' +
        (f.type === 'select'
          ? '<select class="form-select form-select-sm" data-f="nsi">' + nsiOpts + '</select>'
          : '') +
        (f.type === 'lookup'
          ? '<select class="form-select form-select-sm" data-f="registry">' +
            regOpts +
            '</select><input type="text" class="form-control form-control-sm" value="' +
            (f.lookup_label_field || 'name') +
            '" data-f="lookup_label" placeholder="поле подписи">' +
            '<input type="text" class="form-control form-control-sm" value="' +
            (f.fill_map ? JSON.stringify(f.fill_map) : '') +
            '" data-f="fill_map" placeholder=\'fill {"inn":"org_inn"}\'>'
          : '') +
        '<input type="text" class="form-control form-control-sm" value="' +
        (f.section || '') +
        '" data-f="section" placeholder="Секция (группа)">' +
        '<input type="text" class="form-control form-control-sm" value="' +
        (vw.field || '') +
        '" data-f="vw_field" placeholder="Показать если поле">' +
        '<input type="text" class="form-control form-control-sm" value="' +
        (vw.equals !== undefined ? vw.equals : '') +
        '" data-f="vw_equals" placeholder="= значение">' +
        '<input type="text" class="form-control form-control-sm" value="' +
        (f.pattern || '') +
        '" data-f="pattern" placeholder="regex">' +
        '<label class="form-check mb-0"><input type="checkbox" class="form-check-input" data-f="req"' +
        (f.required ? ' checked' : '') +
        '> обяз.</label>' +
        '<button type="button" class="btn btn-sm btn-icon btn-text-danger ms-auto" data-del>&times;</button>';
      canvas.appendChild(chip);
      chip.querySelector('[data-del]').onclick = function () {
        fields.splice(idx, 1);
        render();
      };
      chip.querySelectorAll('[data-f]').forEach(function (inp) {
        inp.onchange = inp.oninput = function () {
          var ff = inp.getAttribute('data-f');
          if (ff === 'label') {
            f.label = inp.value;
            if (f.type !== 'section') {
              f.key = inp.value.toLowerCase().replace(/[^a-z0-9_]/gi, '_').slice(0, 32) || 'field_' + idx;
            }
          } else if (ff === 'type') {
            f.type = inp.value;
            render();
          } else if (ff === 'nsi') f.nsi_classifier = inp.value;
          else if (ff === 'registry') f.registry_code = inp.value;
          else if (ff === 'lookup_label') f.lookup_label_field = inp.value;
          else if (ff === 'fill_map') {
            try {
              f.fill_map = inp.value ? JSON.parse(inp.value) : {};
            } catch (e) {}
          } else if (ff === 'section') f.section = inp.value;
          else if (ff === 'req') f.required = inp.checked;
          else if (ff === 'vw_field') {
            f.visible_when = f.visible_when || {};
            f.visible_when.field = inp.value;
          } else if (ff === 'vw_equals') {
            f.visible_when = f.visible_when || {};
            f.visible_when.equals = inp.value;
          } else if (ff === 'pattern') f.pattern = inp.value;
          renderPreview();
        };
      });
    });
    if (window.Sortable) {
      Sortable.create(canvas, {
        animation: 150,
        handle: '.ri-drag-move-2-line',
        ghostClass: 'studio-sortable-ghost',
        onEnd: function (evt) {
          var item = fields.splice(evt.oldIndex, 1)[0];
          fields.splice(evt.newIndex, 0, item);
          render();
        },
      });
    }
    renderPreview();
  }

  document.querySelectorAll('#studioFieldPalette .studio-palette-item').forEach(function (item) {
    item.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('field-type', item.getAttribute('data-field-type'));
    });
  });
  canvas.addEventListener('dragover', function (e) {
    e.preventDefault();
  });
  canvas.addEventListener('drop', function (e) {
    e.preventDefault();
    var t = e.dataTransfer.getData('field-type');
    if (!t) return;
    fields.push({ key: 'field_' + fields.length, label: 'Новое поле', type: t, required: false });
    if (t === 'section') {
      fields[fields.length - 1] = { key: 'sec_' + fields.length, label: 'Новая секция', type: 'section' };
    }
    render();
  });

  render();
  document.getElementById('studioFormSave').onclick = function () {
    var btn = this;
    var schemaId = root.getAttribute('data-schema-id');
    if (!schemaId) {
      markButtonState(btn, 'hint', 'Сначала выберите схему', 2500);
      return;
    }
    postJson(root.getAttribute('data-save-url'), { schema_id: parseInt(schemaId, 10), schema: fields }).then(
      function (res) {
        handleStudioSave(btn, res, { okMsg: 'Схема сохранена' });
      }
    );
  };

  var diffBtn = document.getElementById('studioFormDiff');
  var diffResult = document.getElementById('studioFormDiffResult');
  var diffUrl = root.getAttribute('data-diff-url');
  if (diffBtn && diffUrl) {
    diffBtn.onclick = function () {
      var schemaId = root.getAttribute('data-schema-id');
      if (!schemaId) {
        markButtonState(diffBtn, 'hint', 'Выберите схему', 2500);
        return;
      }
      markButtonState(diffBtn, 'pending', 'Сравнение…');
      var revEl = document.getElementById('studioFormDiffRevision');
      var body = { schema_id: parseInt(schemaId, 10), schema: fields };
      if (revEl && revEl.value) {
        body.revision_id = parseInt(revEl.value, 10);
      }
      postJson(diffUrl, body)
        .then(function (res) {
          if (!res.ok && res.error) {
            if (diffResult) diffResult.innerHTML = '<span class="text-danger">' + res.error + '</span>';
            markButtonState(diffBtn, 'error', 'Ошибка', 2500);
            return;
          }
          var parts = [];
          if (res.added && res.added.length) {
            parts.push(
              '<strong>Добавлено (' +
                res.added.length +
                '):</strong> ' +
                res.added.map(function (f) {
                  return f.label + ' (' + f.key + ')';
                }).join(', ')
            );
          }
          if (res.removed && res.removed.length) {
            parts.push(
              '<strong>Удалено (' +
                res.removed.length +
                '):</strong> ' +
                res.removed.map(function (f) {
                  return f.label + ' (' + f.key + ')';
                }).join(', ')
            );
          }
          if (res.changed && res.changed.length) {
            parts.push(
              '<strong>Изменено (' +
                res.changed.length +
                '):</strong><ul class="mb-0">' +
                res.changed
                  .map(function (f) {
                    return (
                      '<li>' +
                      f.label +
                      ' — ' +
                      f.diffs
                        .map(function (d) {
                          return d.attr;
                        })
                        .join(', ') +
                      '</li>'
                    );
                  })
                  .join('') +
                '</ul>'
            );
          }
          if (res.by_section && Object.keys(res.by_section).length) {
            var secParts = [];
            Object.keys(res.by_section).forEach(function (sec) {
              var block = res.by_section[sec];
              var secLine = [];
              if (block.added && block.added.length) secLine.push('+' + block.added.length);
              if (block.removed && block.removed.length) secLine.push('−' + block.removed.length);
              if (block.changed && block.changed.length) secLine.push('~' + block.changed.length);
              if (secLine.length) {
                secParts.push('<strong>' + sec + ':</strong> ' + secLine.join(', '));
              }
            });
            if (secParts.length) {
              parts.push('<strong>По секциям:</strong><br>' + secParts.join('<br>'));
            }
          }
          if (!parts.length) {
            if (diffResult) {
              diffResult.innerHTML =
                '<span class="text-success">Совпадает с ' +
                (res.revision_label || 'ревизией') +
                ' (' +
                (res.unchanged || 0) +
                ' полей).</span>';
            }
          } else if (diffResult) {
            diffResult.innerHTML =
              '<span class="text-muted">База: ' +
              (res.revision_label || '—') +
              '</span><br>' +
              parts.join('<br>');
          }
          markButtonState(diffBtn, 'success', 'Готово', 2000);
        })
        .catch(function () {
          if (diffResult) diffResult.textContent = 'Ошибка сети';
          markButtonState(diffBtn, 'error', 'Ошибка', 2500);
        });
    };
  }
}

/* --- BPM --- */
function initBpmEditor(root) {
  var nodesEl = document.getElementById('studioBpmNodes');
  var svg = document.getElementById('studioBpmSvg');
  var data = readJson('studioBpmJson', { nodes: [], edges: [] });
  var nodes = data.nodes || [];
  var edges = data.edges || [];
  var linkFrom = null;
  var formSchemas = readJson('studioBpmFormsJson', []);
  var bpmRoles = readJson('studioBpmRolesJson', []);
  var nodeMetrics = readJson('studioBpmMetricsJson', {});
  var nodeListEl = document.getElementById('studioBpmNodeList');

  function renderNodeList() {
    if (!nodeListEl) return;
    nodeListEl.innerHTML = '';
    nodes
      .filter(function (n) {
        return n.type === 'task' || n.type === 'approval';
      })
      .forEach(function (n) {
        var row = document.createElement('div');
        row.className = 'd-flex align-items-center gap-1 mb-1 flex-wrap';
        var opts =
          '<option value="">— форма —</option>' +
          formSchemas
            .map(function (s) {
              return (
                '<option value="' +
                s.code +
                '"' +
                (n.form_schema_code === s.code ? ' selected' : '') +
                '>' +
                s.name +
                '</option>'
              );
            })
            .join('');
        var roleOpts =
          '<option value="">— эскалация —</option>' +
          bpmRoles
            .map(function (r) {
              return (
                '<option value="' +
                r.code +
                '"' +
                (n.escalate_to_role === r.code ? ' selected' : '') +
                '>' +
                r.name +
                '</option>'
              );
            })
            .join('');
        var m = nodeMetrics[n.id];
        var metricHtml = m
          ? '<span class="badge bg-label-secondary" title="Среднее время">' +
            (m.avg_hours != null ? m.avg_hours + ' ч' : '—') +
            '</span><span class="badge bg-label-warning" title="Просрочки">' +
            m.overdue_pct +
            '%</span>'
          : '';
        row.innerHTML =
          '<span class="text-truncate" style="max-width:5rem">' +
          (n.label || n.type) +
          '</span>' +
          metricHtml +
          '<select class="form-select form-select-sm" style="max-width:7rem" data-node-id="' +
          n.id +
          '" data-field="form">' +
          opts +
          '</select>' +
          '<input type="number" class="form-control form-control-sm" style="width:4rem" min="0" placeholder="ч" title="Эскалация через, ч" data-node-id="' +
          n.id +
          '" data-field="esc_hours" value="' +
          (n.escalate_after_hours || '') +
          '">' +
          '<select class="form-select form-select-sm" style="max-width:7rem" data-node-id="' +
          n.id +
          '" data-field="esc_role">' +
          roleOpts +
          '</select>';
        nodeListEl.appendChild(row);
        row.querySelectorAll('[data-field]').forEach(function (el) {
          el.onchange = el.oninput = function () {
            var node = nodes.find(function (x) {
              return x.id === n.id;
            });
            if (!node) return;
            if (el.dataset.field === 'form') node.form_schema_code = el.value || null;
            if (el.dataset.field === 'esc_hours') {
              node.escalate_after_hours = el.value ? parseInt(el.value, 10) : null;
            }
            if (el.dataset.field === 'esc_role') node.escalate_to_role = el.value || null;
          };
        });
      });
    if (!nodeListEl.children.length) {
      nodeListEl.innerHTML = '<span class="text-muted">Нет узлов задач/согласований</span>';
    }
  }

  function drawEdges() {
    if (!svg) return;
    svg.innerHTML = '';
    edges.forEach(function (e) {
      var from = nodes.find(function (n) {
        return n.id === e.from;
      });
      var to = nodes.find(function (n) {
        return n.id === e.to;
      });
      if (!from || !to) return;
      var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', (from.x || 0) + 40);
      line.setAttribute('y1', (from.y || 0) + 16);
      line.setAttribute('x2', (to.x || 0) + 40);
      line.setAttribute('y2', (to.y || 0) + 16);
      line.setAttribute('stroke', '#8592a3');
      line.setAttribute('stroke-width', '2');
      line.setAttribute('marker-end', 'url(#arrow)');
      svg.appendChild(line);
    });
    if (!svg.querySelector('defs')) {
      var defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
      defs.innerHTML =
        '<marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="#8592a3"/></marker>';
      svg.appendChild(defs);
    }
  }

  function renderNodes() {
    nodesEl.innerHTML = '';
    nodes.forEach(function (n) {
      var el = document.createElement('div');
      el.className = 'studio-flow-node';
      el.textContent = n.label || n.type;
      el.style.left = (n.x || 20) + 'px';
      el.style.top = (n.y || 20) + 'px';
      el.style.background = n.color || '#696cff';
      el.dataset.id = n.id;
      var m = nodeMetrics[n.id];
      if (m && m.total) {
        el.title =
          'Задач: ' +
          m.total +
          ', ср. ' +
          (m.avg_hours != null ? m.avg_hours + ' ч' : '—') +
          ', просроч. ' +
          m.overdue_pct +
          '%';
      }
      el.draggable = true;
      el.onclick = function (ev) {
        ev.stopPropagation();
        if (!linkFrom) linkFrom = n.id;
        else if (linkFrom !== n.id) {
          edges.push({ from: linkFrom, to: n.id });
          linkFrom = null;
          drawEdges();
        }
      };
      el.ondblclick = function (ev) {
        ev.stopPropagation();
        nodes = nodes.filter(function (x) {
          return x.id !== n.id;
        });
        edges = edges.filter(function (e) {
          return e.from !== n.id && e.to !== n.id;
        });
        renderNodes();
        drawEdges();
        renderNodeList();
      };
      el.addEventListener('dragstart', function (e) {
        e.dataTransfer.setData('node-id', n.id);
      });
      nodesEl.appendChild(el);
    });
    drawEdges();
    renderNodeList();
  }

  document.getElementById('studioBpmCanvas').addEventListener('dragover', function (e) {
    e.preventDefault();
  });
  document.getElementById('studioBpmCanvas').addEventListener('drop', function (e) {
    e.preventDefault();
    var nt = e.dataTransfer.getData('node-type');
    var nc = e.dataTransfer.getData('node-color');
    if (!nt) return;
    var rect = nodesEl.getBoundingClientRect();
    nodes.push({
      id: uid(),
      type: nt,
      label: nt,
      color: nc || '#696cff',
      x: e.clientX - rect.left - 30,
      y: e.clientY - rect.top - 10,
    });
    renderNodes();
    renderNodeList();
  });

  renderNodes();
  renderNodeList();
  document.getElementById('studioBpmSave').onclick = function () {
    var btn = this;
    var tid = root.getAttribute('data-template-id');
    if (!tid) {
      markButtonState(btn, 'hint', 'Сначала выберите шаблон BPM', 2500);
      return;
    }
    postJson(root.getAttribute('data-save-url'), {
      template_id: parseInt(tid, 10),
      diagram: { nodes: nodes, edges: edges },
    }).then(function (res) {
      handleStudioSave(btn, res, { okMsg: 'Процесс сохранён' });
    });
  };

  var bpmDiffBtn = document.getElementById('studioBpmDiff');
  var bpmDiffResult = document.getElementById('studioBpmDiffResult');
  var bpmDiffUrl = root.getAttribute('data-diff-url');
  if (bpmDiffBtn && bpmDiffUrl) {
    bpmDiffBtn.onclick = function () {
      var btn = this;
      var tid = root.getAttribute('data-template-id');
      if (!tid) {
        markButtonState(btn, 'hint', 'Выберите шаблон', 2500);
        return;
      }
      markButtonState(btn, 'pending', 'Сравнение…');
      var body = {
        template_id: parseInt(tid, 10),
        diagram: { nodes: nodes, edges: edges },
      };
      var revEl = document.getElementById('studioBpmDiffRevision');
      if (revEl && revEl.value) body.revision_id = parseInt(revEl.value, 10);
      postJson(bpmDiffUrl, body).then(function (res) {
        if (!res.ok && res.error) {
          if (bpmDiffResult) bpmDiffResult.innerHTML = '<span class="text-danger">' + res.error + '</span>';
          markButtonState(btn, 'error', 'Ошибка', 2500);
          return;
        }
        var parts = [];
        if (res.added && res.added.length) {
          parts.push('Узлы +: ' + res.added.map(function (x) { return x.label || x.id; }).join(', '));
        }
        if (res.removed && res.removed.length) {
          parts.push('Узлы −: ' + res.removed.map(function (x) { return x.label || x.id; }).join(', '));
        }
        if (res.changed && res.changed.length) {
          parts.push(
            'Изменено: ' +
              res.changed
                .map(function (x) {
                  return (x.label || x.id) + ' (' + x.diffs.map(function (d) { return d.attr; }).join(', ') + ')';
                })
                .join('; ')
          );
        }
        if (res.edges_changed) parts.push('Изменены связи между узлами');
        if (!parts.length) {
          if (bpmDiffResult) {
            bpmDiffResult.innerHTML =
              '<span class="text-success">Совпадает с ' + (res.revision_label || 'ревизией') + '.</span>';
          }
        } else if (bpmDiffResult) {
          bpmDiffResult.innerHTML =
            '<span class="text-muted">База: ' + (res.revision_label || '—') + '</span><br>' + parts.join('<br>');
        }
        markButtonState(btn, 'success', 'Готово', 2000);
      });
    };
  }

  var simBtn = document.getElementById('studioBpmSimulate');
  var simLog = document.getElementById('studioBpmSimLog');
  var simMeta = document.getElementById('studioBpmSimMeta');
  if (simBtn) {
    simBtn.onclick = function () {
      var btn = this;
      markButtonState(btn, 'pending', 'Симуляция…');
      nodesEl.querySelectorAll('.studio-flow-node').forEach(function (el) {
        el.classList.remove('studio-bpm-active');
      });
      var simUrl = root.getAttribute('data-simulate-url');
      postJson(simUrl, { diagram: { nodes: nodes, edges: edges } }).then(function (res) {
        if (!res.ok) {
          if (simLog) simLog.innerHTML = '<span class="text-danger">Добавьте узел «Старт»</span>';
          markButtonState(btn, 'error', 'Нет старта', 2500);
          return;
        }
        if (simLog) {
          simLog.innerHTML = (res.timeline || [])
            .map(function (step) {
              var badge =
                step.status === 'escalated'
                  ? 'bg-label-warning'
                  : step.status === 'sla'
                    ? 'bg-label-info'
                    : 'bg-label-primary';
              return (
                '<div class="mb-1"><span class="badge ' +
                badge +
                ' me-1">' +
                step.elapsed_hours +
                ' ч</span>' +
                step.label +
                '</div>'
              );
            })
            .join('');
        }
        if (simMeta) {
          simMeta.textContent = 'Итого: ~' + res.total_days + ' дн. (' + res.total_hours + ' ч)';
        }
        (res.highlight_ids || []).forEach(function (nid) {
          var el = nodesEl.querySelector('[data-id="' + nid + '"]');
          if (el) el.classList.add('studio-bpm-active');
        });
        markButtonState(btn, 'success', 'Готово', 2000);
      });
    };
  }
}

/* --- Menu --- */
function initMenuEditor(root) {
  var layoutEl = document.getElementById('studioMenuLayout');
  var poolEl = document.getElementById('studioMenuPool');
  var allItems = readJson('studioMenuAllJson', []);
  var rolesList = readJson('studioMenuRolesJson', []);
  var badgeList = readJson('studioMenuBadgesJson', [{ key: '', label: 'Без счётчика' }]);
  var rawLayout = readJson('studioMenuJson', []);
  var layout = rawLayout.map(function (sec) {
    return {
      header: sec.header,
      items: (sec.items || []).map(function (it) {
        if (typeof it === 'string') return { url: it, roles: [], badge: '', pinned: false };
        return {
          url: it.url || it.url_name || '',
          roles: it.roles || [],
          badge: it.badge || '',
          pinned: !!it.pinned,
        };
      }),
    };
  });
  var byUrl = {};
  allItems.forEach(function (i) {
    byUrl[i.url_name] = i;
  });

  function render() {
    layoutEl.innerHTML = '';
    layout.forEach(function (sec, si) {
      var section = document.createElement('div');
      section.className = 'studio-menu-section';
      section.dataset.si = si;
      section.innerHTML = '<h6 class="mb-2"><i class="ri-drag-move-2-line me-1"></i>' + (sec.header || 'Раздел') + '</h6>';
      var list = document.createElement('div');
      list.className = 'studio-menu-items';
      (sec.items || []).forEach(function (entry) {
        var meta = byUrl[entry.url];
        if (!meta) return;
        var row = document.createElement('div');
        row.className = 'studio-menu-item studio-palette-item mb-1 d-flex align-items-center gap-2 flex-wrap';
        row.dataset.url = entry.url;
        var roleOpts = rolesList
          .map(function (r) {
            var sel = (entry.roles || []).indexOf(r.code) >= 0 ? ' selected' : '';
            return '<option value="' + r.code + '"' + sel + '>' + r.name + '</option>';
          })
          .join('');
        var badgeOpts = badgeList
          .map(function (b) {
            var sel = entry.badge === b.key ? ' selected' : '';
            return '<option value="' + b.key + '"' + sel + '>' + b.label + '</option>';
          })
          .join('');
        row.innerHTML =
          '<i class="ri ' +
          meta.icon +
          ' me-1"></i><span class="flex-grow-1">' +
          meta.label +
          '</span><select multiple class="form-select form-select-sm" data-roles title="Роли" style="max-width:9rem;min-height:2.2rem">' +
          roleOpts +
          '</select><select class="form-select form-select-sm" data-badge style="max-width:8rem">' +
          badgeOpts +
          '</select><label class="form-check mb-0" title="Быстрый доступ"><input type="checkbox" class="form-check-input" data-pinned' +
          (entry.pinned ? ' checked' : '') +
          '> 📌</label>';
        list.appendChild(row);
      });
      section.appendChild(list);
      layoutEl.appendChild(section);
      if (window.Sortable) {
        Sortable.create(list, { group: 'menu', animation: 150, ghostClass: 'studio-sortable-ghost' });
      }
    });
    if (window.Sortable) {
      Sortable.create(layoutEl, { animation: 150, handle: 'h6', ghostClass: 'studio-sortable-ghost' });
      Sortable.create(poolEl, { group: 'menu', animation: 150, sort: false });
    }
  }

  poolEl.innerHTML = '';
  allItems.forEach(function (i) {
    var row = document.createElement('div');
    row.className = 'studio-menu-item studio-palette-item';
    row.dataset.url = i.url_name;
    row.innerHTML = '<i class="ri ' + i.icon + ' me-2"></i>' + i.label + ' <small class="text-muted">(' + i.section + ')</small>';
    poolEl.appendChild(row);
  });
  render();

  function collectMenuLayout() {
    var newLayout = [];
    layoutEl.querySelectorAll('.studio-menu-section').forEach(function (sec) {
      var header = sec.querySelector('h6').textContent.replace(/^\s*[^\s]+\s*/, '').trim();
      var items = [];
      sec.querySelectorAll('.studio-menu-items .studio-menu-item').forEach(function (row) {
        if (!row.dataset.url) return;
        var roles = [];
        var sel = row.querySelector('[data-roles]');
        if (sel) {
          Array.prototype.forEach.call(sel.selectedOptions, function (opt) {
            roles.push(opt.value);
          });
        }
        var badge = '';
        var badgeSel = row.querySelector('[data-badge]');
        if (badgeSel) badge = badgeSel.value || '';
        var pinned = !!(row.querySelector('[data-pinned]') && row.querySelector('[data-pinned]').checked);
        items.push({ url: row.dataset.url, roles: roles, badge: badge, pinned: pinned });
      });
      if (items.length) newLayout.push({ header: header, items: items });
    });
    return newLayout;
  }

  document.getElementById('studioMenuSave').onclick = function () {
    var btn = this;
    postJson(root.getAttribute('data-save-url'), { layout: collectMenuLayout() }).then(function (res) {
      handleStudioSave(btn, res, { okMsg: 'Меню сохранено', draftMsg: 'Сохранено в черновик' });
    });
  };

  var menuDiffBtn = document.getElementById('studioMenuDiff');
  var menuDiffResult = document.getElementById('studioMenuDiffResult');
  var menuDiffUrl = root.getAttribute('data-diff-url');
  if (menuDiffBtn && menuDiffUrl) {
    menuDiffBtn.onclick = function () {
      var btn = this;
      markButtonState(btn, 'pending', 'Сравнение…');
      var body = { layout: collectMenuLayout() };
      var revEl = document.getElementById('studioMenuDiffRevision');
      if (revEl && revEl.value) body.revision_id = parseInt(revEl.value, 10);
      postJson(menuDiffUrl, body).then(function (res) {
        if (!res.ok && res.error) {
          if (menuDiffResult) menuDiffResult.innerHTML = '<span class="text-danger">' + res.error + '</span>';
          markButtonState(btn, 'error', 'Ошибка', 2500);
          return;
        }
        var parts = [];
        if (res.added && res.added.length) {
          parts.push('Добавлено: ' + res.added.map(function (x) { return x.url; }).join(', '));
        }
        if (res.removed && res.removed.length) {
          parts.push('Удалено: ' + res.removed.map(function (x) { return x.url; }).join(', '));
        }
        if (res.changed && res.changed.length) {
          parts.push(
            'Изменено: ' +
              res.changed
                .map(function (x) {
                  return x.url + ' (' + x.diffs.map(function (d) { return d.attr; }).join(', ') + ')';
                })
                .join('; ')
          );
        }
        if (!parts.length) {
          if (menuDiffResult) {
            menuDiffResult.innerHTML =
              '<span class="text-success">Совпадает с ' + (res.revision_label || 'ревизией') + '.</span>';
          }
        } else if (menuDiffResult) {
          menuDiffResult.innerHTML =
            '<span class="text-muted">База: ' + (res.revision_label || '—') + '</span><br>' + parts.join('<br>');
        }
        markButtonState(btn, 'success', 'Готово', 2000);
      });
    };
  }
}

/* --- Dashboard --- */
function initDashboardEditor(root) {
  var canvas = document.getElementById('studioDashCanvas');
  var palette = document.getElementById('studioDashPalette');
  var catalog = readJson('studioDashCatalog', []);
  var widgets = readJson('studioDashJson', []);
  var byId = {};
  catalog.forEach(function (w) {
    byId[w.id] = w;
  });

  function render() {
    canvas.innerHTML = '';
    widgets.forEach(function (wid) {
      var meta = byId[wid.id || wid] || { label: wid.id || wid, w: 3 };
      var id = meta.id || wid.id || wid;
      var el = document.createElement('div');
      el.className = 'studio-dash-widget w-' + (meta.w || 3);
      el.dataset.id = id;
      el.innerHTML = '<i class="ri-drag-move-2-line"></i><div class="mt-2">' + meta.label + '</div>';
      canvas.appendChild(el);
    });
    if (window.Sortable)
      Sortable.create(canvas, { animation: 150, ghostClass: 'studio-sortable-ghost' });
  }

  palette.innerHTML = '';
  catalog.forEach(function (w) {
    var el = document.createElement('div');
    el.className = 'studio-palette-item';
    el.draggable = true;
    el.textContent = w.label;
    el.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('widget-id', w.id);
    });
    palette.appendChild(el);
  });
  canvas.addEventListener('dragover', function (e) {
    e.preventDefault();
  });
  canvas.addEventListener('drop', function (e) {
    e.preventDefault();
    var id = e.dataTransfer.getData('widget-id');
    if (id && !widgets.some(function (x) { return (x.id || x) === id; })) widgets.push({ id: id });
    render();
  });

  render();
  document.getElementById('studioDashSave').onclick = function () {
    var btn = this;
    var out = [];
    canvas.querySelectorAll('.studio-dash-widget').forEach(function (el) {
      var meta = byId[el.dataset.id] || {};
      out.push({ id: el.dataset.id, label: meta.label, w: meta.w || 3, h: meta.h || 1 });
    });
    var roleEl = document.getElementById('studioDashRoleId');
    var body = { widgets: out };
    if (roleEl && roleEl.value) body.role_id = parseInt(roleEl.value, 10);
    postJson(root.getAttribute('data-save-url'), body).then(function (res) {
      handleStudioSave(btn, res, { okMsg: 'Шаблон дашборда для роли сохранён' });
    });
  };
}

/* --- Today widgets by role --- */
function initTodayEditor(root) {
  var canvas = document.getElementById('studioTodayCanvas');
  var palette = document.getElementById('studioTodayPalette');
  var catalog = [];
  palette.querySelectorAll('[data-widget-id]').forEach(function (el) {
    catalog.push({
      id: el.getAttribute('data-widget-id'),
      label: el.getAttribute('data-widget-label') || el.textContent.trim(),
      icon: el.getAttribute('data-widget-icon') || 'ri-drag-move-2-line',
    });
  });
  if (!catalog.length) catalog = readJson('studioTodayCatalog', []);
  var raw = readJson('studioTodayJson', []);
  if (!Array.isArray(raw)) raw = [];
  var widgets = raw.map(function (w) {
    return typeof w === 'string' ? w : w.id;
  });

  function render() {
    canvas.innerHTML = '';
    if (!widgets.length) {
      canvas.innerHTML = '<p class="text-muted small studio-canvas-empty">Перетащите виджеты сюда</p>';
      return;
    }
    widgets.forEach(function (id, idx) {
      var meta = catalog.find(function (c) { return c.id === id; }) || { label: id };
      var chip = document.createElement('div');
      chip.className = 'studio-palette-item mb-2';
      chip.dataset.idx = idx;
      chip.innerHTML = '<i class="ri ' + (meta.icon || 'ri-drag-move-2-line') + ' me-2"></i>' + meta.label;
      canvas.appendChild(chip);
    });
    if (window.Sortable) {
      Sortable.create(canvas, { animation: 150, ghostClass: 'studio-sortable-ghost' });
    }
  }

  function wirePaletteItem(el) {
    el.draggable = true;
    el.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('widget-id', el.getAttribute('data-widget-id'));
    });
  }

  if (!palette.querySelector('[data-widget-id]')) {
    palette.innerHTML = '';
    catalog.forEach(function (w) {
      var el = document.createElement('div');
      el.className = 'studio-palette-item';
      el.setAttribute('data-widget-id', w.id);
      el.setAttribute('data-widget-label', w.label);
      el.setAttribute('data-widget-icon', w.icon || 'ri-drag-move-2-line');
      el.innerHTML = '<i class="ri ' + (w.icon || 'ri-drag-move-2-line') + ' me-2"></i>' + w.label;
      wirePaletteItem(el);
      palette.appendChild(el);
    });
  } else {
    palette.querySelectorAll('[data-widget-id]').forEach(wirePaletteItem);
  }

  canvas.addEventListener('dragover', function (e) { e.preventDefault(); });
  canvas.addEventListener('drop', function (e) {
    e.preventDefault();
    var id = e.dataTransfer.getData('widget-id');
    if (id && widgets.indexOf(id) === -1) widgets.push(id);
    render();
  });

  render();

  document.getElementById('studioTodaySave').onclick = function () {
    var btn = this;
    var out = [];
    canvas.querySelectorAll('.studio-palette-item').forEach(function (el) {
      var idx = parseInt(el.dataset.idx, 10);
      if (!isNaN(idx) && widgets[idx]) out.push(widgets[idx]);
    });
    if (!out.length) out = widgets.slice();
    var roleEl = document.getElementById('studioTodayRoleId');
    if (!roleEl || !roleEl.value) {
      markButtonState(btn, 'hint', 'Сначала выберите роль', 2500);
      return;
    }
    postJson(root.getAttribute('data-save-url'), {
      widgets: out,
      role_id: parseInt(roleEl.value, 10),
    }).then(function (res) {
      handleStudioSave(btn, res, { okMsg: 'Шаблон «Мне на сегодня» сохранён' });
    });
  };
}

/* --- Correspondence workflow --- */
function initCorrEditor(root) {
  var canvas = document.getElementById('studioCorrCanvas');
  var wf = readJson('studioCorrJson', { steps: [], sla_days: {} });
  var steps = wf.steps || [];
  var sla = wf.sla_days || {};
  var labels = {
    register: 'Регистрация',
    assign: 'Назначение',
    execute: 'Исполнение',
    review: 'Проверка',
    reply: 'Ответ',
    archive: 'Архив',
  };

  function render() {
    canvas.innerHTML = '';
    steps.forEach(function (sid) {
      var li = document.createElement('li');
      li.className = 'list-group-item d-flex align-items-center gap-2 studio-corr-step';
      li.dataset.step = sid;
      li.innerHTML =
        '<i class="ri-drag-move-2-line"></i><span class="flex-grow-1">' +
        (labels[sid] || sid) +
        '</span><input type="number" class="form-control form-control-sm w-25" min="0" value="' +
        (sla[sid] || 1) +
        '" data-sla><span class="small text-muted">дн.</span>';
      canvas.appendChild(li);
      li.querySelector('[data-sla]').oninput = function (e) {
        sla[sid] = parseInt(e.target.value, 10) || 0;
      };
    });
    if (window.Sortable)
      Sortable.create(canvas, { animation: 150, ghostClass: 'studio-sortable-ghost' });
  }

  document.querySelectorAll('#studioCorrPalette .studio-palette-item').forEach(function (item) {
    item.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('step-id', item.getAttribute('data-step-id'));
    });
  });
  canvas.addEventListener('dragover', function (e) {
    e.preventDefault();
  });
  canvas.addEventListener('drop', function (e) {
    e.preventDefault();
    var sid = e.dataTransfer.getData('step-id');
    if (sid && steps.indexOf(sid) < 0) steps.push(sid);
    render();
  });

  render();
  function collectWorkflow() {
    var newSteps = [];
    canvas.querySelectorAll('[data-step]').forEach(function (el) {
      newSteps.push(el.dataset.step);
    });
    return { steps: newSteps, sla_days: sla };
  }

  document.getElementById('studioCorrSave').onclick = function () {
    var btn = this;
    postJson(root.getAttribute('data-save-url'), { workflow: collectWorkflow() }).then(function (res) {
      handleStudioSave(btn, res, { okMsg: 'Маршрут сохранён', draftMsg: 'Сохранено в черновик' });
    });
  };

  var corrDiffBtn = document.getElementById('studioCorrDiff');
  var corrDiffResult = document.getElementById('studioCorrDiffResult');
  var corrDiffUrl = root.getAttribute('data-diff-url');
  if (corrDiffBtn && corrDiffUrl) {
    corrDiffBtn.onclick = function () {
      var btn = this;
      markButtonState(btn, 'pending', 'Сравнение…');
      var body = { workflow: collectWorkflow() };
      var revEl = document.getElementById('studioCorrDiffRevision');
      if (revEl && revEl.value) body.revision_id = parseInt(revEl.value, 10);
      postJson(corrDiffUrl, body).then(function (res) {
        if (!res.ok && res.error) {
          if (corrDiffResult) corrDiffResult.innerHTML = '<span class="text-danger">' + res.error + '</span>';
          markButtonState(btn, 'error', 'Ошибка', 2500);
          return;
        }
        var parts = [];
        if (res.added_steps && res.added_steps.length) parts.push('Этапы +: ' + res.added_steps.join(', '));
        if (res.removed_steps && res.removed_steps.length) parts.push('Этапы −: ' + res.removed_steps.join(', '));
        if (res.moved_steps && res.moved_steps.length) parts.push('Порядок изменён: ' + res.moved_steps.length);
        if (res.sla_changed && res.sla_changed.length) {
          parts.push(
            'SLA: ' +
              res.sla_changed
                .map(function (x) {
                  return x.step + ' ' + x.before + '→' + x.after;
                })
                .join(', ')
          );
        }
        if (!parts.length) {
          if (corrDiffResult) {
            corrDiffResult.innerHTML =
              '<span class="text-success">Совпадает с ' + (res.revision_label || 'ревизией') + '.</span>';
          }
        } else if (corrDiffResult) {
          corrDiffResult.innerHTML =
            '<span class="text-muted">База: ' + (res.revision_label || '—') + '</span><br>' + parts.join('<br>');
        }
        markButtonState(btn, 'success', 'Готово', 2000);
      });
    };
  }
}

/* --- Print --- */
function initPrintEditor(root) {
  var editor = document.getElementById('studioPrintEditor');
  document.querySelectorAll('#studioPrintVars .studio-palette-item').forEach(function (item) {
    item.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('text/plain', item.getAttribute('data-var'));
    });
  });
  editor.addEventListener('dragover', function (e) {
    e.preventDefault();
  });
  editor.addEventListener('drop', function (e) {
    e.preventDefault();
    var v = e.dataTransfer.getData('text/plain');
    if (v) document.execCommand('insertText', false, v);
  });
  document.getElementById('studioPrintSave').onclick = function () {
    var btn = this;
    var tid = root.getAttribute('data-template-id');
    if (!tid) {
      markButtonState(btn, 'hint', 'Сначала выберите шаблон', 2500);
      return;
    }
    postJson(root.getAttribute('data-save-url'), {
      template_id: parseInt(tid, 10),
      body: editor.innerHTML,
    }).then(function (res) {
      handleStudioSave(btn, res, { okMsg: 'Шаблон сохранён' });
    });
  };

  var printDiffBtn = document.getElementById('studioPrintDiff');
  var printDiffResult = document.getElementById('studioPrintDiffResult');
  var printDiffUrl = root.getAttribute('data-diff-url');
  if (printDiffBtn && printDiffUrl && editor) {
    printDiffBtn.onclick = function () {
      var btn = this;
      var tid = root.getAttribute('data-template-id');
      if (!tid) return;
      markButtonState(btn, 'pending', 'Сравнение…');
      var body = { template_id: parseInt(tid, 10), body: editor.innerHTML };
      var revEl = document.getElementById('studioPrintDiffRevision');
      if (revEl && revEl.value) body.revision_id = parseInt(revEl.value, 10);
      postJson(printDiffUrl, body).then(function (res) {
        if (!res.ok && res.error) {
          if (printDiffResult) printDiffResult.innerHTML = '<span class="text-danger">' + res.error + '</span>';
          markButtonState(btn, 'error', 'Ошибка', 2500);
          return;
        }
        var parts = [];
        if (res.body_changed) parts.push('Текст изменён');
        if (res.added_variables && res.added_variables.length) {
          parts.push('Переменные +: ' + res.added_variables.join(', '));
        }
        if (res.removed_variables && res.removed_variables.length) {
          parts.push('Переменные −: ' + res.removed_variables.join(', '));
        }
        if (!parts.length) {
          if (printDiffResult) {
            printDiffResult.innerHTML =
              '<span class="text-success">Совпадает с ' + (res.revision_label || 'ревизией') + '.</span>';
          }
        } else if (printDiffResult) {
          printDiffResult.innerHTML =
            '<span class="text-warning">' +
            (res.revision_label || 'Ревизия') +
            ': ' +
            parts.join('; ') +
            '</span>';
        }
        markButtonState(btn, 'success', 'Готово', 2200);
      });
    };
  }
}

/* --- Permissions --- */
function initPermEditor(root) {
  var tbody = document.querySelector('#studioPermTable tbody');
  var matrix = readJson('studioPermJson', []);
  var presets = {
    viewer: ['view'],
    operator: ['view', 'create', 'change'],
    admin: ['view', 'create', 'change', 'delete', 'view_pii', 'export_pii', 'approve', 'sign', 'archive', 'bulk'],
  };
  var permCols = ['view', 'create', 'change', 'delete', 'view_pii', 'export_pii', 'approve', 'sign', 'archive', 'bulk'];

  matrix.forEach(function (row) {
    if (!row.own) {
      row.own = {};
      permCols.forEach(function (a) {
        row.own[a] = false;
      });
    }
  });

  function render() {
    tbody.innerHTML = '';
    matrix.forEach(function (row, idx) {
      var tr = document.createElement('tr');
      if (row.inherited) tr.classList.add('table-warning');
      tr.innerHTML =
        '<td><strong>' +
        row.code +
        '</strong><br><small class="text-muted">' +
        row.name +
        (row.inherited ? ' <span class="badge bg-label-info">наслед.</span>' : '') +
        '</small></td>' +
        permCols
          .map(function (a) {
            var inherited = row[a] && !row.own[a];
            return (
              '<td class="text-center">' +
              (inherited ? '<span class="text-muted small" title="от родителя">↓</span> ' : '') +
              '<input type="checkbox" data-idx="' +
              idx +
              '" data-action="' +
              a +
              '"' +
              (row.own[a] ? ' checked' : '') +
              '></td>'
            );
          })
          .join('');
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll('input[type=checkbox]').forEach(function (cb) {
      cb.onchange = function () {
        var row = matrix[parseInt(cb.dataset.idx, 10)];
        row.own[cb.dataset.action] = cb.checked;
        row[cb.dataset.action] = cb.checked || (row[cb.dataset.action] && !row.own[cb.dataset.action]);
      };
    });
  }

  render();
  document.querySelectorAll('.studio-preset').forEach(function (btn) {
    btn.onclick = function () {
      var p = presets[btn.getAttribute('data-preset')];
      matrix.forEach(function (row) {
        permCols.forEach(function (a) {
          row.own[a] = p.indexOf(a) >= 0;
          row[a] = row.own[a];
        });
      });
      render();
    };
  });
  document.getElementById('studioPermSave').onclick = function () {
    var btn = this;
    var roleId = document.getElementById('studioPermRoleId').value;
    var parentEl = document.getElementById('studioPermParentRole');
    var body = {
      role_id: parseInt(roleId, 10),
      matrix: matrix,
      parent_role_id: parentEl && parentEl.value ? parseInt(parentEl.value, 10) : null,
    };
    postJson(root.getAttribute('data-save-url'), body).then(function (res) {
      handleStudioSave(btn, res, { okMsg: 'Права сохранены' });
    });
  };
}

/* --- NSI --- */
function initNsiEditor(root) {
  var list = document.getElementById('studioNsiList');
  var values = readJson('studioNsiJson', []);

  function render() {
    list.innerHTML = '';
    values.forEach(function (v) {
      var li = document.createElement('li');
      li.className = 'list-group-item d-flex align-items-center gap-2';
      li.dataset.id = v.id;
      li.innerHTML =
        '<i class="ri-drag-move-2-line"></i><code>' +
        v.code +
        '</code><input class="form-control form-control-sm" value="' +
        v.name +
        '" data-name><input class="form-control form-control-sm w-25" value="' +
        v.code +
        '" data-code>';
      list.appendChild(li);
      li.querySelector('[data-name]').oninput = function (e) {
        v.name = e.target.value;
      };
      li.querySelector('[data-code]').oninput = function (e) {
        v.code = e.target.value;
      };
    });
    if (window.Sortable)
      Sortable.create(list, { animation: 150, ghostClass: 'studio-sortable-ghost' });
  }

  render();
  document.getElementById('studioNsiSave').onclick = function () {
    var btn = this;
    var cid = root.getAttribute('data-classifier-id');
    var out = [];
    list.querySelectorAll('li').forEach(function (li) {
      out.push({
        id: parseInt(li.dataset.id, 10),
        name: li.querySelector('[data-name]').value,
        code: li.querySelector('[data-code]').value,
      });
    });
    postJson(root.getAttribute('data-save-url'), { classifier_id: parseInt(cid, 10), values: out }).then(
      function (res) {
        handleStudioSave(btn, res, { okMsg: 'НСИ сохранён' });
      }
    );
  };

  var nsiDiffBtn = document.getElementById('studioNsiDiff');
  var nsiDiffResult = document.getElementById('studioNsiDiffResult');
  var nsiDiffUrl = root.getAttribute('data-diff-url');
  if (nsiDiffBtn && nsiDiffUrl && list) {
    nsiDiffBtn.onclick = function () {
      var btn = this;
      var cid = root.getAttribute('data-classifier-id');
      if (!cid) return;
      markButtonState(btn, 'pending', 'Сравнение…');
      var out = [];
      list.querySelectorAll('li').forEach(function (li) {
        out.push({
          code: li.querySelector('[data-code]').value,
          name: li.querySelector('[data-name]').value,
        });
      });
      var body = { classifier_id: parseInt(cid, 10), values: out };
      var revEl = document.getElementById('studioNsiDiffRevision');
      if (revEl && revEl.value) body.revision_id = parseInt(revEl.value, 10);
      postJson(nsiDiffUrl, body).then(function (res) {
        if (!res.ok && res.error) {
          if (nsiDiffResult) nsiDiffResult.innerHTML = '<span class="text-danger">' + res.error + '</span>';
          markButtonState(btn, 'error', 'Ошибка', 2500);
          return;
        }
        var parts = [];
        if (res.added_values && res.added_values.length) parts.push('Добавлено: ' + res.added_values.join(', '));
        if (res.removed_values && res.removed_values.length) parts.push('Удалено: ' + res.removed_values.join(', '));
        if (res.reordered) parts.push('Изменён порядок');
        if (res.renamed_values && res.renamed_values.length) parts.push('Переименовано: ' + res.renamed_values.length);
        if (!parts.length) {
          if (nsiDiffResult) {
            nsiDiffResult.innerHTML =
              '<span class="text-success">Совпадает с ' + (res.revision_label || 'ревизией') + '.</span>';
          }
        } else if (nsiDiffResult) {
          nsiDiffResult.innerHTML =
            '<span class="text-warning">' + (res.revision_label || 'Ревизия') + ': ' + parts.join('; ') + '</span>';
        }
        markButtonState(btn, 'success', 'Готово', 2200);
      });
    };
  }
}

/* --- Integration pipeline --- */
function initPipeEditor(root) {
  var canvas = document.getElementById('studioPipeNodes');
  var data = readJson('studioPipeJson', { nodes: [] });
  var nodes = data.nodes || [];

  function render() {
    canvas.innerHTML = '';
    nodes.forEach(function (n, idx) {
      var el = document.createElement('div');
      el.className = 'studio-pipe-node';
      el.innerHTML = '<i class="ri-drag-move-2-line me-1"></i>' + (n.label || n.type) + ' <button type="button" class="btn btn-xs btn-link text-danger" data-x>&times;</button>';
      el.querySelector('[data-x]').onclick = function () {
        nodes.splice(idx, 1);
        render();
      };
      canvas.appendChild(el);
    });
    if (window.Sortable)
      Sortable.create(canvas, { animation: 150, ghostClass: 'studio-sortable-ghost' });
  }

  document.querySelectorAll('#studioPipePalette .studio-palette-item').forEach(function (item) {
    item.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('pipe-type', item.getAttribute('data-pipe-type'));
      e.dataTransfer.setData('pipe-label', item.textContent.trim());
    });
  });
  canvas.parentElement.addEventListener('dragover', function (e) {
    e.preventDefault();
  });
  canvas.parentElement.addEventListener('drop', function (e) {
    e.preventDefault();
    var t = e.dataTransfer.getData('pipe-type');
    var l = e.dataTransfer.getData('pipe-label');
    if (t) {
      var node = { id: uid(), type: t, label: l || t };
      if (t === 'smev') node.message_type = 'Request';
      nodes.push(node);
    }
    render();
  });

  render();
  document.getElementById('studioPipeSave').onclick = function () {
    var btn = this;
    var eid = root.getAttribute('data-endpoint-id');
    var ordered = [];
    canvas.querySelectorAll('.studio-pipe-node').forEach(function (el, i) {
      ordered.push(nodes[i] || { type: 'step', label: el.textContent });
    });
    postJson(root.getAttribute('data-save-url'), {
      endpoint_id: parseInt(eid, 10),
      pipeline: { nodes: ordered, edges: [] },
      smev_config: collectSmevConfig(),
    }).then(function (res) {
      handleStudioSave(btn, res, { okMsg: 'Pipeline сохранён' });
    });
  };

  function collectSmevConfig() {
    var transportEl = document.getElementById('studioSmevTransport');
    if (!transportEl) return null;
    var testEl = document.getElementById('studioSmevTestMode');
    return {
      transport: transportEl.value || 'simulated',
      url: (document.getElementById('studioSmevUrl') || {}).value || '',
      test_mode: testEl ? testEl.value === '1' : true,
      client_id: (document.getElementById('studioSmevClientId') || {}).value || '',
    };
  }

  var dryBtn = document.getElementById('studioPipeDryRun');
  var runBtn = document.getElementById('studioPipeRun');
  var dryLog = document.getElementById('studioPipeDryLog');

  function orderedPipeNodes() {
    var ordered = [];
    canvas.querySelectorAll('.studio-pipe-node').forEach(function (el, i) {
      ordered.push(nodes[i] || { type: 'step', label: (el.textContent || '').trim() });
    });
    return ordered;
  }

  function renderPipeLog(res) {
    if (!dryLog) return;
    var modeLabel = res.mode === 'runtime' ? ' [runtime]' : '';
    dryLog.innerHTML = (res.log || [])
      .map(function (line) {
        var cls = line.status === 'error' ? 'text-danger' : 'text-body';
        return (
          '<div class="' +
          cls +
          ' mb-1"><strong>' +
          line.step +
          '.</strong> ' +
          line.label +
          modeLabel +
          ' — ' +
          line.detail +
          '</div>'
        );
      })
      .join('');
    if (res.output && res.output.smev_message_id) {
      dryLog.innerHTML +=
        '<div class="text-success mt-1">MSG-' + res.output.smev_message_id + '</div>';
    }
  }

  if (dryBtn) {
    dryBtn.onclick = function () {
      var btn = this;
      markButtonState(btn, 'pending', 'Прогон…');
      var dryUrl = root.getAttribute('data-dry-run-url');
      postJson(dryUrl, { pipeline: { nodes: orderedPipeNodes() } }).then(function (res) {
        renderPipeLog(res);
        if (res.ok) markButtonState(btn, 'success', 'Прогон OK', 2200);
        else markButtonState(btn, 'error', 'Есть ошибки', 2800);
      });
    };
  }

  if (runBtn) {
    runBtn.onclick = function () {
      var btn = this;
      var eid = root.getAttribute('data-endpoint-id');
      if (!eid) {
        markButtonState(btn, 'hint', 'Выберите endpoint', 2500);
        return;
      }
      markButtonState(btn, 'pending', 'Runtime…');
      var runUrl = root.getAttribute('data-run-url');
      postJson(runUrl, {
        pipeline: { nodes: orderedPipeNodes() },
        endpoint_id: parseInt(eid, 10),
        mode: 'runtime',
      }).then(function (res) {
        renderPipeLog(res);
        if (res.ok) markButtonState(btn, 'success', 'СМЭВ OK', 2200);
        else markButtonState(btn, 'error', 'Ошибка', 2800);
      });
    };
  }

  var intDiffBtn = document.getElementById('studioIntDiff');
  var intDiffResult = document.getElementById('studioIntDiffResult');
  var intDiffUrl = root.getAttribute('data-diff-url');
  if (intDiffBtn && intDiffUrl) {
    intDiffBtn.onclick = function () {
      var btn = this;
      var eid = root.getAttribute('data-endpoint-id');
      if (!eid) return;
      markButtonState(btn, 'pending', 'Сравнение…');
      var body = {
        endpoint_id: parseInt(eid, 10),
        pipeline: { nodes: orderedPipeNodes(), edges: [] },
        smev_config: collectSmevConfig(),
      };
      var revEl = document.getElementById('studioIntDiffRevision');
      if (revEl && revEl.value) body.revision_id = parseInt(revEl.value, 10);
      postJson(intDiffUrl, body).then(function (res) {
        if (!res.ok && res.error) {
          if (intDiffResult) intDiffResult.innerHTML = '<span class="text-danger">' + res.error + '</span>';
          markButtonState(btn, 'error', 'Ошибка', 2500);
          return;
        }
        var parts = [];
        if (res.pipeline_changed) {
          parts.push('Pipeline: ' + res.pipeline_before + '→' + res.pipeline_after + ' узлов');
        }
        if (res.smev_changed && res.smev_changed.length) {
          parts.push(
            'СМЭВ: ' +
              res.smev_changed
                .map(function (x) {
                  return x.attr;
                })
                .join(', ')
          );
        }
        if (!parts.length) {
          if (intDiffResult) {
            intDiffResult.innerHTML =
              '<span class="text-success">Совпадает с ' + (res.revision_label || 'ревизией') + '.</span>';
          }
        } else if (intDiffResult) {
          intDiffResult.innerHTML =
            '<span class="text-warning">' + (res.revision_label || 'Ревизия') + ': ' + parts.join('; ') + '</span>';
        }
        markButtonState(btn, 'success', 'Готово', 2200);
      });
    };
  }
}
function initCabinetEditor(root) {
  var canvas = document.getElementById('studioCabCanvas');
  var palette = document.getElementById('studioCabPalette');
  var catalog = readJson('studioCabCatalog', []);
  var widgets = readJson('studioCabJson', []);
  if (typeof widgets[0] === 'string') widgets = widgets.map(function (id) { return { id: id }; });
  var byId = {};
  catalog.forEach(function (w) {
    byId[w.id] = w;
  });

  function render() {
    canvas.innerHTML = '';
    widgets.forEach(function (w) {
      var meta = byId[w.id] || { label: w.id, icon: 'ri-layout-line' };
      var el = document.createElement('div');
      el.className = 'studio-palette-item mb-2';
      el.dataset.id = w.id;
      el.innerHTML = '<i class="ri ' + meta.icon + ' me-2"></i>' + meta.label;
      canvas.appendChild(el);
    });
    if (window.Sortable)
      Sortable.create(canvas, { animation: 150, ghostClass: 'studio-sortable-ghost' });
  }

  palette.innerHTML = '';
  catalog.forEach(function (w) {
    var el = document.createElement('div');
    el.className = 'studio-palette-item';
    el.draggable = true;
    el.innerHTML = '<i class="ri ' + w.icon + ' me-2"></i>' + w.label;
    el.addEventListener('dragstart', function (e) {
      e.dataTransfer.setData('cab-id', w.id);
    });
    palette.appendChild(el);
  });
  canvas.addEventListener('dragover', function (e) {
    e.preventDefault();
  });
  canvas.addEventListener('drop', function (e) {
    e.preventDefault();
    var id = e.dataTransfer.getData('cab-id');
    if (id && !widgets.some(function (x) { return x.id === id; })) widgets.push({ id: id });
    render();
  });

  render();
  document.getElementById('studioCabSave').onclick = function () {
    var btn = this;
    var out = [];
    canvas.querySelectorAll('[data-id]').forEach(function (el) {
      out.push(el.dataset.id);
    });
    postJson(root.getAttribute('data-save-url'), { widgets: out }).then(function (res) {
      handleStudioSave(btn, res, { okMsg: 'Кабинет сохранён' });
    });
  };
}
