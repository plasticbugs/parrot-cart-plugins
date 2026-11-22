// All plugins (plugins/): search, filters, sort and pages over the cards the page
// already holds. The index is in the page (#browse-data, the same as
// plugins/index.json), so nothing is fetched. Without script every card shows.
// With it, what you pick lives in the address: a link keeps it, and Back undoes it.
(() => {
  const root = document.querySelector('[data-browse]');
  const source = document.getElementById('browse-data');
  if (!root || !source) return;
  const index = JSON.parse(source.textContent);
  const form = document.getElementById('browse-form');
  const input = form.querySelector('input[name="q"]');
  const sort = document.getElementById('sort');
  const list = document.getElementById('browse-list');
  const results = document.getElementById('browse-results');
  const status = root.querySelector('[role="status"]');
  const empty = root.querySelector('.browse__empty');
  const pager = root.querySelector('.pager');
  const toggle = root.querySelector('.browse__toggle');
  const panel = document.getElementById(toggle.getAttribute('aria-controls'));
  const badge = toggle.querySelector('.browse__on');
  const clears = Array.from(root.querySelectorAll('[data-clear]'));
  const words = root.dataset;          // the page's words, from site/copy.toml
  const per = Number(words.perPage) || 12;
  const FACETS = ['type', 'works', 'opens', 'by'];
  const fill = (s, v) => s.replace(/\{(\w+)\}/g, (m, k) => (k in v ? String(v[k]) : m));
  const byName = (a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : a.p.id < b.p.id ? -1 : 1);
  const newest = (a, b) => (a.p.published < b.p.published ? 1 : a.p.published > b.p.published ? -1 : byName(a, b));

  // each plugin: its card, what each filter sees in it, and the words a search looks through
  const cards = new Map(Array.from(list.children, (li) => [li.dataset.id, li]));
  const names = index.names || { tags: {}, works_with: {} };
  const items = index.plugins.filter((p) => cards.has(p.id)).map((p) => ({
    p,
    card: cards.get(p.id),
    key: p.name.toLowerCase(),
    values: { type: p.tags, works: p.works_with, opens: p.standalone ? p.opens.concat('app') : p.opens, by: [p.made_by] },
    text: [p.name, p.description, p.by, p.id, p.opens.join(' '), p.tags.join(' '),
      p.tags.map((t) => names.tags[t] || '').join(' '),
      p.works_with.map((w) => names.works_with[w] || '').join(' ')].join(' ').toLowerCase(),
  }));
  const boxes = {};
  FACETS.forEach((f) => { boxes[f] = Array.from(form.querySelectorAll(`input[type="checkbox"][name="${f}"]`)); });

  // ---- the state and the address that holds it ----
  const blank = (sortBy = 'name') => {
    const st = { q: '', sort: sortBy, page: 1 };
    FACETS.forEach((f) => { st[f] = new Set(); });
    return st;
  };
  const read = () => {
    const q = new URLSearchParams(window.location.search);
    const st = blank(q.get('sort') === 'new' ? 'new' : 'name');
    st.q = (q.get('q') || '').slice(0, 200);
    st.page = Math.max(1, parseInt(q.get('page'), 10) || 1);
    FACETS.forEach((f) => {
      const ok = new Set(boxes[f].map((b) => b.value));
      q.getAll(f).forEach((v) => { if (ok.has(v)) st[f].add(v); });
    });
    return st;
  };
  const address = (st, page = st.page) => {
    const q = new URLSearchParams();
    if (st.q.trim()) q.set('q', st.q.trim());
    FACETS.forEach((f) => boxes[f].forEach((b) => { if (st[f].has(b.value)) q.append(f, b.value); }));
    if (st.sort !== 'name') q.set('sort', st.sort);
    if (page > 1) q.set('page', String(page));
    const s = q.toString();
    return s ? `?${s}` : window.location.pathname;
  };
  let state = read();

  const terms = () => state.q.toLowerCase().split(/\s+/).filter(Boolean);
  // a plugin fits when it has every word searched for, and one of the ticked choices in each
  // filter (skip: a filter left out, to count what its own choices would find)
  const fits = (it, ws, skip) => ws.every((w) => it.text.includes(w))
    && FACETS.every((f) => f === skip || state[f].size === 0 || it.values[f].some((v) => state[f].has(v)));

  const el = (tag, text, attrs = {}) => {
    const x = document.createElement(tag);
    if (text != null) x.textContent = text;
    Object.entries(attrs).forEach(([k, v]) => x.setAttribute(k, v));
    return x;
  };

  const drawPager = (pages) => {
    const ul = pager.querySelector('ul');
    ul.textContent = '';
    pager.hidden = pages < 2;
    if (pages < 2) return;
    const add = (child, attrs) => ul.appendChild(el('li', null, attrs)).appendChild(child);
    const link = (n, text, extra = {}) => el('a', text, Object.assign({ class: 'pager__link', href: address(state, n), 'data-page': n }, extra));
    const off = (text) => el('a', text, { class: 'pager__link', role: 'link', 'aria-disabled': 'true' });
    add(state.page > 1 ? link(state.page - 1, words.previous, { rel: 'prev' }) : off(words.previous), { class: 'pager__end' });
    const show = new Set([1, pages, state.page - 1, state.page, state.page + 1]);
    let last = 0;
    for (let n = 1; n <= pages; n += 1) {
      if (!show.has(n) && !(show.has(n - 1) && show.has(n + 1))) continue;     // one page between: show it
      if (n - last > 1) add(el('span', '…'), { class: 'pager__gap', 'aria-hidden': 'true' });
      const label = { 'aria-label': fill(words.page, { page: n }) };
      if (n === state.page) label['aria-current'] = 'page';
      add(link(n, String(n), label));
      last = n;
    }
    add(state.page < pages ? link(state.page + 1, words.next, { rel: 'next' }) : off(words.next), { class: 'pager__end' });
  };

  const render = (moved) => {
    const ws = terms();
    const hits = items.filter((it) => fits(it, ws)).sort(state.sort === 'new' ? newest : byName);
    const pages = Math.max(1, Math.ceil(hits.length / per));
    state.page = Math.min(state.page, pages);
    const first = (state.page - 1) * per;
    const shown = hits.slice(first, first + per);
    const on = new Set(shown);
    // this page's cards first, in order, and the rest after them, hidden
    shown.forEach((it) => { it.card.hidden = false; list.appendChild(it.card); });
    items.forEach((it) => { if (!on.has(it)) { it.card.hidden = true; list.appendChild(it.card); } });
    const n = hits.length;
    status.textContent = n === 1 ? words.countOne
      : n <= per ? fill(words.count, { count: n })
        : fill(words.countPage, { first: first + 1, last: first + shown.length, count: n });
    list.setAttribute('aria-label', fill(words.list, { page: state.page, pages }));
    list.hidden = n === 0;
    empty.hidden = n > 0;
    // each choice's number: what it would find, with everything else as it is
    FACETS.forEach((f) => boxes[f].forEach((b) => {
      const c = items.filter((it) => it.values[f].includes(b.value) && fits(it, ws, f)).length;
      b.closest('label').querySelector('.facet__n').textContent = String(c);
      b.closest('li').classList.toggle('is-none', c === 0 && !b.checked);
    }));
    const picked = FACETS.reduce((s, f) => s + state[f].size, 0);
    badge.textContent = String(picked);
    badge.hidden = picked === 0;
    clears.forEach((c) => { if (!c.closest('.browse__empty')) c.hidden = !(picked || ws.length); });
    drawPager(pages);
    if (moved) {                          // a new page: the list takes the focus, its top in sight
      list.focus({ preventScroll: true });
      if (results.getBoundingClientRect().top < 0) results.scrollIntoView({ block: 'start' });
    }
  };

  const sync = () => {
    input.value = state.q;
    sort.value = state.sort;
    FACETS.forEach((f) => boxes[f].forEach((b) => { b.checked = state[f].has(b.value); }));
  };

  // a search is one step back: its first letter adds a step, the rest of the typing changes it
  let searching = false;
  let typing = 0;
  const step = (moved) => {
    searching = false;
    window.history.pushState(null, '', address(state));
    render(moved);
  };

  input.addEventListener('input', () => {
    state.q = input.value;
    state.page = 1;
    if (!searching) {
      searching = true;
      window.history.pushState(null, '', address(state));
    }
    render(false);
    window.clearTimeout(typing);
    typing = window.setTimeout(() => window.history.replaceState(null, '', address(state)), 250);
  });
  form.addEventListener('submit', (ev) => ev.preventDefault());
  form.addEventListener('change', (ev) => {
    const b = ev.target;
    if (b.type !== 'checkbox' || !FACETS.includes(b.name)) return;
    if (b.checked) state[b.name].add(b.value); else state[b.name].delete(b.value);
    state.page = 1;
    step(false);
  });
  sort.addEventListener('change', () => {
    state.sort = sort.value === 'new' ? 'new' : 'name';
    state.page = 1;
    step(false);
  });
  clears.forEach((c) => c.addEventListener('click', () => {
    state = blank(state.sort);
    sync();
    step(false);
    input.focus();
  }));
  pager.addEventListener('click', (ev) => {
    const a = ev.target.closest('a[data-page]');
    if (!a || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    ev.preventDefault();
    state.page = Number(a.dataset.page);
    step(true);
  });
  window.addEventListener('popstate', () => {
    searching = false;
    state = read();
    sync();
    render(false);
  });
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    panel.toggleAttribute('data-open', open);
  });

  sync();
  render(false);
  list.querySelectorAll('[data-more]').forEach((li) => li.removeAttribute('data-more'));
  if (window.location.search && address(state) !== window.location.search) {
    window.history.replaceState(null, '', address(state));          // what the address asked for, tidied
  }
})();
