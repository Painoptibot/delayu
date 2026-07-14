(function () {
  var cfg = window.delayuAppealAi || {};
  var subjectEl = document.getElementById('id_subject');
  var bodyEl = document.getElementById('id_body');
  var panel = document.getElementById('appealAiPanel');
  var draftBtn = document.getElementById('btnAppealDraftAi');
  var answerEl = document.getElementById('id_answer_text');
  var conclusionEl = document.getElementById('id_conclusion_kind');
  var timer = null;

  function fetchClassify() {
    if (!cfg.classifyUrl || !panel) return;
    var subject = subjectEl ? subjectEl.value.trim() : '';
    var body = bodyEl ? bodyEl.value.trim() : '';
    if (subject.length < 3 && body.length < 3) return;
    var url = cfg.classifyUrl + '?subject=' + encodeURIComponent(subject) + '&body=' + encodeURIComponent(body);
    fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.theme) return;
        panel.classList.remove('d-none');
        document.getElementById('appealAiTheme').textContent =
          data.theme + ' · приоритет ' + data.priority + ' · ' + (data.confidence * 100).toFixed(0) + '%';
        document.getElementById('appealAiRoute').textContent =
          (data.route || '') + (data.department ? ' · ' + data.department : '');
        var ul = document.getElementById('appealAiReasons');
        ul.innerHTML = '';
        (data.reasons || []).forEach(function (r) {
          var li = document.createElement('li');
          li.textContent = r;
          ul.appendChild(li);
        });
        document.getElementById('appealAiConfidence').textContent =
          'Уверенность: ' + Number(data.confidence).toFixed(2);
      })
      .catch(function () {});
  }

  function scheduleClassify() {
    clearTimeout(timer);
    timer = setTimeout(fetchClassify, 400);
  }

  if (subjectEl) subjectEl.addEventListener('input', scheduleClassify);
  if (bodyEl) bodyEl.addEventListener('input', scheduleClassify);

  if (draftBtn && cfg.draftUrl) {
    draftBtn.addEventListener('click', function () {
      draftBtn.disabled = true;
      fetch(cfg.draftUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          Accept: 'application/json',
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        }
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (answerEl && data.draft) {
            answerEl.value = data.draft;
            answerEl.focus();
          }
          if (conclusionEl && data.conclusion_kind) {
            conclusionEl.value = data.conclusion_kind;
          }
          alert('Черновик подставлен. Проверьте текст перед сохранением.');
        })
        .catch(function () { alert('Не удалось сформировать черновик'); })
        .finally(function () { draftBtn.disabled = false; });
    });
  }

  scheduleClassify();
})();
