mapboxgl.accessToken = 'YOUR MAPBOX TOKEN HERE';
const map = new mapboxgl.Map({
  container: 'map', // container ID
  // Choose from Mapbox's core styles, or make your own style with Mapbox Studio
  style: 'mapbox://styles/mapbox/streets-v12', // style URL
  center: [-122.2684, 37.8734], // starting position [lng, lat]
  zoom: 14 // starting zoom
});

var places = {
	'type': 'FeatureCollection',
	'features': []
}
const mapboxClient = mapboxSdk({ accessToken: mapboxgl.accessToken });
map.onClickCallbacks = [];
map.proposalMarkers = [];

// Sets the source of the map markers if the map
// is loaded, or add it as a property for loading later.
map.setData = function (geojson) {
  if (map.getSource("places")) {
    map.getSource("places").setData(geojson);
  } else {
    map.dataToLoad = geojson;
  }
}

map.drawRoute = function(route, id) {
  // Update map with route.
  const geojson = {
    type: 'Feature',
    properties: {},
    geometry: {
      type: 'LineString',
      coordinates: route
    }
  };
  let route_id = `route-${id}`;
  if (map.getSource(route_id)) {
    map.getSource(route_id).setData(geojson);
  } else {
    map.addLayer({
      id: route_id,
      type: 'line',
      source: {
        type: 'geojson',
        data: geojson
      },
      layout: {
        'line-join': 'round',
        'line-cap': 'round'
      },
      paint: {
        'line-color': '#3887be',
        'line-width': 5,
        'line-opacity': 0.75
      }
    });
  }
}

/* -------------------------------------------------------------------------- */
/*                              API                                           */
/* -------------------------------------------------------------------------- */

async function getCyclingRoute(start, end) {
  console.log("ROUTING");
  console.log(start, end);
  const query = await fetch(
    `https://api.mapbox.com/directions/v5/mapbox/cycling/${start[0]},${start[1]};${end[0]},${end[1]}?steps=true&geometries=geojson&access_token=${mapboxgl.accessToken}`,
    { method: 'GET' }
  );
  console.log(query);
  const json = await query.json();
  console.log(json);
  const data = json.routes[0];
  route = data.geometry.coordinates;
  console.log(route);
  let duration = Math.ceil(data.duration / 60).toString() + " min";
  return {"route": route, "duration": duration};
}

/* -------------------------------------------------------------------------- */
/*                              Event handlers                                */
/* -------------------------------------------------------------------------- */

map.registerOnClickCallback = function (callback) {
  map.onClickCallbacks.push(callback);
}

map.on('load', () => {
  map.resize();
// Add a GeoJSON source containing place coordinates and information.
	map.style.stylesheet.layers.forEach(function(layer) {
		if (layer.type === 'symbol') {
			map.removeLayer(layer.id);
		}
	});

	map.addSource('places', {
		'type': 'geojson',
		'data': map.dataToLoad || places,
	});
  console.log(map.dataToLoad);

	map.addLayer({
		'id': 'places',
		'type': 'symbol',
		'source': 'places',
		'layout': {
			'text-field': ['get', 'description'],
			'text-variable-anchor': ['top', 'bottom', 'left', 'right'],
			'text-radial-offset': 0.5,
			'text-justify': 'auto',
			'icon-image': ['get', 'icon'],
      'text-allow-overlap': true,
      'icon-allow-overlap': true,
		}
	});
});


map.on('click', 'places', (e) => {
  map.onClickCallbacks.forEach(cb => cb(e));
});

// Change the cursor to a pointer when the mouse is over the places layer.
map.on('mouseenter', 'places', () => {
  map.getCanvas().style.cursor = 'pointer';
});

// Change it back to a pointer when it leaves.
map.on('mouseleave', 'places', () => {
  map.getCanvas().style.cursor = '';
});

map.showProposal = function(proposal) {
  // Clear markers for the current proposal
  map.proposalMarkers.forEach(mk => mk.remove());
  map.proposalMarkers = [];
  // Create new markers
  proposal.forEach((evt, i) => {
    if (!evt || evt.type !== "event") return;
    const el = document.createElement("div");
    el.className = "map-proposal-marker";
    let evtIdx = Math.floor(i / 2) + 1;
    el.innerHTML = evtIdx;
    let mk = new mapboxgl.Marker(el, {anchor: "center"})
                .setLngLat(evt.loc)
                .addTo(map);
    map.proposalMarkers.push(mk);
  });
}

/* -------------------------------------------------------------------------- */
/*                              Utils                                         */
/* -------------------------------------------------------------------------- */

// Wrap coordinates in a feature object
function wrapCoords(latLong, properties) {
    let test = {
      "type": "Feature",
      "properties": properties,
      "geometry": {
        "coordinates": latLong,
        "type": "Point"
      },
    }
  console.log("test");
  console.log(test);
  return test;
}


export { map, getCyclingRoute, wrapCoords };
