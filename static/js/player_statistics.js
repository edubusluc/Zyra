(function () {
  const read = (id) => JSON.parse(document.getElementById(id).textContent);
  const seasons = read('data-seasons');
  const affinity = read('data-affinity');
  const lang = document.documentElement.lang || 'es';

  // Paleta Zyra (tema oscuro)
  const C = {
    navy: '#B4F100',
    gold: '#B4F100',
    win: '#B4F100',
    loss: '#FF5C63',
    muted: '#A3A3A3',
    line: 'rgba(255, 255, 255, 0.08)',
  };

  Chart.defaults.font.family = "'Archivo', system-ui, sans-serif";
  Chart.defaults.color = C.muted;
  Chart.defaults.borderColor = C.line;

  const base = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } } },
  };

  // Partidos jugados por temporada (ganados + perdidos apilados)
  const playedCanvas = document.getElementById('chartPlayed');
  if (playedCanvas) new Chart(playedCanvas, {
    type: 'bar',
    data: {
      labels: seasons.labels,
      datasets: [
        { label: gettext('Ganados'), data: seasons.wins, backgroundColor: C.win, borderRadius: 4 },
        { label: gettext('Perdidos'), data: seasons.losses, backgroundColor: C.loss, borderRadius: 4 },
      ],
    },
    options: {
      ...base,
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, grid: { color: C.line } },
      },
    },
  });

  // Evolución del % de victorias
  const pctCanvas = document.getElementById('chartPct');
  if (pctCanvas) new Chart(pctCanvas, {
    type: 'line',
    data: {
      labels: seasons.labels,
      datasets: [{
        label: gettext('% victorias'),
        data: seasons.pct,
        borderColor: C.navy,
        backgroundColor: 'rgba(180, 241, 0, 0.15)',
        pointBackgroundColor: C.gold,
        pointBorderColor: '#0B0B0B',
        pointRadius: 5,
        tension: 0.3,
        fill: true,
      }],
    },
    options: {
      ...base,
      plugins: { ...base.plugins, legend: { display: false },
        tooltip: { callbacks: { label: (c) => ` ${c.parsed.y}%` } } },
      scales: {
        x: { grid: { display: false } },
        y: { min: 0, max: 100, ticks: { callback: (v) => v + '%' }, grid: { color: C.line } },
      },
    },
  });

  // Evolución de los puntos SNP en la temporada (mismo estilo que el % de victorias)
  const snp = read('data-snp');
  const snpCanvas = document.getElementById('chartSnp');
  if (snpCanvas) {
    new Chart(snpCanvas, {
      type: 'line',
      data: {
        labels: snp.labels,
        datasets: [{
          label: gettext('Puntos SNP'),
          data: snp.scores,
          borderColor: C.navy,
          backgroundColor: 'rgba(180, 241, 0, 0.15)',
          pointBackgroundColor: C.gold,
          pointBorderColor: '#0B0B0B',
          pointRadius: 5,
          tension: 0.3,
          fill: true,
        }],
      },
      options: {
        ...base,
        plugins: { ...base.plugins, legend: { display: false },
          tooltip: { callbacks: {
          label: (c) => ' ' + interpolate(gettext('%(n)s puntos'), { n: c.parsed.y.toLocaleString(lang) }, true),
          afterLabel: (c) => {
            const d = snp.changes[c.dataIndex];
            if (d === null || d === undefined) return '';
            return ' ' + (d > 0 ? '▲ +' : d < 0 ? '▼ ' : '= ') + d.toLocaleString(lang);
          },
        } } },
        scales: {
          x: { grid: { display: false } },
          y: { ticks: { callback: (v) => v.toLocaleString(lang) }, grid: { color: C.line } },
        },
      },
    });
  }

  // Afinidad con compañeros (barras horizontales).
  // Por defecto solo compañeros que siguen en el equipo; "Incluir antiguos" añade
  // a los que se fueron o se eliminaron.
  // En pantallas estrechas: "Eduardo Bustamante Lucena (3)" -> "E. Bustamante (3)"
  const PARTICLES = new Set(['de', 'del', 'la', 'las', 'los', 'y', 'da', 'do', 'dos', 'van', 'von']);
  const shortName = (name, max) => {
    if (name.length <= max) return name;
    const parts = name.trim().split(/\s+/);
    const surname = parts.slice(1).find((w) => !PARTICLES.has(w.toLowerCase()));
    const short = surname ? `${parts[0][0]}. ${surname}` : name;
    return short.length <= max ? short : `${short.slice(0, max - 1)}…`;
  };
  const affinityBox = document.getElementById('affinityChart');
  const affinityLabel = (a) => {
    const max = affinityBox.clientWidth < 520 ? 14 : 40;
    return `${shortName(a.name, max)} (${a.games})`;
  };

  const affinityChart = new Chart(document.getElementById('chartAffinity'), {
    type: 'bar',
    data: { labels: [], datasets: [{ label: gettext('Afinidad'), data: [], backgroundColor: [], borderRadius: 4, maxBarThickness: 56 }] },
    options: {
      ...base,
      indexAxis: 'y',
      plugins: {
        ...base.plugins,
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (c) => {
              const a = affinityChart.$rows[c.dataIndex];
              return ` ${a.affinity}% · ` + interpolate(gettext('%(wins)sV - %(losses)sD'), { wins: a.wins, losses: a.losses }, true);
            },
            afterLabel: (c) => (affinityChart.$rows[c.dataIndex].in_team ? '' : ' ' + gettext('Ya no está en el equipo')),
          },
        },
      },
      scales: {
        x: { min: 0, max: 100, grid: { color: C.line } },
        y: {
          grid: { display: false },
          ticks: { autoSkip: false, callback: (v, i) => affinityLabel(affinityChart.$rows[i]) },
        },
      },
    },
  });

  function showAffinity(scope) {
    const rows = scope === 'all' ? affinity : affinity.filter((a) => a.in_team);
    affinityChart.$rows = rows;
    affinityChart.data.labels = rows.map((a) => `${a.name} (${a.games})`);
    const ds = affinityChart.data.datasets[0];
    ds.data = rows.map((a) => a.affinity);
    // por encima del 50 % rinden mejor de lo esperado juntos; los antiguos, más apagados
    ds.backgroundColor = rows.map((a) => (a.affinity >= 50 ? C.win : C.loss) + (a.in_team ? '' : '80'));
    affinityChart.update();
    affinityBox.hidden = rows.length === 0;
    document.getElementById('affinityEmpty').hidden = rows.length > 0;
  }

  const scopeButtons = document.querySelectorAll('.st-aff-scope [data-scope]');
  scopeButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      scopeButtons.forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
      showAffinity(btn.dataset.scope);
    });
  });
  showAffinity('team');
})();