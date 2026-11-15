// Runs before CSS to avoid flashing the opposite theme. No clinical data is stored in the browser.
(() => {
  const root = document.documentElement;
  const theme = root.dataset.theme;
  if (theme !== 'light' && theme !== 'dark') {
    root.dataset.theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
})();
