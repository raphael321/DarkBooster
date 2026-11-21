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
  let width = 0, height = 0, dpr = Math.min(window.devicePixelRatio || 1, 1.75);

  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener('resize', resize);
  resize();

  // Fast 3D Recursive Erosion Noise approximation (multi-octave trigonometric curl field)
  function erosionField(x, y, z, t) {
    const s1 = Math.sin(x * 2.1 + t * 0.7) * Math.cos(y * 2.1 - t * 0.5) * Math.sin(z * 2.1 + t * 0.4);
    const s2 = Math.sin(x * 4.7 - y * 3.3 + t * 1.1) * Math.cos(z * 4.5 + x * 2.7 - t * 0.8) * 0.5;
    const s3 = Math.cos((x + y + z) * 7.5 - t * 1.6) * 0.25;
    return s1 + s2 + s3;
  }

  // Fibonacci sphere particle distribution
  const NUM_PARTICLES = 2400;
  const particles = [];
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));

  for (let i = 0; i < NUM_PARTICLES; i++) {
    const y = 1 - (i / (NUM_PARTICLES - 1)) * 2;
    const radiusAtY = Math.sqrt(1 - y * y);
    const theta = goldenAngle * i;
    const x = Math.cos(theta) * radiusAtY;
    const z = Math.sin(theta) * radiusAtY;
    const layer = (i % 3 === 0) ? 1.18 : ((i % 5 === 0) ? 0.78 : 1.0);
    particles.push({
      bx: x * layer,
      by: y * layer,
      bz: z * layer,
      seed: (i * 1.6180339) % 1,
      size: 0.9 + ((i * 7) % 10) * 0.16,
      isEmber: (i % 4 === 0)
    });
  }

  let time = 0;
  function render() {
    if (document.hidden) {
      requestAnimationFrame(render);
      return;
    }
    time += 0.0085;
    const isLight = document.documentElement.dataset.sfMode === 'light';

    // Subtle motion trail background fill
    ctx.fillStyle = isLight ? 'rgba(244, 243, 241, 0.28)' : 'rgba(10, 9, 8, 0.30)';
    ctx.fillRect(0, 0, width, height);

    const cx = width * 0.5;
    const cy = height * 0.5;
    const baseRadius = Math.min(width, height) * 0.36;

    // Subtle radial ambient core glow
    const grad = ctx.createRadialGradient(cx, cy, baseRadius * 0.05, cx, cy, baseRadius * 1.45);
    if (isLight) {
      grad.addColorStop(0, 'rgba(255, 95, 0, 0.10)');
      grad.addColorStop(1, 'rgba(244, 243, 241, 0)');
    } else {
      grad.addColorStop(0, 'rgba(255, 95, 0, 0.12)');
      grad.addColorStop(0.5, 'rgba(210, 80, 20, 0.04)');
      grad.addColorStop(1, 'rgba(10, 9, 8, 0)');
    }
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);

    const rotY = time * 0.42;
    const rotX = Math.sin(time * 0.25) * 0.35;
    const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
    const cosX = Math.cos(rotX), sinX = Math.sin(rotX);

    for (let i = 0; i < NUM_PARTICLES; i++) {
      const p = particles[i];
      const e = erosionField(p.bx, p.by, p.bz, time);

      // Erode particles outward along fractal ridges
      if (e < -0.58) continue; // eroded void craters
      const displacement = 1 + e * 0.24 + Math.sin(time * 2 + p.seed * 12) * 0.03;

      const px = p.bx * displacement;
      const py = p.by * displacement;
      const pz = p.bz * displacement;

      // 3D rotation
      const x1 = px * cosY - pz * sinY;
      const z1 = pz * cosY + px * sinY;
      const y2 = py * cosX - z1 * sinX;
      const z2 = z1 * cosX + py * sinX;

      const fov = 2.6;
      const scale = fov / (fov + z2 + 1.35);
      const sx = cx + x1 * baseRadius * scale;
      const sy = cy + y2 * baseRadius * scale;

      const depthAlpha = Math.max(0.08, Math.min(1, (1.15 - z2) * 0.58));
      const r = p.size * scale * (e > 0.35 ? 1.35 : 1.0);

      if (p.isEmber || e > 0.42) {
        ctx.fillStyle = isLight
          ? 'rgba(230, 75, 0, ' + (depthAlpha * 0.85).toFixed(2) + ')'
          : 'rgba(255, 115, 35, ' + (depthAlpha * 0.92).toFixed(2) + ')';
      } else {
        ctx.fillStyle = isLight
          ? 'rgba(40, 36, 32, ' + (depthAlpha * 0.65).toFixed(2) + ')'
          : 'rgba(235, 226, 215, ' + (depthAlpha * 0.62).toFixed(2) + ')';
      }

      ctx.beginPath();
      ctx.arc(sx, sy, r, 0, Math.PI * 2);
      ctx.fill();
    }

    requestAnimationFrame(render);
  }
  requestAnimationFrame(render);
})();
</script>
</body>
</html>`;
