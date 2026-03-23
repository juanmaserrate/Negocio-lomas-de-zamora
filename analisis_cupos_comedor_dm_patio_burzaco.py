# -*- coding: utf-8 -*-
"""
Análisis adicional: rutas desde Ombú 1269 (Burzaco) por separado para
- Cupos por día Comedor
- Cupos por día Desayuno/Merienda
- Cupos Patios (columna patios/coros sábado)

Solo entran en el ruteo las filas con cupos > 0 en ese concepto.
Capacidad camión: 5000 cupos por tipo de análisis.
"""
from __future__ import annotations

import pandas as pd

from viajes_burzaco_por_zona import (
    BASE_DIR,
    CSV_COLEGIOS,
    CUPO_CAMION,
    VENTANA_ENTRE_PARADAS_MIN,
    geocodificar_depot_burzaco,
    ordenar_paradas_viaje,
    particionar_por_cupo_nn,
    ruta_osrm,
)

OUT_XLSX = BASE_DIR / "analisis_cupos_comedor_dm_patio_burzaco.xlsx"
OUT_DETALLE = BASE_DIR / "analisis_cupos_comedor_dm_patio_detalle.csv"
OUT_RESUMEN_GLOBAL = BASE_DIR / "analisis_cupos_comedor_dm_patio_resumen_global.csv"
OUT_RESUMEN_ZONA = BASE_DIR / "analisis_cupos_comedor_dm_patio_resumen_zona.csv"

COL_COMEDOR = "Cupos por día Comedor"
COL_DM = "Cupos por día Desayuno/Merienda"
COL_PATIO = "Cupos Patios Abiertos/Coros y Orquestas Sábado"

ESCENARIOS: list[tuple[str, str, str]] = [
    ("Comedor", COL_COMEDOR, "Cupos por día de comedor"),
    (
        "Desayuno_merienda",
        COL_DM,
        "Cupos por día desayuno y merienda (misma columna planilla)",
    ),
    (
        "Patios_coros_sabado",
        COL_PATIO,
        "Cupos patios abiertos / coros y orquestas sábado",
    ),
]


def analizar_escenario(
    df_ok: pd.DataFrame,
    col_cupos: str,
    nombre_corto: str,
    depot: tuple[float, float],
    depot_lonlat: tuple[float, float],
    todas_zonas: list,
) -> tuple[list[dict], list[dict]]:
    detalle_rows: list[dict] = []
    resumen_rows: list[dict] = []

    for zona in todas_zonas:
        sub = df_ok[df_ok["ZONA"] == zona]
        filas = []
        for id_fila, row in sub.iterrows():
            cup = int(pd.to_numeric(row[col_cupos], errors="coerce") or 0)
            if cup <= 0:
                continue
            filas.append(
                {
                    "id_fila": int(id_fila),
                    "Direccion": str(row.get("Direccion", "")),
                    "Escuela": str(row.get("Escuela", "")),
                    "cupos": cup,
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                }
            )

        if not filas:
            resumen_rows.append(
                {
                    "escenario": nombre_corto,
                    "ZONA": int(zona),
                    "n_paradas": 0,
                    "cupos_total": 0,
                    "n_viajes_camion": 0,
                    "horas_conduccion_total": None,
                    "horas_viaje_con_ventanas": None,
                    "km_total_rutas": None,
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

            escuelas_txt = " | ".join(
                f"[{p['id_fila']}] {str(p['Escuela'])[:25]}:{p['Direccion'][:30]}({p['cupos']})"
                for p in ordenados
            )

            detalle_rows.append(
                {
                    "escenario": nombre_corto,
                    "ZONA": int(zona),
                    "viaje_n_en_zona": nv,
                    "cupos_camion_capacidad": CUPO_CAMION,
                    "cupos_cargados": cupos_v,
                    "n_paradas": n_paradas,
                    "min_conduccion_OSRM": round(min_cond, 2) if min_cond else None,
                    "horas_conduccion_viaje": round(min_cond / 60.0, 3)
                    if min_cond
                    else None,
                    "min_ventanas_10min_entre_paradas": ventanas,
                    "min_total_viaje": round(min_total, 2) if min_total else None,
                    "horas_total_viaje_con_ventanas": round(min_total / 60.0, 3)
                    if min_total
                    else None,
                    "km_ruta_OSRM": round(dist_m / 1000, 3) if dist_m else None,
                    "ids_filas_paradas": ",".join(str(p["id_fila"]) for p in ordenados),
                    "paradas_orden_visita": escuelas_txt,
                }
            )

        resumen_rows.append(
            {
                "escenario": nombre_corto,
                "ZONA": int(zona),
                "n_paradas": len(filas),
                "cupos_total": cupos_zona,
                "n_viajes_camion": len(viajes_crudos),
                "horas_conduccion_total": round(min_cond_acum / 60.0, 3)
                if min_cond_acum
                else None,
                "horas_viaje_con_ventanas": round(min_total_acum / 60.0, 3)
                if min_total_acum
                else None,
                "km_total_rutas": round(km_acum, 3) if km_acum else None,
            }
        )

    return detalle_rows, resumen_rows


def main() -> None:
    dlat, dlon, daddr = geocodificar_depot_burzaco()
    depot = (dlat, dlon)
    depot_lonlat = (dlon, dlat)

    df = pd.read_csv(CSV_COLEGIOS, encoding="utf-8-sig")
    for col in (COL_COMEDOR, COL_DM, COL_PATIO):
        if col not in df.columns:
            raise SystemExit(f"Falta columna en CSV: {col}")

    df_ok = df.dropna(subset=["lat", "lon"]).copy().reset_index(drop=True)
    todas_zonas = sorted(df["ZONA"].dropna().unique())

    todo_detalle: list[dict] = []
    todo_resumen_zona: list[dict] = []
    resumen_global: list[dict] = []

    for nombre_corto, col_cupos, descripcion in ESCENARIOS:
        det, res_z = analizar_escenario(
            df_ok, col_cupos, nombre_corto, depot, depot_lonlat, todas_zonas
        )
        todo_detalle.extend(det)
        todo_resumen_zona.extend(res_z)

        det_df = pd.DataFrame(det)
        cupos_tot = int(
            pd.to_numeric(df_ok[col_cupos], errors="coerce").fillna(0).clip(lower=0).sum()
        )
        n_paradas_con_entrega = int((pd.to_numeric(df_ok[col_cupos], errors="coerce").fillna(0) > 0).sum())

        if len(det_df) > 0:
            h_cond = det_df["min_conduccion_OSRM"].fillna(0).sum() / 60.0
            h_tot = det_df["min_total_viaje"].fillna(0).sum() / 60.0
            max_h_viaje = det_df["horas_total_viaje_con_ventanas"].max()
            n_viajes = len(det_df)
        else:
            h_cond = h_tot = max_h_viaje = 0.0
            n_viajes = 0

        resumen_global.append(
            {
                "escenario": nombre_corto,
                "descripcion": descripcion,
                "columna_excel": col_cupos,
                "cupos_totales_planilla": cupos_tot,
                "n_paradas_con_cupos_mayor_0": n_paradas_con_entrega,
                "n_viajes_camion": n_viajes,
                "horas_conduccion_suma_todos_viajes": round(h_cond, 3),
                "horas_totales_suma_viajes_con_ventanas_10min": round(h_tot, 3),
                "horas_viaje_mas_largo_individual": round(float(max_h_viaje or 0), 3),
            }
        )

    det_all = pd.DataFrame(todo_detalle)
    res_z_all = pd.DataFrame(todo_resumen_zona)
    res_g = pd.DataFrame(resumen_global)

    meta = pd.DataFrame(
        [
            ["Depósito", "Ombú 1269, Burzaco (ver depot_burzaco.json)"],
            ["Dirección resuelta", daddr],
            ["Capacidad camión (cada análisis)", CUPO_CAMION],
            ["Ventana entre paradas (min)", VENTANA_ENTRE_PARADAS_MIN],
            [
                "Nota horas",
                "Suma de horas = todos los viajes; si un solo camión hace todo en serie, "
                "la jornada es esa suma (más tiempo entre viajes si aplica).",
            ],
        ],
        columns=["Concepto", "Valor"],
    )

    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        meta.to_excel(writer, sheet_name="Parametros", index=False)
        res_g.to_excel(writer, sheet_name="Resumen_global_tipo_cupo", index=False)
        res_z_all.to_excel(writer, sheet_name="Resumen_por_zona_y_tipo", index=False)
        det_all.to_excel(writer, sheet_name="Detalle_viajes", index=False)

    det_all.to_csv(OUT_DETALLE, index=False, encoding="utf-8-sig")
    res_g.to_csv(OUT_RESUMEN_GLOBAL, index=False, encoding="utf-8-sig")
    res_z_all.to_csv(OUT_RESUMEN_ZONA, index=False, encoding="utf-8-sig")

    print("Depósito:", daddr[:70], "...")
    print(res_g.to_string(index=False))
    print(f"\nExcel: {OUT_XLSX}")


if __name__ == "__main__":
    main()
