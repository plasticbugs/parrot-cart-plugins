// The site's script for every page: the tabs that switch the home page's
// screens. Without it every screen still shows. (All plugins has its own,
// browse.js.)

// the switcher: one screen at a time, the tabs move with the arrow keys
document.querySelectorAll('[data-switch]').forEach((sw) => {
  const tabs = Array.from(sw.querySelectorAll('[role="tab"]'));
  const show = (i, focus) => {
    tabs.forEach((t, k) => {
      const on = k === i;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
    });
    if (focus) tabs[i].focus();
  };
  tabs.forEach((t, i) => {
    t.addEventListener('click', () => show(i, false));
    t.addEventListener('keydown', (e) => {
      const k = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
      if (k) { e.preventDefault(); show((i + k + tabs.length) % tabs.length, true); }
      if (e.key === 'Home') { e.preventDefault(); show(0, true); }
      if (e.key === 'End') { e.preventDefault(); show(tabs.length - 1, true); }
    });
  });
  show(Math.max(0, tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true')), false);
});
