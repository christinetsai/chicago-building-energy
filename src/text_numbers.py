"""
text_numbers.py

Calculates every number quoted in the text of the page, saves them to
static-viz/text_numbers.json, and fills them into the page template
static-viz/index_template.html to write static-viz/index.html.

Edit the page text in index_template.html, where each number is a
placeholder such as {{reporting_buildings}}. Do not edit index.html. It is
rewritten every time this script runs.

Author: Christine Tsai

Usage: uv run python src/text_numbers.py
"""

import json
import re

import pandas as pd

from constants import (
    DATA_DIR,
    GHG_INTENSITY,
    GHG_TOTAL,
    MILLION,
    PROJECT_ROOT,
    SECTOR_VALUE,
)
from final_graphs import (
    INTENSE_MULTIPLE,
    MIN_INTENSE_BUILDINGS,
    SECTOR_CSV,
    calculate_cumulative_emissions,
    PEER_MIN_BUILDINGS,
    REDUCTION_TYPES_SHOWN,
    calculate_excess_emissions,
    select_high_for_type,
    calculate_pareto_marks,
    calculate_same_building_trend,
    estimate_emission_factors,
    load_chicago_benchmarks,
    load_chicago_geojson,
    select_priority_buildings,
    summarize_community_areas,
    summarize_fuel_use,
)

PAGE_DIR = PROJECT_ROOT / "static-viz"
TEMPLATE_PATH = PAGE_DIR / "index_template.html"
PAGE_PATH = PAGE_DIR / "index.html"
NUMBERS_PATH = PAGE_DIR / "text_numbers.json"
RAW_BENCHMARKS = DATA_DIR / "Chicago_Energy_Benchmarking_20261001.csv"

# =============================================================================
# NUMBERS CHOSEN FOR THE ANALYSIS
# =============================================================================

# Rounding for tons quoted as "about"
ROUND_TO_THOUSAND = -3
ROUND_TO_HUNDRED = -2
ROUND_TO_TEN = -1


NAMED_BUILDINGS = 3  # Largest priority buildings named in the text
# How each named building's tons are rounded in the text (thousand, hundred)
NAMED_ROUNDING = [ROUND_TO_THOUSAND, ROUND_TO_HUNDRED, ROUND_TO_HUNDRED]
DOWNTOWN_AREAS = [
    "Loop",
    "Near North Side",
    "Near West Side",
    "Near South Side",
]
OFFICE_AND_HOUSING = ["Multifamily Housing", "Office"]
ONE_STAR_SHARE_AREAS = 3  # Areas with the highest poorly rated share named
LARGEST_AREAS = 3  # Areas with the most buildings named
TREND_START = 2018
TREND_END = 2023
PERCENT = 100
# Types whose median emissions per square foot are quoted in the Figure 6 text
INTENSE_MEDIAN_TYPES = {
    "Data center": "data_center",
    "Supermarket": "supermarket",
    "Laboratory": "laboratory",
    "Hospital": "hospital",
}
SENTENCE_NAMES = {"Loop": "the Loop"}  # Names that read better with "the"


# =============================================================================
# FORMATTING
# =============================================================================


def format_percent(share):
    """
    Format a share as a whole-number percent without the percent sign.

    Inputs: a share where 1 is 100%.
    Output: a string such as "42".
    """
    return f"{share * PERCENT:.0f}"


def format_tons(tons, digits):
    """
    Format tons rounded to the given digit, with commas.

    Inputs: a number of tons, and a rounding digit (-3 rounds to the
        nearest thousand).
    Output: a string such as "87,000".
    """
    return f"{round(tons, digits):,.0f}"


def format_area_name(name):
    """
    Add "the" to community area names that read better with it.

    Inputs: a community area name.
    Output: the name for use in a sentence.
    """
    return SENTENCE_NAMES.get(name, name)


# =============================================================================
# CALCULATE THE NUMBERS
# One function for each part of the page, in page order
# =============================================================================


def load_reporting_counts(year):
    """
    Count the buildings in each reporting status for one year.

    Inputs: the data year.
    Output: a Series of building counts indexed by reporting status.
    """
    raw = pd.read_csv(
        RAW_BENCHMARKS,
        usecols=["Data Year", "Reporting Status"],
        thousands=",",
    )
    return raw.loc[raw["Data Year"] == year, "Reporting Status"].value_counts()


def calculate_sector_numbers(latest):
    """
    Numbers for Figure 1: the citywide inventory and the reporting
    buildings' share of it.

    Inputs: latest-year DataFrame.
    Output: a dictionary of formatted values.
    """
    sectors = pd.read_csv(SECTOR_CSV)
    by_sector = sectors.groupby("sector")[SECTOR_VALUE].sum()
    city_total = by_sector.sum()
    reporting_tons = latest[GHG_TOTAL].sum()
    counts = load_reporting_counts(latest["data_year"].max())
    submitted = len(latest)
    required = submitted + counts["Not Submitted"]
    return {
        "buildings_mt": f"{by_sector['Buildings']:.0f}",
        "buildings_mt_precise": f"{by_sector['Buildings']:.1f}",
        "industry_mt": f"{by_sector['Industry & other']:.1f}",
        "transport_mt": f"{by_sector['Transportation']:.1f}",
        "waste_mt": f"{by_sector['Waste']:.1f}",
        "city_total_mt": f"{city_total:.1f}",
        "cmap_buildings_pct": format_percent(
            by_sector["Buildings"] / city_total
        ),
        "reporting_mt": f"{reporting_tons / MILLION:.1f}",
        "reporting_buildings": f"{submitted:,}",
        "not_submitted": f"{counts['Not Submitted']:,}",
        "not_covered": f"{counts['Not Covered 2024']:,}",
        "required_buildings": f"{required:,}",
        "submitted_pct": format_percent(submitted / required),
    }


def calculate_area_numbers(latest, geojson):
    """
    Numbers for Figure 2: buildings and poorly rated shares by area.

    Inputs: latest-year DataFrame and the community area GeoJSON.
    Output: a dictionary of formatted values.
    """
    areas = summarize_community_areas(latest, geojson)
    numbers = {}

    # The areas with the most buildings
    largest = areas.nlargest(LARGEST_AREAS, "buildings")
    for rank, (_, row) in enumerate(largest.iterrows(), start=1):
        numbers[f"largest_area_{rank}"] = format_area_name(
            row["community_area"]
        )
        numbers[f"largest_area_{rank}_buildings"] = f"{row['buildings']:,}"

    # Downtown's share of the buildings and of the poorly rated ones
    downtown = areas[areas["community_area"].isin(DOWNTOWN_AREAS)]
    numbers["downtown_buildings_pct"] = format_percent(
        downtown["buildings"].sum() / areas["buildings"].sum()
    )
    numbers["downtown_one_star_pct"] = format_percent(
        downtown["one_star"].sum() / downtown["rated"].sum()
    )

    # The areas with the highest poorly rated share, among areas with enough
    # buildings to compare
    comparable = areas[~areas["is_small"]]
    worst = comparable.nlargest(ONE_STAR_SHARE_AREAS, "one_star_share")
    for rank, (_, row) in enumerate(worst.iterrows(), start=1):
        numbers[f"one_star_area_{rank}"] = row["community_area"]
        numbers[f"one_star_area_{rank}_pct"] = format_percent(
            row["one_star_share"]
        )
    numbers["one_star_areas_min_buildings"] = f"{worst['buildings'].min()}"
    numbers["one_star_areas_max_buildings"] = f"{worst['buildings'].max()}"
    return numbers


def format_factors(factors, prefix):
    """
    Format the electricity and gas emission factors.

    Inputs: a Series of factors indexed by fuel column, and a key prefix.
    Output: a dictionary of formatted values.
    """
    electricity = factors["electricity_use_kbtu_"]
    gas = factors["natural_gas_use_kbtu_"]
    return {
        f"{prefix}_electricity_factor": f"{electricity:.3f}",
        f"{prefix}_gas_factor": f"{gas:.3f}",
    }


def calculate_trend_numbers(all_years, latest):
    """
    Numbers for Figure 3 and the emission factors behind Figures 3 and 4.

    Inputs: all-years DataFrame and latest-year DataFrame.
    Output: a dictionary of formatted values.
    """
    trend, ids = calculate_same_building_trend(
        all_years, TREND_START, TREND_END
    )
    end = trend.loc[TREND_END].round()
    first_year = all_years[
        (all_years["data_year"] == TREND_START) & all_years["id"].isin(ids)
    ]
    numbers = {
        "trend_buildings": f"{len(ids):,}",
        "trend_energy_end": f"{end['energy']:.0f}",
        "trend_emissions_end": f"{end['emissions']:.0f}",
        "trend_fixed_end": f"{end['fixed']:.0f}",
        "trend_energy_drop": f"{PERCENT - end['energy']:.0f}",
        "trend_emissions_drop": f"{PERCENT - end['emissions']:.0f}",
        "trend_grid_gap": f"{end['fixed'] - end['emissions']:.0f}",
        "trend_grid_share_pct": format_percent(
            (end["fixed"] - end["emissions"]) / (PERCENT - end["emissions"])
        ),
    }
    numbers.update(
        format_factors(estimate_emission_factors(first_year), "first")
    )
    numbers.update(format_factors(estimate_emission_factors(latest), "latest"))
    return numbers


def calculate_fuel_numbers(latest):
    """
    Numbers for Figure 4: each fuel's share of energy and of emissions.

    Inputs: latest-year DataFrame.
    Output: a dictionary of formatted values.
    """
    shares = summarize_fuel_use(latest).set_index(["measure", "fuel"])["share"]
    names = {
        "Natural gas": "gas",
        "Electricity": "electricity",
        "Other fuels": "other",
    }
    numbers = {}
    for (measure, fuel), share in shares.items():
        key = "energy" if measure == "Energy used" else "emissions"
        numbers[f"{key}_{names[fuel]}_pct"] = format_percent(share)
    # "About" figure for the caption, to the nearest ten percent
    electricity = shares["Emissions", "Electricity"] * PERCENT
    numbers["emissions_electricity_pct_rounded"] = (
        f"{round(electricity, ROUND_TO_TEN):.0f}"
    )
    return numbers


def calculate_type_numbers(latest):
    """
    Numbers for Figures 5 and 6: totals and intensity by property type.

    Inputs: latest-year DataFrame.
    Output: a dictionary of formatted values.
    """
    total = latest[GHG_TOTAL].sum()
    by_type = latest.groupby("type_label", observed=True).agg(
        tons=(GHG_TOTAL, "sum"),
        buildings=(GHG_TOTAL, "count"),
        median=(GHG_INTENSITY, "median"),
        intensity_buildings=(GHG_INTENSITY, "count"),
    )
    by_type["average"] = by_type["tons"] / by_type["buildings"]
    city_median = latest[GHG_INTENSITY].median()

    housing = by_type.loc["Multifamily housing"]
    hospital = by_type.loc["Hospital"]
    numbers = {
        "type_multifamily_buildings": (
            f"{by_type.loc['Multifamily housing', 'buildings']:,}"
        ),
        "type_office_buildings": f"{by_type.loc['Office', 'buildings']:,}",
        "type_multifamily_mt": f"{housing['tons'] / MILLION:.1f}",
        "type_office_mt": f"{by_type.loc['Office', 'tons'] / MILLION:.1f}",
        "type_hospital_average": f"{hospital['average']:,.0f}",
        "type_data_center_average": (
            f"{by_type.loc['Data center', 'average']:,.0f}"
        ),
        "type_convention_average": (
            f"{by_type.loc['Convention center', 'average']:,.0f}"
        ),
        "type_multifamily_average": f"{housing['average']:,.0f}",
        "hospital_vs_multifamily": (
            f"{hospital['average'] / housing['average']:.0f}"
        ),
        "city_median_intensity": f"{city_median:.1f}",
    }

    housing_and_offices = latest["primary_property_type"].isin(
        OFFICE_AND_HOUSING
    )
    numbers["housing_office_buildings"] = format_tons(
        by_type.loc[["Multifamily housing", "Office"], "buildings"].sum(),
        ROUND_TO_HUNDRED,
    )
    numbers["housing_office_pct"] = format_percent(
        latest.loc[housing_and_offices, GHG_TOTAL].sum() / total
    )

    # Property types that are much more intense than the city as a whole
    intense = by_type[
        (by_type["median"] >= INTENSE_MULTIPLE * city_median)
        & (by_type["intensity_buildings"] >= MIN_INTENSE_BUILDINGS)
    ]
    numbers["intense_types_pct"] = format_percent(intense["tons"].sum() / total)
    ratios = intense["median"] / city_median
    numbers["intense_ratio_low"] = f"{ratios.min():.0f}"
    numbers["intense_ratio_high"] = f"{ratios.max():.0f}"
    for label, key in INTENSE_MEDIAN_TYPES.items():
        numbers[f"median_{key}"] = f"{by_type.loc[label, 'median']:.1f}"
    return numbers


def calculate_pareto_numbers(latest):
    """
    Numbers for Figure 7: the share of emissions from the largest buildings.

    Inputs: latest-year DataFrame.
    Output: a dictionary of formatted values.
    """
    marks = calculate_pareto_marks(calculate_cumulative_emissions(latest))
    numbers = {}
    for mark in marks.itertuples():
        prefix = f"top_{mark.percent}"
        numbers[f"{prefix}_buildings"] = f"{mark.buildings:,}"
        numbers[f"{prefix}_emissions_pct"] = f"{mark.cum_pct_emissions:.0f}"
    return numbers


def calculate_priority_numbers(latest):
    """
    Numbers for Figure 8: the big, poorly rated buildings and what they
    could save.

    Inputs: latest-year DataFrame.
    Output: a dictionary of formatted values.
    """
    d, _ = select_priority_buildings(latest)
    total = latest[GHG_TOTAL].sum()

    both = d[d["is_top"] & d["is_one_star"]]
    high = select_high_for_type(d)
    saved = calculate_excess_emissions(d)[high.index]

    stars = d.groupby("chicago_energy_rating")[GHG_INTENSITY].median()
    not_top = (~d[d["is_one_star"]]["is_top"]).mean()
    numbers = {
        "median_intensity_1_star": f"{stars[1]:.1f}",
        "median_intensity_4_star": f"{stars[4]:.1f}",
        "one_star_not_top_tenths": f"{round(not_top * 10)}",
        "priority_buildings": f"{len(both)}",
        "priority_tons": format_tons(both[GHG_TOTAL].sum(), ROUND_TO_THOUSAND),
        "priority_pct": format_percent(both[GHG_TOTAL].sum() / total),
        "priority_high_for_type": f"{len(high)}",
        "saved_tons": format_tons(saved.sum(), ROUND_TO_THOUSAND),
        "saved_pct": format_percent(saved.sum() / total),
    }

    # The largest priority buildings. A name that is only a number is
    # replaced by the address.
    largest = both.nlargest(NAMED_BUILDINGS, GHG_TOTAL)
    for rank, (_, row) in enumerate(largest.iterrows(), start=1):
        name = row["property_name"]
        if str(name).strip().isdigit():
            name = row["address"]
        numbers[f"priority_name_{rank}"] = name
        numbers[f"priority_tons_{rank}"] = format_tons(
            row[GHG_TOTAL], NAMED_ROUNDING[rank - 1]
        )
    return numbers


def calculate_reduction_numbers(latest):
    """
    Numbers for Figure 9: the emissions above the typical building of each
    property type, in total and for the groups shown.

    Inputs: latest-year DataFrame.
    Output: a dictionary of formatted values.
    """
    d, _ = select_priority_buildings(latest)
    excess = calculate_excess_emissions(d)
    total = latest[GHG_TOTAL].sum()
    housing_and_offices = d["primary_property_type"].isin(OFFICE_AND_HOUSING)
    shown = excess.groupby(d["type_label"], observed=True).sum()
    shown = shown.nlargest(REDUCTION_TYPES_SHOWN)
    return {
        "peer_min_buildings": f"{PEER_MIN_BUILDINGS}",
        "excess_tons": format_tons(excess.sum(), ROUND_TO_THOUSAND),
        "excess_pct": format_percent(excess.sum() / total),
        "excess_housing_office_pct": format_percent(
            excess[housing_and_offices].sum() / excess.sum()
        ),
        "excess_shown_pct": format_percent(shown.sum() / excess.sum()),
    }


def calculate_text_numbers(all_years, geojson):
    """
    Calculate every number quoted in the text of the page.

    Inputs: all-years DataFrame and the community area GeoJSON.
    Output: a dictionary from placeholder name to formatted text.
    """
    latest = all_years[all_years["data_year"] == all_years["data_year"].max()]
    numbers = {}
    for part in (
        calculate_sector_numbers(latest),
        calculate_area_numbers(latest, geojson),
        calculate_trend_numbers(all_years, latest),
        calculate_fuel_numbers(latest),
        calculate_type_numbers(latest),
        calculate_pareto_numbers(latest),
        calculate_priority_numbers(latest),
        calculate_reduction_numbers(latest),
    ):
        numbers.update(part)
    return numbers


# =============================================================================
# BUILD THE PAGE
# =============================================================================

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
GENERATED_NOTICE = (
    "Generated by src/text_numbers.py from index_template.html. "
    "Edit the template, not this file."
)


def save_text_numbers(numbers, path=NUMBERS_PATH):
    """
    Save the numbers to a JSON file.

    Inputs: the dictionary of numbers, and the output path.
    Output: none (writes one file).
    """
    path.write_text(json.dumps(numbers, indent=2) + "\n")


def render_page(template, numbers):
    """
    Replace each {{name}} in the template with its number.

    Inputs: the template text and the dictionary of numbers.
    Output: the page text.
    Errors: raises KeyError if the template uses a name with no number.
    """
    fields = {**numbers, "generated_notice": GENERATED_NOTICE}
    return PLACEHOLDER.sub(lambda match: fields[match.group(1)], template)


def main():
    """
    Calculate the numbers in the text, save them to JSON, and write the page.

    Inputs: none (reads data/ and static-viz/index_template.html).
    Output: none (writes static-viz/text_numbers.json and index.html).
    """
    numbers = calculate_text_numbers(
        load_chicago_benchmarks(), load_chicago_geojson()
    )
    save_text_numbers(numbers)
    PAGE_PATH.write_text(render_page(TEMPLATE_PATH.read_text(), numbers))


if __name__ == "__main__":
    main()
