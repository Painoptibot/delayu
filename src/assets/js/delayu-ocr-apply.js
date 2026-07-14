(function () {
  function csrfToken() {
    const el = document.querySelector("[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  const modalEl = document.getElementById("uzhvOcrModal");
  if (!modalEl) return;

  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  let applyUrl = "";
  let currentFields = [];

  function showLoading(on) {
    document.getElementById("uzhvOcrLoading").classList.toggle("d-none", !on);
    document.getElementById("uzhvOcrApplyForm").classList.toggle("d-none", on);
    document.getElementById("uzhvOcrApplyBtn").classList.toggle("d-none", on);
  }

  function renderResult(data) {
    document.getElementById("uzhvOcrError").classList.add("d-none");
    const warnBox = document.getElementById("uzhvOcrWarnings");
    warnBox.innerHTML = "";
    (data.warnings || []).forEach(function (w) {
      const d = document.createElement("div");
      d.className = "alert alert-warning py-2 small";
      d.textContent = w;
      warnBox.appendChild(d);
    });
    const meta = document.getElementById("uzhvOcrMeta");
    meta.textContent = "Движок: " + (data.engine || "—") + " · полей: " + (data.field_count || 0);
    meta.classList.remove("d-none");

    const container = document.getElementById("uzhvOcrFields");
    container.innerHTML = "";
    currentFields = data.fields || [];
    if (!currentFields.length) {
      container.innerHTML = '<p class="text-muted small mb-0">Реквизиты не найдены.</p>';
    } else {
      currentFields.forEach(function (f, idx) {
        const id = "ocr_field_" + idx;
        const wrap = document.createElement("div");
        wrap.className = "form-check mb-2";
        wrap.innerHTML =
          '<input class="form-check-input" type="checkbox" id="' +
          id +
          '" data-key="' +
          f.key +
          '" checked>' +
          '<label class="form-check-label" for="' +
          id +
          '"><strong>' +
          f.label +
          "</strong>: " +
          f.value +
          ' <span class="text-muted">(' +
          f.confidence +
          ")</span></label>";
        container.appendChild(wrap);
      });
    }
    document.getElementById("uzhvOcrText").textContent = data.text_preview || "";
    document.getElementById("uzhvOcrApplyForm").classList.remove("d-none");
    document.getElementById("uzhvOcrApplyBtn").classList.toggle("d-none", !currentFields.length);
    showLoading(false);
  }

  document.querySelectorAll(".js-uzhv-ocr").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const previewUrl = btn.getAttribute("data-preview-url");
      applyUrl = btn.getAttribute("data-apply-url");
      document.getElementById("uzhvOcrModalLabel").textContent =
        "ИИ: " + (btn.getAttribute("data-title") || "документ");
      showLoading(true);
      document.getElementById("uzhvOcrError").classList.add("d-none");
      modal.show();

      fetch(previewUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken() },
        credentials: "same-origin",
      })
        .then(function (r) {
          return r.json().then(function (j) {
            return { ok: r.ok, body: j };
          });
        })
        .then(function (res) {
          if (!res.ok) {
            throw new Error(res.body.error || "Ошибка распознавания");
          }
          renderResult(res.body);
        })
        .catch(function (err) {
          showLoading(false);
          const box = document.getElementById("uzhvOcrError");
          box.textContent = err.message;
          box.classList.remove("d-none");
        });
    });
  });

  document.getElementById("uzhvOcrApplyBtn").addEventListener("click", function () {
    const payload = { fields: {} };
    document.querySelectorAll("#uzhvOcrFields input[type=checkbox]:checked").forEach(function (cb) {
      const key = cb.getAttribute("data-key");
      const field = currentFields.find(function (f) {
        return f.key === key;
      });
      if (field) payload.fields[key] = field.value;
    });
    if (!Object.keys(payload.fields).length) {
      alert("Выберите хотя бы одно поле");
      return;
    }
    fetch(applyUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, body: j };
        });
      })
      .then(function (res) {
        if (!res.ok) throw new Error(res.body.error || "Не удалось применить");
        modal.hide();
        window.location.reload();
      })
      .catch(function (err) {
        alert(err.message);
      });
  });
})();
