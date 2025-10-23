// app/static/js/profile_menu.js
(function () {
  const btn  = document.getElementById('profile-menu-btn');
  const menu = document.getElementById('profile-menu');
  if (!btn || !menu) return;

  const isOpen = () => !menu.classList.contains('hidden');
  const open   = () => { menu.classList.remove('hidden'); btn.setAttribute('aria-expanded','true'); };
  const close  = () => { menu.classList.add('hidden');    btn.setAttribute('aria-expanded','false'); };

  // Toggle on button click
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation(); // avoid immediate close from other global click handlers
    isOpen() ? close() : open();
  });

  // Click-away (capture phase = robust around overlays)
  document.addEventListener('click', (e) => {
    if (!isOpen()) return;
    if (menu.contains(e.target) || btn.contains(e.target)) return;
    close();
  }, true);

  // ESC to close
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen()) close();
  });

  // ARIA
  btn.setAttribute('aria-haspopup', 'menu');
  btn.setAttribute('aria-expanded', 'false');
})();
