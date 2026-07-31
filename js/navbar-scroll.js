// Show the compact avatar + subtitle in the navbar once the page header scrolls out of view
(function () {
  const navbar = document.getElementById('mainNavbar');
  const header = document.getElementById('pageHeader');
  if (!navbar || !header) return;

  const observer = new IntersectionObserver(function (entries) {
    navbar.classList.toggle('scrolled', !entries[0].isIntersecting);
  }, { rootMargin: '-72px 0px 0px 0px' });

  observer.observe(header);
})();
