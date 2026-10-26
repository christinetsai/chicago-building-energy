"""
constants.py

Constants shared by the chart code. Settings that belong to a single chart
stay with the chart in final_graphs.py.
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

# Keep the 24 most common property types (this includes data centers,
# which have only 5 buildings)
TOP_N_TYPES = 24

# Unit conversions
MILLION = 1_000_000
THOUSAND = 1_000

# Panel charts: row height (pixels) and gap between panels
PANEL_ROW_HEIGHT = 22
PANEL_SPACING = 14

# Shared chart size (pixels) and sizes for charts that differ
CHART_WIDTH = 500
CHART_HEIGHT = 380
LINE_CHART_HEIGHT = 350
PRIORITY_WIDTH = 600
PRIORITY_HEIGHT = 450
