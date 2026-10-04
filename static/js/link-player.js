// «¿Quién eres en el equipo?» (players/templates/link_player.html): el buscador filtra la
// lista mientras se escribe y «Soy yo» pide confirmación con el nombre completo.
(function () {
  const normalize = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
  const search = document.querySelector('[data-claim-search]');
  const cards = Array.from(document.querySelectorAll('[data-claim-list] .z-claim'));
  const empty = document.querySelector('[data-claim-empty]');

  if (search) {
    const filter = () => {
      const q = normalize(search.value);
      let shown = 0;
      cards.forEach((card) => {
        const match = !q || normalize(card.dataset.name).includes(q);
        card.hidden = !match;
        if (match) shown += 1;
      });
      if (empty) empty.style.display = shown ? 'none' : '';
    };
    search.addEventListener('input', filter);
    // Con JavaScript no hace falta recargar la página al pulsar Intro.
    search.form.addEventListener('submit', (event) => { event.preventDefault(); filter(); });
    filter();
  }

  const modalEl = document.getElementById('claimModal');
  if (!modalEl || !window.bootstrap) return;
  const modal = new bootstrap.Modal(modalEl);
  let pending = null;
  cards.forEach((card) => {
    card.addEventListener('submit', (event) => {
      if (card.dataset.confirmed) return;
      event.preventDefault();
      pending = card;
      modalEl.querySelector('[data-claim-name]').textContent = card.dataset.name;
      modal.show();
    });
  });
  modalEl.querySelector('[data-claim-confirm]').addEventListener('click', () => {
    if (!pending) return;
    pending.dataset.confirmed = '1';
    pending.requestSubmit ? pending.requestSubmit() : pending.submit();
  });
}());
