# -*- coding: utf-8 -*-
"""
Análisis logístico: colegios por zona (Lomas de Zamora y alrededores).
Requiere: pandas, geopy, requests, openpyxl
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from geopy.geocoders import Nominatim, Photon
from haversine import Unit, haversine

BASE_DIR = Path(r"C:\Users\Usuario\Desktop\ANALISIS EMPRESARIAL")
EXCEL = BASE_DIR / "Cupos x colegio_actualizado.xlsx"
CACHE_GEO = BASE_DIR / "geocache_colegios.json"
DEPOT_QUERY = "Ombú 1269, Lomas de Zamora, Partido de Lomas de Zamora, Buenos Aires, Argentina"
OSRM = "https://router.project-osrm.org/route/v1/driving/{coords}"
CUPOS_CAMION = 5000
VENTANA_ENTRE_PARADAS_MIN = 10
VENTANA_ENTRE_VIAJES_ZONA_MIN = 10

USER_AGENT = "realdecatorce_logistica_escolar/1.0 (contacto interno)"
MAX_KM_DESDE_DEPOSITO = 42.0

SUFIJO_LOMAS = ", Partido de Lomas de Zamora, Buenos Aires, Argentina"
SUFIJO_AR = ", Argentina"


def cargar_cache() -> dict:
    if CACHE_GEO.exists():
        return json.loads(CACHE_GEO.read_text(encoding="utf-8"))
    return {}


def guardar_cache(c: dict) -> None:
    CACHE_GEO.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_direccion(d: str) -> tuple[str, str, str, str]:
    """Separa calle, altura; localidad heurística; provincia fija."""
    s = (d or "").strip()
    if not s:
        return "", "", "", "Buenos Aires"
    sl = s.lower()
    if "temperley" in sl:
        localidad = "Temperley"
    elif "lomas" in sl or "banfield" in sl or "lanús" in sl or "lanus" in sl:
        localidad = "Lomas de Zamora / alrededores"
    else:
        localidad = "Lomas de Zamora (referencia)"
    m = re.search(r"^(.*?)[\s,]+(\d{1,5})\s*$", s)
    if m:
        calle = m.group(1).strip().rstrip(",")
        altura = m.group(2)
    else:
        m2 = re.search(r"(\d{3,5})", s)
        if m2:
            altura = m2.group(1)
            calle = s.replace(altura, "").strip().rstrip(",")
        else:
            calle, altura = s, ""
    provincia = "Buenos Aires"
    return calle, altura, localidad, provincia


def _km_desde_depot(
    lat: float, lon: float, dep_lat: float | None, dep_lon: float | None
) -> float:
    if dep_lat is None or dep_lon is None:
        return 0.0
    return float(haversine((dep_lat, dep_lon), (lat, lon), unit=Unit.KILOMETERS))


def cache_valido_para_depot(
    cache: dict, clave: str, dep_lat: float, dep_lon: float
) -> bool:
    c = cache.get(clave)
    if not c or c.get("lat") is None or c.get("lon") is None:
        return False
    return (
        _km_desde_depot(float(c["lat"]), float(c["lon"]), dep_lat, dep_lon)
        <= MAX_KM_DESDE_DEPOSITO
    )


def normalizar_unicode(s: str) -> str:
    return unicodedata.normalize("NFKC", (s or "").strip())


def limpiar_ruido_direccion(s: str) -> str:
    s = normalizar_unicode(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*-\s*1\s*[º°]?\s*piso.*$", "", s, flags=re.I)
    s = re.sub(r"\s*\(ex[^)]+\)", "", s, flags=re.I)
    return s.strip()


def aplicar_reemplazos_calle(s: str) -> str:
    """Nombres frecuentemente mal escritos en planillas / homónimos."""
    t = s
    rep_regex = [
        (r"(?i)\bA\.\s*Cap\.\s*Giaccino\b", "Capitán Santiago Giacchino"),
        (r"(?i)\bBruno\s+Tavano\b", "Intendente Juan B. Tavano"),
        (r"(?i)(Av\.?\s*)?Alte\s+Brown", "Avenida Almirante Brown"),
        (r"(?i)\bAvenida\s+Alte\s+Brown\b", "Avenida Almirante Brown"),
        (r"(?i)\bAntartida\b", "Antártida"),
        (r"(?i)\bEjercto\b", "Ejército"),
        (r"(?i)Piocollivadino", "Pirovano"),
        (r"(?i)Espronceneda", "Espronceda"),
        (r"(?i)Labarden", "Lavardén"),
        (r"(?i)\bVilla\s+Barcelo\b", "Villa Barcelona"),
        (r"(?i)\bAnchoris\b", "Anchorena"),
        (r"(?i)\bCid\s+guido\s+de\s+franc\b", "Cid Campeador"),
        (r"(?i)\bMorazan\b", "Morazán"),
        (r"(?i)\bvernet\b", "Vernet"),
        (r"(?i)\bLlaroque\b", "Larroque"),
        (r"(?i)Hi[^\w\s]*lito\s+Yrigoyen", "Hipólito Yrigoyen"),
    ]
    for pat, repl in rep_regex:
        t = re.sub(pat, repl, t)
    for a, b in (
        ("Llaroque", "Larroque"),
        ("Espronceneda", "Espronceda"),
        ("Pio Baroja2098", "Pío Baroja 2098"),
        ("B.P. GaldosS", "Benito Pérez Galdós"),
    ):
        if a in t:
            t = t.replace(a, b)
    return t.strip()


def variantes_interseccion_y_esquina(d: str) -> list[str]:
    """Genera variantes para 'Calle A y Calle B', E/, esq., entre."""
    out: list[str] = []
    low = d.lower()
    m = re.search(
        r"(?i)^(.+?)\s+y\s+(.+?)\s+(\d{1,5})\s*$",
        d,
    )
    if m:
        a, b, num = m.group(1).strip(), m.group(2).strip(), m.group(3)
        if "hornero" in b.lower() or "hornero" in a.lower():
            out.append(
                f"El Hornero {num}, San José, Temperley, Partido de Lomas de Zamora, Buenos Aires, Argentina"
            )
            out.append(
                f"El Hornero {num}, San José, Partido de Lomas de Zamora, Buenos Aires, Argentina"
            )
        out.append(
            f"{a} {num}, Temperley, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )
        out.append(
            f"{b} {num}, Temperley, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )
        out.append(
            f"esquina {a} y {b}, Temperley, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )
    m2 = re.search(r"(?i)(.+?)\s+e/\s*(.+)$", d)
    if m2:
        a, b = m2.group(1).strip(), m2.group(2).strip()
        out.append(
            f"entre {a} y {b}, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )
    if "esq." in low or "esquina" in low:
        out.append(d.replace("esq.", "esquina") + SUFIJO_LOMAS)
    if "entre" in low and "islandia" in low:
        out.append(
            "Morazán entre Islandia y Australia, Banfield, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )
    m_sin_num = re.match(r"(?i)^(.+?)\s+y\s+(.+)$", d.rstrip())
    if m_sin_num and not re.search(r"\d{1,5}\s*$", d):
        a, b = m_sin_num.group(1).strip(), m_sin_num.group(2).strip()
        if len(a) > 2 and len(b) > 2 and " y " not in a:
            out.append(
                f"esquina {a} y {b}, Partido de Lomas de Zamora, Buenos Aires, Argentina"
            )
    return out


def variantes_rango_altura(d: str) -> list[str]:
    out: list[str] = []
    m = re.search(r"(\d+)\s*/\s*(\d+)", d)
    if m:
        a, b = m.groups()
        mid = str((int(a) + int(b)) // 2)
        base = re.sub(r"\s*\d+\s*/\s*\d+", "", d).strip()
        out.append(f"{base} {a}, Partido de Lomas de Zamora, Buenos Aires, Argentina")
        out.append(f"{base} {b}, Partido de Lomas de Zamora, Buenos Aires, Argentina")
        out.append(f"{base} {mid}, Partido de Lomas de Zamora, Buenos Aires, Argentina")
    return out


# Consultas probadas a mano para direcciones de esquina / sin número en OSM
CONSULTAS_MANUALES: dict[str, list[str]] = {
    "Ostende y Labarden S/Nro": [
        "Ostende y Lavarden, Villa Centenario, Partido de Lomas de Zamora, Buenos Aires, Argentina",
        "Ostende & Lavarden, Villa Centenario, Partido de Lomas de Zamora, Argentina",
    ],
    "Morazan s/n entre Islandia y Australia": [
        "Morazán e Islandia, Banfield, Partido de Lomas de Zamora, Buenos Aires, Argentina",
        "Islandia y Francisco de Morazán, Banfield, Partido de Lomas de Zamora, Argentina",
    ],
}


def generar_consultas_geocodificacion(direccion_raw: str) -> list[str]:
    d0 = limpiar_ruido_direccion(direccion_raw)
    d = aplicar_reemplazos_calle(normalizar_direccion_tipica(d0))
    out: list[str] = []

    if d0 in CONSULTAS_MANUALES:
        out.extend(CONSULTAS_MANUALES[d0])

    # Prioridad: variantes específicas (intersecciones, rangos)
    out.extend(variantes_interseccion_y_esquina(d))
    out.extend(variantes_rango_altura(d))

    low = d.lower()
    if "almirante brown" in low or "alte brown" in low:
        out.append(
            re.sub(
                r"(?i)(Avenida\s+Almirante\s+Brown)\s+(\d+)",
                r"\1 \2, Banfield, Partido de Lomas de Zamora, Buenos Aires, Argentina",
                d,
            )
        )
        mnum = re.search(r"(\d{3,5})", d)
        if mnum:
            n = mnum.group(1)
            out.append(
                f"{n}, Avenida Almirante Brown, Banfield, Partido de Lomas de Zamora, Buenos Aires, Argentina"
            )

    if "santos vega" in low and "pareta" in low:
        out.append(
            "Santos Vega y Pareto, Llavallol, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )
        out.append(
            "Avenida Santos Vega, Llavallol, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )

    if "olivan" in low and "107" in d:
        out.append(
            "Jesús R. Oliván 107, Llavallol, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )

    if "muzzili" in low:
        out.append(
            f"{d}, Banfield, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )

    if "cipolletti" in low and "2202" in d:
        out.append(
            "Cipolletti 2202, Banfield, Partido de Lomas de Zamora, Buenos Aires, Argentina"
        )

    # Formulaciones estándar (siempre al final como respaldo)
    sufijos = [
        SUFIJO_LOMAS,
        ", Banfield, Partido de Lomas de Zamora, Buenos Aires, Argentina",
        ", Temperley, Partido de Lomas de Zamora, Buenos Aires, Argentina",
        ", Llavallol, Partido de Lomas de Zamora, Buenos Aires, Argentina",
        ", Gran Buenos Aires, Buenos Aires, Argentina",
        SUFIJO_AR,
    ]
    for suf in sufijos:
        out.append(d + suf)

    seen: set[str] = set()
    uniq: list[str] = []
    for q in out:
        q = q.strip()
        if len(q) < 4 or q in seen:
            continue
        seen.add(q)
        uniq.append(q)
    return uniq[:28]


def normalizar_direccion_tipica(d: str) -> str:
    """Correcciones ortográficas frecuentes en el padrón."""
    s = (d or "").strip()
    if not s:
        return s
    rep = (
        ("Llaroque", "Larroque"),
        ("llaroque", "Larroque"),
        ("Giaccino", "Giacchino"),
        ("Espronceneda", "Espronceda"),
        ("Hiñlito", "Hipólito"),
        ("Hi\u00f1lito", "Hipólito"),
        ("Pio Baroja2098", "Pío Baroja 2098"),
        ("B.P. GaldosS", "Benito Pérez Galdós"),
    )
    for a, b in rep:
        if a in s:
            s = s.replace(a, b)
    return s


def _aceptar_ubicacion(
    lat: float, lon: float, dep_lat: float | None, dep_lon: float | None
) -> bool:
    if dep_lat is None or dep_lon is None:
        return True
    return (
        _km_desde_depot(lat, lon, dep_lat, dep_lon) <= MAX_KM_DESDE_DEPOSITO
    )


def geocodificar_direccion(
    geolocator: Nominatim,
    photon: Photon,
    cache: dict,
    clave: str,
    query_extra: str,
    dep_lat: float | None = None,
    dep_lon: float | None = None,
) -> tuple[float | None, float | None, str]:
    if clave == "__depot__":
        if clave in cache and cache[clave].get("lat") is not None:
            c = cache[clave]
            return c["lat"], c["lon"], c.get("display", "")
        for q in (
            "Ombú 1269" + SUFIJO_LOMAS,
            DEPOT_QUERY,
            "Ombú 1269, Lomas de Zamora, Buenos Aires, Argentina",
        ):
            try:
                loc = geolocator.geocode(
                    q, timeout=20, language="es", country_codes="ar"
                )
                time.sleep(1.05)
                if loc:
                    cache[clave] = {
                        "lat": loc.latitude,
                        "lon": loc.longitude,
                        "display": loc.address,
                        "query": q,
                        "motor": "nominatim",
                    }
                    guardar_cache(cache)
                    return loc.latitude, loc.longitude, loc.address
            except (GeocoderTimedOut, GeocoderUnavailable):
                time.sleep(2)
        return None, None, ""

    if clave in cache and cache[clave].get("lat") is not None:
        c = cache[clave]
        lat, lon = c["lat"], c["lon"]
        if (
            dep_lat is not None
            and dep_lon is not None
            and _km_desde_depot(lat, lon, dep_lat, dep_lon) > MAX_KM_DESDE_DEPOSITO
        ):
            del cache[clave]
            guardar_cache(cache)
        else:
            return lat, lon, c.get("display", "")

    consultas = generar_consultas_geocodificacion(query_extra)
    ultimo_error = ""
    for q in consultas:
        try:
            loc = photon.geocode(q, timeout=18)
            time.sleep(1.0)
            if loc and _aceptar_ubicacion(
                loc.latitude, loc.longitude, dep_lat, dep_lon
            ):
                cache[clave] = {
                    "lat": loc.latitude,
                    "lon": loc.longitude,
                    "display": loc.address,
                    "query": q,
                    "motor": "photon",
                }
                guardar_cache(cache)
                return loc.latitude, loc.longitude, loc.address
        except Exception as e:
            ultimo_error = str(e)
            time.sleep(1.0)

        try:
            loc = geolocator.geocode(
                q,
                timeout=18,
                language="es",
                country_codes="ar",
            )
            time.sleep(1.05)
            if loc and _aceptar_ubicacion(
                loc.latitude, loc.longitude, dep_lat, dep_lon
            ):
                cache[clave] = {
                    "lat": loc.latitude,
                    "lon": loc.longitude,
                    "display": loc.address,
                    "query": q,
                    "motor": "nominatim",
                }
                guardar_cache(cache)
                return loc.latitude, loc.longitude, loc.address
        except (GeocoderTimedOut, GeocoderUnavailable) as e:
            ultimo_error = str(e)
            time.sleep(2)
        except Exception as e:
            ultimo_error = str(e)
            time.sleep(1)

    cache[clave] = {"lat": None, "lon": None, "display": "", "error": ultimo_error}
    guardar_cache(cache)
    return None, None, ""


def orden_vecino_mas_cercano(
    depot: tuple[float, float],
    puntos: list[tuple[int, tuple[float, float]]],
) -> list[int]:
    """puntos: (idx_fila, (lat, lon)). Retorna índices de fila en orden de visita."""
    from math import atan2, cos, radians, sin, sqrt

    def dist_km(a: tuple[float, float], b: tuple[float, float]) -> float:
        r = 6371.0
        la1, lo1, la2, lo2 = map(radians, [a[0], a[1], b[0], b[1]])
        dlat, dlon = la2 - la1, lo2 - lo1
        x = sin(dlat / 2) ** 2 + cos(la1) * cos(la2) * sin(dlon / 2) ** 2
        return 2 * r * atan2(sqrt(x), sqrt(1 - x))

    resto = list(puntos)
    orden_idx: list[int] = []
    actual = depot
    while resto:
        j = min(range(len(resto)), key=lambda k: dist_km(actual, resto[k][1]))
        idx, coord = resto.pop(j)
        orden_idx.append(idx)
        actual = coord
    return orden_idx


def ruta_osrm(coords_lonlat: list[tuple[float, float]]) -> tuple[float | None, float | None]:
    """coords: [(lon,lat), ...]. Devuelve (duración_segundos, distancia_metros)."""
    if len(coords_lonlat) < 2:
        return None, None
    s = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords_lonlat)
    url = OSRM.format(coords=s)
    try:
        r = requests.get(url, params={"overview": "false"}, timeout=60)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "Ok" or not j.get("routes"):
            return None, None
        route = j["routes"][0]
        return route["duration"], route["distance"]
    except Exception:
        return None, None


def main() -> None:
    df = pd.read_excel(EXCEL, sheet_name="ANEXO 1", header=0)
    df = df.rename(
        columns={
            df.columns[2]: "Direccion",
            df.columns[0]: "cod_a",
            df.columns[1]: "cod_b",
        }
    )

    cache = cargar_cache()
    geo = Nominatim(user_agent=USER_AGENT, timeout=20)
    photon = Photon(user_agent=USER_AGENT, timeout=20)

    print("Geocodificando depósito (Real de Catorce / Ombú 1269)...")
    dlat, dlon, daddr = geocodificar_direccion(
        geo, photon, cache, "__depot__", "Ombú 1269", None, None
    )
    if dlat is None:
        dlat, dlon, daddr = geocodificar_direccion(
            geo, photon, cache, "__depot__", DEPOT_QUERY, None, None
        )
    if dlat is None:
        raise SystemExit("No se pudo geocodificar el depósito. Revisá conexión o caché.")

    dirs_unicas = df["Direccion"].astype(str).str.strip().unique()
    print(
        f"Geocodificando {len(dirs_unicas)} direcciones únicas (Photon + Nominatim, ~1 s entre llamadas)..."
    )

    for i, direccion in enumerate(sorted(dirs_unicas), 1):
        clave = f"addr:{direccion}"
        if not cache_valido_para_depot(cache, clave, dlat, dlon):
            print(f"  [{i}/{len(dirs_unicas)}] {direccion[:60]}...")
        _, _, _ = geocodificar_direccion(geo, photon, cache, clave, direccion, dlat, dlon)

    # Mapear a filas
    lat_list, lon_list, disp_list = [], [], []
    for _, row in df.iterrows():
        clave = f"addr:{str(row['Direccion']).strip()}"
        c = cache.get(clave, {})
        lat_list.append(c.get("lat"))
        lon_list.append(c.get("lon"))
        disp_list.append(c.get("display", ""))

    df["lat"] = lat_list
    df["lon"] = lon_list
    df["geocode_display"] = disp_list

    # Columnas presentación usuario
    partes = df["Direccion"].astype(str).apply(parse_direccion)
    df["Calle"] = partes.apply(lambda x: x[0])
    df["Altura"] = partes.apply(lambda x: x[1])
    df["Localidad"] = partes.apply(lambda x: x[2])
    df["Provincia"] = partes.apply(lambda x: x[3])
    df["Direccion_formateada"] = (
        df["Calle"].astype(str)
        + ", "
        + df["Altura"].astype(str)
        + ", "
        + df["Localidad"].astype(str)
        + ", "
        + df["Provincia"].astype(str)
    )

    resumen_zonas = []
    zonas = sorted(df["ZONA"].dropna().unique())

    for zona in zonas:
        sub = df[df["ZONA"] == zona].reset_index(drop=False)
        sub = sub.rename(columns={"index": "fila_orig"})
        puntos = []
        for _, r in sub.iterrows():
            if pd.isna(r["lat"]) or pd.isna(r["lon"]):
                continue
            puntos.append((int(r["fila_orig"]), (float(r["lat"]), float(r["lon"]))))

        cupos = int(sub["DMC+COMEDOR"].sum())
        camiones_cap = (cupos + CUPOS_CAMION - 1) // CUPOS_CAMION
        n_colegios = len(sub)

        if len(puntos) < 1:
            resumen_zonas.append(
                {
                    "ZONA": int(zona),
                    "colegios_con_coord": 0,
                    "colegios_total": n_colegios,
                    "cupos_DMC_COMEDOR": cupos,
                    "camiones_necesarios_5000": camiones_cap,
                    "min_conduccion_OSRM": None,
                    "min_ventanas_10min_entre_paradas": None,
                    "min_total_viaje_conduccion_mas_ventanas": None,
                    "km_ruta_aprox": None,
                }
            )
            continue

        orden_filas = orden_vecino_mas_cercano((dlat, dlon), puntos)
        seq = [sub[sub["fila_orig"] == fi].iloc[0] for fi in orden_filas]

        lonlat: list[tuple[float, float]] = []
        lonlat.append((float(cache["__depot__"]["lon"]), float(cache["__depot__"]["lat"])))
        for r in seq:
            lonlat.append((float(r["lon"]), float(r["lat"])))
        lonlat.append((float(cache["__depot__"]["lon"]), float(cache["__depot__"]["lat"])))

        dur_s, dist_m = ruta_osrm(lonlat)
        min_cond = (dur_s / 60.0) if dur_s is not None else None
        paradas = len(seq)
        ventanas_paradas = (paradas - 1) * VENTANA_ENTRE_PARADAS_MIN if paradas > 1 else 0
        min_total = None
        if min_cond is not None:
            min_total = min_cond + ventanas_paradas

        resumen_zonas.append(
            {
                "ZONA": int(zona),
                "colegios_con_coord": paradas,
                "colegios_total": n_colegios,
                "cupos_DMC_COMEDOR": cupos,
                "camiones_necesarios_5000": camiones_cap,
                "min_conduccion_OSRM": round(min_cond, 1) if min_cond is not None else None,
                "min_ventanas_10min_entre_paradas": ventanas_paradas,
                "min_total_viaje_conduccion_mas_ventanas": round(min_total, 1)
                if min_total is not None
                else None,
                "km_ruta_aprox": round((dist_m or 0) / 1000, 2) if dist_m else None,
            }
        )

    res_df = pd.DataFrame(resumen_zonas)
    n_zonas = len(res_df)
    tiempo_entre_viajes = (n_zonas - 1) * VENTANA_ENTRE_VIAJES_ZONA_MIN
    suma_cond = res_df["min_conduccion_OSRM"].fillna(0).sum()
    suma_total = res_df["min_total_viaje_conduccion_mas_ventanas"].fillna(0).sum()
    jornada_estimada = suma_total + tiempo_entre_viajes
    sin_coord = int(df["lat"].isna().sum())
    max_viaje_zona = float(res_df["min_total_viaje_conduccion_mas_ventanas"].max())

    out_csv = BASE_DIR / "colegios_geocodificados.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8-sig")
    out_res = BASE_DIR / "resumen_por_zona.csv"
    res_df.to_csv(out_res, index=False, encoding="utf-8-sig")

    out_xlsx = BASE_DIR / "informe_logistica_colegios.xlsx"
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Colegios", index=False)
        res_df.to_excel(writer, sheet_name="Resumen_zonas", index=False)
        pd.DataFrame(
            [
                ["Depósito", DEPOT_QUERY],
                ["Lat depósito", dlat],
                ["Lon depósito", dlon],
                ["Dirección resuelta", daddr],
                ["Cupos por camión", CUPOS_CAMION],
                ["Ventana 10 min (entre paradas en mismo viaje)", VENTANA_ENTRE_PARADAS_MIN],
                ["Ventana 10 min (entre viaje zona y viaje zona)", VENTANA_ENTRE_VIAJES_ZONA_MIN],
                ["Suma min conducción (todas las zonas)", round(suma_cond, 1)],
                ["Suma min viaje (conducción + ventanas entre paradas)", round(suma_total, 1)],
                ["+ min entre viajes de zona (12 zonas)", tiempo_entre_viajes],
                ["Jornada estimada secuencial (min)", round(jornada_estimada, 1)],
                ["Camiones-cupo total (suma ceil por zona)", int(res_df["camiones_necesarios_5000"].sum())],
                [
                    "Colegios sin geocodificar (revisar dirección a mano)",
                    sin_coord,
                ],
                [
                    "Si un camión hace zona tras zona en el mismo día (min)",
                    round(jornada_estimada, 1),
                ],
                [
                    "Si hay un camión por zona en paralelo: minutos del viaje más largo",
                    round(max_viaje_zona, 1),
                ],
            ],
            columns=["Concepto", "Valor"],
        ).to_excel(writer, sheet_name="Parametros", index=False)

    print("\n--- Listo ---")
    print(f"CSV: {out_csv}")
    print(f"Resumen: {out_res}")
    print(f"Excel: {out_xlsx}")
    print(f"Camiones (suma por zona, capacidad {CUPOS_CAMION}): {int(res_df['camiones_necesarios_5000'].sum())}")
    print(f"Jornada estimada (12 viajes seguidos + ventanas entre zonas): ~{jornada_estimada:.0f} min")
    print(f"Sin coordenadas (completar a mano): {sin_coord}")
    print(f"Viaje más largo (un camión por zona en paralelo): ~{max_viaje_zona:.0f} min")


if __name__ == "__main__":
    main()
