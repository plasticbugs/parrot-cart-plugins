// The registry's two bits of script. Without them every plugin and every
// screen still shows: the search field and the tabs only appear with script.

// search: filter the catalogue's rows by what they say
document.querySelectorAll('[data-finder]').forEach((finder) => {
  const input = finder.querySelector('input');
  const status = finder.querySelector('[role="status"]');
  const table = document.getElementById(finder.dataset.finder);
  const rows = Array.from(table.querySelectorAll('tbody tr'));
  const empty = document.getElementById(finder.dataset.empty);
  finder.hidden = false;
  const say = (n) => { status.textContent = n === 1 ? '1 plugin' : n + ' plugins'; };
  const run = () => {
    const words = input.value.toLowerCase().trim().split(/\s+/).filter(Boolean);
    let n = 0;
    rows.forEach((tr) => {
      const hit = words.every((w) => tr.dataset.text.includes(w));
      tr.hidden = !hit;
      if (hit) n += 1;
    });
    empty.hidden = n > 0;
    say(n);
  };
  input.addEventListener('input', run);
  say(rows.length);
});

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
