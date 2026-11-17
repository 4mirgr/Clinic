document.querySelector('.menu-toggle')?.addEventListener('click', event => {
  const expanded = event.currentTarget.getAttribute('aria-expanded') !== 'true';
  event.currentTarget.setAttribute('aria-expanded', String(expanded));
  document.querySelector('.sidebar')?.classList.toggle('is-open', expanded);
});
document.querySelectorAll('[data-preview-form]').forEach(form => {
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (form.classList.contains('theme-form')) {
      const dark = document.documentElement.dataset.theme !== 'dark';
      document.documentElement.dataset.theme = dark ? 'dark' : 'light';
      document.querySelectorAll('.theme-icon').forEach(icon => icon.textContent = dark ? '☀' : '☾');
      document.querySelectorAll('.theme-label').forEach(label => label.textContent = dark ? 'حالت روز' : 'حالت شب');
    }
  });
});
document.querySelectorAll('[name=q]').forEach(input => {
  input.addEventListener('input', () => {
    const query = input.value.trim().replace(/ي/g, 'ی').replace(/ك/g, 'ک');
    document.querySelectorAll('.advice-card,.patient-row').forEach(row => row.hidden = !row.textContent.includes(query));
  });
});
document.querySelector('[data-print]')?.addEventListener('click', async () => {
  await document.fonts.ready;
  window.print();
});
