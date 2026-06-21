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

function toastOk(msg) {
  if (window.Notyf) {
    new Notyf().success(msg || 'Сохранено');
  } else {
    alert(msg || 'Сохранено');
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
  var schema = readJson('studioFormSchemaJson', []);
  var nsiList = readJson('studioNsiJson', []);
  var fields = Array.isArray(schema) ? schema.slice() : [];

  function render() {
    canvas.innerHTML = '';
    if (!fields.length) {
      canvas.innerHTML = '<p class="text-muted small studio-canvas-empty">Перетащите поля сюда</p>';
      return;
    }
    fields.forEach(function (f, idx) {
      var chip = document.createElement('div');
      chip.className = 'studio-field-chip';
      chip.dataset.idx = idx;
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
      chip.innerHTML =
        '<i class="ri-drag-move-2-line text-muted"></i>' +
        '<input type="text" class="form-control form-control-sm" value="' +
        (f.label || f.key || '') +
        '" data-f="label">' +
        '<select class="form-select form-select-sm" data-f="type">' +
        ['text', 'textarea', 'date', 'select', 'number']
          .map(function (t) {
            return '<option value="' + t + '"' + (f.type === t ? ' selected' : '') + '>' + t + '</option>';
          })
          .join('') +
        '</select>' +
        (f.type === 'select'
          ? '<select class="form-select form-select-sm" data-f="nsi">' + nsiOpts + '</select>'
          : '') +
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
            f.key = inp.value.toLowerCase().replace(/[^a-z0-9_]/gi, '_').slice(0, 32) || 'field_' + idx;
          } else if (ff === 'type') {
            f.type = inp.value;
            render();
          } else if (ff === 'nsi') f.nsi_classifier = inp.value;
          else if (ff === 'req') f.required = inp.checked;
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
    render();
  });

  render();
  document.getElementById('studioFormSave').onclick = function () {
    var schemaId = root.getAttribute('data-schema-id');
    if (!schemaId) {
      alert('Выберите схему формы');
      return;
    }
    postJson(root.getAttribute('data-save-url'), { schema_id: parseInt(schemaId, 10), schema: fields }).then(
      function (res) {
        if (res.ok) toastOk('Схема сохранена');
        else alert(res.error || 'Ошибка');
      }
    );
  };
}

/* --- BPM --- */
function initBpmEditor(root) {
  var nodesEl = document.getElementById('studioBpmNodes');
  var svg = document.getElementById('studioBpmSvg');
  var data = readJson('studioBpmJson', { nodes: [], edges: [] });
  var nodes = data.nodes || [];
  var edges = data.edges || [];
  var linkFrom = null;

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
      };
      el.addEventListener('dragstart', function (e) {
        e.dataTransfer.setData('node-id', n.id);
      });
      nodesEl.appendChild(el);
    });
    drawEdges();
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
  });

  renderNodes();
  document.getElementById('studioBpmSave').onclick = function () {
    var tid = root.getAttribute('data-template-id');
    if (!tid) {
      alert('Нет шаблона BPM');
      return;
    }
    postJson(root.getAttribute('data-save-url'), {
      template_id: parseInt(tid, 10),
      diagram: { nodes: nodes, edges: edges },
    }).then(function (res) {
      if (res.ok) toastOk('Процесс сохранён');
      else alert(res.error || 'Ошибка');
    });
  };
}

/* --- Menu --- */
function initMenuEditor(root) {
  var layoutEl = document.getElementById('studioMenuLayout');
  var poolEl = document.getElementById('studioMenuPool');
  var allItems = readJson('studioMenuAllJson', []);
  var layout = readJson('studioMenuJson', []);
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
      (sec.items || []).forEach(function (urlName, ii) {
        var meta = byUrl[urlName];
        if (!meta) return;
        var row = document.createElement('div');
        row.className = 'studio-menu-item studio-palette-item mb-1';
        row.dataset.url = urlName;
        row.innerHTML = '<i class="ri ' + meta.icon + ' me-2"></i>' + meta.label;
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

  document.getElementById('studioMenuSave').onclick = function () {
    var newLayout = [];
    layoutEl.querySelectorAll('.studio-menu-section').forEach(function (sec) {
      var header = sec.querySelector('h6').textContent.replace(/^\s*[^\s]+\s*/, '').trim();
      var items = [];
      sec.querySelectorAll('.studio-menu-items .studio-menu-item').forEach(function (row) {
        if (row.dataset.url) items.push(row.dataset.url);
      });
      if (items.length) newLayout.push({ header: header, items: items });
    });
    postJson(root.getAttribute('data-save-url'), { layout: newLayout }).then(function (res) {
      if (res.ok) toastOk('Меню сохранено — обновите страницу');
      else alert(res.error || 'Ошибка');
    });
  };
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
    var out = [];
    canvas.querySelectorAll('.studio-dash-widget').forEach(function (el) {
      var meta = byId[el.dataset.id] || {};
      out.push({ id: el.dataset.id, label: meta.label, w: meta.w || 3, h: meta.h || 1 });
    });
    postJson(root.getAttribute('data-save-url'), { widgets: out }).then(function (res) {
      if (res.ok) toastOk('Дашборд сохранён');
      else alert(res.error || 'Ошибка');
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
  document.getElementById('studioCorrSave').onclick = function () {
    var newSteps = [];
    canvas.querySelectorAll('[data-step]').forEach(function (el) {
      newSteps.push(el.dataset.step);
    });
    postJson(root.getAttribute('data-save-url'), { workflow: { steps: newSteps, sla_days: sla } }).then(
      function (res) {
        if (res.ok) toastOk('Маршрут сохранён');
        else alert(res.error || 'Ошибка');
      }
    );
  };
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
    var tid = root.getAttribute('data-template-id');
    if (!tid) {
      alert('Нет шаблона');
      return;
    }
    postJson(root.getAttribute('data-save-url'), {
      template_id: parseInt(tid, 10),
      body: editor.innerHTML,
    }).then(function (res) {
      if (res.ok) toastOk('Шаблон сохранён');
      else alert(res.error || 'Ошибка');
    });
  };
}

/* --- Permissions --- */
function initPermEditor(root) {
  var tbody = document.querySelector('#studioPermTable tbody');
  var matrix = readJson('studioPermJson', []);
  var presets = { viewer: ['view'], operator: ['view', 'create', 'change'], admin: ['view', 'create', 'change', 'delete'] };

  function render() {
    tbody.innerHTML = '';
    matrix.forEach(function (row, idx) {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td><strong>' +
        row.code +
        '</strong><br><small class="text-muted">' +
        row.name +
        '</small></td>' +
        ['view', 'create', 'change', 'delete', 'view_pii', 'export_pii']
          .map(function (a) {
            return (
              '<td class="text-center"><input type="checkbox" data-idx="' +
              idx +
              '" data-action="' +
              a +
              '"' +
              (row[a] ? ' checked' : '') +
              '></td>'
            );
          })
          .join('');
      tbody.appendChild(tr);
    });
    tbody.querySelectorAll('input[type=checkbox]').forEach(function (cb) {
      cb.onchange = function () {
        matrix[parseInt(cb.dataset.idx, 10)][cb.dataset.action] = cb.checked;
      };
    });
  }

  render();
  document.querySelectorAll('.studio-preset').forEach(function (btn) {
    btn.onclick = function () {
      var p = presets[btn.getAttribute('data-preset')];
      matrix.forEach(function (row) {
        ['view', 'create', 'change', 'delete', 'view_pii', 'export_pii'].forEach(function (a) {
          row[a] = p.indexOf(a) >= 0;
        });
      });
      render();
    };
  });
  document.getElementById('studioPermSave').onclick = function () {
    var roleId = document.getElementById('studioPermRoleId').value;
    postJson(root.getAttribute('data-save-url'), { role_id: parseInt(roleId, 10), matrix: matrix }).then(
      function (res) {
        if (res.ok) toastOk('Права сохранены');
        else alert(res.error || 'Ошибка');
      }
    );
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
        if (res.ok) toastOk('НСИ сохранён');
        else alert(res.error || 'Ошибка');
      }
    );
  };
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
    if (t) nodes.push({ id: uid(), type: t, label: l || t });
    render();
  });

  render();
  document.getElementById('studioPipeSave').onclick = function () {
    var eid = root.getAttribute('data-endpoint-id');
    var ordered = [];
    canvas.querySelectorAll('.studio-pipe-node').forEach(function (el, i) {
      ordered.push(nodes[i] || { type: 'step', label: el.textContent });
    });
    postJson(root.getAttribute('data-save-url'), {
      endpoint_id: parseInt(eid, 10),
      pipeline: { nodes: ordered, edges: [] },
    }).then(function (res) {
      if (res.ok) toastOk('Pipeline сохранён');
      else alert(res.error || 'Ошибка');
    });
  };
}

/* --- Cabinet --- */
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
    var out = [];
    canvas.querySelectorAll('[data-id]').forEach(function (el) {
      out.push(el.dataset.id);
    });
    postJson(root.getAttribute('data-save-url'), { widgets: out }).then(function (res) {
      if (res.ok) toastOk('Кабинет сохранён');
      else alert(res.error || 'Ошибка');
    });
  };
}
