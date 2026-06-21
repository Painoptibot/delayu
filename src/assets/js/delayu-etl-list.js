(function () {
  document.querySelectorAll('.etl-run-open').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var url = btn.getAttribute('data-modal-url');
      if (!url) return;
      fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          var body = document.getElementById('etlRunModalBody');
          if (body) body.innerHTML = html;
          var modal = document.getElementById('etlRunModal');
          if (modal && window.bootstrap) new bootstrap.Modal(modal).show();
        });
    });
  });
})();
