// Estilo común de los gráficos de estadísticas («Social club»): sin cuadrículas ni ejes,
// barras redondeadas con su cifra dentro, líneas lima con área suave y tooltips oscuros.
// Se carga tras Chart.js y antes del script de cada vista.
(function () {
  if (typeof Chart === 'undefined') return;
  const LIME = '#B4F100';
  const INK = '#0A0A0A';

  Chart.defaults.font.family = "'Archivo', system-ui, sans-serif";
  Chart.defaults.font.weight = 700;
  Chart.defaults.scale.grid.display = false;
  Chart.defaults.scale.border.display = false;
  Chart.defaults.elements.bar.borderRadius = 10;
  Chart.defaults.elements.bar.borderSkipped = false;
  Chart.defaults.elements.line.tension = 0.35;
  Chart.defaults.elements.line.borderWidth = 4;
  Chart.defaults.elements.line.borderColor = LIME;
  Chart.defaults.elements.point.radius = 5;
  Chart.defaults.elements.point.hoverRadius = 7;
  Chart.defaults.elements.point.borderWidth = 3;
  Chart.defaults.elements.point.borderColor = '#171813';
  Chart.defaults.elements.point.backgroundColor = LIME;
  Chart.defaults.plugins.tooltip.backgroundColor = INK;
  Chart.defaults.plugins.tooltip.borderColor = 'rgba(180, 241, 0, 0.5)';
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.cornerRadius = 12;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.titleFont = { weight: 800 };

  const rgba = (hex, a) => {
    const m = /^#([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return hex;
    const n = parseInt(m[1], 16);
    return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  };

  // Área bajo cada línea: degradado del color de la línea a transparente.
  Chart.register({
    id: 'zAreaGradient',
    beforeDatasetsDraw(chart) {
      const area = chart.chartArea;
      if (!area) return;
      chart.data.datasets.forEach((ds, i) => {
        const meta = chart.getDatasetMeta(i);
        if (meta.type !== 'line' || !ds.fill || typeof ds.borderColor !== 'string') return;
        const g = chart.ctx.createLinearGradient(0, area.top, 0, area.bottom);
        g.addColorStop(0, rgba(ds.borderColor, 0.35));
        g.addColorStop(1, rgba(ds.borderColor, 0));
        ds.backgroundColor = g;
      });
    },
  });

  // Cifra de cada barra dentro de ella, en Anton, solo si cabe (barras anchas y altas; en las
  // horizontales, tramos de al menos 16 px).
  Chart.register({
    id: 'zBarValues',
    afterDatasetsDraw(chart) {
      if (chart.config.type !== 'bar') return;
      const horizontal = chart.options.indexAxis === 'y';
      const ctx = chart.ctx;
      ctx.save();
      ctx.font = horizontal ? "400 13px 'Anton', 'Archivo', sans-serif" : "400 18px 'Anton', 'Archivo', sans-serif";
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = INK;
      chart.data.datasets.forEach((ds, i) => {
        if (chart.isDatasetVisible && !chart.isDatasetVisible(i)) return;
        chart.getDatasetMeta(i).data.forEach((bar, j) => {
          const v = ds.data[j];
          if (typeof v !== 'number' || v <= 0) return;
          // Barras horizontales (UX-040): la cifra va en el centro del tramo, si cabe.
          if (horizontal) {
            if (Math.abs(bar.x - bar.base) < 16 || bar.height < 14) return;
            ctx.fillText(String(v), (bar.x + bar.base) / 2, bar.y);
            return;
          }
          if (bar.width < 26 || Math.abs(bar.base - bar.y) < 30) return;
          ctx.fillText(String(v), bar.x, (bar.y + bar.base) / 2);
        });
      });
      ctx.restore();
    },
  });
})();
