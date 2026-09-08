(function () {
  function medSymbol(adress, symbol) {
    var bas = adress.split('?')[0];
    return symbol ? bas + '?symbol=' + encodeURIComponent(symbol) : bas;
  }

  document.addEventListener('click', function (e) {
    var knapp = e.target.closest('[data-qr-open]');
    if (!knapp) return;

    var ruta = document.getElementById(knapp.dataset.qrOpen);
    if (!ruta) return;

    var bild = ruta.querySelector('img[data-src]');
    if (bild && !bild.getAttribute('src')) bild.src = bild.dataset.src;
    ruta.style.display = ruta.dataset.qrDisplay || 'flex';

    var behallare = ruta.parentElement;
    while (behallare) {
      if (behallare.scrollWidth > behallare.clientWidth) behallare.scrollLeft = 0;
      behallare = behallare.parentElement;
    }
    knapp.style.display = 'none';
  });

  document.addEventListener('change', function (e) {
    var val = e.target.closest('[data-qr-val]');
    if (!val || e.target.type !== 'radio') return;

    var ruta = val.closest('.qr-ruta');
    var symbol = e.target.value;
    var bild = ruta.querySelector('img[data-src]');

    bild.src = medSymbol(bild.dataset.src, symbol);
    ruta.querySelectorAll('[data-qr-lank]').forEach(function (lank) {
      lank.href = medSymbol(lank.getAttribute('href'), symbol);
    });
  });
})();
