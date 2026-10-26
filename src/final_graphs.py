"""
final_graphs.py

Generates the charts for the Chicago building energy analysis.

Usage: uv run python src/final_graphs.py
"""

import pandas as pd
import altair as alt
import janitor
import requests
import json
from pathlib import Path
import numpy as np

alt.data_transformers.disable_max_rows()

# Input and output folders relative to the repo root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "static-viz" / "charts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# Theme based off Chicago flag colors with energy adjacent accents (amber = electricity, flame = natural gas, green = clean energy)
FLAG_BLUE = "#41B6E6"
STAR_RED = "#E4002B"
DEEP_BLUE = "#1C7FB5"
AMBER = "#F5B700"
FLAME = "#F2792B"
GREEN = "#2E9E6B"
GRAY = "#8D99AE"
CHARCOAL = "#4A5568"
INK, MUTED, GRID = "#1B2A3A", "#6B7785", "#E6E9ED"

WARM_RANGE = ["#FFF6E0", "#FBD87A", "#F5A03A", "#E4572E", "#E4002B", "#7A0019"]
WARM_SCALE = alt.Scale(range=WARM_RANGE)
COOL_SCALE = alt.Scale(
    range=["#EAF7FD", "#BDE6F6", "#41B6E6", "#1C7FB5", "#0E4A73"]
)
STAR_SCALE = alt.Scale(
    domain=[0.0, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
    range=[
        "#8F0020",
        "#E4002B",
        "#EE7078",
        "#F6B3B8",
        "#B3DDF1",
        "#79C8EE",
        "#41B6E6",
        "#1C7FB5",
    ],
)
FUEL_SCALE = alt.Scale(
    domain=[
        "Natural gas",
        "Electricity",
        "District steam",
        "District chilled water",
        "Other fuel",
    ],
    range=[FLAME, FLAG_BLUE, GRAY, GREEN, "#0E4A73"],
)


@alt.theme.register("chi_bench_theme", enable=True)
def chi_bench_theme():
    return alt.theme.ThemeConfig(
        {
            "config": {
                "background": "#ffffff",
                "font": "Roboto, Helvetica, Arial, sans-serif",
                "title": {
                    "anchor": "start",
                    "fontSize": 18,
                    "fontWeight": "bold",
                    "color": INK,
                    "subtitleColor": MUTED,
                    "subtitleFontSize": 13,
                    "offset": 12,
                },
                "axis": {
                    "labelFontSize": 12,
                    "titleFontSize": 13,
                    "labelColor": INK,
                    "titleColor": INK,
                    "gridColor": GRID,
                    "domainColor": "#B8C0C8",
                    "tickColor": "#B8C0C8",
                },
                "legend": {
                    "labelFontSize": 12,
                    "titleFontSize": 13,
                    "labelColor": INK,
                    "titleColor": INK,
                    "symbolSize": 120,
                },
                "view": {"stroke": None},
                "range": {
                    "category": [
                        FLAG_BLUE,
                        STAR_RED,
                        AMBER,
                        GREEN,
                        FLAME,
                        GRAY,
                        DEEP_BLUE,
                        CHARCOAL,
                    ]
                },
            }
        }
    )


FUEL_COLS = {
    "electricity_use_kbtu_": "Electricity",
    "natural_gas_use_kbtu_": "Natural gas",
    "district_steam_use_kbtu_": "District steam",
    "district_chilled_water_use_kbtu_": "District chilled water",
    "all_other_fuel_use_kbtu_": "Other fuel",
}


def chi_bench_df():
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
        "total_ghg_emissions_metric_tons_co2e_",
        "ghg_intensity_kg_co2e_sq_ft_",
        *FUEL_COLS.keys(),
    ]:
        clean_df[c] = pd.to_numeric(clean_df[c], errors="coerce")
    return clean_df


# Chicago community areas geojson
GEOJSON_URL = "https://data.cityofchicago.org/resource/igwz-8jzy.geojson"


def load_chicago_geojson(path=DATA_DIR / "chicago_community_areas.geojson"):
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
LATEST_YEAR = chi_bench_df()["data_year"].max()
latest = chi_bench_df()[chi_bench_df()["data_year"] == LATEST_YEAR].copy()

# There are 45 different types of properties
# data centers are top 24 with count 5
type_counts = (
    latest["primary_property_type"]
    .value_counts()
    .rename_axis("primary_property_type")
    .reset_index(name="properties")
)

TOP_N_TYPES = 24
top_types = (
    latest["primary_property_type"]
    .value_counts()
    .head(TOP_N_TYPES)
    .index.tolist()
)
latest_top = latest[latest["primary_property_type"].isin(top_types)]


def building_dot_map(df):
    d = df.dropna(
        subset=["chicago_energy_rating"]
    )  # unrated buildings have no star color
    chart = (
        alt.Chart(d)
        .mark_circle(opacity=0.85, stroke="#6b7785", strokeWidth=0.4)
        .encode(
            longitude="longitude:Q",
            latitude="latitude:Q",
            size=alt.Size(
                "total_ghg_emissions_metric_tons_co2e_",
                scale=alt.Scale(range=[5, 60], type="sqrt"),
                title="Total GHG (tons)",
            ),
            color=alt.Color(
                "chicago_energy_rating:O", title="Stars", scale=STAR_SCALE
            ),
        )
        .project("mercator", center=[-87.68, 41.84], scale=62000)
        .properties(
            width=500, height=600, title="Buildings by emissions and rating"
        )
    )

    return chart


building_dot_map(latest_top).save(OUTPUT_DIR / "1_building_dot_map.png")


def building_choropleth(df, metric):
    community_area = (
        df.assign(
            ca_key=df["community_area"].astype(str).str.upper().str.strip()
        )
        .groupby("ca_key")
        .agg(
            count=("id", "count"),
            median=("#_of_buildings", "median"),
            sum=("#_of_buildings", "sum"),
        )
        .reset_index()
    )
    labels = {
        "count": "Reporting buildings",
        "median": "Median # of buildings per property",
        "sum": "Total buildings",
    }
    chart = (
        alt.Chart(alt.Data(values=CHI_GJ["features"]))
        .mark_geoshape(stroke="white", strokeWidth=0.5)
        .transform_lookup(
            lookup="properties.community",
            from_=alt.LookupData(
                community_area, "ca_key", ["count", "median", "sum"]
            ),
        )
        .encode(
            color=alt.Color(
                f"{metric}:Q", title=labels[metric], scale=COOL_SCALE
            ),
        )
        .project("mercator")
        .properties(
            width=450,
            height=550,
            title=f"{labels[metric]} by community area ({LATEST_YEAR})",
        )
    )
    return chart


building_choropleth(latest_top, metric="median").save(
    OUTPUT_DIR / "2.1_building_choropleth.png"
)
building_choropleth(latest_top, metric="count").save(
    OUTPUT_DIR / "2.2_building_choropleth.png"
)
building_choropleth(latest_top, metric="sum").save(
    OUTPUT_DIR / "2.3_building_choropleth.png"
)


def ghg_choropleth(df):
    community_area = (
        df.assign(
            ca_key=latest["community_area"].astype(str).str.upper().str.strip()
        )
        .groupby("ca_key")
        .agg(
            median_ghg_intensity=("ghg_intensity_kg_co2e_sq_ft_", "median"),
            buildings=("id", "count"),
        )
        .reset_index()
    )
    chart = (
        alt.Chart(alt.Data(values=CHI_GJ["features"]))
        .mark_geoshape(stroke="white", strokeWidth=0.5)
        .transform_lookup(
            lookup="properties.community",
            from_=alt.LookupData(
                community_area, "ca_key", ["median_ghg_intensity", "buildings"]
            ),
        )
        .encode(
            color=alt.Color(
                "median_ghg_intensity:Q",
                title="Median GHG intensity (kg CO2e / sq ft)",
                scale=WARM_SCALE,
            ),
        )
        .project("mercator")
        .properties(
            width=450,
            height=550,
            title=f"Where are the least efficient buildings? ({LATEST_YEAR})",
        )
    )
    return chart


ghg_choropleth(latest_top).save(OUTPUT_DIR / "3_ghg_choropleth.png")


def emissions_by_type_bar_chart(df):
    property_type = (
        df.groupby("primary_property_type")
        .agg(
            total_ghg=("total_ghg_emissions_metric_tons_co2e_", "sum"),
            buildings=("id", "count"),
        )
        .reset_index()
        .nlargest(15, "total_ghg")
    )
    chart = (
        alt.Chart(property_type)
        .mark_bar()
        .encode(
            x=alt.X(
                "total_ghg:Q", title="Total GHG emissions (metric tons CO2e)"
            ),
            y=alt.Y("primary_property_type:N", sort="-x", title=None),
            color=alt.value(STAR_RED),
        )
        .properties(
            width=500,
            height=380,
            title=f"Which property types emit the most? ({LATEST_YEAR})",
        )
    )
    return chart


emissions_by_type_bar_chart(latest).save(OUTPUT_DIR / "4_emissions_by_type.png")


def emissions_by_type_box_plot(df):
    d = df.dropna(subset=["ghg_intensity_kg_co2e_sq_ft_"])
    chart = (
        alt.Chart(d)
        .mark_boxplot(extent=1.5)
        .encode(
            x=alt.X(
                "ghg_intensity_kg_co2e_sq_ft_:Q",
                title="GHG intensity (kg CO2e / sq ft)",
            ),
            y=alt.Y(
                "primary_property_type:N",
                title=None,
                sort=alt.EncodingSortField(
                    "ghg_intensity_kg_co2e_sq_ft_",
                    op="median",
                    order="descending",
                ),
            ),
            color=alt.value(FLAG_BLUE),
        )
        .properties(
            width=500,
            height=400,
            title=f"Variation in emissions within building types ({LATEST_YEAR})",
        )
    )
    return chart


emissions_by_type_box_plot(latest_top).save(
    OUTPUT_DIR / "5_emissions_type_box.png"
)


def building_age_energy_scatter(df):
    d = df.dropna(subset=["site_eui_kbtu_sq_ft_", "year_built"])
    d = d[
        (d["year_built"] > 1850)
        & (d["site_eui_kbtu_sq_ft_"] < d["site_eui_kbtu_sq_ft_"].quantile(0.99))
    ]
    pts = (
        alt.Chart(d)
        .mark_circle(size=35, opacity=0.5)
        .encode(
            x=alt.X(
                "year_built:Q",
                title="Year built",
                scale=alt.Scale(zero=False),
                axis=alt.Axis(format="d"),
            ),
            y=alt.Y("site_eui_kbtu_sq_ft_:Q", title="Site EUI (kBtu / sq ft)"),
            color=alt.Color(
                "chicago_energy_rating:O",
                title="Stars",
                scale=STAR_SCALE,
            ),
        )
    )
    trend = (
        alt.Chart(d)
        .transform_loess("year_built", "site_eui_kbtu_sq_ft_")
        .mark_line(color="black", size=3)
        .encode(x="year_built:Q", y="site_eui_kbtu_sq_ft_:Q")
    )
    chart = (pts + trend).properties(
        width=550,
        height=380,
        title=f"Do older buildings use more energy per square foot? ({LATEST_YEAR})",
    )
    return chart


building_age_energy_scatter(latest).save(
    OUTPUT_DIR / "6_building_age_energy_scatter.png"
)


def energy_rating_stacked_bar(df):
    d = df.dropna(subset=["chicago_energy_rating"])
    ratings = (
        d.groupby(["primary_property_type", "chicago_energy_rating"])
        .agg(buildings=("id", "count"))
        .reset_index()
    )
    ratings["share"] = ratings["buildings"] / ratings.groupby(
        "primary_property_type"
    )["buildings"].transform("sum")
    type_order = (
        d.groupby("primary_property_type")["chicago_energy_rating"]
        .mean()
        .sort_values(ascending=False)
        .index.tolist()
    )
    chart = (
        alt.Chart(ratings)
        .mark_bar()
        .encode(
            x=alt.X(
                "share:Q", title="Share of buildings", axis=alt.Axis(format="%")
            ),
            y=alt.Y("primary_property_type:N", title=None, sort=type_order),
            color=alt.Color(
                "chicago_energy_rating:O",
                title="Stars",
                scale=STAR_SCALE,
            ),
        )
        .properties(
            width=500,
            height=380,
            title=f"Chicago Energy Rating mix by property type ({LATEST_YEAR})",
        )
    )
    return chart


energy_rating_stacked_bar(latest_top).save(
    OUTPUT_DIR / "7_energy_rating_stacked_bar.png"
)


def fuel_mix(df):
    fuel_use = (
        df.assign(**{c: df[c].clip(lower=0) for c in FUEL_COLS})
        .groupby("primary_property_type")[list(FUEL_COLS)]
        .sum()
        .rename(columns=FUEL_COLS)
        .reset_index()
        .melt("primary_property_type", var_name="fuel", value_name="kbtu")
    )
    fuel_use["share"] = fuel_use["kbtu"] / fuel_use.groupby(
        "primary_property_type"
    )["kbtu"].transform("sum")
    type_order = (
        fuel_use[fuel_use["fuel"] == "Natural gas"]
        .sort_values("share", ascending=False)["primary_property_type"]
        .tolist()
    )
    fuel_order = [
        "Natural gas",
        "Electricity",
        "District steam",
        "District chilled water",
        "Other fuel",
    ]

    chart = (
        alt.Chart(fuel_use)
        .mark_bar()
        .encode(
            x=alt.X(
                "share:Q",
                title="Share of energy use (kBtu)",
                axis=alt.Axis(format="%"),
            ),
            y=alt.Y("primary_property_type:N", title=None, sort=type_order),
            color=alt.Color(
                "fuel:N",
                title="Fuel",
                sort=fuel_order,
                scale=FUEL_SCALE,
            ),
            order=alt.Order("fuel_rank:Q"),
        )
        .transform_calculate(fuel_rank=f"indexof({fuel_order}, datum.fuel)")
        .properties(
            width=500,
            height=380,
            title=f"Fuel mix by property type ({LATEST_YEAR})",
        )
    )
    return chart


fuel_mix(latest_top).save(OUTPUT_DIR / "8_fuel_mix.png")


def same_building_trend(df, start=2018, end=2023):
    metrics = {
        "site_eui_kbtu_sq_ft_": "Site EUI (energy used)",
        "ghg_intensity_kg_co2e_sq_ft_": "GHG intensity (emissions)",
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
        width=500,
        height=350,
        title=f"The same {len(ids):,} buildings from {start}–{end}",
    )


same_building_trend(chi_bench_df()).save(
    OUTPUT_DIR / "9_same_building_trend.png"
)


def pareto_curve(df, top_pct=10):
    ghg = "total_ghg_emissions_metric_tons_co2e_"
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
        width=500,
        height=350,
        title=f"Pareto curve showing cumulative building emissions ({df['data_year'].max()})",
    )
    return chart


pareto_curve(latest).save(OUTPUT_DIR / "10_pareto_curve.png")


def priority_buildings(df, top_pct=0.10, n_labels=8):
    ghg, inten = (
        "total_ghg_emissions_metric_tons_co2e_",
        "ghg_intensity_kg_co2e_sq_ft_",
    )
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
        width=600,
        height=450,
        title=alt.TitleParams(
            "Big emitters and poor performers: where they overlap",
            subtitle=subtitle,
            anchor="start",
        ),
    )


priority_buildings(latest).save(
    OUTPUT_DIR / "11_priority_buildings.png", scale_factor=2.0
)
