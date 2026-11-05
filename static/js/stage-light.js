/* Luz y parallax de la ficha del enfrentamiento: el puntero mueve la fuente de luz del escenario
   y ladea un poco los escudos (variables CSS --lx, --ly). Sin puntero fino o con movimiento
   reducido no hace nada. */
(function () {
    var stage = document.querySelector('.z-versus--stage');
    if (!stage || !window.matchMedia) { return; }
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || !window.matchMedia('(pointer: fine)').matches) { return; }
    var frame = 0;
    var x = 0;
    var y = 0;
    function paint() {
        frame = 0;
        stage.style.setProperty('--lx', x.toFixed(3));
        stage.style.setProperty('--ly', y.toFixed(3));
    }
    stage.addEventListener('pointermove', function (e) {
        var r = stage.getBoundingClientRect();
        x = ((e.clientX - r.left) / r.width) * 2 - 1;
        y = ((e.clientY - r.top) / r.height) * 2 - 1;
        if (!frame) { frame = requestAnimationFrame(paint); }
    });
    stage.addEventListener('pointerleave', function () {
        x = 0;
        y = 0;
        if (!frame) { frame = requestAnimationFrame(paint); }
    });
})();
