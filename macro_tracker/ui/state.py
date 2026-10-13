"""Conexión compartida a la base de datos para las páginas de Streamlit."""
from __future__ import annotations

import streamlit as st

from macro_tracker.config import db_path
from macro_tracker.db.connection import connect
from macro_tracker.db.repository import Repository


@st.cache_resource(show_spinner=False)
def _connection(path: str):
    return connect(path)


def get_repo() -> Repository:
    return Repository(_connection(str(db_path())))
