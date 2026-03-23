/**
 * Informe interactivo — datos en data/rutas.json
 */
(function () {
  const ORDER = [
    "dmc",
    "comedor",
    "desayuno_merienda",
    "patios",
    "analisis_cupos",
    "analisis_zona",
    "analisis_rentabilidad",
  ];

  const ETIQUETA_TAB = {
    dmc: "DMC",
    comedor: "Comedor",
    desayuno_merienda: "Desayuno / merienda",
    patios: "Patios",
    analisis_cupos: "Analis de cupo por unidad de negocio",
    analisis_zona: "Analisis de cupo por zona",
    analisis_rentabilidad: "Analisis de rentabilidad",
  };

  let data = null;
  let map = null;
  let layerGroup = null;
  let depotMarker = null;
  let analisis = null;
  let analisisZona = null;
  let analisisRentabilidad = null;

  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function hideLoader() {
    const loader = document.getElementById("appLoader");
    if (loader) {
      loader.classList.add("app-loader--done");
      loader.setAttribute("aria-hidden", "true");
      loader.setAttribute("aria-busy", "false");
      setTimeout(() => {
        loader.hidden = true;
      }, 320);
    }
  }

  function iconDepot() {
    return L.divIcon({
      className: "num-marker",
      html: '<div class="depot-marker-inner" title="Depósito">⌂</div>',
      iconSize: [34, 34],
      iconAnchor: [17, 34],
      popupAnchor: [0, -30],
    });
  }

  function iconStop(n, hue) {
    const border = `hsla(${hue}, 65%, 70%, 0.5)`;
    const bg = `hsla(${hue}, 40%, 20%, 0.45)`;
    return L.divIcon({
      className: "num-marker",
      html: `<div class="num-marker-inner" style="border-color:${border};background:${bg}">${n}</div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 32],
      popupAnchor: [0, -28],
    });
  }

  function hueForTrip(viajeN) {
    return 190 + ((viajeN || 1) * 37) % 80;
  }

  function invalidateMapSoon() {
    if (!map) return;
    requestAnimationFrame(() => {
      map.invalidateSize(true);
    });
    setTimeout(() => map && map.invalidateSize(true), 200);
  }

  function initMap(dep) {
    if (map) {
      map.remove();
      map = null;
    }
    map = L.map("mapa", {
      zoomControl: true,
      scrollWheelZoom: true,
    }).setView([dep.lat, dep.lon], 12);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> · CARTO',
      subdomains: "abcd",
      maxZoom: 19,
    }).addTo(map);

    layerGroup = L.layerGroup().addTo(map);
    depotMarker = L.marker([dep.lat, dep.lon], { icon: iconDepot() })
      .bindPopup(`<strong>Depósito</strong><br/>${escapeHtml(dep.nombre || "Burzaco")}`)
      .addTo(layerGroup);

    invalidateMapSoon();
  }

  function showTripOnMap(stops, dep, viajeN) {
    if (!map || !layerGroup) return;
    layerGroup.clearLayers();

    depotMarker = L.marker([dep.lat, dep.lon], { icon: iconDepot() })
      .bindPopup(`<strong>Depósito</strong><br/>${escapeHtml(dep.nombre || "")}`)
      .addTo(layerGroup);

    const hue = hueForTrip(viajeN);
    const bounds = [];

    (stops || []).forEach((s) => {
      const m = L.marker([s.lat, s.lon], {
        icon: iconStop(s.orden, hue),
      }).bindPopup(
        `<strong>#${s.orden}</strong> ${escapeHtml(s.escuela)}<br/>${escapeHtml(s.direccion)}<br/><span style="opacity:.8">${escapeHtml(s.barrio)}</span><br/><em>${s.cupos} cupos</em>`
      );
      m.addTo(layerGroup);
      bounds.push([s.lat, s.lon]);
    });

    if (stops && stops.length > 0) {
      const latlngs = [[dep.lat, dep.lon], ...stops.map((s) => [s.lat, s.lon])];
      const pl = L.polyline(latlngs, {
        color: `hsl(${hue}, 52%, 52%)`,
        weight: 3,
        opacity: 0.72,
        dashArray: "10 8",
        lineJoin: "round",
        lineCap: "round",
      }).addTo(layerGroup);
      pl.bringToBack();
    }

    bounds.push([dep.lat, dep.lon]);
    if (bounds.length) {
      map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
    }
    updateMapLegend(hue, dep);
    invalidateMapSoon();
  }

  function updateMapLegend(hue, dep) {
    const leg = document.getElementById("mapLegend");
    if (!leg) return;
    leg.style.setProperty("--legend-hue", String(hue));
    const depName = escapeHtml(dep?.nombre || "Depósito");
    leg.innerHTML = `
      <div class="legend-title">Leyenda</div>
      <div class="legend-row"><span class="legend-swatch legend-swatch--depot" aria-hidden="true"></span> Depósito (${depName})</div>
      <div class="legend-row"><span class="legend-swatch legend-swatch--ruta" aria-hidden="true"></span> Orden de visita</div>
      <div class="legend-row"><span class="legend-swatch legend-swatch--parada" aria-hidden="true"></span> Parada numerada</div>
      <p class="legend-hint">Expandí un viaje para ver su trazo en el mapa.</p>
    `;
  }

  function toTitleCase(s) {
    return String(s || "")
      .toLowerCase()
      .replace(/\b\p{L}/gu, (m) => m.toUpperCase());
  }

  function extraerBarrio(rawBarrio) {
    const raw = String(rawBarrio || "").replace(/\s+/g, " ").trim();
    const low = raw.toLowerCase();
    if (!raw) return "Sin barrio";

    const mapeos = [
      ["villa fiorito", "Villa Fiorito"],
      ["villa centenario", "Villa Centenario"],
      ["san jose", "San Jose"],
      ["san josé", "San Jose"],
      ["banfield", "Banfield"],
      ["temperley", "Temperley"],
      ["turdera", "Turdera"],
      ["lavallol", "Lavallol"],
      ["ingeniero budge", "Ingeniero Budge"],
      ["budge", "Ingeniero Budge"],
      ["lomitas", "Lomas Centro"],
      ["lomas de zamora", "Lomas Centro"],
    ];
    for (const [pat, etiqueta] of mapeos) {
      if (low.includes(pat)) return etiqueta;
    }

    const prefer = raw.includes("·") ? raw.split("·").slice(1).join(" ").trim() : raw;
    const trozos = prefer.split(",").map((p) => p.trim()).filter(Boolean);
    const noBarrio = /^(?:\d+|av\.?|avenida|calle|doctor|dr\.?|general|almirante|pasaje)\b/i;
    const candidato = trozos.find((t) => !noBarrio.test(t)) || trozos[1] || trozos[0] || raw;
    return toTitleCase(candidato);
  }

  function haversineKm(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  function keyEstablecimiento(stop) {
    return `${stop.escuela || ""}||${stop.direccion || ""}`.toLowerCase();
  }

  function kmTotalSegmento(seg) {
    let km = 0;
    (seg?.zonas || []).forEach((z) => {
      (z.viajes || []).forEach((v) => {
        if (Number.isFinite(Number(v.km))) km += Number(v.km);
      });
    });
    return km;
  }

  function calcularAnalisis(dataObj) {
    const unidades = [];
    const keys = ["dmc", "comedor", "desayuno_merienda", "patios"];
    keys.forEach((key) => {
      const seg = dataObj.segmentos[key];
      if (!seg) return;

      let cupos = 0;
      let viajes = 0;
      let km = 0;
      const estabSet = new Set();
      const porZona = new Map();
      const porBarrio = new Map();

      (seg.zonas || []).forEach((z) => {
        let cuposZona = 0;
        let viajesZona = 0;
        const estabZona = new Set();
        (z.viajes || []).forEach((v) => {
          viajes += 1;
          viajesZona += 1;
          cupos += Number(v.cupos_cargados || 0);
          cuposZona += Number(v.cupos_cargados || 0);
          km += Number.isFinite(Number(v.km)) ? Number(v.km) : 0;
          (v.stops || []).forEach((s) => {
            const k = keyEstablecimiento(s);
            estabSet.add(k);
            estabZona.add(k);
            const barrio = extraerBarrio(s.barrio);
            if (!porBarrio.has(barrio)) {
              porBarrio.set(barrio, { establecimientos: new Set(), cupos: 0 });
            }
            porBarrio.get(barrio).establecimientos.add(k);
            porBarrio.get(barrio).cupos += Number(s.cupos || 0);
          });
        });
        porZona.set(z.id, {
          zona: z.id,
          cupos: cuposZona,
          viajes: viajesZona,
          establecimientos: estabZona.size,
        });
      });

      const barrios = Array.from(porBarrio.entries())
        .map(([barrio, vals]) => ({
          barrio,
          establecimientos: vals.establecimientos.size,
          cupos: vals.cupos,
        }))
        .sort((a, b) => b.cupos - a.cupos || b.establecimientos - a.establecimientos || a.barrio.localeCompare(b.barrio, "es"));

      const zonas = Array.from(porZona.values()).sort((a, b) => a.zona - b.zona);

      unidades.push({
        key,
        nombre: ETIQUETA_TAB[key] || key,
        cupos_total: cupos,
        km_total: Number(km.toFixed(2)),
        flotas: viajes,
        viajes_total: viajes,
        establecimientos_total: estabSet.size,
        zonas,
        barrios,
      });
    });

    const global = unidades.reduce(
      (acc, u) => {
        acc.cupos_total += u.cupos_total;
        acc.km_total += u.km_total;
        acc.flotas += u.flotas;
        acc.establecimientos += u.establecimientos_total;
        return acc;
      },
      { cupos_total: 0, km_total: 0, flotas: 0, establecimientos: 0 }
    );

    return {
      unidades,
      global: {
        ...global,
        km_total: Number(global.km_total.toFixed(2)),
      },
    };
  }

  function calcularAnalisisPorZona(dataObj) {
    const zonasMap = new Map();
    const keys = ["dmc", "comedor", "desayuno_merienda", "patios"];

    keys.forEach((key) => {
      const seg = dataObj.segmentos[key];
      if (!seg) return;
      (seg.zonas || []).forEach((z) => {
        if (!zonasMap.has(z.id)) {
          zonasMap.set(z.id, {
            zona: z.id,
            cupos: 0,
            establecimientos: new Set(),
            barrios: new Map(),
            flotas: 0,
            km: 0,
          });
        }
        const acc = zonasMap.get(z.id);
        (z.viajes || []).forEach((v) => {
          acc.flotas += 1;
          acc.cupos += Number(v.cupos_cargados || 0);
          acc.km += Number.isFinite(Number(v.km)) ? Number(v.km) : 0;
          (v.stops || []).forEach((s) => {
            const estKey = keyEstablecimiento(s);
            acc.establecimientos.add(estKey);
            const barrio = extraerBarrio(s.barrio);
            if (!acc.barrios.has(barrio)) {
              acc.barrios.set(barrio, new Set());
            }
            acc.barrios.get(barrio).add(estKey);
          });
        });
      });
    });

    const zonas = Array.from(zonasMap.values())
      .map((z) => ({
        zona: z.zona,
        cupos: z.cupos,
        flotas: z.flotas,
        km: Number(z.km.toFixed(2)),
        establecimientos_total: z.establecimientos.size,
        barrios: Array.from(z.barrios.entries())
          .map(([barrio, setEst]) => ({
            barrio,
            establecimientos: setEst.size,
          }))
          .sort((a, b) => b.establecimientos - a.establecimientos || a.barrio.localeCompare(b.barrio, "es")),
      }))
      .sort((a, b) => a.zona - b.zona);

    const tot = zonas.reduce(
      (acc, z) => {
        acc.cupos += z.cupos;
        acc.flotas += z.flotas;
        acc.km += z.km;
        acc.establecimientos += z.establecimientos_total;
        return acc;
      },
      { cupos: 0, flotas: 0, km: 0, establecimientos: 0 }
    );

    return {
      zonas,
      global: {
        cupos: tot.cupos,
        flotas: tot.flotas,
        km: Number(tot.km.toFixed(2)),
        establecimientos: tot.establecimientos,
      },
    };
  }

  function calcularAnalisisRentabilidad(dataObj) {
    const dep = dataObj?.meta?.deposito || { lat: -34.8353338, lon: -58.4233261 };
    const zonasMap = new Map();
    const keys = ["dmc", "comedor", "desayuno_merienda", "patios"];

    keys.forEach((key) => {
      const seg = dataObj.segmentos[key];
      if (!seg) return;
      (seg.zonas || []).forEach((z) => {
        if (!zonasMap.has(z.id)) {
          zonasMap.set(z.id, {
            zona: z.id,
            cupos: 0,
            km: 0,
            viajes: 0,
            stops: [],
          });
        }
        const acc = zonasMap.get(z.id);
        (z.viajes || []).forEach((v) => {
          acc.viajes += 1;
          acc.cupos += Number(v.cupos_cargados || 0);
          acc.km += Number.isFinite(Number(v.km)) ? Number(v.km) : 0;
          (v.stops || []).forEach((s) => {
            if (Number.isFinite(Number(s.lat)) && Number.isFinite(Number(s.lon))) {
              acc.stops.push({ lat: Number(s.lat), lon: Number(s.lon) });
            }
          });
        });
      });
    });

    const zonas = Array.from(zonasMap.values()).map((z) => {
      const distProm = z.stops.length
        ? z.stops.reduce((sum, s) => sum + haversineKm(dep.lat, dep.lon, s.lat, s.lon), 0) / z.stops.length
        : null;
      const cuposKm = z.km > 0 ? z.cupos / z.km : z.cupos;
      return {
        zona: z.zona,
        cupos: z.cupos,
        km: Number(z.km.toFixed(2)),
        viajes: z.viajes,
        distancia_prom_ombu_km: distProm == null ? null : Number(distProm.toFixed(2)),
        indice_redituable: Number(cuposKm.toFixed(2)),
        indice_costo: Number(((z.km || 0) + (distProm || 0) * 2).toFixed(2)),
      };
    });

    const rankingRedituables = [...zonas].sort(
      (a, b) =>
        b.indice_redituable - a.indice_redituable ||
        b.cupos - a.cupos ||
        a.km - b.km ||
        a.zona - b.zona
    );

    const rankingMenosCostosas = [...zonas].sort(
      (a, b) =>
        a.indice_costo - b.indice_costo ||
        a.km - b.km ||
        (a.distancia_prom_ombu_km || 0) - (b.distancia_prom_ombu_km || 0) ||
        a.zona - b.zona
    );

    return { rankingRedituables, rankingMenosCostosas };
  }

  function hideMapForAnalysis() {
    const panelMap = document.querySelector(".panel-map");
    if (panelMap) panelMap.classList.add("panel-map--analysis");
    const layout = document.querySelector(".layout");
    if (layout) layout.classList.add("layout--analysis");
  }

  function showMapForTrips() {
    const panelMap = document.querySelector(".panel-map");
    if (panelMap) panelMap.classList.remove("panel-map--analysis");
    const layout = document.querySelector(".layout");
    if (layout) layout.classList.remove("layout--analysis");
  }

  function renderAnalisisCupos() {
    const lista = document.getElementById("listaZonas");
    const dep = data.meta.deposito;
    lista.innerHTML = "";
    hideMapForAnalysis();
    initMap(dep);
    updateMapLegend(200, dep);

    const a = analisis || calcularAnalisis(data);
    analisis = a;

    const box = document.getElementById("segmentStats");
    if (box) {
      box.hidden = false;
      box.innerHTML = `
        <span class="stat-chip"><strong>${a.global.cupos_total.toLocaleString("es-AR")}</strong> cupos totales</span>
        <span class="stat-chip"><strong>${a.global.establecimientos.toLocaleString("es-AR")}</strong> estab. (suma por unidad)</span>
        <span class="stat-chip"><strong>${a.global.km_total.toLocaleString("es-AR")}</strong> km totales</span>
        <span class="stat-chip"><strong>${a.global.flotas.toLocaleString("es-AR")}</strong> flotas (viajes)</span>
      `;
    }

    const head = el(
      "div",
      "analysis-head glass-inner",
      `<h2 class="analysis-title">Indicadores por unidad de negocio</h2>
       <p class="analysis-subtitle">Flotas se toma como la cantidad de viajes planificados por unidad.</p>`
    );
    lista.appendChild(head);

    a.unidades.forEach((u) => {
      const card = el("article", "analysis-card glass-inner");
      card.innerHTML = `
        <h3 class="analysis-unit-title">${escapeHtml(u.nombre)}</h3>
        <div class="analysis-kpis">
          <div class="kpi"><span class="kpi-label">Cupos totales</span><strong>${u.cupos_total.toLocaleString("es-AR")}</strong></div>
          <div class="kpi"><span class="kpi-label">Establecimientos</span><strong>${u.establecimientos_total.toLocaleString("es-AR")}</strong></div>
          <div class="kpi"><span class="kpi-label">Kilómetros</span><strong>${u.km_total.toLocaleString("es-AR")} km</strong></div>
          <div class="kpi"><span class="kpi-label">Flotas</span><strong>${u.flotas.toLocaleString("es-AR")}</strong></div>
        </div>
      `;

      const zonas = el("div", "analysis-table-wrap");
      zonas.innerHTML = `
        <h4 class="analysis-table-title">Cupos por zona</h4>
        <table class="analysis-table">
          <thead><tr><th>Zona</th><th>Cupos</th><th>Establec.</th><th>Flotas</th></tr></thead>
          <tbody>
            ${u.zonas
              .map(
                (z) =>
                  `<tr><td>${z.zona}</td><td>${z.cupos.toLocaleString("es-AR")}</td><td>${z.establecimientos.toLocaleString("es-AR")}</td><td>${z.viajes.toLocaleString("es-AR")}</td></tr>`
              )
              .join("")}
          </tbody>
        </table>
      `;
      card.appendChild(zonas);

      const barrios = el("div", "analysis-table-wrap");
      barrios.innerHTML = `
        <h4 class="analysis-table-title">Establecimientos por barrio</h4>
        <table class="analysis-table">
          <thead><tr><th>Barrio</th><th>Establec.</th><th>Cupos</th></tr></thead>
          <tbody>
            ${u.barrios
              .map(
                (b) =>
                  `<tr><td>${escapeHtml(b.barrio)}</td><td>${b.establecimientos.toLocaleString("es-AR")}</td><td>${b.cupos.toLocaleString("es-AR")}</td></tr>`
              )
              .join("")}
          </tbody>
        </table>
      `;
      card.appendChild(barrios);
      lista.appendChild(card);
    });
  }

  function renderAnalisisZona() {
    const lista = document.getElementById("listaZonas");
    const dep = data.meta.deposito;
    lista.innerHTML = "";
    hideMapForAnalysis();
    initMap(dep);
    updateMapLegend(200, dep);

    const a = analisisZona || calcularAnalisisPorZona(data);
    analisisZona = a;

    const box = document.getElementById("segmentStats");
    if (box) {
      box.hidden = false;
      box.innerHTML = `
        <span class="stat-chip"><strong>${a.global.cupos.toLocaleString("es-AR")}</strong> cupos totales</span>
        <span class="stat-chip"><strong>${a.global.establecimientos.toLocaleString("es-AR")}</strong> estab. (suma por zona)</span>
        <span class="stat-chip"><strong>${a.global.km.toLocaleString("es-AR")}</strong> km totales</span>
        <span class="stat-chip"><strong>${a.global.flotas.toLocaleString("es-AR")}</strong> flotas (viajes)</span>
      `;
    }

    const head = el(
      "div",
      "analysis-head glass-inner",
      `<h2 class="analysis-title">Indicadores por zona</h2>
       <p class="analysis-subtitle">En cada zona se muestran cupos, establecimientos, kilómetros, flotas y el detalle de establecimientos por barrio.</p>`
    );
    lista.appendChild(head);

    a.zonas.forEach((z) => {
      const card = el("article", "analysis-card glass-inner");
      card.innerHTML = `
        <h3 class="analysis-unit-title">Zona ${z.zona}</h3>
        <div class="analysis-kpis">
          <div class="kpi"><span class="kpi-label">Cupos totales</span><strong>${z.cupos.toLocaleString("es-AR")}</strong></div>
          <div class="kpi"><span class="kpi-label">Establecimientos</span><strong>${z.establecimientos_total.toLocaleString("es-AR")}</strong></div>
          <div class="kpi"><span class="kpi-label">Kilómetros</span><strong>${z.km.toLocaleString("es-AR")} km</strong></div>
          <div class="kpi"><span class="kpi-label">Flotas</span><strong>${z.flotas.toLocaleString("es-AR")}</strong></div>
        </div>
      `;

      const barrios = el("div", "analysis-table-wrap");
      barrios.innerHTML = `
        <h4 class="analysis-table-title">Establecimientos por barrio (Zona ${z.zona})</h4>
        <table class="analysis-table">
          <thead><tr><th>Barrio</th><th>Establecimientos</th></tr></thead>
          <tbody>
            ${z.barrios
              .map(
                (b) =>
                  `<tr><td>${escapeHtml(b.barrio)}</td><td>${b.establecimientos.toLocaleString("es-AR")}</td></tr>`
              )
              .join("")}
          </tbody>
        </table>
      `;
      card.appendChild(barrios);
      lista.appendChild(card);
    });
  }

  function renderRentabilidadTabla(mode, rows) {
    const isRedituable = mode === "redituable";
    const title = isRedituable ? "Ranking de redituables" : "Las menos costosas";
    const subtitle = isRedituable
      ? "Ordenado de mayor a menor por cupos por km (prioriza mas cupos con menos kilometros)."
      : "Ordenado de menor a mayor costo logistico (km recorridos + cercania promedio a Ombu 1269).";
    const nota = isRedituable
      ? "Por que una zona sube: mueve muchos cupos con poco recorrido. Si dos zonas empatan, gana la de mas cupos y luego la de menos km."
      : "Por que una zona sube: requiere menos km y ademas queda mas cerca de Ombu 1269. Menor indice costo = mas conveniente logisticamente.";

    return `
      <div class="analysis-head glass-inner">
        <h2 class="analysis-title">${title}</h2>
        <p class="analysis-subtitle">${subtitle}</p>
        <p class="analysis-subtitle">${nota}</p>
      </div>
      <div class="analysis-card glass-inner">
        <table class="analysis-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Zona</th>
              <th>Cupos</th>
              <th>Km</th>
              <th>Dist. prom. Ombu</th>
              <th>${isRedituable ? "Indice redituable" : "Indice costo"}</th>
              <th>Por que esta en esta posicion</th>
            </tr>
          </thead>
          <tbody>
            ${rows
              .map((z, idx) => {
                const dist = z.distancia_prom_ombu_km == null ? "—" : `${z.distancia_prom_ombu_km.toLocaleString("es-AR")} km`;
                const ind = isRedituable ? z.indice_redituable : z.indice_costo;
                const razon = isRedituable
                  ? `Tiene ${z.cupos.toLocaleString("es-AR")} cupos para ${z.km.toLocaleString("es-AR")} km (${z.indice_redituable.toLocaleString("es-AR")} cupos/km).`
                  : `Registra ${z.km.toLocaleString("es-AR")} km y distancia promedio de ${dist} a Ombu 1269, lo que baja su costo logistico.`;
                return `<tr>
                  <td>${idx + 1}</td>
                  <td>Zona ${z.zona}</td>
                  <td>${z.cupos.toLocaleString("es-AR")}</td>
                  <td>${z.km.toLocaleString("es-AR")} km</td>
                  <td>${dist}</td>
                  <td>${ind.toLocaleString("es-AR")}</td>
                  <td>${escapeHtml(razon)}</td>
                </tr>`;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderAnalisisRentabilidad() {
    const lista = document.getElementById("listaZonas");
    const dep = data.meta.deposito;
    lista.innerHTML = "";
    hideMapForAnalysis();
    initMap(dep);
    updateMapLegend(200, dep);

    const a = analisisRentabilidad || calcularAnalisisRentabilidad(data);
    analisisRentabilidad = a;

    const box = document.getElementById("segmentStats");
    if (box) {
      box.hidden = false;
      box.innerHTML = `
        <span class="stat-chip"><strong>${a.rankingRedituables.length.toLocaleString("es-AR")}</strong> zonas analizadas</span>
        <span class="stat-chip"><strong>Redituable</strong> = cupos/km alto</span>
        <span class="stat-chip"><strong>Menos costosa</strong> = km bajo + cercania a Ombu 1269</span>
      `;
    }

    const tabs = el("div", "analysis-subtabs glass-inner");
    tabs.innerHTML = `
      <button class="analysis-subtab active" type="button" data-subtab="redituable">Ranking de redituables</button>
      <button class="analysis-subtab" type="button" data-subtab="costosa">Las menos costosas</button>
    `;
    lista.appendChild(tabs);

    const content = el("div", "analysis-subcontent");
    content.innerHTML = renderRentabilidadTabla("redituable", a.rankingRedituables);
    lista.appendChild(content);

    tabs.querySelectorAll(".analysis-subtab").forEach((btn) => {
      btn.addEventListener("click", () => {
        tabs.querySelectorAll(".analysis-subtab").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const mode = btn.dataset.subtab === "costosa" ? "costosa" : "redituable";
        const rows = mode === "costosa" ? a.rankingMenosCostosas : a.rankingRedituables;
        content.innerHTML = renderRentabilidadTabla(mode, rows);
      });
    });
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  /** min_total_viaje viene en minutos (decimal); muestra "X h Y min" o solo minutos. */
  function formatDuracionMinutos(minTotal) {
    if (minTotal == null || !Number.isFinite(Number(minTotal))) return "—";
    const totalMin = Math.round(Number(minTotal));
    const h = Math.floor(totalMin / 60);
    const m = totalMin % 60;
    if (h === 0) return `${m} min`;
    if (m === 0) return `${h} h`;
    return `${h} h ${m} min`;
  }

  function agregarStatsSegmento(seg) {
    let nViajes = 0;
    let nParadas = 0;
    let cupos = 0;
    const nZonas = (seg.zonas || []).length;

    (seg.zonas || []).forEach((z) => {
      (z.viajes || []).forEach((v) => {
        nViajes += 1;
        nParadas += v.n_paradas != null ? v.n_paradas : (v.stops || []).length;
        cupos += v.cupos_cargados != null ? v.cupos_cargados : 0;
      });
    });

    const box = document.getElementById("segmentStats");
    if (!box) return;
    if (nZonas === 0) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    box.innerHTML = `
      <span class="stat-chip"><strong>${nZonas}</strong> zonas</span>
      <span class="stat-chip"><strong>${nViajes}</strong> viajes</span>
      <span class="stat-chip"><strong>${nParadas}</strong> paradas</span>
      <span class="stat-chip"><strong>${cupos.toLocaleString("es-AR")}</strong> cupos tot.</span>
    `;
  }

  function segmentoVacio(seg) {
    if (!seg.zonas || seg.zonas.length === 0) return true;
    return !seg.zonas.some((z) => (z.viajes || []).length > 0);
  }

  function renderSegment(segKey) {
    if (segKey === "analisis_cupos") {
      const titulo = data.meta?.titulo || "Informe de rutas";
      document.getElementById("tituloPrincipal").textContent = titulo;
      document.title = `Analis de cupo por unidad de negocio · ${titulo}`;
      document.getElementById("subtituloMeta").textContent =
        "Análisis de cupos — Indicadores por unidad, zona y barrio";
      renderAnalisisCupos();
      return;
    }
    if (segKey === "analisis_zona") {
      const titulo = data.meta?.titulo || "Informe de rutas";
      document.getElementById("tituloPrincipal").textContent = titulo;
      document.title = `Analisis de cupo por zona · ${titulo}`;
      document.getElementById("subtituloMeta").textContent =
        "Analisis de cupo por zona — Cupos, establecimientos y barrios por zona";
      renderAnalisisZona();
      return;
    }
    if (segKey === "analisis_rentabilidad") {
      const titulo = data.meta?.titulo || "Informe de rutas";
      document.getElementById("tituloPrincipal").textContent = titulo;
      document.title = `Analisis de rentabilidad · ${titulo}`;
      document.getElementById("subtituloMeta").textContent =
        "Analisis de rentabilidad — Ranking de redituables y menos costosas por zona";
      renderAnalisisRentabilidad();
      return;
    }

    showMapForTrips();
    const seg = data.segmentos[segKey];
    if (!seg) return;

    const titulo = data.meta?.titulo || "Informe de rutas";
    document.getElementById("tituloPrincipal").textContent = titulo;
    document.title = `${ETIQUETA_TAB[segKey] || segKey} · ${titulo}`;

    document.getElementById("subtituloMeta").textContent = "";

    agregarStatsSegmento(seg);

    const lista = document.getElementById("listaZonas");
    lista.innerHTML = "";

    const dep = data.meta.deposito;
    initMap(dep);

    if (segmentoVacio(seg)) {
      lista.appendChild(
        el(
          "div",
          "empty-state glass-inner",
          `<p class="empty-state-title">Sin datos en este segmento</p>
           <p class="empty-state-text">No hay viajes generados para <strong>${escapeHtml(
             seg.titulo
           )}</strong>. Verificá el CSV correspondiente y volvé a ejecutar <code>python build_data.py</code>.</p>`
        )
      );
      updateMapLegend(200, dep);
      invalidateMapSoon();
      return;
    }

    (seg.zonas || []).forEach((zona) => {
      const block = el("div", "zona-block");
      block.appendChild(el("h2", "zona-titulo", escapeHtml(zona.titulo)));

      (zona.viajes || []).forEach((v) => {
        const det = el("details", "viaje-details");
        det.open = false;

        const mins = formatDuracionMinutos(v.min_total);
        const km = v.km != null ? `${v.km} km` : "—";
        const sum = el("summary", "viaje-summary", "");
        sum.innerHTML = `<span class="viaje-summary-main"><strong>Viaje ${v.viaje_n}</strong></span>
           <span class="viaje-meta"><strong>${v.n_paradas}</strong> paradas · <strong>${v.cupos_cargados}</strong> cupos · ${mins} · ${km}</span>
           <a class="viaje-map-link" href="#mapa">Mapa ↓</a>`;

        const mapLink = sum.querySelector(".viaje-map-link");
        if (mapLink) {
          mapLink.addEventListener("click", (ev) => {
            ev.preventDefault();
            document.getElementById("mapa")?.scrollIntoView({ behavior: "smooth", block: "center" });
            det.open = true;
            if (v.stops?.length) showTripOnMap(v.stops, dep, v.viaje_n);
          });
        }

        det.appendChild(sum);

        const ul = el("ul", "paradas-lista");
        (v.stops || []).forEach((s) => {
          const li = el("li", "parada-item");
          li.appendChild(el("div", "parada-num", String(s.orden)));
          const body = el("div");
          body.appendChild(el("p", "parada-escuela", escapeHtml(s.escuela)));
          body.appendChild(el("p", "parada-dir", escapeHtml(s.direccion)));
          body.appendChild(el("p", "parada-barrio", escapeHtml(s.barrio)));
          body.appendChild(el("p", "parada-cupos", `${s.cupos} cupos (este concepto)`));
          li.appendChild(body);
          ul.appendChild(li);
        });
        det.appendChild(ul);

        det.addEventListener("toggle", () => {
          if (det.open && v.stops?.length) {
            showTripOnMap(v.stops, dep, v.viaje_n);
          }
        });

        block.appendChild(det);
      });

      lista.appendChild(block);
    });

    const first = seg.zonas?.[0]?.viajes?.[0];
    if (first?.stops?.length) {
      showTripOnMap(first.stops, dep, first.viaje_n);
    } else {
      updateMapLegend(200, dep);
    }
    invalidateMapSoon();
  }

  function buildNav() {
    const nav = document.getElementById("segmentNav");
    nav.innerHTML = "";
    const pestañasVirtuales = new Set(["analisis_cupos", "analisis_zona", "analisis_rentabilidad"]);
    ORDER.forEach((key) => {
      if (!pestañasVirtuales.has(key) && !data.segmentos[key]) return;
      const b = el(
        "button",
        "segment-btn",
        escapeHtml(ETIQUETA_TAB[key] || key)
      );
      b.type = "button";
      b.dataset.seg = key;
      b.addEventListener("click", () => {
        nav.querySelectorAll(".segment-btn").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        renderSegment(key);
      });
      nav.appendChild(b);
    });
    const firstBtn = nav.querySelector(".segment-btn");
    if (firstBtn) {
      firstBtn.classList.add("active");
      renderSegment(firstBtn.dataset.seg);
    }
  }

  async function load() {
    const res = await fetch("data/rutas.json", { cache: "no-store" });
    if (!res.ok) throw new Error("No se encontró data/rutas.json");
    data = await res.json();

    const gen = data.meta?.generado_utc
      ? new Date(data.meta.generado_utc).toLocaleString("es-AR", { timeZone: "America/Argentina/Buenos_Aires" })
      : "";
    const desc = data.meta?.descripcion ? ` · ${data.meta.descripcion}` : "";
    document.getElementById("pieMeta").textContent = gen
      ? `Datos generados: ${gen} · Capacidad camión: ${data.meta?.capacidad_camion || 5000} cupos por segmento${desc}`
      : "";

    buildNav();
    hideLoader();
  }

  window.addEventListener("resize", () => {
    if (map) invalidateMapSoon();
  });

  load().catch((err) => {
    hideLoader();
    document.getElementById("listaZonas").innerHTML =
      `<div class="error-panel glass-inner"><p class="error-title">No se pudieron cargar los datos</p>
       <p>${escapeHtml(err.message)}</p>
       <p class="error-hint">Ejecutá <code>python build_data.py</code> en la carpeta <code>informe</code> y serví el sitio desde <code>public</code>.</p></div>`;
    document.getElementById("subtituloMeta").textContent = "Error al cargar rutas.json";
    console.error(err);
  });
})();
