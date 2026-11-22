export const recursiveErosionSource = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Recursive Erosion Particle Sphere</title>
<style>
  html, body {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    background: #0a0908;
    overflow: hidden;
  }
  #stage {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
  }
  canvas {
    display: block;
    width: 100%;
    height: 100%;
  }
</style>
</head>
<body>
<div id="stage">
  <canvas id="c"></canvas>
</div>
<script>
(function() {
  const canvas = document.getElementById('c');
  const ctx = canvas.getContext('2d', { alpha: false });
  let width = 0, height = 0;

  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    // Keep 1x pixel ratio for ultra-low CPU/GPU heat on laptops
    canvas.width = width;
    canvas.height = height;
  }
  window.addEventListener('resize', resize);
  resize();

  function erosionField(x, y, z, t) {
    const s1 = Math.sin(x * 2.1 + t * 0.7) * Math.cos(y * 2.1 - t * 0.5) * Math.sin(z * 2.1 + t * 0.4);
    const s2 = Math.sin(x * 4.7 - y * 3.3 + t * 1.1) * 0.45;
    return s1 + s2;
  }

  // Smooth 800-particle Fibonacci sphere at 35 FPS (<2% CPU)
  const NUM_PARTICLES = 800;
  const particles = [];
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));

  for (let i = 0; i < NUM_PARTICLES; i++) {
    const y = 1 - (i / (NUM_PARTICLES - 1)) * 2;
    const radiusAtY = Math.sqrt(1 - y * y);
    const theta = goldenAngle * i;
    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;
    const layer = (i % 3 === 0) ? 1.15 : ((i % 5 === 0) ? 0.80 : 1.0);
    particles.push({
      bx: x * layer,
      by: y * layer,
      bz: z * layer,
      size: 1.2 + ((i * 7) % 8) * 0.18,
      isEmber: (i % 3 === 0)
    });
  }

  let time = 0;
  let lastFrame = 0;
  const FRAME_MS = 28; // Smooth 35 FPS

  function render(now) {
    requestAnimationFrame(render);
    if (document.hidden || (now - lastFrame) < FRAME_MS) {
      return;
    }
    lastFrame = now;
    time += 0.014;
    const isLight = document.documentElement.dataset.sfMode === 'light';

    ctx.fillStyle = isLight ? '#f4f3f1' : '#0a0908';
    ctx.fillRect(0, 0, width, height);

    const cx = width * 0.5;
    const cy = height * 0.5;
    const baseRadius = Math.min(width, height) * 0.36;

    const grad = ctx.createRadialGradient(cx, cy, baseRadius * 0.08, cx, cy, baseRadius * 1.35);
    grad.addColorStop(0, 'rgba(255, 95, 0, 0.13)');
    grad.addColorStop(0.55, 'rgba(210, 80, 20, 0.04)');
    grad.addColorStop(1, 'rgba(10, 9, 8, 0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);

    const rotY = time * 0.42;
    const rotX = Math.sin(time * 0.25) * 0.35;
    const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
    const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

    for (let i = 0; i < NUM_PARTICLES; i++) {
      const p = particles[i];
      const e = erosionField(p.bx, p.by, p.bz, time);
      if (e < -0.55) continue;

      const displacement = 1 + e * 0.22;
      const px = p.bx * displacement;
      const py = p.by * displacement;
      const pz = p.bz * displacement;

      const x1 = px * cosY - pz * sinY;
      const z1 = pz * cosY + px * sinY;
      const y2 = py * cosX - z1 * sinX;
      const z2 = z1 * cosX + py * sinX;

      const fov = 2.6;
      const scale = fov / (fov + z2 + 1.35);
      const sx = cx + x1 * baseRadius * scale;
      const sy = cy + y2 * baseRadius * scale;

      const depthAlpha = Math.max(0.12, Math.min(0.95, (1.15 - z2) * 0.58));
      const r = p.size * scale;

      if (p.isEmber || e > 0.40) {
        ctx.fillStyle = 'rgba(255, 115, 35, ' + depthAlpha.toFixed(2) + ')';
      } else {
        ctx.fillStyle = 'rgba(235, 226, 215, ' + (depthAlpha * 0.65).toFixed(2) + ')';
      }
      ctx.fillRect(sx - r * 0.5, sy - r * 0.5, r * 1.6, r * 1.6);
    }
  }
  requestAnimationFrame(render);
})();
</script>
</body>
</html>`;
