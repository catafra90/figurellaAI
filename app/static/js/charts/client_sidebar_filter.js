// static/js/charts/client_sidebar_filter.js
(function () {
  const root = document;
  const searchInput = root.getElementById('clientSearch');
  const onlyCurrent = root.getElementById('onlyCurrent');
  const CURRENT_WORD = /\bcurrent\b/i; // matches "Current client", etc.

  function getRows() {
    const tbody = root.querySelector('#client-sidebar .list-wrap tbody');
    return tbody ? Array.from(tbody.querySelectorAll('tr')) : [];
  }

  function isRowCurrent(row) {
    const status = (row.dataset.status || '').trim();
    return CURRENT_WORD.test(status);
  }

  function rowMatchesText(row, q) {
    if (!q) return true;
    return (row.textContent || '').toLowerCase().includes(q);
  }

  function applyFilters() {
    const q = (searchInput?.value || '').trim().toLowerCase();
    getRows().forEach(row => {
      const okText = rowMatchesText(row, q);
      const okCurr = !onlyCurrent?.checked || isRowCurrent(row);
      row.style.display = (okText && okCurr) ? '' : 'none';
    });
  }

  searchInput && searchInput.addEventListener('input', applyFilters);
  onlyCurrent && onlyCurrent.addEventListener('change', applyFilters);

  // Initial run after DOM paints
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyFilters);
  } else {
    applyFilters();
  }
})();
