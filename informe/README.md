# Informe interactivo (rutas y paradas)

Vista **minimalista estilo liquid glass** para dirección: zonas, viajes, paradas numeradas, colegio, dirección y barrio. Incluye mapa (Leaflet + OSM).

## Segmentos

1. **DMC** — `viajes_burzaco_detalle.csv`  
2. **Cupos día — Comedor**  
3. **Cupos día — Desayuno y merienda**  
4. **Patios / coros / sábado**  
5. **Analis de cupo por unidad de negocio** (sin mapa)  
6. **Analisis de cupo por zona** (sin mapa)  
7. **Analisis de rentabilidad** con subpestañas:
   - Ranking de redituables
   - Las menos costosas

(2–4 desde `analisis_cupos_comedor_dm_patio_detalle.csv`.)

## Generar datos

Desde la carpeta **`informe`** (un nivel arriba están el CSV de colegios y los CSV de viajes):

```bash
python build_data.py
```

Esto escribe `public/data/rutas.json`.

## Ver en local

```bash
cd public
python -m http.server 8080
```

Abrí: http://localhost:8080

## GitHub

1. Subí el repo (al menos la carpeta `informe/public` y `informe/build_data.py` si querés regenerar datos en CI).  
2. **GitHub Pages (recomendado, Actions)**  
   - Settings → **Pages** → **Build and deployment** → Source: **GitHub Actions**.  
   - El workflow `.github/workflows/informe-pages.yml` sube el contenido de `informe/public` en cada push a `main` o `master` (o manualmente con *Run workflow*).  
3. **GitHub Pages (carpeta fija)**  
   - Alternativa: Source → *Deploy from a branch* y elegir la carpeta `informe/public` si tu interfaz lo permite, o copiar `public` a `docs`.  
4. Con URL `https://usuario.github.io/repo/`, los paths relativos (`data/rutas.json`, `css/`, `js/`) funcionan si la raíz del sitio es exactamente el contenido de `public`.

## Replit

1. Importá el repo desde GitHub.  
2. En la raíz del Repl, configurá el comando de ejecución para servir la carpeta `public`:

```bash
cd informe/public && python -m http.server 8080 --bind 0.0.0.0
```

3. Abrí el puerto que muestre Replit (8080 o el que asigne).

Si el Repl tiene como raíz solo `informe`, usá:

```bash
cd public && python -m http.server 8080 --bind 0.0.0.0
```

## Archivos

| Ruta | Rol |
|------|-----|
| `public/index.html` | Página (meta, accesibilidad, carga) |
| `public/css/styles.css` | Estilos glass, leyenda, impresión |
| `public/js/app.js` | Pestañas, lista, mapa, polilínea, resumen |
| `public/favicon.svg` | Icono del sitio |
| `public/manifest.json` | Nombre/tema para “añadir a inicio” |
| `public/data/rutas.json` | Datos (generado) |
| `build_data.py` | Construye `rutas.json` |
| `requirements.txt` | Dependencias para regenerar datos (`pandas`) |
| `replit.nix` | Entorno Python en Replit (opcional) |
| `../.github/workflows/informe-pages.yml` | Despliegue automático a Pages |
