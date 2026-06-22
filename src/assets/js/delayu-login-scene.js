(function () {
  "use strict";

  var COLORS = {
    primary: [105, 108, 255],
    accent: [144, 85, 253],
    cyan: [3, 195, 236],
  };

  function isDarkTheme() {
    return document.documentElement.getAttribute("data-bs-theme") === "dark";
  }

  function prefersReducedMotion() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  function dist(a, b) {
    var dx = a.x - b.x;
    var dy = a.y - b.y;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function initNetwork(scene) {
    var canvas = scene.querySelector("[data-delayu-login-network]");
    if (!canvas) return null;

    var ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return null;

    var nodes = [];
    var packets = [];
    var pulses = [];
    var mouse = { x: -9999, y: -9999, active: false };
    var size = { w: 0, h: 0, dpr: 1 };
    var running = true;
    var reduced = prefersReducedMotion();

    var CONFIG = {
      linkDist: 155,
      maxLinks: 4,
      nodeBase: reduced ? 45 : 95,
      nodeDensity: reduced ? 22000 : 11000,
      nodeCap: reduced ? 60 : 130,
      packetChance: reduced ? 0 : 0.018,
      pulseChance: reduced ? 0 : 0.006,
      mouseRadius: 160,
      mouseForce: 0.045,
    };

    function palette() {
      var dark = isDarkTheme();
      return {
        line: dark ? "rgba(165, 167, 255, " : "rgba(105, 108, 255, ",
        node: dark ? "rgba(200, 201, 255, " : "rgba(80, 84, 200, ",
        packet: dark ? [200, 201, 255] : COLORS.primary,
        glow: dark ? 0.35 : 0.22,
      };
    }

    function nodeCount() {
      var area = size.w * size.h;
      return Math.min(CONFIG.nodeCap, Math.max(CONFIG.nodeBase, Math.floor(area / CONFIG.nodeDensity)));
    }

    function spawnNodes() {
      nodes = [];
      var count = nodeCount();
      var pad = 40;
      for (var i = 0; i < count; i++) {
        nodes.push({
          x: rand(pad, size.w - pad),
          y: rand(pad, size.h - pad),
          vx: rand(-0.25, 0.25),
          vy: rand(-0.25, 0.25),
          r: rand(1.4, 2.8),
          phase: Math.random() * Math.PI * 2,
        });
      }
    }

    function resize() {
      var rect = scene.getBoundingClientRect();
      size.dpr = Math.min(window.devicePixelRatio || 1, 2);
      size.w = Math.max(1, rect.width);
      size.h = Math.max(1, rect.height);
      canvas.width = Math.floor(size.w * size.dpr);
      canvas.height = Math.floor(size.h * size.dpr);
      canvas.style.width = size.w + "px";
      canvas.style.height = size.h + "px";
      ctx.setTransform(size.dpr, 0, 0, size.dpr, 0, 0);
      spawnNodes();
      packets = [];
      pulses = [];
    }

    function findLinks() {
      var links = [];
      for (var i = 0; i < nodes.length; i++) {
        var connected = 0;
        for (var j = i + 1; j < nodes.length && connected < CONFIG.maxLinks; j++) {
          var d = dist(nodes[i], nodes[j]);
          if (d < CONFIG.linkDist) {
            links.push({ a: i, b: j, d: d });
            connected++;
          }
        }
      }
      return links;
    }

    function spawnPacket(links) {
      if (!links.length || Math.random() > CONFIG.packetChance) return;
      var link = links[(Math.random() * links.length) | 0];
      var reverse = Math.random() > 0.5;
      packets.push({
        a: reverse ? link.b : link.a,
        b: reverse ? link.a : link.b,
        t: 0,
        speed: rand(0.006, 0.014),
        hue: Math.random() > 0.82 ? "cyan" : Math.random() > 0.5 ? "accent" : "primary",
      });
    }

    function spawnPulse() {
      if (!nodes.length || Math.random() > CONFIG.pulseChance) return;
      var n = nodes[(Math.random() * nodes.length) | 0];
      pulses.push({ x: n.x, y: n.y, r: n.r, alpha: 0.85 });
    }

    function applyMouseForce(n) {
      if (!mouse.active) return;
      var dx = n.x - mouse.x;
      var dy = n.y - mouse.y;
      var d = Math.sqrt(dx * dx + dy * dy);
      if (d > CONFIG.mouseRadius || d < 1) return;
      var f = (1 - d / CONFIG.mouseRadius) * CONFIG.mouseForce;
      n.vx += (dx / d) * f * 18;
      n.vy += (dy / d) * f * 18;
    }

    function updateNodes() {
      var pad = 20;
      for (var i = 0; i < nodes.length; i++) {
        var n = nodes[i];
        if (!reduced) {
          applyMouseForce(n);
          n.x += n.vx;
          n.y += n.vy;
          n.vx *= 0.98;
          n.vy *= 0.98;
          n.vx += Math.sin(n.phase + performance.now() * 0.0004) * 0.012;
          n.vy += Math.cos(n.phase + performance.now() * 0.00035) * 0.012;
        }
        if (n.x < pad) {
          n.x = pad;
          n.vx *= -0.6;
        }
        if (n.x > size.w - pad) {
          n.x = size.w - pad;
          n.vx *= -0.6;
        }
        if (n.y < pad) {
          n.y = pad;
          n.vy *= -0.6;
        }
        if (n.y > size.h - pad) {
          n.y = size.h - pad;
          n.vy *= -0.6;
        }
      }
    }

    function draw() {
      var pal = palette();
      ctx.clearRect(0, 0, size.w, size.h);

      var links = findLinks();
      spawnPacket(links);
      spawnPulse();

      for (var li = 0; li < links.length; li++) {
        var link = links[li];
        var na = nodes[link.a];
        var nb = nodes[link.b];
        var alpha = (1 - link.d / CONFIG.linkDist) * 0.42;
        ctx.beginPath();
        ctx.moveTo(na.x, na.y);
        ctx.lineTo(nb.x, nb.y);
        ctx.strokeStyle = pal.line + alpha + ")";
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      for (var pi = pulses.length - 1; pi >= 0; pi--) {
        var p = pulses[pi];
        p.r += reduced ? 0.4 : 1.2;
        p.alpha -= reduced ? 0.012 : 0.022;
        if (p.alpha <= 0) {
          pulses.splice(pi, 1);
          continue;
        }
        var c = COLORS.cyan;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.strokeStyle = "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + p.alpha * 0.5 + ")";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      for (var pk = packets.length - 1; pk >= 0; pk--) {
        var pkt = packets[pk];
        pkt.t += pkt.speed;
        if (pkt.t >= 1) {
          packets.splice(pk, 1);
          continue;
        }
        var from = nodes[pkt.a];
        var to = nodes[pkt.b];
        if (!from || !to) {
          packets.splice(pk, 1);
          continue;
        }
        var px = from.x + (to.x - from.x) * pkt.t;
        var py = from.y + (to.y - from.y) * pkt.t;
        var col = pkt.hue === "cyan" ? COLORS.cyan : pkt.hue === "accent" ? COLORS.accent : COLORS.primary;
        ctx.beginPath();
        ctx.arc(px, py, 2.2, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(" + col[0] + "," + col[1] + "," + col[2] + ",0.95)";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(px, py, 6, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(" + col[0] + "," + col[1] + "," + col[2] + ",0.18)";
        ctx.fill();
      }

      var t = performance.now() * 0.002;
      for (var ni = 0; ni < nodes.length; ni++) {
        var node = nodes[ni];
        var pulse = 0.65 + Math.sin(t + node.phase) * 0.35;
        var nr = node.r * pulse;

        if (mouse.active) {
          var mdx = node.x - mouse.x;
          var mdy = node.y - mouse.y;
          var md = Math.sqrt(mdx * mdx + mdy * mdy);
          if (md < CONFIG.mouseRadius) {
            nr += (1 - md / CONFIG.mouseRadius) * 2.5;
          }
        }

        ctx.beginPath();
        ctx.arc(node.x, node.y, nr + 4, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(" + COLORS.primary[0] + "," + COLORS.primary[1] + "," + COLORS.primary[2] + "," + pal.glow + ")";
        ctx.fill();

        ctx.beginPath();
        ctx.arc(node.x, node.y, nr, 0, Math.PI * 2);
        ctx.fillStyle = pal.node + "0.75)";
        ctx.fill();
      }

      if (mouse.active && !reduced) {
        var grad = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, CONFIG.mouseRadius);
        grad.addColorStop(0, "rgba(105, 108, 255, 0.12)");
        grad.addColorStop(0.45, "rgba(144, 85, 253, 0.06)");
        grad.addColorStop(1, "rgba(105, 108, 255, 0)");
        ctx.fillStyle = grad;
        ctx.fillRect(mouse.x - CONFIG.mouseRadius, mouse.y - CONFIG.mouseRadius, CONFIG.mouseRadius * 2, CONFIG.mouseRadius * 2);
      }
    }

    function loop() {
      if (!running) return;
      updateNodes();
      draw();
      requestAnimationFrame(loop);
    }

    function setMouse(clientX, clientY, active) {
      var rect = scene.getBoundingClientRect();
      mouse.x = clientX - rect.left;
      mouse.y = clientY - rect.top;
      mouse.active = active;
    }

    scene.addEventListener(
      "mousemove",
      function (e) {
        setMouse(e.clientX, e.clientY, true);
      },
      { passive: true }
    );

    scene.addEventListener(
      "mouseleave",
      function () {
        mouse.active = false;
      },
      { passive: true }
    );

    var resizeObserver;
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(function () {
        resize();
      });
      resizeObserver.observe(scene);
    } else {
      window.addEventListener("resize", resize);
    }

    document.addEventListener("visibilitychange", function () {
      running = !document.hidden;
      if (running) requestAnimationFrame(loop);
    });

    resize();
    if (!reduced) {
      requestAnimationFrame(loop);
    } else {
      draw();
    }

    return {
      destroy: function () {
        running = false;
        if (resizeObserver) resizeObserver.disconnect();
      },
    };
  }

  function initParallax(scene) {
    if (prefersReducedMotion()) return;

    var stage = scene.querySelector("[data-delayu-login-stage]");
    if (!stage) return;

    var layers = stage.querySelectorAll("[data-depth]");
    var badges = scene.querySelectorAll(".delayu-login-scene__badge[data-depth]");
    var all = [];
    layers.forEach(function (el) {
      all.push(el);
    });
    badges.forEach(function (el) {
      all.push(el);
    });

    var raf = 0;
    var targetX = 0;
    var targetY = 0;
    var currentX = 0;
    var currentY = 0;

    function tick() {
      currentX += (targetX - currentX) * 0.08;
      currentY += (targetY - currentY) * 0.08;

      all.forEach(function (el) {
        var depth = parseFloat(el.getAttribute("data-depth")) || 0.3;
        var mx = currentX * depth * 22;
        var my = currentY * depth * 16;
        el.style.setProperty("--parallax-x", mx + "px");
        el.style.setProperty("--parallax-y", my + "px");
      });

      if (Math.abs(targetX - currentX) > 0.001 || Math.abs(targetY - currentY) > 0.001) {
        raf = requestAnimationFrame(tick);
      } else {
        raf = 0;
      }
    }

    function schedule() {
      if (!raf) raf = requestAnimationFrame(tick);
    }

    scene.addEventListener(
      "mousemove",
      function (e) {
        var rect = scene.getBoundingClientRect();
        targetX = (e.clientX - rect.left) / rect.width - 0.5;
        targetY = (e.clientY - rect.top) / rect.height - 0.5;
        schedule();
      },
      { passive: true }
    );

    scene.addEventListener(
      "mouseleave",
      function () {
        targetX = 0;
        targetY = 0;
        schedule();
      },
      { passive: true }
    );
  }

  document.querySelectorAll("[data-delayu-login-scene]").forEach(function (scene) {
    initNetwork(scene);
    initParallax(scene);
  });
})();
