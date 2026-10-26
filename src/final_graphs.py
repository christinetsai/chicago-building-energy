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
import math
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
    FUEL_SCALE,
    INK,
    STAR_RED,
    STAR_SCALE,
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
    # normalize community area names
    clean_df["community_area"] = clean_df["community_area"].str.title()
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
ROW_LABELS = {
    "Buildings & stationary energy": "Buildings & industry (2019)",
    "Transportation": "Transportation (2019)",
    "Waste": "Waste (2019)",
}
ROW_ORDER = [*ROW_LABELS.values(), SPACER_ROW, REPORTING_ROW]

# Subsector stack order and colors: blues are buildings, grays are other
SUBSECTOR_COLORS = {
    "Commercial & institutional": "#1C5F8A",
    "Residential buildings": "#2F86BE",
    "Industry & other": "#A8D0E6",
    "On-road vehicles": "#4A5568",
    "Other": "#9AA5B4",
    "Waste": "#C9CED6",
    "Large reporting buildings": "#0E4A73",
}
SUBSECTOR_ORDER = list(SUBSECTOR_COLORS)

SECTOR_CHART_WIDTH = 500
SECTOR_CHART_HEIGHT = 240
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
    totals["label"] = totals[SECTOR_VALUE].map("{:.1f}M tons".format)

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
            text=alt.Text(f"{SECTOR_VALUE}:Q", format=".1f"),
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
            "Buildings are Chicago's biggest source of emissions",
            subtitle=[
                "Citywide figures are for 2019 (CMAP). The bottom bar is 2023",
                "data for large buildings that reported to the city.",
            ],
            anchor="start",
        ),
    )


save_chart(make_sector_chart(latest), "1_citywide_emissions_by_sector")


# =============================================================================
# Chart 2: Building dot map and downtown close-up
# =============================================================================

# Full-city map view
MAP_CENTER = [-87.68, 41.84]
MAP_SCALE = 72000
MAP_WIDTH = 540
MAP_HEIGHT = 660

# Downtown close-up view.
INSET_CENTER = [-87.645, 41.885]
INSET_SCALE = 150000
INSET_WIDTH = 260
INSET_HEIGHT = 240

DOT_SIZE_RANGE = [3, 45]


def calculate_view_bounds(center, scale, width, height):
    """
    Work out the longitude and latitude edges a Mercator view shows.

    Inputs: center as [longitude, latitude] in degrees, the projection
        scale (pixels per radian), and the view size in pixels.
    Output: a tuple (west, south, east, north) in degrees.
    """
    longitude, latitude = center
    half_span = math.degrees((width / 2) / scale)
    center_y = math.log(math.tan(math.pi / 4 + math.radians(latitude) / 2))

    def latitude_at(offset_pixels):
        y = center_y + offset_pixels / scale
        return math.degrees(2 * math.atan(math.exp(y)) - math.pi / 2)

    return (
        longitude - half_span,
        latitude_at(-height / 2),
        longitude + half_span,
        latitude_at(height / 2),
    )


# Area covered by the close-up and outlined on the full map
INSET_BOUNDS = calculate_view_bounds(
    INSET_CENTER, INSET_SCALE, INSET_WIDTH, INSET_HEIGHT
)


def make_city_layer(clip=False):
    """
    Build the light community-area shapes that outline the city.

    Inputs: clip, True to cut shapes off at the edge of the view.
    Output: an Altair geoshape chart.
    """
    return alt.Chart(alt.Data(values=CHI_GJ["features"])).mark_geoshape(
        fill="#F1F3F5", stroke="#B8C0C8", strokeWidth=0.6, clip=clip
    )


def make_bounds_layer():
    """
    Build a dashed rectangle marking the area shown in the close-up map.

    Inputs: none (uses INSET_BOUNDS).
    Output: an Altair geoshape chart.
    """
    west, south, east, north = INSET_BOUNDS
    box = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                    [west, south],
                ]
            ],
        },
    }
    return alt.Chart(alt.Data(values=[box])).mark_geoshape(
        fill=None, stroke=INK, strokeWidth=1.2, strokeDash=[5, 3]
    )


def make_dot_layer(data, size_domain, show_legend=True, clip=False):
    """
    Build the building dots, sized by emissions and colored by rating.

    Inputs: a DataFrame of rated buildings; size_domain, the
        [smallest, largest] emissions used to scale dot sizes (shared by
        both maps so dots match); show_legend, False to hide the legends;
        and clip, True to hide dots that fall outside the view.
    Output: an Altair circle chart.
    """
    size_legend = None
    color_legend = None
    if show_legend:
        size_legend = alt.Legend()
        color_legend = alt.Legend()
    return (
        alt.Chart(data)
        .mark_circle(opacity=0.9, stroke=INK, strokeWidth=0.3, clip=clip)
        .encode(
            longitude="longitude:Q",
            latitude="latitude:Q",
            size=alt.Size(
                f"{GHG_TOTAL}:Q",
                scale=alt.Scale(
                    domain=size_domain, range=DOT_SIZE_RANGE, type="sqrt"
                ),
                title=["Greenhouse gas", "emissions", "(tons per year)"],
                legend=size_legend,
            ),
            color=alt.Color(
                "chicago_energy_rating:O",
                title="Energy rating (stars)",
                scale=STAR_SCALE,
                legend=color_legend,
            ),
            # Draw the largest dots first so small ones are not hidden
            order=alt.Order(f"{GHG_TOTAL}:Q", sort="descending"),
        )
    )


def select_rated_buildings(df):
    """
    Keep buildings that have a star rating (unrated ones have no color).

    Inputs: a DataFrame with a "chicago_energy_rating" column.
    Output: the filtered DataFrame.
    """
    return df.dropna(subset=["chicago_energy_rating"])


def get_emissions_range(d):
    """
    Find the smallest and largest emissions, used to scale dot sizes the
    same way on both maps.

    Inputs: a DataFrame with the total emissions column.
    Output: a list [smallest, largest] in metric tons CO2e.
    """
    return [d[GHG_TOTAL].min(), d[GHG_TOTAL].max()]


def building_dot_map(df):
    """
    Map every rated building.

    Inputs: latest-year DataFrame (top property types).
    Output: an Altair chart.
    """
    d = select_rated_buildings(df)
    size_domain = get_emissions_range(d)
    return (
        (
            make_city_layer()
            + make_bounds_layer()
            + make_dot_layer(d, size_domain)
        )
        .project("mercator", center=MAP_CENTER, scale=MAP_SCALE)
        .properties(
            width=MAP_WIDTH,
            height=MAP_HEIGHT,
            title=alt.TitleParams(
                "Chicago's biggest emitters cluster downtown",
                subtitle=[
                    "Each dot is a building: size shows emissions, color shows",
                    "its Chicago Energy Rating (0-4 stars, 4 is best).",
                ],
                anchor="start",
            ),
        )
    )


def building_downtown_closeup(df):
    """
    Zoomed map of the downtown area outlined on the full map. It has no
    legend or title, so it can be placed over the full map in Inkscape.

    Inputs: latest-year DataFrame (top property types).
    Output: an Altair chart with a dashed frame matching the outline box.
    """
    d = select_rated_buildings(df)
    size_domain = get_emissions_range(d)
    west, south, east, north = INSET_BOUNDS
    downtown = d[
        d["longitude"].between(west, east) & d["latitude"].between(south, north)
    ]
    return (
        (
            make_city_layer(clip=True)
            + make_dot_layer(
                downtown, size_domain, show_legend=False, clip=True
            )
        )
        .project("mercator", center=INSET_CENTER, scale=INSET_SCALE)
        .properties(width=INSET_WIDTH, height=INSET_HEIGHT)
        .configure_view(stroke=INK, strokeWidth=1.2, strokeDash=[5, 3])
    )


save_chart(building_dot_map(latest_top), "2_building_dot_map", svg=True)
save_chart(
    building_downtown_closeup(latest_top), "2_downtown_closeup", svg=True
)


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
# Chart 5: Fuel mix by property type
# =============================================================================


# Natural gas labels are drawn only on segments at least this wide (share)
MIN_GAS_LABEL_SHARE = 0.10


def fuel_mix(df):
    """
    Stacked bars of each property type's share of energy by fuel, with one
    panel per building category.

    Panels follow CATEGORY_ORDER, and types are sorted by their natural gas
    share within each panel. Natural gas is drawn first, with its share
    printed on the bar. Fuels that no building uses are left out.

    Inputs: latest-year DataFrame (top property types).
    Output: an Altair chart.
    """
    fuel_order = [
        "Natural gas",
        "Electricity",
        "District steam",
        "District chilled water",
        "Other fuel",
    ]
    fuel_use = (
        df.assign(**{c: df[c].clip(lower=0) for c in FUEL_COLS})
        .groupby("type_label", observed=True)[list(FUEL_COLS)]
        .sum()
        .rename(columns=FUEL_COLS)
        .reset_index()
        .melt("type_label", var_name="fuel", value_name="kbtu")
    )
    fuel_use["share"] = fuel_use["kbtu"] / fuel_use.groupby("type_label")[
        "kbtu"
    ].transform("sum")

    # Leave out fuels that nobody uses, so they do not appear in the legend
    fuel_totals = fuel_use.groupby("fuel")["kbtu"].sum()
    fuels_used = [f for f in fuel_order if fuel_totals[f] > 0]
    gas_share = fuel_totals["Natural gas"] / fuel_totals.sum()
    fuel_use = fuel_use[fuel_use["fuel"].isin(fuels_used)].copy()

    # Panel (category) and axis label, with the number of buildings, for each
    # type. Natural gas is drawn first, so its label sits at half its share.
    reports_fuel = df[list(FUEL_COLS)].notna().any(axis=1)
    type_info = (
        df.assign(reports_fuel=reports_fuel)
        .groupby("type_label", observed=True)
        .agg(category=("category", "first"), buildings=("reports_fuel", "sum"))
        .reset_index()
    )
    type_info["axis_label"] = (
        type_info["type_label"]
        + " ("
        + type_info["buildings"].map("{:,}".format)
        + ")"
    )
    fuel_use = fuel_use.merge(type_info, on="type_label")
    fuel_use["gas_middle"] = fuel_use["share"] / 2

    # Sort types by natural gas share (Altair draws each panel in this order)
    gas_rows = fuel_use[fuel_use["fuel"] == "Natural gas"]
    type_order = gas_rows.sort_values("share", ascending=False)[
        "axis_label"
    ].tolist()

    y_types = alt.Y("axis_label:N", title=None, sort=type_order)
    bars = (
        alt.Chart()
        .mark_bar()
        .encode(
            x=alt.X(
                "share:Q",
                title="Share of energy use",
                axis=alt.Axis(format="%"),
            ),
            y=y_types,
            color=alt.Color(
                "fuel:N",
                title="Fuel",
                scale=FUEL_SCALE,
                legend=alt.Legend(values=fuels_used),
            ),
            order=alt.Order("fuel_rank:Q"),
        )
        .transform_calculate(fuel_rank=f"indexof({fuel_order}, datum.fuel)")
    )
    gas_labels = (
        alt.Chart()
        .transform_filter(
            f"datum.fuel == 'Natural gas' && datum.share >= {MIN_GAS_LABEL_SHARE}"
        )
        .mark_text(color="white", fontSize=11, fontWeight="bold")
        .encode(
            x=alt.X("gas_middle:Q"),
            y=y_types,
            text=alt.Text("share:Q", format=".0%"),
        )
    )

    return (
        alt.layer(bars, gas_labels)
        .properties(width=CHART_WIDTH, height=alt.Step(PANEL_ROW_HEIGHT))
        .facet(
            row=make_category_row(),
            data=fuel_use,
            spacing=PANEL_SPACING,
        )
        .resolve_scale(y="independent")
        .properties(
            title=alt.TitleParams(
                f"Fuel mix by property type ({LATEST_YEAR})",
                subtitle=[
                    f"Natural gas is {gas_share:.0%} of all the energy these "
                    "buildings use,",
                    "and over 60% in multifamily housing, senior living and "
                    "K-12 schools.",
                ],
                anchor="start",
            )
        )
    )


save_chart(fuel_mix(latest_top), "5_fuel_mix")


# =============================================================================
# Chart 6: The same buildings over time
# =============================================================================


def same_building_trend(df, start=2018, end=2023):
    """
    Line chart of median energy use and emissions for the buildings that
    reported every year, indexed to the first year.

    Inputs: all-years DataFrame, and the first and last year to show.
    Output: an Altair chart.
    """
    metrics = {
        "site_eui_kbtu_sq_ft_": "Site EUI (energy used)",
        GHG_INTENSITY: "GHG intensity (emissions)",
    }
    d = df[df["data_year"].between(start, end)]
    wide = d.pivot_table(index="id", columns="data_year", values=list(metrics))
    ids = wide.dropna().index  # buildings with every metric in every year
    d = d[d["id"].isin(ids)]
    trend = (
        d.groupby("data_year")[list(metrics)].median().rename(columns=metrics)
    )
    trend = (
        (trend / trend.loc[start] * 100)
        .reset_index()
        .melt("data_year", var_name="measure", value_name="index")
    )

    base = alt.Chart(trend).encode(
        x=alt.X("data_year:O", title="Year", axis=alt.Axis(labelAngle=0)),
        y=alt.Y(
            "index:Q",
            title=f"Median, indexed ({start} = 100)",
            scale=alt.Scale(zero=False),
        ),
        color=alt.Color(
            "measure:N",
            title=None,
            scale=alt.Scale(
                domain=["Site EUI (energy used)", "GHG intensity (emissions)"],
                range=[DEEP_BLUE, STAR_RED],
            ),
        ),
    )
    lines = base.mark_line(point=True, strokeWidth=3).encode(
        tooltip=[
            alt.Tooltip("data_year:O", title="Year"),
            alt.Tooltip("measure:N", title="Measure"),
            alt.Tooltip("index:Q", title="Index", format=".1f"),
        ]
    )
    labels = (
        base.transform_filter(alt.datum.data_year == end)
        .mark_text(align="left", dx=8, fontSize=12)
        .encode(text=alt.Text("index:Q", format=".0f"))
    )
    ref = (
        alt.Chart(pd.DataFrame({"y": [100]}))
        .mark_rule(strokeDash=[4, 4], color="gray")
        .encode(y="y:Q")
    )
    return (ref + lines + labels).properties(
        width=CHART_WIDTH,
        height=LINE_CHART_HEIGHT,
        title=f"The same {len(ids):,} buildings from {start}–{end}",
    )


save_chart(same_building_trend(ALL_YEARS), "6_same_building_trend")


# =============================================================================
# Chart 7: Cumulative emissions curve
# =============================================================================


def pareto_curve(df, top_pct=10):
    """
    Cumulative share of emissions as buildings are added largest first.

    Inputs: latest-year DataFrame, and the percent of buildings to mark.
    Output: an Altair chart.
    """
    ghg = GHG_TOTAL
    cumulative = (
        df.dropna(subset=[ghg])
        .sort_values(ghg, ascending=False)
        .reset_index(drop=True)
    )
    cumulative["pct_buildings"] = (cumulative.index + 1) / len(cumulative) * 100
    cumulative["cum_pct_emissions"] = (
        cumulative[ghg].cumsum() / cumulative[ghg].sum() * 100
    )
    marker = cumulative.iloc[
        [(cumulative["pct_buildings"] - top_pct).abs().idxmin()]
    ].copy()
    marker["label"] = (
        f"Top {top_pct}% of buildings = "
        + marker["cum_pct_emissions"].round().astype(int).astype(str)
        + "% of emissions"
    )

    line = (
        alt.Chart(cumulative)
        .mark_line(color=STAR_RED, strokeWidth=3)
        .encode(
            x=alt.X(
                "pct_buildings:Q",
                title="% of buildings (largest emitters first)",
            ),
            y=alt.Y(
                "cum_pct_emissions:Q",
                title="Cumulative % of emissions",
                scale=alt.Scale(domain=[0, 100]),
            ),
        )
    )
    point = (
        alt.Chart(marker)
        .mark_point(size=150, filled=True, color="black")
        .encode(x="pct_buildings:Q", y="cum_pct_emissions:Q")
    )
    text = (
        alt.Chart(marker)
        .mark_text(align="left", dx=10, dy=15, fontSize=13)
        .encode(x="pct_buildings:Q", y="cum_pct_emissions:Q", text="label:N")
    )
    chart = (line + point + text).properties(
        width=CHART_WIDTH,
        height=LINE_CHART_HEIGHT,
        title=f"Pareto curve showing cumulative building emissions ({df['data_year'].max()})",
    )
    return chart


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
