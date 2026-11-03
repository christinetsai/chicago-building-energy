"""
final_graphs.py

Generates the charts for the Chicago building energy analysis and saves
them to static-viz/charts/.

Author: Christine Tsai

Usage: uv run python src/final_graphs.py
"""

import pandas as pd
import altair as alt
import janitor  # noqa: F401  (registers DataFrame.clean_names)
import requests
import json
from pathlib import Path
import numpy as np

from categories import SHORT_TYPE_NAMES, add_category_column
from constants import (
    CHART_HEIGHT,
    CHART_WIDTH,
    DATA_DIR,
    FUEL_COLS,
    GEOJSON_URL,
    GHG_INTENSITY,
    DOWNLOAD_TIMEOUT,
    GHG_TOTAL,
    LABEL_FONT_SIZE,
    LABEL_GAP,
    LINE_CHART_HEIGHT,
    LINE_WIDTH,
    MILLION,
    OUTPUT_DIR,
    PANEL_ROW_HEIGHT,
    PRIORITY_HEIGHT,
    PRIORITY_WIDTH,
    REFERENCE_DASH,
    ONE_STAR_RATING,
    SECTOR_VALUE,
    THOUSAND,
)
from theme import (
    AMBER,
    DEEP_BLUE,
    FLAG_BLUE,
    FLAME,
    GRAY,
    GRID,
    INK,
    MUTED,
    ONE_STAR_COLOR,
    STAR_RED,
    apply_theme,
)

# =============================================================================
# SETUP
# Helper for saving charts
# =============================================================================


def save_chart(chart, name, scale_factor=1.0):
    """
    Save a chart as a PNG in the output folder.

    Inputs: an Altair chart, a file name without extension, and the PNG
        resolution multiplier.
    Output: none (writes one file).
    """
    chart.save(OUTPUT_DIR / f"{name}.png", scale_factor=scale_factor)


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
        clean_df["community_area"].str.replace("'", "", regex=False).str.title()
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
    r = requests.get(GEOJSON_URL, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    gj = r.json()
    if "features" not in gj:
        raise ValueError(
            f"Unexpected response from {GEOJSON_URL}: {str(gj)[:200]}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(gj))
    return gj


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
SECTOR_LEGEND_COLUMNS = 2
SECTOR_AXIS_LABEL_LIMIT = 240  # Pixels
TOTAL_LABEL_GAP = 5  # Pixels between a bar and its total


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
        axis=alt.Axis(labelLimit=SECTOR_AXIS_LABEL_LIMIT),
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
                legend=alt.Legend(
                    orient="bottom", columns=SECTOR_LEGEND_COLUMNS
                ),
            ),
            order=alt.Order("subsector_rank:Q"),
        )
    )
    segment_labels = (
        alt.Chart(labeled_segments)
        .mark_text(color="white", fontSize=LABEL_FONT_SIZE, fontWeight="bold")
        .encode(
            y=y_rows,
            x=alt.X("segment_middle:Q"),
            text=alt.Text(f"{SECTOR_VALUE}:Q", format=".2f"),
        )
    )
    total_labels = (
        alt.Chart(totals)
        .mark_text(
            align="left",
            dx=TOTAL_LABEL_GAP,
            fontSize=LABEL_FONT_SIZE,
            color=INK,
        )
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
MAP_LABEL_SIZE = 11
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


def make_city_layer(geojson):
    """
    Build the light community-area shapes that outline the city.

    Inputs: the community area GeoJSON.
    Output: an Altair geoshape chart.
    """
    return alt.Chart(alt.Data(values=geojson["features"])).mark_geoshape(
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
            align=align, fontSize=MAP_LABEL_SIZE, color=MUTED, dy=LABEL_OFFSET
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


def summarize_community_areas(df, geojson):
    """
    Count the reporting buildings in each community area, and the share of
    the rated ones that are poorly rated (1 star).

    Inputs: latest-year DataFrame of reporting buildings, and the community
        area GeoJSON.
    Output: a DataFrame with one row per community area: "community_area",
        "buildings", "rated", "one_star", "one_star_share", "longitude",
        "latitude", and "is_small" (True when there are too few buildings to
        compare).
    Errors: raises ValueError if an area has no position on the map.
    """
    rating = df["chicago_energy_rating"]
    counts = pd.DataFrame(
        {
            "community_area": df["community_area"],
            "rated": rating > 0,
            "one_star": rating == ONE_STAR_RATING,
        }
    )
    areas = counts.groupby("community_area").agg(
        buildings=("rated", "size"),
        rated=("rated", "sum"),
        one_star=("one_star", "sum"),
    )
    areas = areas.reset_index().merge(
        calculate_area_centers(geojson), on="community_area", how="left"
    )
    unplaced = areas.loc[areas["longitude"].isna(), "community_area"]
    if not unplaced.empty:
        raise ValueError(f"No map position for: {', '.join(unplaced)}")
    areas["one_star_share"] = areas["one_star"] / areas["rated"]
    areas["is_small"] = areas["buildings"] < MIN_AREA_BUILDINGS
    return areas


def make_bubble_map(df, geojson):
    """
    Map the reporting buildings by community area: circle size shows how many
    buildings there are, and color shows the share that are poorly rated.
    Areas with few buildings are hollow gray circles because their shares
    are not reliable.

    Inputs: latest-year DataFrame of reporting buildings, and the community
        area GeoJSON.
    Output: an Altair chart.
    """
    areas = summarize_community_areas(df, geojson)
    year = df["data_year"].max()
    city_share = areas["one_star"].sum() / areas["rated"].sum()
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
                "one_star_share:Q",
                scale=alt.Scale(
                    domain=[SHARE_SCALE_MIN, city_share, SHARE_SCALE_MAX],
                    range=[SHARE_LOW_COLOR, SHARE_MID_COLOR, ONE_STAR_COLOR],
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
        (make_city_layer(geojson) + shaded + small + make_label_layer())
        .project("mercator", center=MAP_CENTER, scale=MAP_SCALE)
        .properties(
            width=MAP_WIDTH,
            height=MAP_HEIGHT,
            title=alt.TitleParams(
                f"Reporting buildings by community area ({year})",
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


# =============================================================================
# Chart 3: The same buildings over time
# =============================================================================


# Column with each building's floor area
AREA_COLUMN = "gross_floor_area_buildings_sq_ft_"
LABEL_NUDGE = 9  # Pixels between the end labels of lines that nearly overlap
END_LABEL_GAP = 8  # Pixels between a line's end and its label
TREND_LEGEND_COLUMNS = 1
TREND_LEGEND_LABEL_LIMIT = 400  # Pixels
SOLID_DASH = [1, 0]  # A dash pattern that draws a solid line
HYPOTHETICAL_DASH = [6, 4]
# A paler red than the emissions line
HYPOTHETICAL_EMISSIONS_COLOR = "#EE8B98"


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


def calculate_same_building_trend(df, start, end):
    """
    For the buildings that reported every year, find the median building's
    energy use per square foot, emissions per square foot, and emissions per
    square foot with the emission factors held at their first-year level.
    Each building is compared with its own first-year value, and each
    number is the median of those percentages.

    Inputs: all-years DataFrame, and the first and last year.
    Output: a tuple of a DataFrame of percentages with one row per year and
        columns "energy", "emissions" and "fixed", and the Index of the
        buildings used.
    """
    metrics = {"site_eui_kbtu_sq_ft_": "energy", GHG_INTENSITY: "emissions"}
    d = df[df["data_year"].between(start, end)]
    wide = d.pivot_table(index="id", columns="data_year", values=list(metrics))
    ids = wide.dropna().index  # buildings with every metric in every year
    wide = wide.loc[ids]

    trend = pd.DataFrame(
        {
            name: (wide[column].div(wide[column][start], axis=0) * 100).median()
            for column, name in metrics.items()
        }
    )
    held = calculate_fixed_factor_intensity(d[d["id"].isin(ids)], start)
    held = held.where(held[start] > 0)
    trend["fixed"] = (held.div(held[start], axis=0) * 100).median()
    return trend, ids


def make_trend_chart(df, start=2018, end=2023):
    """
    Line chart of how the median building's energy use and emissions
    changed, for the buildings that reported every year. A dashed line shows
    what emissions would have been if the emission factors had stayed at
    their first-year level, which separates a cleaner grid from changes in
    the buildings.

    Inputs: all-years DataFrame, and the first and last year to show.
    Output: an Altair chart.
    """
    energy = "Energy used per square foot"
    emissions = "Emissions per square foot"
    fixed = "Emissions with the grid at its 2018 level"
    trend, ids = calculate_same_building_trend(df, start, end)
    trend = trend.rename(
        columns={"energy": energy, "emissions": emissions, "fixed": fixed}
    )
    trend = trend.reset_index().melt(
        "data_year", var_name="measure", value_name="index"
    )

    # One legend for color and dashes, with line symbols so the hypothetical
    # line shows as dashes
    legend = alt.Legend(
        orient="top",
        columns=TREND_LEGEND_COLUMNS,
        labelLimit=TREND_LEGEND_LABEL_LIMIT,
        symbolType="stroke",
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
                range=[SOLID_DASH, SOLID_DASH, HYPOTHETICAL_DASH],
            ),
            legend=legend,
        ),
    )
    lines = base.mark_line(point=True, strokeWidth=LINE_WIDTH).encode(
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
            .mark_text(
                align="left",
                dx=END_LABEL_GAP,
                dy=offset,
                fontSize=LABEL_FONT_SIZE,
            )
            .encode(text=alt.Text("index:Q", format=".0f"))
            for measure, offset in label_offsets.items()
        ]
    )
    ref = (
        alt.Chart(pd.DataFrame({"y": [100]}))
        .mark_rule(strokeDash=REFERENCE_DASH, color="gray")
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


# =============================================================================
# Chart 4: Fuel mix of all reporting buildings
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
DONUT_TITLE_SIZE = 14


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
        title=alt.TitleParams(
            title, anchor="middle", fontSize=DONUT_TITLE_SIZE
        ),
    )


def make_fuel_donuts(df):
    """
    Two donuts side by side: fuel shares of energy used and of emissions.

    Inputs: latest-year DataFrame of reporting buildings.
    Output: an Altair chart.
    """
    shares = summarize_fuel_use(df)
    year = df["data_year"].max()
    energy_donut = make_donut(
        shares, "Energy used", "Share of energy used", True
    )
    emissions_donut = make_donut(
        shares, "Emissions", "Share of emissions", False
    )
    return (
        alt.hconcat(energy_donut, emissions_donut)
        .resolve_scale(color="shared")
        .properties(
            title=alt.TitleParams(
                f"Fuel mix of Chicago's reporting buildings ({year})",
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


# =============================================================================
# Chart 5: Total emissions by property type
# =============================================================================

# Types shown, and how many top bars are highlighted
TOP_TYPES_SHOWN = 15
HIGHLIGHT_COUNT = 2
HIGHLIGHT_BAR_COLOR = DEEP_BLUE
OTHER_BAR_COLOR = "#B8C4D0"
AVERAGE_PANEL_WIDTH = 240  # Pixels
LABEL_ROOM = 1.12  # Axis extends past the longest bar for its label
HIDDEN = 0  # Opacity of the layer that only draws the top axis

# Tons of CO2e per gasoline car per year (EPA Equivalencies Calculator)
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


def make_type_totals_chart(df):
    """
    Total emissions (left) and average emissions per building (right) for the
    highest-emitting property types, so total = buildings x average.

    Inputs: latest-year DataFrame (all property types).
    Output: an Altair chart.
    """
    year = df["data_year"].max()
    property_type = (
        df.groupby("primary_property_type")
        .agg(
            total_ghg=(GHG_TOTAL, "sum"),
            buildings=(GHG_TOTAL, "count"),
        )
        .reset_index()
        .nlargest(TOP_TYPES_SHOWN, "total_ghg")
    )
    share_of_total = property_type["total_ghg"].sum() / df[GHG_TOTAL].sum()
    property_type["average_ghg"] = (
        property_type["total_ghg"] / property_type["buildings"]
    )
    property_type["type_label"] = property_type[
        "primary_property_type"
    ].replace(SHORT_TYPE_NAMES)
    # Axis labels include the building count
    property_type["axis_label"] = (
        property_type["type_label"]
        + " ("
        + property_type["buildings"].map("{:,}".format)
        + ")"
    )
    property_type["highlight"] = (
        property_type["total_ghg"].rank(ascending=False) <= HIGHLIGHT_COUNT
    )
    property_type["label"] = property_type["total_ghg"].map(format_compact_tons)
    property_type["average_label"] = property_type["average_ghg"].map(
        "{:,.0f}".format
    )
    property_type["cars"] = property_type["total_ghg"] / TONS_CO2E_PER_CAR_YEAR
    property_type["average_cars"] = (
        property_type["average_ghg"] / TONS_CO2E_PER_CAR_YEAR
    )

    # Both panels list types by total, largest first
    type_order = property_type.sort_values("total_ghg", ascending=False)[
        "axis_label"
    ].tolist()
    bar_color = alt.condition(
        alt.datum.highlight,
        alt.value(HIGHLIGHT_BAR_COLOR),
        alt.value(OTHER_BAR_COLOR),
    )

    def make_panel(value, label, bar_title, cars, panel_width, show_types):
        """
        Build one panel: bars, labels, and a top axis in equivalent cars.
        """
        # Leave room past the longest bar for its label
        axis_max = property_type[value].max() * LABEL_ROOM
        scale = alt.Scale(domain=[0, axis_max])
        # Only the left panel names the types
        y_options = {} if show_types else {"axis": None}
        y = alt.Y("axis_label:N", sort=type_order, title=None, **y_options)
        bars = (
            alt.Chart(property_type)
            .mark_bar()
            .encode(
                x=alt.X(
                    f"{value}:Q",
                    title=bar_title,
                    axis=alt.Axis(format="~s"),
                    scale=scale,
                ),
                y=y,
                color=bar_color,
            )
        )
        labels = (
            alt.Chart(property_type)
            .mark_text(
                align="left", dx=LABEL_GAP, fontSize=LABEL_FONT_SIZE, color=INK
            )
            .encode(
                x=alt.X(f"{value}:Q", scale=scale, axis=None),
                y=alt.Y("axis_label:N", sort=type_order, **y_options),
                text=f"{label}:N",
            )
        )
        cars_axis = (
            alt.Chart(property_type)
            .mark_point(opacity=HIDDEN)
            .encode(
                x=alt.X(
                    f"{cars}:Q",
                    title="Equivalent cars driven for a year (EPA)",
                    axis=alt.Axis(orient="top", format="~s"),
                    scale=alt.Scale(
                        domain=[0, axis_max / TONS_CO2E_PER_CAR_YEAR]
                    ),
                ),
                y=alt.Y("axis_label:N", sort=type_order, **y_options),
            )
        )
        return (
            alt.layer(bars, labels, cars_axis)
            .resolve_scale(x="independent")
            .properties(width=panel_width, height=CHART_HEIGHT)
        )

    total_panel = make_panel(
        "total_ghg",
        "label",
        "Total emissions (metric tons per year)",
        "cars",
        CHART_WIDTH,
        show_types=True,
    )
    average_panel = make_panel(
        "average_ghg",
        "average_label",
        "Average per building (metric tons per year)",
        "average_cars",
        AVERAGE_PANEL_WIDTH,
        show_types=False,
    )
    return alt.hconcat(total_panel, average_panel).properties(
        title=alt.TitleParams(
            f"Total and average emissions by property type ({year})",
            subtitle=[
                f"{TOP_TYPES_SHOWN} building types account for "
                f"{share_of_total:.0%} of emissions from reported buildings.",
                "Counts in parentheses show how many buildings each type has.",
            ],
            anchor="start",
        )
    )


# =============================================================================
# Chart 6: Emissions per square foot by property type (box plot)
# =============================================================================

# Types shown: the largest by total emissions, plus any type with enough
# buildings that is much more intense than the city as a whole
BOX_LARGEST_TYPES = 7
MIN_INTENSE_BUILDINGS = 5
INTENSE_MULTIPLE = 3  # Intense: median at least this times the city's
BOX_THICKNESS = 14  # Pixels
BOX_OTHER_COLOR = "#A9B8C8"
BOX_WHISKER_REACH = 1.5  # Whiskers stop within this many box lengths
MEDIAN_LINE_COLOR = "white"
MEDIAN_LINE_WIDTH = 2
REFERENCE_LINE_WIDTH = 1.5
REFERENCE_LINE_DASH = [5, 4]
REFERENCE_LABEL_SIZE = 12


def make_type_box_plot(df):
    """
    Box plot of emissions per square foot for the BOX_LARGEST_TYPES types
    with the most total emissions, plus the intense types (median at least
    INTENSE_MULTIPLE times the city's, with MIN_INTENSE_BUILDINGS or more
    buildings). Types are sorted by median, and the intense ones are dark.
    A dashed line marks the city's median. Outliers are not shown.

    Inputs: latest-year DataFrame of reporting buildings.
    Output: an Altair chart.
    """
    year = df["data_year"].max()
    city_median = df[GHG_INTENSITY].median()
    type_stats = df.groupby("type_label", observed=True).agg(
        total=(GHG_TOTAL, "sum"),
        median=(GHG_INTENSITY, "median"),
        buildings=(GHG_INTENSITY, "count"),
    )
    type_stats["intense"] = (
        type_stats["median"] >= INTENSE_MULTIPLE * city_median
    )
    largest = type_stats["total"].nlargest(BOX_LARGEST_TYPES).index
    intense = type_stats.index[
        type_stats["intense"]
        & (type_stats["buildings"] >= MIN_INTENSE_BUILDINGS)
    ]
    type_stats = type_stats.loc[largest.union(intense)]
    type_stats["axis_label"] = (
        type_stats.index.astype(str)
        + " ("
        + type_stats["buildings"].map("{:,}".format)
        + ")"
    )
    type_order = type_stats.sort_values("median", ascending=False)[
        "axis_label"
    ].tolist()

    d = df[df["type_label"].isin(type_stats.index)].dropna(
        subset=[GHG_INTENSITY]
    )
    d = d.assign(
        axis_label=d["type_label"].map(type_stats["axis_label"]),
        intense=d["type_label"].map(type_stats["intense"]),
    )

    boxes = (
        alt.Chart(d)
        .mark_boxplot(
            extent=BOX_WHISKER_REACH,
            size=BOX_THICKNESS,
            outliers=False,
            median=alt.MarkConfig(
                color=MEDIAN_LINE_COLOR, strokeWidth=MEDIAN_LINE_WIDTH
            ),
            rule=alt.MarkConfig(color=MUTED),
        )
        .encode(
            x=alt.X(
                f"{GHG_INTENSITY}:Q",
                title="Emissions per square foot (kg CO2e / sq ft)",
            ),
            y=alt.Y("axis_label:N", title=None, sort=type_order),
            color=alt.Color(
                "intense:N",
                scale=alt.Scale(
                    domain=[True, False],
                    range=[HIGHLIGHT_BAR_COLOR, BOX_OTHER_COLOR],
                ),
                legend=None,
            ),
        )
    )
    reference = pd.DataFrame(
        {
            "x": [city_median],
            "label": [f"All buildings: median {city_median:.1f}"],
        }
    )
    reference_line = (
        alt.Chart(reference)
        .mark_rule(
            color=MUTED,
            strokeWidth=REFERENCE_LINE_WIDTH,
            strokeDash=REFERENCE_LINE_DASH,
        )
        .encode(x="x:Q")
    )
    reference_label = (
        alt.Chart(reference)
        .mark_text(
            align="left",
            baseline="bottom",
            dx=LABEL_GAP,
            fontSize=REFERENCE_LABEL_SIZE,
            color=MUTED,
        )
        .encode(x="x:Q", y=alt.value(0), text="label:N")
    )
    return (reference_line + boxes + reference_label).properties(
        width=CHART_WIDTH,
        height=alt.Step(PANEL_ROW_HEIGHT),
        title=alt.TitleParams(
            f"Emissions per square foot by property type ({year})",
            subtitle=[
                "Boxes show the middle half of buildings; the white line is "
                "the median.",
                f"Dark boxes: median at least {INTENSE_MULTIPLE} times the "
                "median of all buildings. Number of buildings in parentheses.",
            ],
            anchor="start",
        ),
    )


# =============================================================================
# Chart 7: Cumulative emissions curve
# =============================================================================


# Shares of buildings that are marked on the curve
MARK_PERCENTS = [1, 5, 10]
PERCENT_RANGE = [0, 100]
MARKER_SIZE = 100  # Square pixels
MARKER_LABEL_DX = 10  # Pixels
MARKER_LABEL_DY = 14


def calculate_cumulative_emissions(df):
    """
    Order the buildings from largest to smallest emissions and find the
    share of all emissions that the buildings so far produce.

    Inputs: latest-year DataFrame.
    Output: a DataFrame with one row per building, largest first, with
        added columns "pct_buildings" and "cum_pct_emissions".
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
    return cumulative


def calculate_pareto_marks(cumulative):
    """
    Find the point on the curve for each share of buildings in
    MARK_PERCENTS.

    Inputs: the DataFrame from calculate_cumulative_emissions.
    Output: a DataFrame with one row per mark: "percent", "buildings",
        "pct_buildings" and "cum_pct_emissions".
    """
    marks = []
    for percent in MARK_PERCENTS:
        buildings = round(len(cumulative) * percent / 100)
        row = cumulative.iloc[buildings - 1]
        marks.append(
            {
                "percent": percent,
                "buildings": buildings,
                "pct_buildings": row["pct_buildings"],
                "cum_pct_emissions": row["cum_pct_emissions"],
            }
        )
    return pd.DataFrame(marks)


def make_pareto_chart(df):
    """
    Cumulative share of emissions as buildings are added largest first,
    with the top 1%, 5% and 10% of buildings marked.

    Inputs: latest-year DataFrame.
    Output: an Altair chart.
    """
    cumulative = calculate_cumulative_emissions(df)
    building_count = len(cumulative)

    # One marked point for each share of buildings, labeled with the number
    # of buildings and the share of emissions they produce
    marks = calculate_pareto_marks(cumulative)
    marks["label"] = (
        "Top "
        + marks["percent"].astype(str)
        + "% ("
        + marks["buildings"].map("{:,}".format)
        + " buildings) = "
        + marks["cum_pct_emissions"].map("{:.0f}".format)
        + "% of emissions"
    )

    line = (
        alt.Chart(cumulative)
        .mark_line(color=STAR_RED, strokeWidth=LINE_WIDTH)
        .encode(
            x=alt.X(
                "pct_buildings:Q",
                title="Share of buildings, largest emitters first",
                axis=alt.Axis(labelExpr="datum.value + '%'"),
            ),
            y=alt.Y(
                "cum_pct_emissions:Q",
                title="Share of total emissions (running total)",
                scale=alt.Scale(domain=PERCENT_RANGE),
                axis=alt.Axis(labelExpr="datum.value + '%'"),
            ),
        )
    )
    points = (
        alt.Chart(marks)
        .mark_point(size=MARKER_SIZE, filled=True, color="black")
        .encode(x="pct_buildings:Q", y="cum_pct_emissions:Q")
    )
    labels = (
        alt.Chart(marks)
        .mark_text(
            align="left",
            dx=MARKER_LABEL_DX,
            dy=MARKER_LABEL_DY,
            fontSize=LABEL_FONT_SIZE,
        )
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


# =============================================================================
# Chart 8: Priority buildings
# =============================================================================

# Share of rated buildings counted as top emitters, and buildings named
PRIORITY_TOP_SHARE = 0.10
PRIORITY_LABEL_COUNT = 5
CUT_LABEL_SIZE = 11
CUT_LABEL_OFFSET = -8  # Pixels above the cutoff line
CUT_LABEL_X = 5  # Pixels from the left edge
NAME_LABEL_SIZE = 10
NAME_LABEL_GAP = 8  # Pixels between a dot and its name

# Dot colors: top emitters (amber) and poorly rated buildings (red, as on the
# map) overlap in a dark crimson
PRIORITY_BOTH_COLOR = "#7A0A24"
OTHER_DOTS_COLOR = "#d9d9d9"
OUTLINE_COLOR = "white"
BOTH_OUTLINE_COLOR = "#4D0516"
OUTLINE_WIDTH = 0.3
BOTH_OUTLINE_WIDTH = 0.5

# Highlighted dots are larger and more opaque than the other buildings
GROUP_DOT_SIZE = 70  # Square pixels
OTHER_DOT_SIZE = 25
GROUP_OPACITY = 0.9
OTHER_OPACITY = 0.5

# Both axes are logarithmic, trimmed to the data, with gridlines at 1, 2 and 5
# times each power of 10. Powers of 10 get a darker line.
INTENSITY_RANGE = [0.5, 200]
EMISSIONS_RANGE = [50, 120000]
MAJOR_GRIDLINE_COLOR = "#B8C0C8"
MINOR_GRIDLINE_COLOR = GRID


def make_log_ticks(low, high):
    """
    Find the 1-2-5 gridline values of a log axis.

    Inputs: the lowest and highest values on the axis.
    Output: a tuple of all tick values, and the powers of 10 among them.
    """
    ticks = [
        step * 10**power
        for power in range(-1, 6)
        for step in (1, 2, 5)
        if low <= step * 10**power <= high
    ]
    return ticks, [t for t in ticks if t in (1, 10, 100, 1000, 10000, 100000)]


def make_axis(title, low, high):
    """
    Build a log axis with 1-2-5 gridlines and darker lines at powers of 10.

    Inputs: the axis title and its lowest and highest values.
    Output: an Altair Axis.
    """
    ticks, major_ticks = make_log_ticks(low, high)
    return alt.Axis(
        title=title,
        values=ticks,
        format=",",
        gridColor={
            "condition": {
                "test": f"indexof({major_ticks}, datum.value) >= 0",
                "value": MAJOR_GRIDLINE_COLOR,
            },
            "value": MINOR_GRIDLINE_COLOR,
        },
    )


def select_priority_buildings(df):
    """
    Flag the top emitters and the poorly rated buildings among the rated
    buildings that have emissions.

    Inputs: latest-year DataFrame.
    Output: a tuple of the DataFrame of those buildings with added "is_top"
        and "is_one_star" columns, and the emissions cutoff (metric tons) for a
        top emitter.
    """
    d = df.dropna(subset=[GHG_TOTAL, GHG_INTENSITY, "chicago_energy_rating"])
    d = d[(d[GHG_TOTAL] > 0) & (d[GHG_INTENSITY] > 0)]
    cutoff = d[GHG_TOTAL].quantile(1 - PRIORITY_TOP_SHARE)
    d = d.assign(
        is_top=d[GHG_TOTAL] >= cutoff,
        is_one_star=d["chicago_energy_rating"] == ONE_STAR_RATING,
    )
    return d, cutoff


def make_priority_scatter(df):
    """
    Scatter of emissions per square foot against total emissions, highlighting
    the top emitters (top PRIORITY_TOP_SHARE by total), the poorly rated
    buildings, and the buildings that are both. The largest of the last group
    are named.

    Inputs: latest-year DataFrame.
    Output: an Altair chart.
    """
    d, cutoff = select_priority_buildings(df)
    group = np.select(
        [d["is_top"] & d["is_one_star"], d["is_top"], d["is_one_star"]],
        ["Both", "Top emitter only", "Poorly rated only"],
        default="Other buildings",
    )
    counts = pd.Series(group).value_counts()

    # Legend names show how many buildings are in each group. The groups are
    # drawn in the order below, so the highlighted ones sit on top.
    draw_order = [
        "Other buildings",
        "Poorly rated only",
        "Top emitter only",
        "Both",
    ]
    legend_names = {
        name: f"{name} ({counts[name]:,})"
        for name in ("Top emitter only", "Poorly rated only", "Both")
    }
    legend_names["Other buildings"] = "All other buildings"
    d = d.assign(
        group=pd.Series(group, index=d.index).map(legend_names),
        layer=[draw_order.index(g) for g in group],
        highlighted=group != "Other buildings",
    )
    names = list(legend_names.values())
    both_name = legend_names["Both"]

    # Every layer must use these same scales, or the layers' own default
    # scales would widen the axes back out
    intensity_scale = alt.Scale(type="log", domain=INTENSITY_RANGE)
    emissions_scale = alt.Scale(type="log", domain=EMISSIONS_RANGE)

    def highlight_scale(other, highlighted):
        return alt.Scale(
            type="ordinal", domain=[False, True], range=[other, highlighted]
        )

    dots = (
        alt.Chart(d)
        .mark_circle()
        .encode(
            x=alt.X(
                f"{GHG_INTENSITY}:Q",
                scale=intensity_scale,
                axis=make_axis(
                    "Emissions per square foot (kg CO2e / sq ft, log scale)",
                    *INTENSITY_RANGE,
                ),
            ),
            y=alt.Y(
                f"{GHG_TOTAL}:Q",
                scale=emissions_scale,
                axis=make_axis(
                    "Total emissions per year (metric tons CO2e, log scale)",
                    *EMISSIONS_RANGE,
                ),
            ),
            color=alt.Color(
                "group:N",
                title=None,
                sort=names,
                scale=alt.Scale(
                    domain=names,
                    range=[
                        AMBER,
                        ONE_STAR_COLOR,
                        PRIORITY_BOTH_COLOR,
                        OTHER_DOTS_COLOR,
                    ],
                ),
            ),
            size=alt.Size(
                "highlighted:N",
                scale=highlight_scale(OTHER_DOT_SIZE, GROUP_DOT_SIZE),
                legend=None,
            ),
            opacity=alt.Opacity(
                "highlighted:N",
                scale=highlight_scale(OTHER_OPACITY, GROUP_OPACITY),
                legend=None,
            ),
            # The overlap dots get a darker, slightly thicker edge
            stroke=alt.condition(
                alt.datum.group == both_name,
                alt.value(BOTH_OUTLINE_COLOR),
                alt.value(OUTLINE_COLOR),
            ),
            strokeWidth=alt.condition(
                alt.datum.group == both_name,
                alt.value(BOTH_OUTLINE_WIDTH),
                alt.value(OUTLINE_WIDTH),
            ),
            order=alt.Order("layer:Q"),
        )
    )

    # Dashed line (and its label) where the top emitters begin
    cut_label = f"Top {PRIORITY_TOP_SHARE:.0%} start at {cutoff:,.0f} tons"
    cut = pd.DataFrame({"y": [cutoff], "text": [cut_label]})
    cut_y = alt.Y("y:Q", scale=emissions_scale)
    cut_line = (
        alt.Chart(cut)
        .mark_rule(strokeDash=REFERENCE_DASH, color="gray")
        .encode(y=cut_y)
    )
    cut_text = (
        alt.Chart(cut)
        .mark_text(
            align="left",
            dy=CUT_LABEL_OFFSET,
            dx=LABEL_GAP,
            fontSize=CUT_LABEL_SIZE,
            color="gray",
        )
        .encode(y=cut_y, text="text:N", x=alt.value(CUT_LABEL_X))
    )

    # Name the largest buildings in both groups, alternating sides so that
    # neighboring labels do not run into each other. A name that is only a
    # number is replaced by the address.
    largest = d[d["group"] == both_name].nlargest(
        PRIORITY_LABEL_COUNT, GHG_TOTAL
    )
    largest = largest.assign(
        label=[
            address if str(name).strip().isdigit() else name
            for name, address in zip(
                largest["property_name"], largest["address"]
            )
        ]
    )
    name_labels = [
        alt.Chart(largest.iloc[start::2])
        .mark_text(align=align, dx=dx, fontSize=NAME_LABEL_SIZE)
        .encode(
            x=alt.X(f"{GHG_INTENSITY}:Q", scale=intensity_scale),
            y=alt.Y(f"{GHG_TOTAL}:Q", scale=emissions_scale),
            text="label:N",
        )
        for start, align, dx in (
            (0, "left", NAME_LABEL_GAP),
            (1, "right", -NAME_LABEL_GAP),
        )
    ]

    return alt.layer(dots, cut_line, cut_text, *name_labels).properties(
        width=PRIORITY_WIDTH,
        height=PRIORITY_HEIGHT,
        title=alt.TitleParams(
            "Emissions per square foot against total emissions, by building",
            subtitle=[
                f"Top emitters: the {PRIORITY_TOP_SHARE:.0%} of rated "
                "buildings with the most emissions.",
                f"Poorly rated: 1 star. Named dots: the "
                f"{PRIORITY_LABEL_COUNT} largest of the {counts['Both']}.",
                "Both axes use a log scale: each darker gridline is 10 times "
                "the one before.",
            ],
            anchor="start",
        ),
    )


# =============================================================================
# Chart 9: Emissions above the typical building of each property type
# =============================================================================

# Types with fewer buildings than this are too small to judge, so their
# buildings are not counted as above typical
PEER_MIN_BUILDINGS = 10
# A building is "high for its type" when its emissions per square foot are in
# the top quarter of its property type
HIGH_FOR_TYPE_PERCENTILE = 0.75
REDUCTION_TYPES_SHOWN = 8
REDUCTION_HIGHLIGHT_COUNT = 2
REDUCTION_LABEL_ROOM = 1.25  # Axis extends past the longest bar for its label
REDUCTION_LABEL_SIZE = 13
REDUCTION_AXIS_LABEL_LIMIT = 300  # Pixels


def calculate_excess_emissions(d):
    """
    Find the tons each building emits above what it would emit at the median
    emissions per square foot of its property type. Buildings at or below
    the median, and buildings in types with fewer than PEER_MIN_BUILDINGS
    buildings, get 0.

    Inputs: DataFrame from select_priority_buildings.
    Output: a Series of tons, with the same index as the DataFrame.
    """
    by_type = d.groupby("primary_property_type")
    big_enough = by_type[GHG_TOTAL].transform("count") >= PEER_MIN_BUILDINGS
    type_median = by_type[GHG_INTENSITY].transform("median")
    excess = d[GHG_TOTAL] * (1 - type_median / d[GHG_INTENSITY])
    return excess.where(big_enough, 0).clip(lower=0)


def select_high_for_type(d):
    """
    Find the priority buildings (top emitters that are poorly rated) that
    are in the top quarter of their property type for emissions per square
    foot. Types with fewer than PEER_MIN_BUILDINGS buildings are skipped.

    Inputs: DataFrame from select_priority_buildings.
    Output: the DataFrame of those buildings.
    """
    by_type = d.groupby("primary_property_type")
    big_enough = by_type[GHG_TOTAL].transform("count") >= PEER_MIN_BUILDINGS
    percentile = by_type[GHG_INTENSITY].rank(pct=True).where(big_enough)
    both = d[d["is_top"] & d["is_one_star"]]
    return both[percentile[both.index] >= HIGH_FOR_TYPE_PERCENTILE]


def make_reduction_chart(df):
    """
    Bars of the emissions that would be cut if buildings came down to the
    median emissions per square foot of their property type: one bar for
    each of the REDUCTION_TYPES_SHOWN types with the most to cut, and one for
    the priority buildings of Figure 8 that are high for their type (which
    are also counted in their types). Each label shows how many buildings
    would have to change.

    Inputs: latest-year DataFrame.
    Output: an Altair chart.
    """
    d, _ = select_priority_buildings(df)
    d = d.assign(excess=calculate_excess_emissions(d))
    by_type = d.groupby("type_label", observed=True)["excess"].agg(
        tons="sum", buildings=lambda excess: (excess > 0).sum()
    )
    by_type = by_type.nlargest(REDUCTION_TYPES_SHOWN, "tons")
    priority = d.loc[select_high_for_type(d).index]
    priority_name = "Priority buildings high for type"

    # Types first, then an empty row that separates the priority buildings
    rows = pd.DataFrame(
        {
            "name": [*by_type.index, SPACER_ROW, priority_name],
            "tons": [*by_type["tons"], np.nan, priority["excess"].sum()],
            "buildings": [*by_type["buildings"], 0, len(priority)],
        }
    )
    rows["row"] = rows["name"] + rows["buildings"].map(
        " ({:,} buildings)".format
    )
    rows.loc[rows["name"] == SPACER_ROW, "row"] = SPACER_ROW
    rows["label"] = rows["tons"].map(lambda t: f"{format_compact_tons(t)} tons")
    rows.loc[rows["name"] == SPACER_ROW, "label"] = ""
    rows["fill"] = OTHER_BAR_COLOR
    rows.loc[: REDUCTION_HIGHLIGHT_COUNT - 1, "fill"] = HIGHLIGHT_BAR_COLOR
    rows.loc[rows["name"] == priority_name, "fill"] = PRIORITY_BOTH_COLOR

    base = alt.Chart(rows).encode(
        y=alt.Y(
            "row:N",
            sort=rows["row"].tolist(),
            title=None,
            axis=alt.Axis(labelLimit=REDUCTION_AXIS_LABEL_LIMIT),
        ),
        x=alt.X(
            "tons:Q",
            title="Tons of CO2e per year above the type's median",
            scale=alt.Scale(
                domain=[0, rows["tons"].max() * REDUCTION_LABEL_ROOM]
            ),
            axis=alt.Axis(format="~s"),
        ),
    )
    bars = base.mark_bar().encode(color=alt.Color("fill:N", scale=None))
    labels = base.mark_text(
        align="left", dx=LABEL_GAP, fontSize=REDUCTION_LABEL_SIZE
    ).encode(text="label:N")
    return (bars + labels).properties(
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        title=alt.TitleParams(
            "Emissions above the typical building of each property type",
            subtitle=[
                "Tons per year cut if each building above the median emissions "
                "per square foot of its",
                "property type came down to it. Parentheses: buildings that "
                "would change. The last bar is also counted above.",
            ],
            anchor="start",
        ),
    )


def main():
    """
    Load the data and save the nine charts to static-viz/charts/.

    Inputs: none (reads the files in data/).
    Output: none (writes nine PNG files).
    """
    apply_theme()
    alt.data_transformers.disable_max_rows()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    geojson = load_chicago_geojson()
    all_years = load_chicago_benchmarks()
    latest = all_years[all_years["data_year"] == all_years["data_year"].max()]

    save_chart(make_sector_chart(latest), "1_citywide_emissions_by_sector")
    save_chart(make_bubble_map(latest, geojson), "2_building_bubble_map")
    save_chart(make_trend_chart(all_years), "3_same_building_trend")
    save_chart(make_fuel_donuts(latest), "4_fuel_mix")
    save_chart(make_type_totals_chart(latest), "5_emissions_by_type")
    save_chart(make_type_box_plot(latest), "6_emissions_type_box")
    save_chart(make_pareto_chart(latest), "7_pareto_curve")
    save_chart(
        make_priority_scatter(latest), "8_priority_buildings", scale_factor=2.0
    )
    save_chart(make_reduction_chart(latest), "9_reduction_potential")


if __name__ == "__main__":
    main()
