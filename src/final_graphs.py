"""
final_graphs.py

Generates the charts for the Chicago building energy analysis and saves
them to static-viz/charts/.

Usage: uv run python src/final_graphs.py
"""

import pandas as pd
import altair as alt
import janitor  # noqa: F401  (registers DataFrame.clean_names)
import requests
import json
from pathlib import Path
import numpy as np

from categories import CATEGORY_ORDER, SHORT_TYPE_NAMES, add_category_column
from constants import (
    CHART_HEIGHT,
    CHART_WIDTH,
    DATA_DIR,
    FUEL_COLS,
    GEOJSON_URL,
    GHG_INTENSITY,
    GHG_TOTAL,
    LINE_CHART_HEIGHT,
    MILLION,
    OUTPUT_DIR,
    PANEL_ROW_HEIGHT,
    PANEL_SPACING,
    POOR_RATING,
    PRIORITY_HEIGHT,
    PRIORITY_WIDTH,
    SECTOR_VALUE,
    THOUSAND,
    TOP_N_TYPES,
)
from theme import (
    AMBER,
    CHARCOAL,
    DEEP_BLUE,
    FLAG_BLUE,
    FLAME,
    GRAY,
    INK,
    MUTED,
    POOR_RATING_COLOR,
    STAR_RED,
    apply_theme,
)

# =============================================================================
# SETUP
# Apply theme, set output folder, and helper for saving charts
# =============================================================================

apply_theme()

alt.data_transformers.disable_max_rows()

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save_chart(chart, name, scale_factor=1.0, svg=False):
    """
    Save a chart as a PNG in the output folder and optionally as an SVG.

    Inputs: an Altair chart, a file name without extension, the PNG
        resolution multiplier, and svg (True to also save an SVG).
    Output: none (writes one or two files).
    """
    chart.save(OUTPUT_DIR / f"{name}.png", scale_factor=scale_factor)
    if svg:
        chart.save(OUTPUT_DIR / f"{name}.svg")


def make_category_row():
    """
    Build the row facet that splits a chart into one panel per building
    category, in CATEGORY_ORDER, with a bold heading above each panel.

    Inputs: none.
    Output: an Altair Row facet on the "category" column.
    """
    return alt.Row(
        "category:N",
        sort=CATEGORY_ORDER,
        title=None,
        header=alt.Header(
            labelAngle=0,
            labelAlign="left",
            labelOrient="top",
            labelFontSize=14,
            labelFontWeight="bold",
            labelPadding=4,
        ),
    )


# =============================================================================
# LOAD DATA
# Load and filter the benchmarking data and load Chicago geojson
# =============================================================================


def load_chicago_benchmarks():
    """
    Load and clean the Chicago Energy Benchmarking data.

    Inputs: none (reads data/Chicago_Energy_Benchmarking_20261001.csv).
    Output: a DataFrame with snake_case columns, numeric columns converted,
        only the buildings that submitted data, and building category
        columns added (see categories.py).
    Errors: raises FileNotFoundError if the CSV is missing.
    """
    chi_bench_df = pd.read_csv(
        DATA_DIR / "Chicago_Energy_Benchmarking_20261001.csv", thousands=","
    )
    # normalize column names
    clean_df = chi_bench_df.clean_names()
    # normalize community area names, including spelling differences such as
    # O'Hare and Ohare
    clean_df["community_area"] = (
        clean_df["community_area"]
        .str.replace("'", "", regex=False)
        .str.title()
    )
    # Two types of reporting status are used for submitted building
    clean_df = clean_df[
        clean_df["reporting_status"].isin(["Submitted", "Submitted Data"])
    ]  # reduces from 28329 to 5621 rows
    for c in [
        "chicago_energy_rating",
        "latitude",
        "longitude",
        "year_built",
        "gross_floor_area_buildings_sq_ft_",
        "energy_star_score",
        "site_eui_kbtu_sq_ft_",
        "source_eui_kbtu_sq_ft_",
        GHG_TOTAL,
        GHG_INTENSITY,
        *FUEL_COLS.keys(),
    ]:
        clean_df[c] = pd.to_numeric(clean_df[c], errors="coerce")
    return add_category_column(clean_df)


def load_chicago_geojson(path=DATA_DIR / "chicago_community_areas.geojson"):
    """
    Load the Chicago community area shapes.

    Inputs: path to the saved GeoJSON file.
    Output: the GeoJSON as a dictionary.
    Errors: raises ValueError if the download has no features, or an
        HTTP error if the download fails.
    """
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text())
    r = requests.get(GEOJSON_URL, timeout=30)
    r.raise_for_status()
    gj = r.json()
    if "features" not in gj:
        raise ValueError(
            f"Unexpected response from {GEOJSON_URL}: {str(gj)[:200]}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(gj))
    return gj


CHI_GJ = load_chicago_geojson()

# Get dataset with top types from the latest year
# Each property can show up multiple times for each report year. Grab records from the latest year
ALL_YEARS = load_chicago_benchmarks()
LATEST_YEAR = ALL_YEARS["data_year"].max()
latest = ALL_YEARS[ALL_YEARS["data_year"] == LATEST_YEAR].copy()

top_types = (
    latest["primary_property_type"]
    .value_counts()
    .head(TOP_N_TYPES)
    .index.tolist()
)
latest_top = latest[latest["primary_property_type"].isin(top_types)]


# =============================================================================
# Chart 1: Citywide emissions by sector
# =============================================================================

SECTOR_CSV = DATA_DIR / "chicago_emissions_by_sector_2019.csv"
REPORTING_ROW = "Large reporting buildings (2023)"
# A single space reserves an empty band that separates the 2023 row
SPACER_ROW = " "
# Sector rows, largest first
ROW_LABELS = {
    "Buildings": "Buildings (2019)",
    "Transportation": "Transportation (2019)",
    "Industry & other": "Industry & other (2019)",
    "Waste": "Waste (2019)",
}
ROW_ORDER = [*ROW_LABELS.values(), SPACER_ROW, REPORTING_ROW]

# Subsector stack order and colors: blues are buildings, teal is industry,
# grays are other
SUBSECTOR_COLORS = {
    "Commercial & institutional": "#1C5F8A",
    "Residential buildings": "#2F86BE",
    "Industry & other": "#5BA4A4",
    "On-road vehicles": "#4A5568",
    "Other": "#9AA5B4",
    "Waste": "#C9CED6",
    "Large reporting buildings": "#0E4A73",
}
SUBSECTOR_ORDER = list(SUBSECTOR_COLORS)

SECTOR_CHART_WIDTH = 500
SECTOR_CHART_HEIGHT = 290
SECTOR_AXIS_MAX = 24  # Million tons; leaves room for the total labels
MIN_LABELED_SEGMENT = 3.0  # Smallest segment (million tons) given a label


def make_sector_chart(df):
    """
    Stacked bars of Chicago's emissions by sector, plus the emissions
    covered by this analysis (large buildings that reported in 2023).

    Citywide numbers come from data/chicago_emissions_by_sector_2019.csv
    (CMAP, 2019). The last bar is computed from the benchmarking data.

    Inputs: latest-year DataFrame of reporting buildings.
    Output: an Altair chart.
    Errors: raises FileNotFoundError if the sector CSV is missing.
    """
    sectors = pd.read_csv(SECTOR_CSV)
    sectors["row"] = sectors["sector"].map(ROW_LABELS)
    reporting_total = df[GHG_TOTAL].sum() / MILLION
    reporting = pd.DataFrame(
        {
            "subsector": ["Large reporting buildings"],
            SECTOR_VALUE: [reporting_total],
            "row": [REPORTING_ROW],
        }
    )
    rows = pd.concat([sectors, reporting], ignore_index=True)
    rows["subsector_rank"] = rows["subsector"].map(SUBSECTOR_ORDER.index)

    # Stack the segments in subsector order within each row and find the
    # middle of each one, where its label goes
    rows = rows.sort_values(["row", "subsector_rank"])
    segment_end = rows.groupby("row")[SECTOR_VALUE].cumsum()
    rows["segment_middle"] = segment_end - rows[SECTOR_VALUE] / 2

    # Row totals, shown just past the end of each bar
    totals = rows.groupby("row", as_index=False)[SECTOR_VALUE].sum()
    totals["label"] = totals[SECTOR_VALUE].map("{:.2f}M tons".format)

    # Only label segments that are wide enough to hold a number
    labeled_segments = rows[rows[SECTOR_VALUE] >= MIN_LABELED_SEGMENT]

    y_rows = alt.Y(
        "row:N",
        title=None,
        scale=alt.Scale(domain=ROW_ORDER),
        axis=alt.Axis(labelLimit=240),
    )
    bars = (
        alt.Chart(rows)
        .mark_bar()
        .encode(
            y=y_rows,
            x=alt.X(
                f"{SECTOR_VALUE}:Q",
                title="Million metric tons CO2e per year",
                scale=alt.Scale(domain=[0, SECTOR_AXIS_MAX]),
            ),
            color=alt.Color(
                "subsector:N",
                title=None,
                scale=alt.Scale(
                    domain=SUBSECTOR_ORDER,
                    range=list(SUBSECTOR_COLORS.values()),
                ),
                legend=alt.Legend(orient="bottom", columns=2),
            ),
            order=alt.Order("subsector_rank:Q"),
        )
    )
    segment_labels = (
        alt.Chart(labeled_segments)
        .mark_text(color="white", fontSize=12, fontWeight="bold")
        .encode(
            y=y_rows,
            x=alt.X("segment_middle:Q"),
            text=alt.Text(f"{SECTOR_VALUE}:Q", format=".2f"),
        )
    )
    total_labels = (
        alt.Chart(totals)
        .mark_text(align="left", dx=5, fontSize=12, color=INK)
        .encode(y=y_rows, x=alt.X(f"{SECTOR_VALUE}:Q"), text="label:N")
    )

    return (bars + segment_labels + total_labels).properties(
        width=SECTOR_CHART_WIDTH,
        height=SECTOR_CHART_HEIGHT,
        title=alt.TitleParams(
            "Chicago's greenhouse gas emissions by sector",
            subtitle=(
                "Citywide figures are for 2019 (CMAP). The bottom bar is 2023 "
                "data for large buildings that reported to the city."
            ),
            anchor="start",
        ),
    )


save_chart(make_sector_chart(latest), "1_citywide_emissions_by_sector")


# =============================================================================
# Chart 2: Bubble map of reporting buildings by community area
# =============================================================================

# Full-city map view
MAP_CENTER = [-87.68, 41.84]
MAP_SCALE = 72000
MAP_WIDTH = 540
MAP_HEIGHT = 660

# Community area shapes and place labels
CITY_FILL_COLOR = "#F1F3F5"
CITY_OUTLINE_COLOR = "#B8C0C8"
CITY_OUTLINE_WIDTH = 0.6
LABEL_FONT_SIZE = 11
LABEL_OFFSET = -1  # Pixels; lifts each label slightly above its point

# Place labels as (text, longitude, latitude, alignment).
MAP_LABELS = [
    ("← Loop", -87.590, 41.879, "left"),
    ("← Near North Side", -87.590, 41.899, "left"),
    ("Near West Side →", -87.682, 41.869, "right"),
    ("Austin", -87.774, 41.894, "right"),
    ("Kenwood", -87.595, 41.815, "left"),
    ("South Shore", -87.563, 41.771, "left"),
]

# Bubble map: one circle per community area. Size is the number of reporting
# buildings and color is the share of rated buildings with 1 star.
MIN_AREA_BUILDINGS = 25  # Areas with fewer buildings are drawn in gray
BUBBLE_MAX_BUILDINGS = 500  # Building count at the top of the size scale
BUBBLE_MAX_SIZE = 1800  # Circle area (square pixels) at that count
BUBBLE_LEGEND_COUNTS = [10, 50, 100, 250, 500]
BUBBLE_OPACITY = 0.9
BUBBLE_OUTLINE_COLOR = "white"
BUBBLE_OUTLINE_WIDTH = 0.8
# Color runs from light blue (low share of poorly rated buildings) through a
# pale neutral at the citywide share to red (high share)
SHARE_SCALE_MIN = 0.08  # Poorly rated share at the bluest color
SHARE_SCALE_MAX = 0.30  # Poorly rated share at the reddest color
SHARE_LOW_COLOR = "#3F9AD6"
SHARE_MID_COLOR = "#E3CBD3"
SMALL_AREA_COLOR = "#8D99AE"
SMALL_AREA_OUTLINE_WIDTH = 1


def make_city_layer():
    """
    Build the light community-area shapes that outline the city.

    Inputs: none (uses CHI_GJ).
    Output: an Altair geoshape chart.
    """
    return alt.Chart(alt.Data(values=CHI_GJ["features"])).mark_geoshape(
        fill=CITY_FILL_COLOR,
        stroke=CITY_OUTLINE_COLOR,
        strokeWidth=CITY_OUTLINE_WIDTH,
        clip=False,
    )


def make_label_layer():
    """
    Build the place labels to sit in empty space.

    Inputs: none (uses MAP_LABELS).
    Output: an Altair text chart layered on the map.
    """
    labels = pd.DataFrame(
        MAP_LABELS, columns=["text", "longitude", "latitude", "align"]
    )
    layers = [
        alt.Chart(labels[labels["align"] == align])
        .mark_text(
            align=align, fontSize=LABEL_FONT_SIZE, color=MUTED, dy=LABEL_OFFSET
        )
        .encode(longitude="longitude:Q", latitude="latitude:Q", text="text:N")
        for align in ("left", "right")
    ]
    return alt.layer(*layers)


def calculate_ring_center(ring):
    """
    Find the center and the area of a polygon ring, from its corner points.

    Inputs: a list of [longitude, latitude] points that closes on itself.
    Output: a tuple of (longitude, latitude, area) of the ring.
    """
    points = np.array(ring)
    x, y = points[:-1, 0], points[:-1, 1]
    next_x, next_y = points[1:, 0], points[1:, 1]
    cross = x * next_y - next_x * y
    area = cross.sum() / 2
    center_x = ((x + next_x) * cross).sum() / (6 * area)
    center_y = ((y + next_y) * cross).sum() / (6 * area)
    return center_x, center_y, abs(area)


def calculate_area_centers(geojson):
    """
    Find a point in the middle of each community area, from the center of its
    largest polygon.

    Inputs: the community area GeoJSON.
    Output: a DataFrame with "community_area" (title case, matching the
        benchmarking data), "longitude" and "latitude".
    """
    rows = []
    for feature in geojson["features"]:
        geometry = feature["geometry"]
        polygons = (
            geometry["coordinates"]
            if geometry["type"] == "MultiPolygon"
            else [geometry["coordinates"]]
        )
        centers = [calculate_ring_center(polygon[0]) for polygon in polygons]
        longitude, latitude, _ = max(centers, key=lambda center: center[2])
        rows.append(
            {
                "community_area": feature["properties"]["community"].title(),
                "longitude": longitude,
                "latitude": latitude,
            }
        )
    return pd.DataFrame(rows)


def summarize_community_areas(df):
    """
    Count the reporting buildings in each community area, and the share of
    the rated ones that are poorly rated (1 star).

    Inputs: latest-year DataFrame of reporting buildings.
    Output: a DataFrame with one row per community area: "community_area",
        "buildings", "rated", "poor", "poor_share", "longitude", "latitude",
        and "is_small" (True when there are too few buildings to compare).
    Errors: raises ValueError if an area has no position on the map.
    """
    rating = df["chicago_energy_rating"]
    counts = pd.DataFrame(
        {
            "community_area": df["community_area"],
            "rated": rating > 0,
            "poor": rating == POOR_RATING,
        }
    )
    areas = counts.groupby("community_area").agg(
        buildings=("rated", "size"),
        rated=("rated", "sum"),
        poor=("poor", "sum"),
    )
    areas = areas.reset_index().merge(
        calculate_area_centers(CHI_GJ), on="community_area", how="left"
    )
    unplaced = areas.loc[areas["longitude"].isna(), "community_area"]
    if not unplaced.empty:
        raise ValueError(f"No map position for: {', '.join(unplaced)}")
    areas["poor_share"] = areas["poor"] / areas["rated"]
    areas["is_small"] = areas["buildings"] < MIN_AREA_BUILDINGS
    return areas


def make_bubble_map(df):
    """
    Map the reporting buildings by community area: circle size shows how many
    buildings there are, and color shows the share that are poorly rated.
    Areas with few buildings are hollow gray circles because their shares
    are not reliable.

    Inputs: latest-year DataFrame of reporting buildings.
    Output: an Altair chart.
    """
    areas = summarize_community_areas(df)
    city_share = areas["poor"].sum() / areas["rated"].sum()
    size_scale = alt.Scale(
        domain=[0, BUBBLE_MAX_BUILDINGS], range=[0, BUBBLE_MAX_SIZE], clamp=True
    )
    # Both kinds of circle sit at the area's center, and the largest are
    # drawn first so the small ones are not hidden
    position = dict(longitude="longitude:Q", latitude="latitude:Q")
    draw_order = alt.Order("buildings:Q", sort="descending")
    circle_style = dict(
        opacity=BUBBLE_OPACITY,
        stroke=BUBBLE_OUTLINE_COLOR,
        strokeWidth=BUBBLE_OUTLINE_WIDTH,
    )
    shaded = (
        alt.Chart(areas[~areas["is_small"]])
        .mark_circle(**circle_style)
        .encode(
            **position,
            size=alt.Size(
                "buildings:Q",
                scale=size_scale,
                legend=alt.Legend(
                    title="Reporting buildings", values=BUBBLE_LEGEND_COUNTS
                ),
            ),
            color=alt.Color(
                "poor_share:Q",
                scale=alt.Scale(
                    domain=[SHARE_SCALE_MIN, city_share, SHARE_SCALE_MAX],
                    range=[SHARE_LOW_COLOR, SHARE_MID_COLOR, POOR_RATING_COLOR],
                    interpolate="lab",
                    clamp=True,
                ),
                legend=alt.Legend(title="Poorly rated (1 star)", format=".0%"),
            ),
            order=draw_order,
        )
    )
    small = (
        alt.Chart(areas[areas["is_small"]])
        .mark_point(
            shape="circle",
            filled=False,
            color=SMALL_AREA_COLOR,
            strokeWidth=SMALL_AREA_OUTLINE_WIDTH,
        )
        .encode(
            **position,
            size=alt.Size("buildings:Q", scale=size_scale, legend=None),
            order=draw_order,
        )
    )
    return (
        (make_city_layer() + shaded + small + make_label_layer())
        .project("mercator", center=MAP_CENTER, scale=MAP_SCALE)
        .properties(
            width=MAP_WIDTH,
            height=MAP_HEIGHT,
            title=alt.TitleParams(
                f"Reporting buildings by community area ({LATEST_YEAR})",
                subtitle=[
                    "Circle size: number of reporting buildings. Color: share "
                    "of rated buildings",
                    f"with 1 star, bluer below the citywide {city_share:.0%} "
                    "and redder above.",
                    f"Hollow gray: fewer than {MIN_AREA_BUILDINGS} buildings, "
                    "too few to compare.",
                ],
                anchor="start",
            ),
        )
    )


save_chart(make_bubble_map(latest), "2_building_bubble_map")


# =============================================================================
# Chart 3: Total emissions by property type
# =============================================================================

# Number of property types shown, and how many top bars get the highlight.
TOP_TYPES_SHOWN = 15
HIGHLIGHT_COUNT = 2
HIGHLIGHT_BAR_COLOR = DEEP_BLUE
OTHER_BAR_COLOR = "#B8C4D0"

# EPA Greenhouse Gas Equivalencies Calculator: metric tons of CO2e emitted
# by one gasoline-powered passenger vehicle in a year.
TONS_CO2E_PER_CAR_YEAR = 4.29


def format_compact_tons(amount):
    """
    Format a number of tons compactly, for example 1.6M or 286K.

    Inputs: a number of tons.
    Output: a string.
    """
    if amount >= MILLION:
        return f"{amount / MILLION:.1f}M"
    return f"{amount / THOUSAND:.0f}K"


def emissions_by_type_bar_chart(df):
    """
    Bar chart of total emissions for the highest-emitting property types.

    The top bars are highlighted and every bar is labeled with its total.

    Inputs: latest-year DataFrame (all property types).
    Output: an Altair chart.
    """
    property_type = (
        df.groupby("primary_property_type")
        .agg(
            total_ghg=(GHG_TOTAL, "sum"),
        )
        .reset_index()
        .nlargest(TOP_TYPES_SHOWN, "total_ghg")
    )
    share_of_total = property_type["total_ghg"].sum() / df[GHG_TOTAL].sum()
    property_type["type_label"] = property_type[
        "primary_property_type"
    ].replace(SHORT_TYPE_NAMES)
    property_type["highlight"] = (
        property_type["total_ghg"].rank(ascending=False) <= HIGHLIGHT_COUNT
    )
    property_type["label"] = property_type["total_ghg"].map(format_compact_tons)

    # Leave room to the right of the longest bar for its label
    axis_max = property_type["total_ghg"].max() * 1.12
    bar_scale = alt.Scale(domain=[0, axis_max])
    property_type["cars"] = property_type["total_ghg"] / TONS_CO2E_PER_CAR_YEAR
    bars = (
        alt.Chart(property_type)
        .mark_bar()
        .encode(
            x=alt.X(
                "total_ghg:Q",
                title="Greenhouse gas emissions (metric tons per year)",
                axis=alt.Axis(format="~s"),
                scale=bar_scale,
            ),
            y=alt.Y("type_label:N", sort="-x", title=None),
            color=alt.condition(
                alt.datum.highlight,
                alt.value(HIGHLIGHT_BAR_COLOR),
                alt.value(OTHER_BAR_COLOR),
            ),
        )
    )
    labels = (
        alt.Chart(property_type)
        .mark_text(align="left", dx=4, fontSize=12, color=INK)
        .encode(
            x=alt.X("total_ghg:Q", scale=bar_scale, axis=None),
            y=alt.Y("type_label:N", sort="-x"),
            text="label:N",
        )
    )
    # Invisible layer that draws a second axis along the top: the same
    # scale as the bars, converted from tons to equivalent cars per year
    cars_axis = (
        alt.Chart(property_type)
        .mark_point(opacity=0)
        .encode(
            x=alt.X(
                "cars:Q",
                title="Equivalent cars driven for a year (EPA)",
                axis=alt.Axis(orient="top", format="~s"),
                scale=alt.Scale(domain=[0, axis_max / TONS_CO2E_PER_CAR_YEAR]),
            ),
            y=alt.Y("type_label:N", sort="-x"),
        )
    )
    chart = (
        alt.layer(bars, labels, cars_axis)
        .resolve_scale(x="independent")
        .properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=alt.TitleParams(
                f"Which property types emit the most? ({LATEST_YEAR})",
                subtitle=[
                    "Multifamily housing and offices emit the most.",
                    f"{TOP_TYPES_SHOWN} building types account for "
                    f"{share_of_total:.0%} of emissions from reported buildings.",
                ],
                anchor="start",
            ),
        )
    )
    return chart


save_chart(emissions_by_type_bar_chart(latest), "3_emissions_by_type")


# =============================================================================
# Chart 4: Emissions per square foot by property type (box plot)
# =============================================================================


# Box thickness (pixels)
BOX_THICKNESS = 12


def emissions_by_type_box_plot(df):
    """
    Box plot of emissions per square foot within each property type, with
    one panel per building category.

    Panels follow CATEGORY_ORDER, and types are sorted by median within
    each panel. The sort order is worked out here because Altair ignores a
    median sort on box plots. Each label shows the number of buildings.

    Inputs: latest-year DataFrame (top property types).
    Output: an Altair chart.
    """
    d = df.dropna(subset=[GHG_INTENSITY])
    type_stats = (
        d.groupby("type_label", observed=True)[GHG_INTENSITY]
        .agg(median="median", buildings="count")
        .reset_index()
    )
    type_stats["axis_label"] = (
        type_stats["type_label"]
        + " ("
        + type_stats["buildings"].map("{:,}".format)
        + ")"
    )
    type_order = type_stats.sort_values("median", ascending=False)[
        "axis_label"
    ].tolist()
    d = d.merge(type_stats[["type_label", "axis_label"]], on="type_label")

    return (
        alt.Chart(d)
        .mark_boxplot(extent=1.5, size=BOX_THICKNESS)
        .encode(
            x=alt.X(
                f"{GHG_INTENSITY}:Q",
                title="Emissions per square foot (kg CO2e / sq ft)",
            ),
            y=alt.Y("axis_label:N", title=None, sort=type_order),
            color=alt.value(FLAG_BLUE),
        )
        .properties(width=CHART_WIDTH, height=alt.Step(PANEL_ROW_HEIGHT))
        .facet(
            row=make_category_row(),
            spacing=PANEL_SPACING,
        )
        .resolve_scale(y="independent")
        .properties(
            title=alt.TitleParams(
                "Variation in emissions per square foot by building type",
                subtitle=[
                    "Each box spans the middle half of buildings of that type;",
                    f"the white line is the median ({LATEST_YEAR}).",
                    "Number of buildings in parentheses.",
                ],
                anchor="start",
            )
        )
    )


save_chart(emissions_by_type_box_plot(latest_top), "4_emissions_type_box")


# =============================================================================
# Chart 5: Fuel mix of all reporting buildings
# =============================================================================

# Gas and electricity get slices; all other fuels are grouped together
OTHER_FUELS = "Other fuels"
DONUT_FUELS = ["Natural gas", "Electricity", OTHER_FUELS]
DONUT_COLORS = [FLAME, FLAG_BLUE, GRAY]
DONUT_SIZE = 240  # Pixels
DONUT_OUTER_RADIUS = 100
DONUT_INNER_RADIUS = 55
DONUT_LABEL_RADIUS = 78  # Middle of the ring
OUTSIDE_LABEL_RADIUS = 114  # Just outside the ring
MIN_INSIDE_LABEL_SHARE = 0.08  # Smaller slices are labeled outside
DONUT_LABEL_SIZE = 14


def estimate_emission_factors(d):
    """
    Estimate each fuel's emission factor (kg CO2e per kBtu) from the
    buildings' fuel use and reported emissions, by least squares through the
    origin. Fuels with a negative factor are dropped and the fit repeated.

    Inputs: a DataFrame of buildings from one year.
    Output: a Series of factors, indexed by fuel column.
    """
    d = d.dropna(subset=[GHG_TOTAL])
    use = d[list(FUEL_COLS)].fillna(0)
    emitted_kg = d[GHG_TOTAL] * THOUSAND
    fuels = list(FUEL_COLS)
    while True:
        factors, *_ = np.linalg.lstsq(
            use[fuels].values, emitted_kg.values, rcond=None
        )
        negative = [f for f, x in zip(fuels, factors) if x < 0]
        if not negative:
            break
        fuels = [f for f in fuels if f not in negative]
    factors = pd.Series(factors, index=fuels)
    return factors.reindex(list(FUEL_COLS), fill_value=0)


def summarize_fuel_use(df):
    """
    Find each fuel group's share of the energy used and of the emissions
    (energy times its emission factor).

    Inputs: latest-year DataFrame of reporting buildings.
    Output: a DataFrame with one row per measure and fuel group: "measure",
        "fuel", "share" and "fuel_rank" (drawing order).
    """
    energy = df[list(FUEL_COLS)].clip(lower=0).sum()
    emissions = energy * estimate_emission_factors(df)
    rows = []
    for measure, amounts in (("Energy used", energy), ("Emissions", emissions)):
        amounts = amounts.rename(index=FUEL_COLS)
        groups = [f if f in DONUT_FUELS else OTHER_FUELS for f in amounts.index]
        shares = amounts.groupby(groups).sum()
        shares = shares / shares.sum()
        for fuel in DONUT_FUELS:
            rows.append(
                {
                    "measure": measure,
                    "fuel": fuel,
                    "share": shares.get(fuel, 0),
                    "fuel_rank": DONUT_FUELS.index(fuel),
                }
            )
    return pd.DataFrame(rows)


def make_donut(shares, measure, title, show_legend):
    """
    Build one donut of fuel shares, labeled inside the ring (small slices
    outside it).

    Inputs: the table from summarize_fuel_use, the measure to draw, the
        title, and whether to show the legend.
    Output: an Altair chart.
    """
    legend = None
    if show_legend:
        legend = alt.Legend(orient="bottom", title=None, symbolType="circle")
    base = alt.Chart(shares[shares["measure"] == measure]).encode(
        theta=alt.Theta("share:Q", stack=True),
        color=alt.Color(
            "fuel:N",
            scale=alt.Scale(domain=DONUT_FUELS, range=DONUT_COLORS),
            legend=legend,
        ),
        order=alt.Order("fuel_rank:Q"),
    )
    ring = base.mark_arc(
        innerRadius=DONUT_INNER_RADIUS,
        outerRadius=DONUT_OUTER_RADIUS,
        stroke="white",
    )
    inside_labels = (
        base.transform_filter(alt.datum.share >= MIN_INSIDE_LABEL_SHARE)
        .mark_text(
            radius=DONUT_LABEL_RADIUS,
            fontSize=DONUT_LABEL_SIZE,
            fontWeight="bold",
        )
        .encode(
            text=alt.Text("share:Q", format=".0%"),
            color=alt.value("white"),  # Not the slice color
        )
    )
    outside_labels = (
        base.transform_filter(alt.datum.share < MIN_INSIDE_LABEL_SHARE)
        .mark_text(radius=OUTSIDE_LABEL_RADIUS, fontSize=DONUT_LABEL_SIZE)
        .encode(
            text=alt.Text("share:Q", format=".0%"),
            color=alt.value(INK),
        )
    )
    return (ring + inside_labels + outside_labels).properties(
        width=DONUT_SIZE,
        height=DONUT_SIZE,
        title=alt.TitleParams(title, anchor="middle", fontSize=14),
    )


def make_fuel_donuts(df):
    """
    Two donuts side by side: fuel shares of energy used and of emissions.

    Inputs: latest-year DataFrame of reporting buildings.
    Output: an Altair chart.
    """
    shares = summarize_fuel_use(df)
    energy_donut = make_donut(shares, "Energy used", "Share of energy used", True)
    emissions_donut = make_donut(
        shares, "Emissions", "Share of emissions", False
    )
    return (
        alt.hconcat(energy_donut, emissions_donut)
        .resolve_scale(color="shared")
        .properties(
            title=alt.TitleParams(
                f"Fuel mix of Chicago's reporting buildings ({LATEST_YEAR})",
                subtitle=[
                    "Left: share of energy used. Right: share of greenhouse "
                    "gas emissions,",
                    "estimated from each fuel's emission factor. Other fuels: "
                    "district steam, chilled water and other fuel.",
                ],
                anchor="start",
            )
        )
    )


save_chart(make_fuel_donuts(latest), "5_fuel_mix")


# =============================================================================
# Chart 6: The same buildings over time
# =============================================================================


# Column with each building's floor area
AREA_COLUMN = "gross_floor_area_buildings_sq_ft_"
LABEL_NUDGE = 9  # Pixels between the end labels of lines that nearly overlap
# A paler red than the emissions line
HYPOTHETICAL_EMISSIONS_COLOR = "#EE8B98"


def calculate_fixed_factor_intensity(d, start):
    """
    Emissions per square foot for every building and year if each fuel had
    kept its emission factor from the first year. Any change in this measure
    comes from the buildings' energy use or fuel mix, not from the grid.

    Inputs: a DataFrame of the buildings in every year, and the first year.
    Output: a DataFrame of emissions per square foot, with one row per
        building and one column per year.
    """
    factors = estimate_emission_factors(d[d["data_year"] == start])
    use = d[list(FUEL_COLS)].fillna(0)
    intensity = (use * factors).sum(axis=1) / d[AREA_COLUMN]
    return intensity.groupby([d["id"], d["data_year"]]).first().unstack()


def same_building_trend(df, start=2018, end=2023):
    """
    Line chart of how the median building's energy use and emissions
    changed, for the buildings that reported every year. Each building is
    compared with its own value in the first year, and the line shows the
    median of those percentages. A dashed line shows what emissions would
    have been if the emission factors had stayed at their first-year level,
    which separates a cleaner grid from changes in the buildings.

    Inputs: all-years DataFrame, and the first and last year to show.
    Output: an Altair chart.
    """
    energy = "Energy used per square foot"
    emissions = "Emissions per square foot"
    fixed = "Emissions with the grid at its 2018 level"
    metrics = {
        "site_eui_kbtu_sq_ft_": energy,
        GHG_INTENSITY: emissions,
    }
    d = df[df["data_year"].between(start, end)]
    wide = d.pivot_table(index="id", columns="data_year", values=list(metrics))
    ids = wide.dropna().index  # buildings with every metric in every year
    wide = wide.loc[ids]

    # Each building as a percent of its own first-year value, then the
    # median across buildings for each year
    trend = pd.DataFrame(
        {
            name: (wide[column].div(wide[column][start], axis=0) * 100).median()
            for column, name in metrics.items()
        }
    )
    held = calculate_fixed_factor_intensity(d[d["id"].isin(ids)], start)
    held = held.where(held[start] > 0)
    trend[fixed] = (held.div(held[start], axis=0) * 100).median()

    trend = trend.reset_index().melt(
        "data_year", var_name="measure", value_name="index"
    )

    # One legend for color and dashes, with line symbols so the hypothetical
    # line shows as dashes
    legend = alt.Legend(
        orient="top", columns=1, labelLimit=400, symbolType="stroke"
    )
    base = alt.Chart(trend).encode(
        x=alt.X("data_year:O", title="Year", axis=alt.Axis(labelAngle=0)),
        y=alt.Y(
            "index:Q",
            title=f"Median building, as % of its own {start} level",
            scale=alt.Scale(zero=False),
        ),
        color=alt.Color(
            "measure:N",
            title=None,
            scale=alt.Scale(
                domain=[energy, emissions, fixed],
                range=[DEEP_BLUE, STAR_RED, HYPOTHETICAL_EMISSIONS_COLOR],
            ),
            legend=legend,
        ),
        strokeDash=alt.StrokeDash(
            "measure:N",
            scale=alt.Scale(
                domain=[energy, emissions, fixed],
                range=[[1, 0], [1, 0], [6, 4]],
            ),
            legend=legend,
        ),
    )
    lines = base.mark_line(point=True, strokeWidth=3).encode(
        tooltip=[
            alt.Tooltip("data_year:O", title="Year"),
            alt.Tooltip("measure:N", title="Measure"),
            alt.Tooltip("index:Q", title="Index", format=".1f"),
        ]
    )
    # End-of-line numbers. Make sure the energy and hypothetical emissions
    # lines are not on top of each other.
    label_offsets = {energy: LABEL_NUDGE, emissions: 0, fixed: -LABEL_NUDGE}
    labels = alt.layer(
        *[
            base.transform_filter(
                (alt.datum.data_year == end) & (alt.datum.measure == measure)
            )
            .mark_text(align="left", dx=8, dy=offset, fontSize=12)
            .encode(text=alt.Text("index:Q", format=".0f"))
            for measure, offset in label_offsets.items()
        ]
    )
    ref = (
        alt.Chart(pd.DataFrame({"y": [100]}))
        .mark_rule(strokeDash=[4, 4], color="gray")
        .encode(y="y:Q")
    )
    return (ref + lines + labels).properties(
        width=CHART_WIDTH,
        height=LINE_CHART_HEIGHT,
        title=alt.TitleParams(
            f"The same {len(ids):,} buildings from {start}–{end}",
            subtitle=[
                "The median building's energy use and emissions per square "
                f"foot, each as a percent of its own {start} level.",
                "The dashed line shows emissions if the grid had stayed at its"
                f" {start} level.",
            ],
            anchor="start",
        ),
    )


save_chart(same_building_trend(ALL_YEARS), "6_same_building_trend")


# =============================================================================
# Chart 7: Cumulative emissions curve
# =============================================================================


# Shares of buildings that are marked on the curve
MARK_PERCENTS = [1, 5, 10]


def pareto_curve(df):
    """
    Cumulative share of emissions as buildings are added largest first,
    with the top 1%, 5% and 10% of buildings marked.

    Inputs: latest-year DataFrame.
    Output: an Altair chart.
    """
    ghg = GHG_TOTAL
    cumulative = (
        df.dropna(subset=[ghg])
        .sort_values(ghg, ascending=False)
        .reset_index(drop=True)
    )
    building_count = len(cumulative)
    cumulative["pct_buildings"] = (cumulative.index + 1) / building_count * 100
    cumulative["cum_pct_emissions"] = (
        cumulative[ghg].cumsum() / cumulative[ghg].sum() * 100
    )

    # One marked point for each share of buildings, labeled with the number
    # of buildings and the share of emissions they produce
    marks = []
    for percent in MARK_PERCENTS:
        buildings = round(building_count * percent / 100)
        row = cumulative.iloc[buildings - 1]
        marks.append(
            {
                "pct_buildings": row["pct_buildings"],
                "cum_pct_emissions": row["cum_pct_emissions"],
                "label": f"Top {percent}% ({buildings:,} buildings) = "
                f"{row['cum_pct_emissions']:.0f}% of emissions",
            }
        )
    marks = pd.DataFrame(marks)

    line = (
        alt.Chart(cumulative)
        .mark_line(color=STAR_RED, strokeWidth=3)
        .encode(
            x=alt.X(
                "pct_buildings:Q",
                title="Share of buildings, largest emitters first",
                axis=alt.Axis(labelExpr="datum.value + '%'"),
            ),
            y=alt.Y(
                "cum_pct_emissions:Q",
                title="Share of total emissions (running total)",
                scale=alt.Scale(domain=[0, 100]),
                axis=alt.Axis(labelExpr="datum.value + '%'"),
            ),
        )
    )
    points = (
        alt.Chart(marks)
        .mark_point(size=100, filled=True, color="black")
        .encode(x="pct_buildings:Q", y="cum_pct_emissions:Q")
    )
    labels = (
        alt.Chart(marks)
        .mark_text(align="left", dx=10, dy=14, fontSize=12)
        .encode(x="pct_buildings:Q", y="cum_pct_emissions:Q", text="label:N")
    )
    year = df["data_year"].max()
    return (line + points + labels).properties(
        width=CHART_WIDTH,
        height=LINE_CHART_HEIGHT,
        title=alt.TitleParams(
            "Cumulative share of emissions, buildings ranked largest to "
            "smallest",
            subtitle=[
                "Buildings are sorted from largest to smallest emitter, and "
                "the line",
                f"adds up their emissions ({building_count:,} reporting "
                f"buildings, {year}).",
            ],
            anchor="start",
        ),
    )


save_chart(pareto_curve(latest), "7_pareto_curve")


# =============================================================================
# Chart 8: Priority buildings
# =============================================================================


def priority_buildings(df, top_pct=0.10, n_labels=8):
    """
    Scatter of emissions intensity vs. total emissions, highlighting the
    top emitters, poorly rated buildings, and the overlap between them.

    Inputs: latest-year DataFrame, the share of buildings counted as top
        emitters, and how many overlap buildings to label by name.
    Output: an Altair chart.
    """
    ghg, inten = GHG_TOTAL, GHG_INTENSITY
    d = df.dropna(subset=[ghg, inten, "chicago_energy_rating"]).copy()
    d = d[(d[ghg] > 0) & (d[inten] > 0)]
    cutoff = d[ghg].quantile(1 - top_pct)
    top = d[ghg] >= cutoff
    low = d["chicago_energy_rating"] <= 1
    d["group"] = np.select(
        [top & low, top, low],
        ["Both", "Top 10% emitter", "Rated 0–1 stars"],
        default="Other buildings",
    )
    d["layer"] = d["group"].map(
        {
            "Other buildings": 0,
            "Rated 0–1 stars": 1,
            "Top 10% emitter": 2,
            "Both": 3,
        }
    )
    order = ["Both", "Top 10% emitter", "Rated 0–1 stars", "Other buildings"]
    colors = [STAR_RED, AMBER, CHARCOAL, "#d9d9d9"]
    counts = d["group"].value_counts()
    subtitle = [f"{counts.get(g, 0):,} buildings: {g}" for g in order[:3]]

    pts = (
        alt.Chart(d)
        .mark_circle(stroke="white", strokeWidth=0.3)
        .encode(
            x=alt.X(
                f"{inten}:Q",
                scale=alt.Scale(type="log"),
                title="GHG intensity (kg CO2e / sq ft, log scale)",
            ),
            y=alt.Y(
                f"{ghg}:Q",
                scale=alt.Scale(type="log"),
                title="Total GHG emissions (metric tons CO2e, log scale)",
            ),
            color=alt.Color(
                "group:N",
                title=None,
                sort=order,
                scale=alt.Scale(domain=order, range=colors),
            ),
            size=alt.condition(
                alt.datum.layer > 0, alt.value(70), alt.value(25)
            ),
            opacity=alt.condition(
                alt.datum.layer > 0, alt.value(0.9), alt.value(0.5)
            ),
            order=alt.Order("layer:Q"),
        )
    )

    cut_line = (
        alt.Chart(pd.DataFrame({"y": [cutoff]}))
        .mark_rule(strokeDash=[4, 4], color="gray")
        .encode(y="y:Q")
    )
    cut_text = (
        alt.Chart(
            pd.DataFrame(
                {
                    "y": [cutoff],
                    "t": [f"Top {top_pct:.0%} threshold: {cutoff:,.0f} tons"],
                }
            )
        )
        .mark_text(align="left", dy=-8, dx=4, fontSize=11, color="gray")
        .encode(y="y:Q", text="t:N", x=alt.value(5))
    )

    labeled = d[d["group"] == "Both"].nlargest(n_labels, ghg)
    labels = (
        alt.Chart(labeled)
        .mark_text(align="left", dx=8, fontSize=10)
        .encode(x=f"{inten}:Q", y=f"{ghg}:Q", text="property_name:N")
    )

    return (pts + cut_line + cut_text + labels).properties(
        width=PRIORITY_WIDTH,
        height=PRIORITY_HEIGHT,
        title=alt.TitleParams(
            "Big emitters and poor performers: where they overlap",
            subtitle=subtitle,
            anchor="start",
        ),
    )


save_chart(priority_buildings(latest), "8_priority_buildings", scale_factor=2.0)
