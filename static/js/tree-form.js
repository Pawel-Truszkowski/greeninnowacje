/* Tree registration (UI doc §8.5): device GPS with a draggable pin for corrections.
 *
 * The hidden lat/lng/accuracy inputs are the only channel to the server, and the server
 * revalidates them — the map is a convenience, not a source of trust.
 */
(function () {
  'use strict';

  var mapEl = document.getElementById('pick-map');
  var statusEl = document.getElementById('gps-status');
  var latInput = document.getElementById('id_lat');
  var lngInput = document.getElementById('id_lng');
  var accuracyInput = document.getElementById('id_gps_accuracy_m');

  var DEFAULT_CENTER = [52.871, 19.651];
  var map = L.map(mapEl).setView(DEFAULT_CENTER, 17);
  L.tileLayer(mapEl.dataset.tilesUrl, {
    maxZoom: 19,
    attribution: mapEl.dataset.attribution,
  }).addTo(map);

  // Our own pin instead of Leaflet's default one: the default loads three PNGs whose
  // path it *guesses* from the stylesheet, which breaks once filenames carry a hash
  // (production static storage). A divIcon also matches the pins on the public map.
  var PIN_SVG =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="#fff">' +
    '<path d="M12 2C8 8 5 11.5 5 15a7 7 0 0 0 14 0c0-3.5-3-7-7-13z"/></svg>';
  var pinIcon = L.divIcon({
    html: '<div class="tree-pin pin-new">' + PIN_SVG + '</div>',
    className: '',
    iconSize: [34, 34],
    iconAnchor: [17, 30],
  });

  var marker = L.marker(DEFAULT_CENTER, { draggable: true, icon: pinIcon }).addTo(map);

  function round6(value) {
    return Math.round(value * 1e6) / 1e6;
  }

  function setPosition(lat, lng, accuracy) {
    marker.setLatLng([lat, lng]);
    latInput.value = round6(lat);
    lngInput.value = round6(lng);
    if (accuracy !== undefined) accuracyInput.value = Math.round(accuracy * 10) / 10;
  }

  // Keep a previously entered position (e.g. after a validation error or duplicate check).
  if (latInput.value && lngInput.value) {
    var saved = [parseFloat(latInput.value), parseFloat(lngInput.value)];
    map.setView(saved, 18);
    marker.setLatLng(saved);
    statusEl.textContent = 'Lokalizacja z poprzedniej próby — sprawdź pinezkę.';
  } else if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      function (position) {
        var coords = position.coords;
        setPosition(coords.latitude, coords.longitude, coords.accuracy);
        map.setView([coords.latitude, coords.longitude], 19);
        statusEl.textContent = 'Dokładność GPS: ±' + Math.round(coords.accuracy) + ' m.';
      },
      function () {
        statusEl.textContent = 'Brak zgody na lokalizację — wskaż miejsce, przesuwając pinezkę.';
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  } else {
    statusEl.textContent = 'Twoja przeglądarka nie udostępnia lokalizacji — przesuń pinezkę.';
  }

  marker.on('dragend', function () {
    var position = marker.getLatLng();
    // A hand-placed pin has no GPS accuracy to report.
    accuracyInput.value = '';
    setPosition(position.lat, position.lng);
    statusEl.textContent = 'Pinezka ustawiona ręcznie.';
  });

  map.on('click', function (event) {
    accuracyInput.value = '';
    setPosition(event.latlng.lat, event.latlng.lng);
    statusEl.textContent = 'Pinezka ustawiona ręcznie.';
  });

  /* The free-text species field only makes sense for the "Inny" choice. */
  var speciesSelect = document.getElementById('id_species');
  var otherBox = document.getElementById('species-other');
  var OTHER = '__other__';

  function toggleOther() {
    otherBox.classList.toggle('hidden', speciesSelect.value !== OTHER);
  }

  speciesSelect.addEventListener('change', toggleOther);
  // Also on load: after a validation error the browser restores the choice, but fires
  // no change event — the field would stay hidden with "Inny" selected.
  toggleOther();
})();
