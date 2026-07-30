from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class ApplicationData:
    """Snapshot completo y listo para ser mostrado por Streamlit."""

    equipment: pd.DataFrame = field(default_factory=pd.DataFrame)
    history: pd.DataFrame = field(default_factory=pd.DataFrame)
    gps: pd.DataFrame = field(default_factory=pd.DataFrame)
    movements: pd.DataFrame = field(default_factory=pd.DataFrame)
    certifications: pd.DataFrame = field(default_factory=pd.DataFrame)
    contracts: pd.DataFrame = field(default_factory=pd.DataFrame)
    workshop_capacity: pd.DataFrame = field(default_factory=pd.DataFrame)
    current_workshops: pd.DataFrame = field(default_factory=pd.DataFrame)
    search_aliases: dict[str, list[str]] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    loaded_at: datetime = field(default_factory=datetime.now)
