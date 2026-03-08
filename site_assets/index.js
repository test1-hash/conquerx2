(() => {
  const form = document.getElementById('table-controls');
  const searchInput = document.getElementById('search-input');
  const sortSelect = document.getElementById('sort-select');
  const table = document.getElementById('ranking-table');
  const tbody = table ? table.querySelector('tbody') : null;
  const visibleCount = document.getElementById('visible-count');
  if (!form || !tbody || !searchInput || !sortSelect) return;

  const rows = Array.from(tbody.querySelectorAll('tr'));
  const params = new URLSearchParams(window.location.search);
  const initialQ = params.get('q') || '';
  const initialSort = params.get('sort') || 'rank';
  searchInput.value = initialQ;
  sortSelect.value = initialSort;

  const compare = (a, b, key) => {
    if (key === 'name') {
      return a.dataset.name.localeCompare(b.dataset.name, 'ja');
    }
    if (key === 'rank') {
      return Number(a.dataset.rank) - Number(b.dataset.rank);
    }
    const aVal = Number(a.dataset[key]);
    const bVal = Number(b.dataset[key]);
    if (bVal !== aVal) return bVal - aVal;
    return Number(a.dataset.rank) - Number(b.dataset.rank);
  };

  const apply = () => {
    const q = searchInput.value.trim().toLowerCase();
    const sort = sortSelect.value;
    let visible = 0;
    rows.forEach((row) => {
      const matched = !q || row.dataset.search.includes(q);
      row.classList.toggle('is-hidden', !matched);
      if (matched) visible += 1;
    });
    rows.sort((a, b) => compare(a, b, sort)).forEach((row) => tbody.appendChild(row));
    if (visibleCount) visibleCount.textContent = `表示件数: ${visible}`;
    const next = new URL(window.location.href);
    if (q) next.searchParams.set('q', q); else next.searchParams.delete('q');
    if (sort && sort !== 'rank') next.searchParams.set('sort', sort); else next.searchParams.delete('sort');
    window.history.replaceState({}, '', next);
  };

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    apply();
  });
  searchInput.addEventListener('input', apply);
  sortSelect.addEventListener('change', apply);
  apply();
})();
