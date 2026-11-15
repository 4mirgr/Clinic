document.querySelector('[data-print]')?.addEventListener('click', async () => {
  await document.fonts.ready;
  await Promise.all([...document.images].map(image => image.decode().catch(() => {})));
  window.print();
});
document.querySelector('.menu-toggle')?.addEventListener('click', event => {
  const button = event.currentTarget;
  const expanded = button.getAttribute('aria-expanded') !== 'true';
  button.setAttribute('aria-expanded', String(expanded));
  document.querySelector('.sidebar').classList.toggle('is-open', expanded);
});
