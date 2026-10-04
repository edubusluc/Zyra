/*
 * Ajuste de la foto dentro del círculo al subirla (escudos de equipo y fotos de jugador).
 *
 * Se aplica solo a los <input type="file" name="photo"> de la página. Al elegir una imagen
 * se abre un popup donde se arrastra la foto y se acerca o aleja (rueda, pellizco o barra)
 * hasta que el círculo enseña lo que se quiere. Al aplicar, el input pasa a llevar un PNG
 * cuadrado con ese recorte (el servidor lo reduce a WebP como cualquier otra foto); al
 * cancelar, la foto elegida se descarta. Una vista previa redonda junto al campo enseña el
 * resultado. Sin JavaScript, o si el navegador no lo admite, se sube la foto tal cual.
 */
(function () {
  const OUTPUT = 512; // lado del PNG recortado (igual que PHOTO_MAX_SIZE en el servidor)
  const MAX_ZOOM = 4; // cuánto se puede acercar respecto a «llenar el círculo»
  const inputs = Array.from(document.querySelectorAll('input[type="file"][name="photo"]'));
  if (!inputs.length || !window.bootstrap || !window.DataTransfer || !HTMLCanvasElement.prototype.toBlob) return;

  let modalEl = null;
  let ui = null;

  function buildModal() {
    modalEl = document.createElement('div');
    modalEl.className = 'modal fade z-crop-modal';
    modalEl.tabIndex = -1;
    modalEl.setAttribute('aria-labelledby', 'zCropTitle');
    modalEl.setAttribute('aria-hidden', 'true');
    modalEl.innerHTML = `
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h2 class="modal-title h5" id="zCropTitle"></h2>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
          </div>
          <div class="modal-body">
            <p class="form-text mt-0" data-crop-help></p>
            <div class="z-crop-stage" data-crop-stage tabindex="0">
              <canvas data-crop-canvas></canvas>
              <div class="z-crop-ring" aria-hidden="true"></div>
            </div>
            <div class="z-crop-zoom">
              <button type="button" class="btn btn-outline-light btn-sm" data-crop-zoom="-1"><i class="fa-solid fa-magnifying-glass-minus" aria-hidden="true"></i></button>
              <input type="range" class="form-range" min="0" max="1000" value="0" data-crop-range>
              <button type="button" class="btn btn-outline-light btn-sm" data-crop-zoom="1"><i class="fa-solid fa-magnifying-glass-plus" aria-hidden="true"></i></button>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal"></button>
            <button type="button" class="btn btn-primary" data-crop-apply></button>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modalEl);
    const q = (sel) => modalEl.querySelector(sel);
    q('#zCropTitle').textContent = gettext('Ajusta la foto');
    q('[data-crop-help]').textContent = gettext('Arrastra la foto y usa el zoom para elegir lo que se verá dentro del círculo.');
    q('.btn-close').setAttribute('aria-label', gettext('Cerrar'));
    q('.modal-footer [data-bs-dismiss]').textContent = gettext('Cancelar');
    q('[data-crop-apply]').textContent = gettext('Usar esta foto');
    q('[data-crop-stage]').setAttribute('aria-label', gettext('Foto: arrastra o usa las flechas para moverla, + y - para el zoom'));
    q('[data-crop-range]').setAttribute('aria-label', gettext('Zoom'));
    q('[data-crop-zoom="-1"]').setAttribute('aria-label', gettext('Alejar'));
    q('[data-crop-zoom="1"]').setAttribute('aria-label', gettext('Acercar'));
    ui = {
      modal: bootstrap.Modal.getOrCreateInstance(modalEl),
      stage: q('[data-crop-stage]'),
      canvas: q('[data-crop-canvas]'),
      range: q('[data-crop-range]'),
      apply: q('[data-crop-apply]'),
    };
    wire();
  }

  // ---- Estado del recorte: posición (x, y) y escala de la imagen en píxeles del escenario ----
  let img = null;
  let current = null; // { input, file, applied }
  let size = 0; // lado del escenario
  let box = null; // cuadrado que rodea al círculo: { left, top, side }
  let scale = 1;
  let minScale = 1;
  let coverScale = 1;
  let x = 0;
  let y = 0;

  const w = () => img.naturalWidth * scale;
  const h = () => img.naturalHeight * scale;

  function clamp() {
    // Si la imagen es más grande que el círculo, no deja huecos; si es más pequeña, no sale de él.
    const lim = (pos, len, start) => (len >= box.side
      ? Math.min(start, Math.max(start + box.side - len, pos))
      : Math.max(start, Math.min(start + box.side - len, pos)));
    x = lim(x, w(), box.left);
    y = lim(y, h(), box.top);
  }

  function draw() {
    const ratio = window.devicePixelRatio || 1;
    const ctx = ui.canvas.getContext('2d');
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, size, size);
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, x, y, w(), h());
  }

  // Zoom alrededor de un punto del escenario (por defecto, el centro del círculo).
  function zoomTo(next, cx, cy) {
    next = Math.min(coverScale * MAX_ZOOM, Math.max(minScale, next));
    if (cx === undefined) { cx = box.left + box.side / 2; cy = box.top + box.side / 2; }
    x = cx - (cx - x) * (next / scale);
    y = cy - (cy - y) * (next / scale);
    scale = next;
    clamp();
    syncRange();
    draw();
  }

  // La barra va de 0 a 1000 en escala logarítmica: el zoom se nota igual en todo el recorrido.
  const maxScale = () => coverScale * MAX_ZOOM;
  function syncRange() {
    const t = Math.log(scale / minScale) / Math.log(maxScale() / minScale || 1);
    ui.range.value = String(Math.round((Number.isFinite(t) ? t : 0) * 1000));
  }
  const rangeScale = () => minScale * Math.pow(maxScale() / minScale, Number(ui.range.value) / 1000);

  function layout() {
    size = ui.stage.clientWidth;
    const ratio = window.devicePixelRatio || 1;
    ui.canvas.width = Math.round(size * ratio);
    ui.canvas.height = Math.round(size * ratio);
    const margin = Math.round(size * 0.08);
    box = { left: margin, top: margin, side: size - margin * 2 };
    coverScale = box.side / Math.min(img.naturalWidth, img.naturalHeight);
    minScale = box.side / Math.max(img.naturalWidth, img.naturalHeight);
    scale = coverScale;
    x = box.left + (box.side - w()) / 2;
    y = box.top + (box.side - h()) / 2;
    syncRange();
    draw();
  }

  function wire() {
    const pointers = new Map();
    let pinch = null;

    ui.stage.addEventListener('pointerdown', (e) => {
      ui.stage.setPointerCapture(e.pointerId);
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pointers.size === 2) {
        const [a, b] = Array.from(pointers.values());
        pinch = { dist: Math.hypot(a.x - b.x, a.y - b.y), scale };
      }
    });
    ui.stage.addEventListener('pointermove', (e) => {
      const prev = pointers.get(e.pointerId);
      if (!prev) return;
      const now = { x: e.clientX, y: e.clientY };
      pointers.set(e.pointerId, now);
      if (pointers.size === 1) {
        x += now.x - prev.x;
        y += now.y - prev.y;
        clamp();
        draw();
      } else if (pinch && pointers.size === 2) {
        const [a, b] = Array.from(pointers.values());
        const rect = ui.stage.getBoundingClientRect();
        zoomTo(pinch.scale * (Math.hypot(a.x - b.x, a.y - b.y) / pinch.dist),
          (a.x + b.x) / 2 - rect.left, (a.y + b.y) / 2 - rect.top);
      }
    });
    const release = (e) => {
      pointers.delete(e.pointerId);
      if (pointers.size < 2) pinch = null;
    };
    ui.stage.addEventListener('pointerup', release);
    ui.stage.addEventListener('pointercancel', release);

    ui.stage.addEventListener('wheel', (e) => {
      e.preventDefault();
      const rect = ui.stage.getBoundingClientRect();
      zoomTo(scale * Math.exp(-e.deltaY * 0.0015), e.clientX - rect.left, e.clientY - rect.top);
    }, { passive: false });

    ui.stage.addEventListener('keydown', (e) => {
      const step = e.shiftKey ? 20 : 6;
      const moves = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
      if (moves[e.key]) {
        x += moves[e.key][0];
        y += moves[e.key][1];
        clamp();
        draw();
      } else if (e.key === '+' || e.key === '=') {
        zoomTo(scale * 1.1);
      } else if (e.key === '-') {
        zoomTo(scale / 1.1);
      } else {
        return;
      }
      e.preventDefault();
    });

    ui.range.addEventListener('input', () => zoomTo(rangeScale()));
    modalEl.querySelectorAll('[data-crop-zoom]').forEach((btn) => {
      btn.addEventListener('click', () => zoomTo(scale * (btn.dataset.cropZoom === '1' ? 1.2 : 1 / 1.2)));
    });

    modalEl.addEventListener('shown.bs.modal', () => { layout(); ui.stage.focus(); });
    ui.apply.addEventListener('click', apply);
    modalEl.addEventListener('hidden.bs.modal', () => {
      // Cerrar sin aplicar descarta la foto elegida: el campo vuelve a como estaba.
      if (current && !current.applied) {
        current.input.value = '';
        showPreview(current.input, null);
      }
      if (img) URL.revokeObjectURL(img.src);
      img = null;
      current = null;
    });
  }

  function apply() {
    const out = document.createElement('canvas');
    out.width = OUTPUT;
    out.height = OUTPUT;
    const k = OUTPUT / box.side;
    const ctx = out.getContext('2d');
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(img, (x - box.left) * k, (y - box.top) * k, w() * k, h() * k);
    const target = current;
    out.toBlob((blob) => {
      if (!blob || !target) return;
      const base = (target.file.name || 'foto').replace(/\.[^.]+$/, '');
      const file = new File([blob], `${base}.png`, { type: 'image/png' });
      const dt = new DataTransfer();
      dt.items.add(file);
      target.input.files = dt.files;
      target.applied = true;
      showPreview(target.input, file);
      ui.modal.hide();
    }, 'image/png');
  }

  // ---- Vista previa redonda junto al campo ----
  function preview(input) {
    const form = input.form || document;
    let el = form.querySelector('[data-photo-preview]');
    if (!el) {
      el = document.createElement('img');
      el.alt = '';
      el.className = 'z-avatar z-avatar--sm';
      el.dataset.photoPreview = '';
      el.hidden = true;
      const row = document.createElement('div');
      row.className = 'z-crop-field';
      input.parentNode.insertBefore(row, input);
      row.append(el, input);
    }
    if (!('original' in el.dataset)) el.dataset.original = el.hidden ? '' : el.src;
    return el;
  }

  function showPreview(input, file) {
    const el = preview(input);
    if (el.dataset.objectUrl) URL.revokeObjectURL(el.dataset.objectUrl);
    delete el.dataset.objectUrl;
    if (file) {
      el.dataset.objectUrl = URL.createObjectURL(file);
      el.src = el.dataset.objectUrl;
      el.hidden = false;
    } else if (el.dataset.original) {
      el.src = el.dataset.original;
    } else {
      el.hidden = true;
    }
  }

  function open(input, file) {
    if (!modalEl) buildModal();
    const loaded = new Image();
    loaded.onload = () => {
      img = loaded;
      current = { input, file, applied: false };
      ui.modal.show();
    };
    loaded.onerror = () => URL.revokeObjectURL(loaded.src); // no es una imagen: lo dirá el servidor
    loaded.src = URL.createObjectURL(file);
  }

  inputs.forEach((input) => {
    preview(input);
    input.addEventListener('change', () => {
      const file = input.files && input.files[0];
      if (!file) { showPreview(input, null); return; }
      if (!file.type.startsWith('image/')) return;
      open(input, file);
    });
  });

  window.addEventListener('resize', () => {
    if (img && modalEl && modalEl.classList.contains('show')) layout();
  });
})();
