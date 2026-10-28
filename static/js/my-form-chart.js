// «Mi forma»: al pasar el ratón (o tocar) la gráfica de puntos SNP, marca el punto más cercano y muestra
// sus puntos y su fecha. Los datos salen de la lista oculta [data-myform-points] de la propia tarjeta.
(function () {
    var chart = document.querySelector('.z-myform-chart');
    var list = document.querySelector('[data-myform-points]');
    if (!chart || !list) return;
    var points = Array.prototype.map.call(list.children, function (li) {
        return { x: parseFloat(li.dataset.x), y: parseFloat(li.dataset.y), score: li.dataset.score, date: li.dataset.date };
    });
    var marker = chart.querySelector('.z-myform-hover');
    var tip = chart.querySelector('.z-myform-tip');

    function show(event) {
        var box = chart.getBoundingClientRect();
        var pct = (event.clientX - box.left) / box.width * 100;
        var best = points.reduce(function (a, b) { return Math.abs(b.x - pct) < Math.abs(a.x - pct) ? b : a; });
        marker.style.left = best.x + '%';
        marker.style.top = best.y + '%';
        tip.textContent = best.date + ' · ' + best.score;
        tip.style.left = Math.min(Math.max(best.x, 14), 86) + '%';
        tip.style.top = best.y + '%';
        tip.classList.toggle('z-myform-tip--below', best.y < 35);
        marker.hidden = false;
        tip.hidden = false;
    }

    function hide() {
        marker.hidden = true;
        tip.hidden = true;
    }

    chart.addEventListener('pointermove', show);
    chart.addEventListener('pointerdown', show);
    chart.addEventListener('pointerleave', hide);
})();
