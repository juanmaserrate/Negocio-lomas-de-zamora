# -*- coding: utf-8 -*-
"""
Viajes desde Ombú 1269 (Burzaco): por zona del Excel, división por cupos (5000/camión),
orden geográfico coherente (vecino más cercano con restricción de capacidad + NN por viaje).

Cada fila del Excel = una parada distinta para cupos y conteo, aunque compartan coordenadas
(mismo edificio, colegios distintos). Un camión puede tener dos paradas seguidas en el mismo punto.
"""
from __future__ import annotations

import json
import time
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path

import pandas as pd
import requests
from haversine import Unit, haversine

BASE_DIR = Path(r"C:\Users\Usuario\Desktop\ANALISIS EMPRESARIAL")
CSV_COLEGIOS = BASE_DIR / "colegios_geocodificados.csv"
CACHE_DEPOT = BASE_DIR / "depot_burzaco.json"
OUT_XLSX = BASE_DIR / "viajes_burzaco_por_zona_cupos.xlsx"
OUT_DETALLE = BASE_DIR / "viajes_burzaco_detalle.csv"
OUT_RESUMEN = BASE_DIR / "viajes_burzaco_resumen_zona.csv"

OSRM = "https://router.project-osrm.org/route/v1/driving/{coords}"
CUPO_CAMION = 5000
VENTANA_ENTRE_PARADAS_MIN = 10
USER_AGENT_NOMINATIM = "realdecatorce_viajes_burzaco/1.0"

DEPOT_QUERY = (
    "Ombú 1269, Burzaco, Partido de Almirante Brown, Buenos Aires, Argentina"
)


def dist_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(radians, [a[0], a[1], b[0], b[1]])
    r = 6371.0
    dlat, dlon = la2 - la1, lo2 - lo1
    x = sin(dlat / 2) ** 2 + cos(la1) * cos(la2) * sin(dlon / 2) ** 2
    return 2 * r * atan2(sqrt(x), sqrt(1 - x))


def geocodificar_depot_burzaco() -> tuple[float, float, str]:
    if CACHE_DEPOT.exists():
        d = json.loads(CACHE_DEPOT.read_text(encoding="utf-8"))
        if d.get("lat") is not None:
            return float(d["lat"]), float(d["lon"]), d.get("display", "")
    from geopy.geocoders import Nominatim

    g = Nominatim(user_agent=USER_AGENT_NOMINATIM, timeout=25)
    time.sleep(1.05)
    loc = g.geocode(
        DEPOT_QUERY,
        country_codes="ar",
        timeout=25,
        language="es",
    )
    if not loc:
        raise SystemExit("No se pudo geocodificar el depósito en Burzaco.")
    CACHE_DEPOT.write_text(
        json.dumps(
            {
                "lat": loc.latitude,
                "lon": loc.longitude,
                "display": loc.address,
                "query": DEPOT_QUERY,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return loc.latitude, loc.longitude, loc.address


def orden_vecino_mas_cercano(
    depot: tuple[float, float],
    puntos: list[tuple[int, tuple[float, float]]],
) -> list[int]:
    resto = list(puntos)
    orden_idx: list[int] = []
    actual = depot
    while resto:
        j = min(range(len(resto)), key=lambda k: dist_km(actual, resto[k][1]))
        idx, coord = resto.pop(j)
        orden_idx.append(idx)
        actual = coord
    return orden_idx


def particionar_por_cupo_nn(
    filas: list[dict],
    depot: tuple[float, float],
    capacidad: int,
) -> list[list[dict]]:
    """
    Agrupa paradas en viajes: en cada viaje, desde la última posición (o depósito),
    elige la parada libre más cercana que quepa en el cupo restante.
    """
    libres = list(filas)
    viajes: list[list[dict]] = []
    while libres:
        ruta: list[dict] = []
        restante = capacidad
        pos = depot
        while True:
            candidatos = [f for f in libres if int(f["cupos"]) <= restante]
            if not candidatos:
                break
            sig = min(
                candidatos,
                key=lambda f: dist_km(pos, (float(f["lat"]), float(f["lon"]))),
            )
            ruta.append(sig)
            libres.remove(sig)
            restante -= int(sig["cupos"])
            pos = (float(sig["lat"]), float(sig["lon"]))
        if not ruta:
            raise RuntimeError("Parada no asignable (cupos > capacidad?).")
        viajes.append(ruta)
    return viajes


def ordenar_paradas_viaje(
    depot: tuple[float, float], paradas: list[dict]
) -> list[dict]:
    """Orden de visita dentro del viaje: NN desde depósito (coherencia de distancia)."""
    idx_pts = [(i, (float(p["lat"]), float(p["lon"]))) for i, p in enumerate(paradas)]
    orden_i = orden_vecino_mas_cercano(depot, idx_pts)
    return [paradas[i] for i in orden_i]


def ruta_osrm(coords_lonlat: list[tuple[float, float]]) -> tuple[float | None, float | None]:
    if len(coords_lonlat) < 2:
        return None, None
    s = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coords_lonlat)
    url = OSRM.format(coords=s)
    try:
        r = requests.get(url, params={"overview": "false"}, timeout=90)
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "Ok" or not j.get("routes"):
            return None, None
        route = j["routes"][0]
        return route["duration"], route["distance"]
    except Exception:
        return None, None


def main() -> None:
    dlat, dlon, daddr = geocodificar_depot_burzaco()
    depot = (dlat, dlon)
    depot_lonlat = (dlon, dlat)

    df = pd.read_csv(CSV_COLEGIOS, encoding="utf-8-sig")
    if "DMC+COMEDOR" not in df.columns:
        raise SystemExit("Falta columna DMC+COMEDOR en el CSV.")

    sin = df[df["lat"].isna() | df["lon"].isna()]
    if len(sin) > 0:
        print(f"Advertencia: {len(sin)} filas sin coordenadas (se omiten).")

    df_ok = df.dropna(subset=["lat", "lon"]).copy().reset_index(drop=True)
    n_paradas_total = len(df_ok)
    print(
        f"Paradas (1 fila Excel = 1 parada), con coordenadas: {n_paradas_total}"
    )

    detalle_rows: list[dict] = []
    resumen_rows: list[dict] = []
    ids_asignados: set[int] = set()

    todas_zonas = sorted(df["ZONA"].dropna().unique())

    for zona in todas_zonas:
        sub = df_ok[df_ok["ZONA"] == zona]
        filas = []
        for id_fila, row in sub.iterrows():
            filas.append(
                {
                    "id_fila": int(id_fila),
                    "Direccion": str(row.get("Direccion", "")),
                    "Escuela": str(row.get("Escuela", "")),
                    "cupos": int(row["DMC+COMEDOR"]),
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                }
            )

        if not filas:
            resumen_rows.append(
                {
                    "ZONA": int(zona),
                    "n_paradas": 0,
                    "cupos_total": 0,
                    "n_viajes_camion": 0,
                    "min_conduccion_total": None,
                    "min_total_con_ventanas": None,
                    "km_total": None,
                }
            )
            continue

        cupos_zona = sum(f["cupos"] for f in filas)
        viajes_crudos = particionar_por_cupo_nn(filas, depot, CUPO_CAMION)

        min_cond_acum = 0.0
        min_total_acum = 0.0
        km_acum = 0.0

        for nv, paradas in enumerate(viajes_crudos, start=1):
            ordenados = ordenar_paradas_viaje(depot, paradas)
            cupos_v = sum(p["cupos"] for p in ordenados)

            lonlat: list[tuple[float, float]] = [depot_lonlat]
            for p in ordenados:
                lonlat.append((float(p["lon"]), float(p["lat"])))
            lonlat.append(depot_lonlat)

            dur_s, dist_m = ruta_osrm(lonlat)
            min_cond = (dur_s / 60.0) if dur_s is not None else None
            n_paradas = len(ordenados)
            ventanas = (n_paradas - 1) * VENTANA_ENTRE_PARADAS_MIN if n_paradas > 1 else 0
            min_total = (min_cond + ventanas) if min_cond is not None else None

            if min_cond is not None:
                min_cond_acum += min_cond
            if min_total is not None:
                min_total_acum += min_total
            if dist_m is not None:
                km_acum += dist_m / 1000.0

            tramos_km: list[float] = []
            for a in range(len(lonlat) - 1):
                la1, lo1 = lonlat[a][1], lonlat[a][0]
                la2, lo2 = lonlat[a + 1][1], lonlat[a + 1][0]
                tramos_km.append(
                    float(haversine((la1, lo1), (la2, lo2), unit=Unit.KILOMETERS))
                )
            km_prom_tramo = sum(tramos_km) / len(tramos_km) if tramos_km else None
            km_max_tramo = max(tramos_km) if tramos_km else None

            escuelas_txt = " | ".join(
                f"[{p['id_fila']}] {str(p['Escuela'])[:25]}:{p['Direccion'][:30]}({p['cupos']})"
                for p in ordenados
            )

            for p in ordenados:
                pid = p["id_fila"]
                if pid in ids_asignados:
                    raise RuntimeError(f"id_fila repetido en rutas: {pid}")
                ids_asignados.add(pid)

            detalle_rows.append(
                {
                    "ZONA": int(zona),
                    "viaje_n_en_zona": nv,
                    "cupos_camion_capacidad": CUPO_CAMION,
                    "cupos_cargados": cupos_v,
                    "n_paradas": n_paradas,
                    "min_conduccion_OSRM": round(min_cond, 2) if min_cond else None,
                    "min_ventanas_10min_entre_paradas": ventanas,
                    "min_total_viaje": round(min_total, 2) if min_total else None,
                    "km_ruta_OSRM": round(dist_m / 1000, 3) if dist_m else None,
                    "km_promedio_tramo_recto": round(km_prom_tramo, 3)
                    if km_prom_tramo
                    else None,
                    "km_max_tramo_recto": round(km_max_tramo, 3)
                    if km_max_tramo
                    else None,
                    "ids_filas_paradas": ",".join(str(p["id_fila"]) for p in ordenados),
                    "paradas_orden_visita": escuelas_txt,
                }
            )

        resumen_rows.append(
            {
                "ZONA": int(zona),
                "n_paradas": len(filas),
                "cupos_total": cupos_zona,
                "n_viajes_camion": len(viajes_crudos),
                "min_conduccion_total": round(min_cond_acum, 2) if min_cond_acum else None,
                "min_total_con_ventanas": round(min_total_acum, 2)
                if min_total_acum
                else None,
                "km_total_rutas": round(km_acum, 3) if km_acum else None,
            }
        )

    esperados_ids = set(int(i) for i in df_ok.index.tolist())
    if ids_asignados != esperados_ids:
        raise RuntimeError(
            "Inconsistencia: no todas las filas del Excel quedaron asignadas a un viaje."
        )

    det_df = pd.DataFrame(detalle_rows)
    res_df = pd.DataFrame(resumen_rows)

    meta = pd.DataFrame(
        [
            ["Depósito", DEPOT_QUERY],
            ["Dirección resuelta", daddr],
            ["Latitud", dlat],
            ["Longitud", dlon],
            ["Cupos por camión", CUPO_CAMION],
            ["Ventana entre paradas (min)", VENTANA_ENTRE_PARADAS_MIN],
            [
                "Criterio división",
                "Vecino más cercano con cupo ≤ capacidad; orden visita NN por viaje",
            ],
            [
                "Paradas",
                "Cada fila del Excel con coordenadas = 1 parada (cupos y tiempos separados)",
            ],
            ["Total paradas contabilizadas", n_paradas_total],
            ["Total viajes (todas las zonas)", len(det_df)],
        ],
        columns=["Concepto", "Valor"],
    )

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        meta.to_excel(writer, sheet_name="Parametros", index=False)
        det_df.to_excel(writer, sheet_name="Detalle_viajes", index=False)
        res_df.to_excel(writer, sheet_name="Resumen_zona", index=False)

    det_df.to_csv(OUT_DETALLE, index=False, encoding="utf-8-sig")
    res_df.to_csv(OUT_RESUMEN, index=False, encoding="utf-8-sig")

    print("Depósito Burzaco:", daddr)
    print(f"Viajes calculados: {len(det_df)}")
    print(f"Excel: {OUT_XLSX}")
    print(f"CSV detalle: {OUT_DETALLE}")


if __name__ == "__main__":
    main()
