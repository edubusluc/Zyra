// Escudo 3D del selector de competición (alta de equipo). Expone ZyraStage.show(entrada) y pinta en el
// canvas un escudo metálico con el color y las siglas de la competición. three.js (static/vendor/three/)
// se descarga solo cuando hace falta; sin WebGL, si falla la descarga o con la librería sin cargar se ve la
// insignia de reserva. El dibujo se pausa si la pestaña está oculta o el escenario fuera de pantalla, y con
// «reducir movimiento» se pinta un único fotograma. El canvas es decorativo (aria-hidden, sin foco); su contenedor lleva el role="img" y el texto.
(function () {
  const root = document.querySelector('[data-competition-stage]');
  if (!root) return;
  const canvas = root.querySelector('[data-stage-canvas]');
  const fallback = root.querySelector('[data-stage-fallback]');
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SCRIPT = (document.querySelector('script[src*="competition-stage.js"]') || {}).src || '';
  const THREE_URL = SCRIPT.replace(/js\/competition-stage\.js.*$/, 'vendor/three/three.min.js');

  let pending = null;   // entrada pedida antes de que el 3D esté listo
  let api = null;       // { show, nudge } cuando el 3D está listo
  let failed = false;
  let started = false;

  function showFallback(entry) {
    fallback.hidden = false;
    canvas.hidden = true;
    if (entry) fallback.querySelector('[data-stage-mono]').textContent = entry.monogram;
  }

  function loadThree() {
    return new Promise((resolve, reject) => {
      if (window.THREE) { resolve(); return; }
      const script = document.createElement('script');
      script.src = THREE_URL;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  function build() {
    const THREE = window.THREE;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch (err) { throw new Error('webgl'); }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, window.matchMedia('(pointer: coarse)').matches ? 1.5 : 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.9;
    const scene = new THREE.Scene();
    const cam = new THREE.PerspectiveCamera(28, 1, 0.1, 50);
    cam.position.set(0, 0, 7.2);

    // Entorno sencillo para los reflejos del metal
    const envScene = new THREE.Scene();
    [[0xffffff, 8, [0, 4, 3], [6, 0.3, 3]], [0xffd9a0, 4, [-5, 0, 2], [0.3, 5, 3]], [0x9fd8ff, 4, [5, -1, 2], [0.3, 5, 3]], [0xffffff, 2, [0, -4, -3], [8, 0.3, 3]]]
      .forEach((m) => {
        const box = new THREE.Mesh(new THREE.BoxGeometry(m[3][0], m[3][1], m[3][2]), new THREE.MeshBasicMaterial({ color: new THREE.Color(m[0]).multiplyScalar(m[1]) }));
        box.position.set(m[2][0], m[2][1], m[2][2]);
        envScene.add(box);
      });
    envScene.add(new THREE.Mesh(new THREE.SphereGeometry(20, 16, 16), new THREE.MeshBasicMaterial({ color: 0x151612, side: THREE.BackSide })));
    scene.environment = new THREE.PMREMGenerator(renderer).fromScene(envScene, 0.04).texture;

    function shield(s) {
      const p = new THREE.Shape();
      const w = s; const t = 1.18 * s; const b = -1.25 * s;
      p.moveTo(-w, t); p.lineTo(w, t); p.lineTo(w, 0.15 * s);
      p.bezierCurveTo(w, -0.6 * s, 0.45 * s, -1 * s, 0, b);
      p.bezierCurveTo(-0.45 * s, -1 * s, -w, -0.6 * s, -w, 0.15 * s);
      p.lineTo(-w, t);
      return p;
    }
    const group = new THREE.Group();
    scene.add(group);
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0xdba400, metalness: 1, roughness: 0.28, envMapIntensity: 1.3 });
    const body = new THREE.Mesh(new THREE.ExtrudeGeometry(shield(1), { depth: 0.35, bevelEnabled: true, bevelThickness: 0.12, bevelSize: 0.1, bevelSegments: 6, curveSegments: 32 }), bodyMat);
    body.position.z = -0.17;
    group.add(body);
    const faceGeo = new THREE.ShapeGeometry(shield(0.84), 32);
    const pos = faceGeo.attributes.position; const uv = faceGeo.attributes.uv;
    for (let i = 0; i < pos.count; i += 1) uv.setXY(i, (pos.getX(i) / 0.84 + 1) / 2, (pos.getY(i) / 0.84 + 1.25) / 2.43);
    const faceMat = new THREE.MeshStandardMaterial({ color: 0xffffff, metalness: 0, roughness: 0.55, envMapIntensity: 0.25 });
    const face = new THREE.Mesh(faceGeo, faceMat);
    face.position.z = 0.315;
    group.add(face);
    scene.add(new THREE.AmbientLight(0xffffff, 0.5));
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(3, 4, 6);
    scene.add(key);

    // Cara del escudo: banda diagonal (eco del logotipo de Zyra), siglas y estrellas, en el color de la competición
    const textures = {};
    function makeTexture(entry) {
      const cv = document.createElement('canvas');
      cv.width = 1024; cv.height = 1024;
      const g = cv.getContext('2d');
      const col = entry.color;
      const grad = g.createLinearGradient(0, 0, 1024, 1024);
      grad.addColorStop(0, '#101210'); grad.addColorStop(1, '#1c1e1a');
      g.fillStyle = grad; g.fillRect(0, 0, 1024, 1024);
      g.save(); g.translate(512, 512); g.rotate(-Math.PI / 5.2);
      g.fillStyle = col; g.fillRect(-900, -150, 1800, 300);
      g.fillStyle = 'rgba(0,0,0,.18)'; g.fillRect(-900, 150, 1800, 26);
      g.restore();
      g.globalAlpha = 0.12; g.fillStyle = col;
      for (let k = 0; k < 10; k += 1) { g.beginPath(); g.moveTo(512, 120); g.lineTo(512 + (k - 4.5) * 180, 0); g.lineTo(512 + (k - 4) * 180, 0); g.fill(); }
      g.globalAlpha = 1;
      g.textAlign = 'center'; g.textBaseline = 'middle';
      g.font = '300px Anton, Impact, sans-serif'; g.lineWidth = 18; g.strokeStyle = '#0A0B09';
      g.strokeText(entry.monogram, 512, 520);
      g.fillStyle = '#F4F5F1'; g.fillText(entry.monogram, 512, 520);
      g.beginPath(); g.arc(512, 250, 62, 0, 7); g.fillStyle = col; g.fill();
      g.lineWidth = 7; g.strokeStyle = '#0A0B09';
      g.beginPath(); g.arc(402, 250, 110, -0.6, 0.6); g.stroke();
      g.beginPath(); g.arc(622, 250, 110, Math.PI - 0.6, Math.PI + 0.6); g.stroke();
      g.fillStyle = col; g.font = '70px Archivo, sans-serif'; g.fillText('★ ★ ★', 512, 850);
      const t = new THREE.CanvasTexture(cv);
      t.encoding = THREE.sRGBEncoding; t.anisotropy = 8;
      return t;
    }

    const col = new THREE.Color(0xdba400); const colTarget = new THREE.Color(0xdba400);
    let rot = 0; let spin = 0; let bounce = 0; let px = 0; let py = 0; let tx = 0; let ty = 0;
    const wrap = canvas.parentNode;
    function size() {
      const w = wrap.clientWidth; const h = wrap.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      cam.aspect = w / h;
      cam.position.z = w / h < 0.9 ? 9.5 : 7.2;
      cam.updateProjectionMatrix();
      render();
    }
    wrap.addEventListener('pointermove', (e) => {
      const r = wrap.getBoundingClientRect();
      tx = ((e.clientX - r.left) / r.width - 0.5) * 2; ty = ((e.clientY - r.top) / r.height - 0.5) * 2;
    });
    wrap.addEventListener('pointerleave', () => { tx = 0; ty = 0; });

    const clock = new THREE.Clock();
    function render() {
      const dt = Math.min(clock.getDelta(), 0.05); const t = clock.elapsedTime;
      rot += (spin - rot) * Math.min(1, dt * 4.5);
      bounce += (0 - bounce) * Math.min(1, dt * 4);
      px += (tx - px) * Math.min(1, dt * 5); py += (ty - py) * Math.min(1, dt * 5);
      group.rotation.y = rot + px * 0.45 + (reduce ? 0 : Math.sin(t * 0.7) * 0.25);
      group.rotation.x = py * 0.25;
      group.position.y = 0.16 + (reduce ? 0 : Math.sin(t * 1.2) * 0.08);
      const s = 1 + bounce * 0.12;
      group.scale.set(s, s, s);
      col.lerp(colTarget, Math.min(1, dt * 6));
      bodyMat.color.copy(col);
      renderer.render(scene, cam);
    }
    let visible = true; let raf = 0;
    const active = () => visible && !document.hidden;
    function loop() {
      cancelAnimationFrame(raf);
      if (!active()) return;
      render();
      raf = requestAnimationFrame(loop);
    }
    function wake() { if (active() && !reduce) { clock.getDelta(); loop(); } }
    if ('IntersectionObserver' in window) new IntersectionObserver((entries) => { visible = entries[0].isIntersecting; wake(); }).observe(wrap);
    document.addEventListener('visibilitychange', wake);
    if ('ResizeObserver' in window) new ResizeObserver(size).observe(wrap);

    const handle = {
      show(entry) {
        if (!textures[entry.code]) textures[entry.code] = makeTexture(entry);
        faceMat.map = textures[entry.code]; faceMat.needsUpdate = true;
        colTarget.set(entry.color);
        if (!reduce) { spin += Math.PI * 2; bounce = 1; }
        render();
      },
    };
    size();
    if (reduce) render(); else loop();
    return handle;
  }

  function start() {
    if (started) return;
    started = true;
    const fonts = document.fonts && document.fonts.load
      ? Promise.all([document.fonts.load('300px Anton'), document.fonts.load('70px Archivo')]).catch(() => {})
      : Promise.resolve();
    Promise.all([loadThree(), fonts]).then(() => {
      api = build();
      canvas.hidden = false; fallback.hidden = true;
      if (pending) api.show(pending);
    }).catch(() => { failed = true; showFallback(pending); });
  }

  window.ZyraStage = {
    show(entry) {
      pending = entry;
      if (api) { api.show(entry); return; }
      if (failed) { showFallback(entry); return; }
      showFallback(entry);   // insignia mientras llega el 3D
      start();
    },
  };
})();
