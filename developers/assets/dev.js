// The portal's one bit of script. On a phone the list of pages beside each
// doc folds up under its button; on a wide screen it's always open. Without
// script it stays open everywhere.
(() => {
  const wide = window.matchMedia('(min-width: 60.0625rem)');
  const set = () => document.querySelectorAll('[data-fold]').forEach((d) => { d.open = wide.matches; });
  set();
  wide.addEventListener('change', set);
})();
