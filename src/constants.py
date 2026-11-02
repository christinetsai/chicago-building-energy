"""
constants.py

Constants shared by the chart code. Settings that belong to a single chart
stay with the chart in final_graphs.py.

Author: Christine Tsai
"""

from pathlib import Path

# Input and output folders relative to the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "static-viz" / "charts"

# Column names in the benchmarking data (after clean_names)
GHG_TOTAL = "total_ghg_emissions_metric_tons_co2e_"
GHG_INTENSITY = "ghg_intensity_kg_co2e_sq_ft_"

# Fuel columns and the names shown on charts
FUEL_COLS = {
    "electricity_use_kbtu_": "Electricity",
    "natural_gas_use_kbtu_": "Natural gas",
    "district_steam_use_kbtu_": "District steam",
    "district_chilled_water_use_kbtu_": "District chilled water",
    "all_other_fuel_use_kbtu_": "Other fuel",
}

# Value column in the sector CSV (million metric tons of CO2e)
SECTOR_VALUE = "million_metric_tons_co2e"

# Chicago community areas geojson
GEOJSON_URL = "https://data.cityofchicago.org/resource/igwz-8jzy.geojson"

# Star rating that counts as poorly rated.
POOR_RATING = 1

# Unit conversions
MILLION = 1_000_000
THOUSAND = 1_000

# Row height (pixels) of the box plot
PANEL_ROW_HEIGHT = 22

# Sizes shared by the charts (pixels, unless noted)
LABEL_FONT_SIZE = 12
LABEL_GAP = 4  # Space between a mark and its label
LINE_WIDTH = 3
REFERENCE_DASH = [4, 4]  # Dash pattern of a reference line
DOWNLOAD_TIMEOUT = 30  # Seconds to wait for a download

# Shared chart size (pixels) and sizes for charts that differ
CHART_WIDTH = 500
CHART_HEIGHT = 380
LINE_CHART_HEIGHT = 350
PRIORITY_WIDTH = 600
PRIORITY_HEIGHT = 450
