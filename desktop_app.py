from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from anonymization_core import (
    AnonymisationCancelled,
    DEFAULT_ENTITY_TYPES,
    ENTITY_TYPE_OPTIONS,
    default_selected_columns,
    load_dataframe,
    process_dataframe,
    write_output_workbook,
)

APP_VERSION = "1.2.2"
LARGE_FILE_ROW_WARNING = 3000
