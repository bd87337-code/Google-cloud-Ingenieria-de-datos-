"""Punto de entrada: `streamlit run app.py`."""
import streamlit as st

st.set_page_config(page_title="Macro Tracker", page_icon="🥑", layout="wide")

pages = [
    st.Page("macro_tracker/ui/pages/today.py", title="Hoy", icon="🍽️", default=True),
    st.Page("macro_tracker/ui/pages/progress.py", title="Progreso", icon="📈"),
    st.Page("macro_tracker/ui/pages/foods.py", title="Alimentos y recetas", icon="🥑"),
    st.Page("macro_tracker/ui/pages/goals.py", title="Perfil y metas", icon="🎯"),
    st.Page("macro_tracker/ui/pages/data.py", title="Datos", icon="💾"),
]
st.navigation(pages).run()
