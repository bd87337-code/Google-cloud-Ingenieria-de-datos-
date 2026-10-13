"""Datos: exportar e importar todo en CSV."""
from __future__ import annotations

from datetime import date

import streamlit as st

from macro_tracker import io_csv
from macro_tracker.config import db_path
from macro_tracker.ui.state import get_repo

repo = get_repo()
st.title("Datos")
st.caption(f"Todo vive en un archivo local: `{db_path()}`. Nada sale de tu computadora salvo las consultas a "
           "Open Food Facts cuando buscas un alimento que no tienes.")

st.header("Exportar")
c1, c2 = st.columns(2)
with c1:
    st.download_button("Descargar todo (ZIP de CSV)", io_csv.export_zip(repo),
                       file_name=f"macro_tracker_{date.today():%Y%m%d}.zip", mime="application/zip",
                       type="primary", width="stretch")
    st.caption("Un CSV por tabla más un manifest. Sirve de respaldo y para abrirlo en Excel, R o Python.")
with c2:
    labels = {"body_log": "Peso y medidas", "food_log": "Diario de alimentos", "foods": "Alimentos y recetas",
              "targets": "Historial de metas", "profile": "Perfil", "recipes": "Recetas (rendimiento)",
              "recipe_items": "Recetas (ingredientes)", "day_status": "Estado de los días"}
    table = st.selectbox("Tabla individual", list(labels), format_func=labels.get)
    st.download_button("Descargar CSV", io_csv.export_table_csv(repo, table), file_name=f"{table}.csv",
                       mime="text/csv", width="stretch")

st.header("Importar")
st.write("Acepta el ZIP exportado por esta app o un CSV suelto de cualquiera de las tablas. "
         "La importación es **todo o nada**: si una fila tiene un error, no se guarda nada y se te dice dónde está.")
upload = st.file_uploader("Archivo", type=["zip", "csv"])
mode = st.radio("Modo", ["merge", "replace"], horizontal=True,
                format_func={"merge": "Combinar (agrega lo nuevo y actualiza lo existente)",
                             "replace": "Reemplazar (borra antes de importar)"}.get)
table_for_csv = None
if upload and upload.name.lower().endswith(".csv"):
    guess = upload.name.rsplit(".", 1)[0]
    table_for_csv = st.selectbox("¿A qué tabla corresponde este CSV?", list(io_csv.TABLES),
                                 index=list(io_csv.TABLES).index(guess) if guess in io_csv.TABLES else 0)
confirm = True
if mode == "replace":
    confirm = st.checkbox("Entiendo que esto borra los datos actuales de las tablas importadas "
                          "(con un ZIP completo, de todas).")
if upload and st.button("Importar", type="primary", disabled=not confirm):
    try:
        blob = upload.getvalue()
        report = (io_csv.import_zip(repo, blob, mode) if upload.name.lower().endswith(".zip")
                  else io_csv.import_csv(repo, table_for_csv, blob, mode))
    except io_csv.ImportErrors as exc:
        st.error("Importación cancelada; no se guardó nada.")
        for line in exc.errors[:io_csv.MAX_ERRORS_SHOWN]:
            st.write("• " + line)
        if len(exc.errors) > io_csv.MAX_ERRORS_SHOWN:
            st.caption(f"… y {len(exc.errors) - io_csv.MAX_ERRORS_SHOWN} errores más.")
    else:
        st.success("Importación completada: " + ", ".join(f"{t}: {n} filas" for t, n in report.counts.items()))
