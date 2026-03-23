# -*- coding: utf-8 -*-
"""Genera informe/public/data/rutas.json para el informe interactivo."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
PUBLIC = BASE / "public"
DATA_DIR = PUBLIC / "data"
CSV_COLEGIOS = BASE.parent / "colegios_geocodificados.csv"
CSV_DMC = BASE.parent / "viajes_burzaco_detalle.csv"
CSV_TIPOS = BASE.parent / "analisis_cupos_comedor_dm_patio_detalle.csv"
DEPOT_JSON = BASE.parent / "depot_burzaco.json"


def barrio_desde_fila(row: pd.Series) -> str:
    loc = (
        str(row.get("Localidad") or "")
        .replace("(referencia)", "")
        .replace("Lomas de Zamora / alrededores", "Lomas de Zamora")
        .strip()
    )
    g = str(row.get("geocode_display") or "")
    if not g:
        return loc or "—"
    if "Partido" in g:
        antes = g.split("Partido")[0]
        trozos = [t.strip() for t in antes.split(",")[1:] if t.strip()]
        geo = ", ".join(trozos[-4:]) if trozos else ""
    else:
        partes = [p.strip() for p in g.split(",")]
        geo = ", ".join(partes[1:4]) if len(partes) > 3 else ""
    partes_out = [p for p in (loc, geo) if p]
    return " · ".join(partes_out)[:200] if partes_out else loc or "—"


def nombre_escuela(row: pd.Series) -> str:
    e = row.get("Escuela", "")
    n = str(row.get("Nivel", "") or "")
    if pd.isna(e) or str(e).strip() == "":
        return "Sin código"
    s = str(e).strip()
    if n and str(n) != "nan":
        return f"{s} ({n})"
    return s


def cargar_lookup() -> pd.DataFrame:
    df = pd.read_csv(CSV_COLEGIOS, encoding="utf-8-sig")
    df = df.dropna(subset=["lat", "lon"]).copy().reset_index(drop=True)
    return df


def fila_a_stop(row: pd.Series, orden: int, cupos: int) -> dict:
    return {
        "orden": orden,
        "escuela": nombre_escuela(row),
        "direccion": str(row.get("Direccion") or ""),
        "direccion_completa": str(row.get("Direccion_formateada") or row.get("Direccion") or ""),
        "barrio": barrio_desde_fila(row),
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "cupos": int(cupos),
    }


def construir_desde_detalle(
    df_lookup: pd.DataFrame,
    det: pd.DataFrame,
    cupos_col: str | None,
) -> dict:
    """cupos_col: si None, usa columna DMC del lookup por id."""
    zonas_map: dict[int, list[dict]] = {}

    for _, r in det.iterrows():
        z = int(r["ZONA"])
        nv = int(r["viaje_n_en_zona"])
        ids_raw = str(r.get("ids_filas_paradas") or "")
        ids = [int(x.strip()) for x in ids_raw.split(",") if x.strip().isdigit()]

        stops: list[dict] = []
        orden = 1
        for fid in ids:
            if fid < 0 or fid >= len(df_lookup):
                continue
            row = df_lookup.iloc[fid]
            if cupos_col and cupos_col in df_lookup.columns:
                c = int(pd.to_numeric(row[cupos_col], errors="coerce") or 0)
            else:
                c = int(pd.to_numeric(row["DMC+COMEDOR"], errors="coerce") or 0)
            stops.append(fila_a_stop(row, orden, c))
            orden += 1

        trip = {
            "viaje_n": nv,
            "cupos_cargados": int(r.get("cupos_cargados") or 0),
            "n_paradas": int(r.get("n_paradas") or 0),
            "min_total": float(r["min_total_viaje"])
            if pd.notna(r.get("min_total_viaje"))
            else None,
            "km": float(r["km_ruta_OSRM"]) if pd.notna(r.get("km_ruta_OSRM")) else None,
            "stops": stops,
        }
        zonas_map.setdefault(z, []).append(trip)

    zonas_out = []
    for z in sorted(zonas_map.keys()):
        viajes = sorted(zonas_map[z], key=lambda t: t["viaje_n"])
        zonas_out.append({"id": z, "titulo": f"Zona {z}", "viajes": viajes})
    return {"zonas": zonas_out}


def main() -> None:
    df_lookup = cargar_lookup()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    dep_lat, dep_lon = -34.8353338, -58.4233261
    if DEPOT_JSON.exists():
        dj = json.loads(DEPOT_JSON.read_text(encoding="utf-8"))
        if dj.get("lat") is not None:
            dep_lat, dep_lon = float(dj["lat"]), float(dj["lon"])

    dmc = pd.read_csv(CSV_DMC, encoding="utf-8-sig")
    tipos = pd.read_csv(CSV_TIPOS, encoding="utf-8-sig")

    COL_C = "Cupos por día Comedor"
    COL_DM = "Cupos por día Desayuno/Merienda"
    COL_P = "Cupos Patios Abiertos/Coros y Orquestas Sábado"

    out = {
        "meta": {
            "titulo": "Informe de rutas — Real de Catorce",
            "descripcion": "Zonas, viajes y paradas desde depósito Burzaco",
            "generado_utc": datetime.now(timezone.utc).isoformat(),
            "deposito": {
                "nombre": "Ombú 1269, Burzaco",
                "lat": dep_lat,
                "lon": dep_lon,
            },
            "capacidad_camion": 5000,
        },
        "segmentos": {
            "dmc": {
                "id": "dmc",
                "titulo": "DMC",
                "subtitulo": "Cupos DMC+COMEDOR",
                **construir_desde_detalle(df_lookup, dmc, None),
            },
            "comedor": {
                "id": "comedor",
                "titulo": "Cupos día — Comedor",
                "subtitulo": "Solo columna comedor",
                **construir_desde_detalle(
                    df_lookup,
                    tipos[tipos["escenario"] == "Comedor"],
                    COL_C,
                ),
            },
            "desayuno_merienda": {
                "id": "desayuno_merienda",
                "titulo": "Cupos día — Desayuno y merienda",
                "subtitulo": "Una columna en planilla (desayuno + merienda)",
                **construir_desde_detalle(
                    df_lookup,
                    tipos[tipos["escenario"] == "Desayuno_merienda"],
                    COL_DM,
                ),
            },
            "patios": {
                "id": "patios",
                "titulo": "Patios / coros / sábado",
                "subtitulo": "Cupos patios abiertos y orquestas",
                **construir_desde_detalle(
                    df_lookup,
                    tipos[tipos["escenario"] == "Patios_coros_sabado"],
                    COL_P,
                ),
            },
        },
    }

    path = DATA_DIR / "rutas.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Escrito:", path)


if __name__ == "__main__":
    main()
