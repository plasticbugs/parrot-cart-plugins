// The icon editor: two 8 x 8 one-bit icons, as a plugin's header holds them
// (a byte a row, bit 7 the left pixel). It draws on buttons the page already
// has, redraws the two glyphs the preview screens use, and reads and writes
// the hex string and the .txt file the SDK takes. Nothing is sent anywhere:
// no requests, and a file you open is read here in the page.
(() => {
  const root = document.querySelector('[data-editor]');
  if (!root) return;
  const fallback = { plugin: root.dataset.plug, file: root.dataset.file };
  const keyOf = { plugin: 'p', file: 'f' };

  const toHex = (rows) => rows.map((b) => b.toString(16).padStart(2, '0')).join('');
  const toTxt = (rows) => rows.map((b) => [...Array(8)].map((_, x) => (b >> (7 - x) & 1 ? '#' : '.')).join('')).join('\n');
  const fromHex = (s) => {
    const h = s.replace(/0x/gi, '').replace(/[\s,]/g, '');
    if (!/^[0-9a-f]{16}$/i.test(h)) return null;
    return h.match(/../g).map((b) => parseInt(b, 16));
  };
  // as mkcvp.py reads it: blank lines and the space around a line don't count
  const fromTxt = (s) => {
    const lines = s.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (lines.length !== 8) return `It has ${lines.length} lines, but an icon has 8.`;
    const bad = lines.findIndex((l) => !/^[#.]{8}$/.test(l));
    if (bad >= 0) return `Line ${bad + 1} should be 8 characters, each one # or .`;
    return lines.map((l) => parseInt(l.replace(/#/g, '1').replace(/\./g, '0'), 2));
  };
  // the same runs of pixels the site's own screens are drawn with
  const toPath = (rows) => {
    let d = '';
    rows.forEach((b, y) => {
      for (let x = 0; x < 8;) {
        if (b >> (7 - x) & 1) {
          const start = x;
          while (x < 8 && (b >> (7 - x) & 1)) x++;
          d += `M${start} ${y}h${x - start}v1h${start - x}z`;
        } else x++;
      }
    });
    return d;
  };

  const pads = {};
  const saveHash = () => {
    const q = Object.entries(pads).map(([k, p]) => `${keyOf[k]}=${toHex(p.rows)}`).join('&');
    try { history.replaceState(null, '', `#${q}`); } catch (e) { /* a file: page; the drawing still works */ }
  };

  root.querySelectorAll('[data-pad]').forEach((el) => {
    const kind = el.dataset.pad;
    const cells = [...el.querySelectorAll('.px__c')];
    const hex = el.querySelector('[data-hex]');
    const txt = el.querySelector('[data-txt]');
    const msg = el.querySelector('[data-msg]');
    const glyph = document.getElementById(`ed-${kind}`);
    const pad = (pads[kind] = { rows: Array(8).fill(0) });
    const cell = (x, y) => cells[y * 8 + x];
    const get = (x, y) => pad.rows[y] >> (7 - x) & 1;

    const say = (text, bad) => {
      msg.textContent = text;
      msg.toggleAttribute('data-bad', !!bad);
    };
    const render = (from) => {
      cells.forEach((c) => c.setAttribute('aria-pressed', get(+c.dataset.x, +c.dataset.y) ? 'true' : 'false'));
      if (from !== hex) { hex.value = toHex(pad.rows); hex.removeAttribute('aria-invalid'); }
      if (from !== txt) { txt.value = toTxt(pad.rows); txt.removeAttribute('aria-invalid'); }
      const empty = pad.rows.every((b) => !b);
      if (glyph) glyph.setAttribute('d', toPath(empty ? fromHex(fallback[kind]) : pad.rows));
      if (!from) say(empty ? "It's empty, so the menu will draw its own icon." : '');
      saveHash();
    };
    const set = (x, y, on) => {
      pad.rows[y] = on ? pad.rows[y] | (0x80 >> x) : pad.rows[y] & ~(0x80 >> x);
    };
    pad.load = (rows, from) => { pad.rows = rows.slice(); render(from); };

    // the pointer: the first pixel decides whether this stroke draws or erases
    let stroke = null;
    const grid = el.querySelector('.px');
    grid.addEventListener('pointerdown', (e) => {
      const c = e.target.closest('.px__c');
      if (!c || e.button) return;
      e.preventDefault();
      stroke = !get(+c.dataset.x, +c.dataset.y);
      set(+c.dataset.x, +c.dataset.y, stroke);
      focusCell(c);
      render();
    });
    grid.addEventListener('pointermove', (e) => {
      if (stroke === null) return;
      const c = document.elementFromPoint(e.clientX, e.clientY);
      if (!c || !c.classList.contains('px__c') || !grid.contains(c)) return;
      if (get(+c.dataset.x, +c.dataset.y) !== +stroke) { set(+c.dataset.x, +c.dataset.y, stroke); render(); }
    });
    ['pointerup', 'pointercancel'].forEach((t) => window.addEventListener(t, () => { stroke = null; }));

    // the keys: one tab stop, arrows inside
    const focusCell = (c) => {
      cells.forEach((o) => { o.tabIndex = o === c ? 0 : -1; });
      c.focus({ preventScroll: true });
    };
    grid.addEventListener('keydown', (e) => {
      const c = e.target.closest('.px__c');
      if (!c) return;
      let x = +c.dataset.x, y = +c.dataset.y;
      const was = get(x, y);
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        set(x, y, !was);
        render();
        return;
      }
      if (e.key === 'ArrowLeft') x = Math.max(0, x - 1);
      else if (e.key === 'ArrowRight') x = Math.min(7, x + 1);
      else if (e.key === 'ArrowUp') y = Math.max(0, y - 1);
      else if (e.key === 'ArrowDown') y = Math.min(7, y + 1);
      else if (e.key === 'Home') x = 0;
      else if (e.key === 'End') x = 7;
      else return;
      e.preventDefault();
      if (e.shiftKey) { set(x, y, was); render(); }
      focusCell(cell(x, y));
    });

    el.querySelector('.pad__tools').addEventListener('click', (e) => {
      const b = e.target.closest('[data-do]');
      if (!b) return;
      const r = pad.rows;
      const next = {
        clear: () => Array(8).fill(0),
        invert: () => r.map((v) => ~v & 0xff),
        left: () => r.map((v) => ((v << 1) | (v >> 7)) & 0xff),
        right: () => r.map((v) => ((v >> 1) | (v << 7)) & 0xff),
        up: () => [...r.slice(1), r[0]],
        down: () => [r[7], ...r.slice(0, 7)],
      }[b.dataset.do]();
      pad.load(next);
    });

    hex.addEventListener('input', () => {
      const rows = fromHex(hex.value);
      hex.toggleAttribute('aria-invalid', !rows);
      if (rows) { hex.removeAttribute('aria-invalid'); pad.load(rows, hex); say(''); } else {
        hex.setAttribute('aria-invalid', 'true');
        say('The hex should be 16 digits from 0-9 and a-f, two for each row.', true);
      }
    });
    txt.addEventListener('input', () => {
      const rows = fromTxt(txt.value);
      if (Array.isArray(rows)) { pad.load(rows, txt); say(''); } else {
        txt.setAttribute('aria-invalid', 'true');
        say(rows, true);
      }
    });
    [hex, txt].forEach((f) => f.addEventListener('blur', () => { if (!f.hasAttribute('aria-invalid')) render(); }));

    el.querySelector('[data-save]').addEventListener('click', (e) => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([toTxt(pad.rows) + '\n'], { type: 'text/plain' }));
      a.download = e.currentTarget.dataset.save;
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      say(`Saved ${a.download}.`);
    });
    el.querySelector('[data-open]').addEventListener('change', async (e) => {
      const f = e.target.files[0];
      e.target.value = '';
      if (!f) return;
      if (f.size > 4096) { say(`${f.name} is too big to be an icon.`, true); return; }
      const rows = fromTxt(await f.text());
      if (Array.isArray(rows)) { pad.load(rows); say(`Opened ${f.name}.`); } else say(`${f.name}: ${rows}`, true);
    });
    el.querySelector('[data-copy]').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(toHex(pad.rows));
        say('Copied.');
      } catch (err) {
        hex.focus();
        hex.select();
        say("Copying didn't work. Select the hex and copy it yourself.");
      }
    });
  });

  // a drawing kept in the page's address: #p=<16 hex>&f=<16 hex>
  const fromHash = () => {
    const q = new URLSearchParams(location.hash.slice(1));
    Object.entries(pads).forEach(([k, p]) => p.load(fromHex(q.get(keyOf[k]) || '') || p.rows));
  };
  fromHash();
  window.addEventListener('hashchange', fromHash);
})();
