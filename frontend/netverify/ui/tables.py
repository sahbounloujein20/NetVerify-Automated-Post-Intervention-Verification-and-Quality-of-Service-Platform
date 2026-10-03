"""Data tables: column configuration, search, export."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from ..settings import STATUS_LABELS

# Readable labels for the technical column names of the backend.
COLUMN_LABELS = {
    "ref_demande": "Reference",
    "num_appel": "Line no.",
    "num_telephone": "Phone no.",
    "nom_client": "Customer",
    "techno_souscrite": "Technology",
    "technologie": "Technology",
    "fsi": "ISP",
    "debit": "Subscribed rate",
    "type_demande": "Request type",
    "type_ot": "Work-order type",
    "etat_ot": "Status",
    "date_etat": "Status date",
    "date_test": "Test date",
    "id_technicien": "Technician",
    "id_log": "ID",
    "statut_test": "Status",
    "message_log": "Diagnosis",
    "zone": "Zone",
    "total": "Total",
    "traitees": "Processed",
    "en_cours": "In progress",
    "emises": "Issued",
    "taux_resolution": "Resolution rate",
    "taux_conformite": "Compliance rate",
    "nb_anomalies": "Anomalies",
    "nb_reclamations": "Work orders",
    "nb_clients": "Customers",
    "position_site_nouvelle": "Intervention site",
    "debit_promis_kbps": "Promised rate",
    "debit_mesure_kbps": "Measured rate",
    # Privileged-action journal
    "horodatage": "Timestamp",
    "auteur": "Author",
    "role": "Role",
    "action": "Action",
    "resultat": "Outcome",
    "details": "Detail",
}


def label_of(column: str) -> str:
    return COLUMN_LABELS.get(column, column.replace("_", " ").capitalize())


def text_col(column: str, width: str = "medium") -> Any:
    return st.column_config.TextColumn(label_of(column), width=width)


def number_col(column: str, fmt: str = "%d", help_text: str | None = None) -> Any:
    return st.column_config.NumberColumn(label_of(column), format=fmt, help=help_text)


def percent_col(column: str, maximum: float = 100.0) -> Any:
    """Gauge column — the length carries the value, the number stays readable."""
    return st.column_config.ProgressColumn(
        label_of(column), format="%.1f %%", min_value=0, max_value=maximum
    )


def datetime_col(column: str) -> Any:
    return st.column_config.DatetimeColumn(label_of(column), format="DD/MM/YYYY HH:mm")


def auto_config(frame: pd.DataFrame) -> dict[str, Any]:
    """Default configuration: readable labels + formats matching the type."""
    config: dict[str, Any] = {}
    for column in frame.columns:
        if column in ("taux_resolution", "taux_conformite"):
            config[column] = percent_col(column)
        elif column in ("date_etat", "date_test", "timestamp_mesure", "horodatage"):
            config[column] = datetime_col(column)
        elif pd.api.types.is_numeric_dtype(frame[column]):
            config[column] = number_col(column)
        else:
            config[column] = text_col(column)
    return config


def prettify_status(frame: pd.DataFrame, column: str = "etat_ot") -> pd.DataFrame:
    if column in frame.columns:
        frame = frame.copy()
        frame[column] = frame[column].map(lambda v: STATUS_LABELS.get(v, v))
    return frame


def export_button(frame: pd.DataFrame, filename: str, key: str) -> None:
    st.download_button(
        "Export to CSV",
        data=frame.to_csv(index=False).encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
        icon=":material/download:",
        width="stretch",
        key=key,
    )


def data_table(
    frame: pd.DataFrame,
    *,
    key: str,
    height: int = 460,
    columns: list[str] | None = None,
    config: dict[str, Any] | None = None,
    selectable: bool = False,
):
    """Configured table. Returns the selection state when `selectable`."""
    visible = [c for c in (columns or list(frame.columns)) if c in frame.columns]
    view = frame[visible]
    return st.dataframe(
        view,
        width="stretch",
        height=height,
        hide_index=True,
        key=key,
        column_config=config or auto_config(view),
        on_select="rerun" if selectable else "ignore",
        selection_mode="single-row" if selectable else "multi-row",
    )


def selected_row(state: Any, frame: pd.DataFrame) -> pd.Series | None:
    """Extracts the selected row from a `st.dataframe(on_select="rerun")`."""
    try:
        rows = state["selection"]["rows"]
    except (TypeError, KeyError):
        return None
    if not rows or rows[0] >= len(frame):
        return None
    return frame.iloc[rows[0]]
