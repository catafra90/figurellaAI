// static/js/profile_menu.js
(function () {
  function setup(idBtn = 'profile-menu-btn', idMenu = 'profile-menu') {
    const btn  = document.getElementById(idBtn);
    const menu = document.getElementById(idMenu);
    if (!btn || !menu || menu.__profileMenuInit) return;
    menu.__profileMenuInit = true; // guard against double init

    // Ensure hidden to start
    if (!menu.classList.contains('hidden')) menu.classList.add('hidden');

    // Make sure the menu can receive clicks and sits above UI
    menu.style.zIndex = '2100';
    menu.style.pointerEvents = 'auto';

    const open = () => {
      menu.classList.remove('hidden');
      btn.setAttribute('aria-expanded', 'true');
      const first = menu.querySelector('[role="menuitem"], a, button');
      if (first) setTimeout(() => first.focus?.({ preventScroll: true }), 0);
    };

    const close = () => {
      if (!menu.classList.contains('hidden')) {
        menu.classList.add('hidden');
        btn.setAttribute('aria-expanded', 'false');
      }
    };

    const toggle = (e) => {
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation?.();
      menu.classList.contains('hidden') ? open() : close();
    };

    // Open/close (support mouse, touch, and pointer)
    btn.addEventListener('click', toggle, { passive: false });
    btn.addEventListener('pointerdown', () => {}, { passive: true });
    btn.addEventListener('touchstart', () => {}, { passive: true });

    // ✅ Close when clicking outside (use contains, not equality)
    document.addEventListener('click', (e) => {
      if (!menu.contains(e.target) && !btn.contains(e.target)) close();
    }, { capture: true });

    // Close on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') close();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setup());
  } else {
    setup();
  }
})();
