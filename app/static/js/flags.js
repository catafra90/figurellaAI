// Flag toggle + color pulse (works for <label> or <div> wrappers)
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flag-group').forEach(group => {
    const input = group.querySelector('input[type="checkbox"]');
    const btn   = group.querySelector('.flag-btn');
    if (!input || !btn) return;

    // If wrapper is a <div>, simulate label behavior
    if (group.tagName.toLowerCase() === 'div') {
      group.addEventListener('click', (e) => {
        if (e.target === input) return; // direct checkbox click already toggles
        input.checked = !input.checked;
        input.dispatchEvent(new Event('change', { bubbles: true }));
      });
    }

    // Ensure initial animation class state (SSR checked)
    applyPulse(btn, input);

    // Pulse on change
    input.addEventListener('change', () => applyPulse(btn, input));
  });

  function applyPulse(btn, input) {
    // reset animation classes
    btn.classList.remove('pulse-green', 'pulse-red', 'pulse-pink');
    // restart animation
    // eslint-disable-next-line no-unused-expressions
    btn.offsetWidth;

    if (!input.checked) return;

    switch (input.name) {
      case 'flag_nutrition':
        btn.classList.add('pulse-green');
        break;
      case 'flag_focus_case':
        btn.classList.add('pulse-red');
        break;
      case 'flag_goal':
        // ✅ Goal uses GREEN pulse (not pink)
        btn.classList.add('pulse-green');
        break;
      default:
        break;
    }
  }
});
