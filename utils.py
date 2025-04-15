"""
Utility functions for Master Scheduler application.
Contains common helper functions used across modules.
"""

import io
import base64

import pandas as pd
import streamlit as st

def download_excel(df, sheet_name, filename):
    """Create a download link for an Excel file from a DataFrame"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)

    b64 = base64.b64encode(output.getvalue()).decode()
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}.xlsx">Download Excel file</a>'
    return href


def format_metric(value, threshold_low, threshold_high, format_str="{:.2f}%", reverse=False):
    """Format a metric with color coding based on thresholds"""
    formatted = format_str.format(value)

    if not reverse:
        if value <= threshold_low:
            return f"<span style='color:#27ae60;font-weight:bold'>{formatted}</span>"
        elif value >= threshold_high:
            return f"<span style='color:#e74c3c;font-weight:bold'>{formatted}</span>"
        else:
            return f"<span style='color:#f39c12;font-weight:bold'>{formatted}</span>"
    else:
        if value >= threshold_high:
            return f"<span style='color:#27ae60;font-weight:bold'>{formatted}</span>"
        elif value <= threshold_low:
            return f"<span style='color:#e74c3c;font-weight:bold'>{formatted}</span>"
        else:
            return f"<span style='color:#f39c12;font-weight:bold'>{formatted}</span>"