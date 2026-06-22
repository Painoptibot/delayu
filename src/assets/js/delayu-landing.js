(function () {
  "use strict";

  function animateCounter(el) {
    var target = parseInt(el.getAttribute("data-count"), 10);
    if (!target || el.dataset.animated === "1") return;
    el.dataset.animated = "1";
    var duration = 1600;
    var start = performance.now();

    function tick(now) {
      var p = Math.min((now - start) / duration, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased);
      if (p < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  }

  function initReveal() {
    var nodes = document.querySelectorAll(
      ".delayu-landing__stat, .delayu-landing__pillar"
    );
    if (!("IntersectionObserver" in window)) {
      nodes.forEach(function (n) {
        n.classList.add("is-visible");
      });
      document.querySelectorAll("[data-count]").forEach(animateCounter);
      return;
    }

    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          var counter = entry.target.querySelector("[data-count]");
          if (counter) animateCounter(counter);
          io.unobserve(entry.target);
        });
      },
      { threshold: 0.2, rootMargin: "0px 0px -40px 0px" }
    );

    nodes.forEach(function (n) {
      io.observe(n);
    });
  }

  function initParallax() {
    var mock = document.querySelector(".delayu-landing__dashboard-mock");
    if (!mock || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }
    window.addEventListener(
      "mousemove",
      function (e) {
        var x = (e.clientX / window.innerWidth - 0.5) * 10;
        var y = (e.clientY / window.innerHeight - 0.5) * 8;
        mock.style.transform =
          "perspective(1200px) rotateY(" +
          (-8 + x * 0.3) +
          "deg) rotateX(" +
          (4 - y * 0.25) +
          "deg)";
      },
      { passive: true }
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      initReveal();
      initParallax();
    });
  } else {
    initReveal();
    initParallax();
  }
})();
