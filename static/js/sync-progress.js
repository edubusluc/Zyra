// Barra de progreso de la sincronización con SNP (includes/sync_bar.html).
// Pregunta cada pocos segundos; al terminar recarga la página para ver el resultado.
(function () {
    const bar = document.querySelector('[data-sync-bar]');
    if (!bar) return;
    const fill = bar.querySelector('[data-sync-fill]');
    const track = bar.querySelector('[data-sync-track]');
    const stage = bar.querySelector('[data-sync-stage]');
    const pct = bar.querySelector('[data-sync-pct]');
    function poll() {
        fetch(bar.dataset.syncUrl, {headers: {'Accept': 'application/json'}, credentials: 'same-origin'})
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.active) { window.location.reload(); return; }
                fill.style.width = data.progress + '%';
                track.setAttribute('aria-valuenow', data.progress);
                pct.textContent = data.progress + '%';
                stage.textContent = data.stage;
                setTimeout(poll, 2000);
            })
            .catch(function () { setTimeout(poll, 5000); });
    }
    setTimeout(poll, 1500);
})();
