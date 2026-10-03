// Career data: elements with [data-years-company] show the whole years since joining IBM (now Kyndryl).
(function () {
  var COMPANY_START = new Date(2011, 8, 1); // September 2011

  var now = new Date();
  var years = now.getFullYear() - COMPANY_START.getFullYear();
  if (now.getMonth() < COMPANY_START.getMonth()) years--;

  document.querySelectorAll('[data-years-company]').forEach(function (el) {
    el.textContent = years;
  });
})();
