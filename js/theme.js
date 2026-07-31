// Theme toggle: dark by default, an explicit light choice is persisted.
(function () {
  var root = document.documentElement;

  document.querySelectorAll('.theme-toggle').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var light = root.getAttribute('data-bs-theme') !== 'light';
      root.setAttribute('data-bs-theme', light ? 'light' : 'dark');
      try { localStorage.setItem('theme', light ? 'light' : 'dark'); } catch (e) {}
    });
  });
})();
