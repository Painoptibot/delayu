(function () {
  "use strict";

  var scene = document.querySelector("[data-delayu-welcome-scene]");
  if (!scene) return;

  var layers = scene.querySelectorAll("[data-depth]");
  if (!layers.length) return;

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  var targetX = 0;
  var targetY = 0;
  var currentX = 0;
  var currentY = 0;

  function onMove(event) {
    var rect = scene.getBoundingClientRect();
    targetX = (event.clientX - rect.left) / rect.width - 0.5;
    targetY = (event.clientY - rect.top) / rect.height - 0.5;
  }

  function reset() {
    targetX = 0;
    targetY = 0;
  }

  function tick() {
    currentX += (targetX - currentX) * 0.1;
    currentY += (targetY - currentY) * 0.1;

    layers.forEach(function (layer) {
      var depth = parseFloat(layer.getAttribute("data-depth") || "0.3");
      var tx = currentX * depth * 10;
      var ty = currentY * depth * 6;
      var extra = "";
      if (layer.classList.contains("delayu-welcome-scene__layer--man")) {
        extra = "translateX(-50%) ";
      }
      layer.style.transform = extra + "translate3d(" + tx + "px, " + ty + "px, 0)";
    });

    window.requestAnimationFrame(tick);
  }

  scene.addEventListener("mousemove", onMove);
  scene.addEventListener("mouseleave", reset);
  window.requestAnimationFrame(tick);
})();
