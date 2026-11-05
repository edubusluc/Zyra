// Hora en 24 h en los campos [data-time-24h]: escribe 2030 y queda 20:30.
(function () {
  'use strict';
  document.querySelectorAll('[data-time-24h]').forEach(function (input) {
    input.addEventListener('input', function () {
      var digits = input.value.replace(/\D/g, '').slice(0, 4);
      input.value = digits.length > 2 ? digits.slice(0, 2) + ':' + digits.slice(2) : digits;
    });
  });
})();
