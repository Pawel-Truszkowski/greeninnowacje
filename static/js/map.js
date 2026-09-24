/* Public tree map (UI doc §8.1): Leaflet + clustering, fed by GET /api/trees.
 *
 * Tree data comes from volunteers, so every value from the API goes into the DOM through
 * textContent — never innerHTML — which is what keeps a species name like "<script>…"
 * harmless (spec §7).
 */
(function () {
  'use strict';

  var mapEl = document.getElementById('map');
  var config = JSON.parse(document.getElementById('map-config').textContent);
  var errorEl = document.getElementById('map-error');
  var countEl = document.getElementById('count-all');
  var localitySelect = document.getElementById('locality-filter');
  var filters = { status: '', locality: '' };

  var map = L.map(mapEl, { zoomControl: false }).setView([52.871, 19.651], 13);
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  L.tileLayer(config.tilesUrl, {
    maxZoom: 19,
    attribution: config.attribution,
  }).addTo(map);

  var cluster = L.markerClusterGroup({
    maxClusterRadius: 45,
    iconCreateFunction: function (c) {
      var el = document.createElement('div');
      el.className = 'tree-cluster';
      el.textContent = c.getChildCount();
      return L.divIcon({ html: el, className: '', iconSize: [40, 40] });
    },
  });
  map.addLayer(cluster);

  var DROP_SVG =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="#fff">' +
    '<path d="M12 2C8 8 5 11.5 5 15a7 7 0 0 0 14 0c0-3.5-3-7-7-13z"/></svg>';

  function pinIcon(status, isMine) {
    return L.divIcon({
      html:
        '<div class="tree-pin pin-' + status + (isMine ? ' mine' : '') + '">' + DROP_SVG + '</div>',
      className: '',
      iconSize: [34, 34],
      iconAnchor: [17, 30],
    });
  }

  function lastWateringText(tree) {
    if (!tree.last_watered_on) return 'Jeszcze nie podlewano';
    var days = Math.round((Date.now() - Date.parse(tree.last_watered_on)) / 86400000);
    if (days <= 0) return 'Ostatnie podlanie: dziś';
    if (days === 1) return 'Ostatnie podlanie: wczoraj';
    return 'Ostatnie podlanie: ' + days + ' dni temu';
  }

  function popupContent(tree) {
    var wrap = document.createElement('div');

    var title = document.createElement('strong');
    title.className = 'popup-title';
    title.textContent = tree.species;

    var badge = document.createElement('span');
    badge.className = 'status-badge status-' + tree.status;
    badge.textContent = (config.statuses[tree.status] || {}).label || tree.status;

    var care;
    if (tree.is_mine) {
      care = ' · 💚 Twoje drzewo';
    } else if (tree.has_caretaker) {
      care = ' · ma opiekuna 💚';
    } else {
      care = ' · szuka opiekuna!';
    }

    var meta = document.createElement('p');
    meta.className = 'muted popup-meta';
    meta.textContent = lastWateringText(tree) + care;

    var link = document.createElement('a');
    link.className = 'btn btn-primary popup-link';
    link.href = '/drzewo/' + tree.id;
    link.textContent = 'Zobacz kartę drzewa';

    wrap.append(title, badge, meta, link);
    return wrap;
  }

  function query() {
    var params = new URLSearchParams();
    if (filters.status) params.set('status', filters.status);
    if (filters.locality) params.set('locality', filters.locality);
    var qs = params.toString();
    return '/api/trees/' + (qs ? '?' + qs : '');
  }

  function refresh() {
    fetch(query(), { headers: { Accept: 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (trees) {
        errorEl.hidden = true;
        cluster.clearLayers();
        trees.forEach(function (tree) {
          var marker = L.marker([tree.lat, tree.lng], {
            icon: pinIcon(tree.status, tree.is_mine),
          });
          marker.bindPopup(popupContent(tree), { minWidth: 220 });
          cluster.addLayer(marker);
        });
        countEl.textContent = '(' + trees.length + ')';
        if (trees.length) map.fitBounds(cluster.getBounds().pad(0.25));
      })
      .catch(function () {
        errorEl.hidden = false;
      });
  }

  document.getElementById('status-filters').addEventListener('click', function (event) {
    var chip = event.target.closest('.chip');
    if (!chip) return;
    document.querySelectorAll('#status-filters .chip').forEach(function (other) {
      other.classList.toggle('active', other === chip);
    });
    filters.status = chip.dataset.status;
    refresh();
  });

  localitySelect.addEventListener('change', function () {
    filters.locality = localitySelect.value;
    refresh();
  });

  refresh();
})();
