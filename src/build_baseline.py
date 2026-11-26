"""
build_baseline.py

Builds baseline emissions and energy use information for all of Chicago,
segmented by building type, and saves it to www/data/baseline.json to be used by
the interactive page.

The citywide total comes from the City of Chicago 2017 greenhouse gas
inventory because the 62% goal is measured against that inventory. The
inventory only reports building energy for all residential buildings and all
commercial buildings together. The Chicago Energy Benchmarking data covers
the large buildings among them. The buildings it does not cover (mostly
homes and small businesses) are estimated as what is left over:

    small buildings = inventory total - benchmarked buildings

Units used to keep math straightforward:
    energy:    billion kBtu
    factors:   kg CO2e per kBtu
    emissions: million metric tons CO2e (MMT)
    -----------------------------------------------------------
    billion kBtu x kg/kBtu = 1e9 kg = 1e6 metric tons = 1 MMT.

Author: Christine Tsai

Usage: uv run python src/build_baseline.py
"""

import json

import numpy as np
import pandas as pd

from constants import (
    DATA_DIR,
    FUEL_COLS,
    PROJECT_ROOT,
)
from final_graphs import (
    calculate_same_building_trend,
    estimate_emission_factors,
    load_chicago_benchmarks,
)

# =============================================================================
# SETTINGS
# =============================================================================

BASELINE_JSON = PROJECT_ROOT / "www" / "data" / "baseline.json"

# Year of the City inventory. The benchmarking data from the same year is
# used so the two sources describe the same buildings in the same year.
BASELINE_YEAR = 2017

# 2022 Climate Action Plan goal: cut emissions 62% below 2017 by 2040
GOAL_REDUCTION = 0.62
GOAL_YEAR = 2040

# Unit conversions
KBTU_PER_KWH = 3.412
KBTU_PER_THERM = 100
THOUSAND = 1_000
MILLION = 1_000_000
BILLION = 1_000_000_000

# Benchmarking columns for the two fuels the inventory also reports
ELECTRICITY_COL = "electricity_use_kbtu_"
GAS_COL = "natural_gas_use_kbtu_"

# Years used to benchmark the "current trend"
TREND_START = 2018
TREND_END = 2023

# =============================================================================
# LOAD DATA
# =============================================================================


def load_data():
    """
    Load the saved tables from the 2017 Chicago GHG Report as two dicts for
    simple lookups.

    Inputs: none (reads data/chicago_2017_ghg_inventory.csv and
        data/chicago_2017_energy_use.csv).
    Output: a tuple (emissions, energy). Each is a dict mapping a row's name
        to its numeric value. Emissions are in metric tons CO2e. Energy holds
        fuel use for gas (therms) and electricity (kWh) and the grid factor.
    Errors: raises FileNotFoundError if either CSV is missing.
    """
    emissions = pd.read_csv(DATA_DIR / "chicago_2017_ghg_inventory.csv")
    energy = pd.read_csv(DATA_DIR / "chicago_2017_energy_use.csv")
    return (
        dict(zip(emissions["subsector"], emissions["emissions_mt_co2e"])),
        dict(zip(energy["measure"], energy["value"])),
    )


def summarize_benchmarks(year):
    """
    Add up the benchmarked buildings' energy and emissions for one year,
    separately for residential and for commercial and institutional.

    Inputs: the data year to summarize.
    Output: a DataFrame with one row per group ("residential" or
        "commercial") and columns electricity_kbtu, gas_kbtu and
        other_fuel_mmt (emissions from fuels the inventory does not report).
    """
    buildings = load_chicago_benchmarks()
    buildings = buildings[buildings["data_year"] == year].copy()
    # Multifamily housing and other places people live (dormitories, senior
    # and residential care, other lodging) count as residential.
    # Every other building type(offices, hospitals, schools, hotels, etc.) counts
    # as commercial and institutional.
    residential_types = [
        "Multifamily Housing",
        "Residence Hall/Dormitory",
        "Senior Care Community",
        "Residential Care Facility",
        "Other - Lodging/Residential",
    ]
    buildings["group"] = np.where(
        buildings["primary_property_type"].isin(residential_types),
        "residential",
        "commercial",
    )
    # The remaining fuels (steam, chilled water, other fuel) are not in the
    # inventory. Leaving them out keeps the baseline equal to the inventory,
    # and their size is reported in baseline.json under "left_out".
    other_fuel_cols = [
        c for c in FUEL_COLS if c not in (ELECTRICITY_COL, GAS_COL)
    ]
    # Emissions of the other fuels need a factor for each fuel. The factors
    # are estimated from what the buildings reported (see final_graphs.py).
    factors = estimate_emission_factors(buildings)
    buildings["other_fuel_kg"] = (
        buildings[other_fuel_cols].fillna(0) * factors[other_fuel_cols]
    ).sum(axis=1)
    totals = buildings.groupby("group")[
        [ELECTRICITY_COL, GAS_COL, "other_fuel_kg"]
    ].sum()
    totals = totals.rename(
        columns={ELECTRICITY_COL: "electricity_kbtu", GAS_COL: "gas_kbtu"}
    )
    # kg to million metric tons: divide by 1,000 kg per ton and 1 million
    totals["other_fuel_mmt"] = totals["other_fuel_kg"] / (THOUSAND * MILLION)
    return totals.drop(columns="other_fuel_kg")


# =============================================================================
# CALCULATE EMISSION FACTORS
# =============================================================================


def calculate_factors(emissions, energy):
    """
    Calculate emission factor of each fuel from the inventory by using emissions
    divided by energy used.

    For example, residential electricity emitted 3,468,411 metric tons from
    6,149,008,543 kWh, so each kWh emitted about 0.564 kg.

    Inputs: the emissions and energy dicts from load_data.
    Output: a dict with "electricity" and "gas" factors in kg CO2e per kBtu.
    Errors: raises ValueError if the residential and commercial rows imply
        factors that differ by more than 2%.
    """
    # Residential rows
    res_elec = (
        emissions["Residential electricity emissions 2017"]
        * THOUSAND
        / (energy["Residential electricity use 2017"] * KBTU_PER_KWH)
    )
    res_gas = (
        emissions["Residential natural gas emissions 2017"]
        * THOUSAND
        / (energy["Residential natural gas use 2017"] * KBTU_PER_THERM)
    )
    # Commercial and manufacturing rows (reported only as one combined group)
    com_elec = (
        emissions["Commercial and manufacturing electricity emissions 2017"]
        * THOUSAND
        / (
            energy["Commercial and manufacturing electricity use 2017"]
            * KBTU_PER_KWH
        )
    )
    com_gas = (
        emissions["Commercial and manufacturing natural gas emissions 2017"]
        * THOUSAND
        / (
            energy["Commercial and manufacturing natural gas use 2017"]
            * KBTU_PER_THERM
        )
    )
    # The same fuel should have the same factor in both groups (within 2%)
    for name, a, b in [
        ("electricity", res_elec, com_elec),
        ("gas", res_gas, com_gas),
    ]:
        if abs(a - b) / a > 0.02:
            raise ValueError(f"{name} factors disagree: {a:.4f} vs {b:.4f}")
    return {"electricity": res_elec, "gas": res_gas}


# =============================================================================
# CALCULATE EMISSIONS
# =============================================================================


def calculate_emissions(group_energy, factors):
    """
    Emissions of one group of energy use, in million metric tons CO2e.

    Inputs: a dict with electricity_bkbtu and gas_bkbtu, and the factors.
    Output: emissions in MMT (billion kBtu x kg/kBtu = MMT).
    """
    return (
        group_energy["electricity_bkbtu"] * factors["electricity"]
        + group_energy["gas_bkbtu"] * factors["gas"]
    )


# =============================================================================
# BUILDINGS AND INDUSTRY
# =============================================================================


def to_billion_kbtu(emitted_mt, factor):
    """
    Convert a sector's emissions back into the energy that caused them.

    Inputs: emissions in metric tons CO2e and a factor in kg CO2e per kBtu.
    Output: energy in billion kBtu.
    """
    return emitted_mt * THOUSAND / factor / BILLION


def split_buildings_by_size(emissions, factors, benchmark):
    """
    Split residential and commercial building energy into large buildings
    (from the benchmarking data) and small buildings (the remainder).

    Inputs: the emissions dict, the factors from calculate_factors, and the
        benchmarking totals from summarize_benchmarks.
    Output: a dict mapping each group name to a dict with electricity and
        gas energy (billion kBtu) and whether the numbers are an estimate.
    Errors: raises ValueError if a benchmarked group uses more energy than
        the inventory says the whole group used.
    """
    # Report energy (billion kBtu) for each building group
    report_energy = {
        "residential": {
            "electricity": to_billion_kbtu(
                emissions["Residential buildings scope 2 (electricity)"],
                factors["electricity"],
            ),
            "gas": to_billion_kbtu(
                emissions["Residential buildings scope 1 (gas)"],
                factors["gas"],
            ),
        },
        "commercial": {
            "electricity": to_billion_kbtu(
                emissions["Commercial and institutional scope 2 (electricity)"],
                factors["electricity"],
            ),
            "gas": to_billion_kbtu(
                emissions["Commercial and institutional scope 1 (gas)"],
                factors["gas"],
            ),
        },
    }
    groups = {}
    for group, energy in report_energy.items():
        large_elec = benchmark.loc[group, "electricity_kbtu"] / BILLION
        large_gas = benchmark.loc[group, "gas_kbtu"] / BILLION
        small_elec = energy["electricity"] - large_elec
        small_gas = energy["gas"] - large_gas
        if small_elec < 0 or small_gas < 0:
            raise ValueError(f"benchmarked {group} exceeds the inventory")
        groups[f"{group}_large"] = {
            "electricity_bkbtu": large_elec,
            "gas_bkbtu": large_gas,
            "estimated": False,
        }
        groups[f"{group}_small"] = {
            "electricity_bkbtu": small_elec,
            "gas_bkbtu": small_gas,
            "estimated": True,
        }
    return groups


def build_industry(emissions, factors):
    """
    Convert the inventory's manufacturing and construction emissions into
    electricity and gas energy. Industry is not in the benchmarking data.

    Inputs: the emissions dict and the factors from calculate_factors.
    Output: a dict with electricity_bkbtu and gas_bkbtu.
    """
    return {
        "electricity_bkbtu": to_billion_kbtu(
            emissions["Manufacturing scope 2 (electricity)"],
            factors["electricity"],
        ),
        "gas_bkbtu": to_billion_kbtu(
            emissions["Manufacturing scope 1 (gas)"], factors["gas"]
        ),
    }


# =============================================================================
# CURRENT TREND
# =============================================================================


def calculate_current_trend():
    """
    Measure how fast large buildings and the grid changed from TREND_START
    to TREND_END to be applied to the current trend slider in the simulation.
    "Current trend" thus mocks what change looks like at the same pace as these
    years.

    Three measurements taken from the benchmarking data:
      efficiency: the median same-building drop in energy use per square
          foot (the line in Figure 3), turned into a yearly rate.
      electrification: how much the gas share of the same buildings' energy
          fell. It rose slightly, so this comes out as 0.
      grid cleaning: the fall in the electricity emission factor, held at
          the same yearly pace until the goal year.

    Inputs: none (reads the benchmarking data).
    Output: a dict with the setting for each lever plus the measurements
        behind it.
    """
    benchmarks = load_chicago_benchmarks()
    years = TREND_END - TREND_START
    horizon = GOAL_YEAR - BASELINE_YEAR

    # Efficiency
    # The trend table is a percentage of each building's own
    # first-year value, so 88 means energy per square foot fell 12%.
    trend, ids = calculate_same_building_trend(
        benchmarks, TREND_START, TREND_END
    )
    energy_left = trend.loc[TREND_END, "energy"] / 100
    efficiency_rate = 1 - energy_left ** (1 / years)

    # Electrification: gas share of the same buildings' total energy
    panel = benchmarks[benchmarks["id"].isin(ids)]
    totals = panel.groupby("data_year")[[ELECTRICITY_COL, GAS_COL]].sum()
    gas_share = totals[GAS_COL] / totals.sum(axis=1)
    gas_share_drop = 1 - gas_share[TREND_END] / gas_share[TREND_START]
    electrification = max(0.0, gas_share_drop) / years * horizon

    # Grid cleaning: factors estimated the same way in both years
    start_factor = estimate_emission_factors(
        benchmarks[benchmarks["data_year"] == TREND_START]
    )[ELECTRICITY_COL]
    end_factor = estimate_emission_factors(
        benchmarks[benchmarks["data_year"] == TREND_END]
    )[ELECTRICITY_COL]
    yearly_drop = (start_factor - end_factor) / start_factor / years
    grid_cleaning = yearly_drop * horizon

    return {
        "start_year": TREND_START,
        "end_year": TREND_END,
        "buildings_in_panel": len(ids),
        "settings": {
            "efficiencyRate": efficiency_rate,
            "electrification": min(electrification, 1.0),
            "gridCleaning": min(grid_cleaning, 1.0),
        },
        "measured": {
            "energy_per_sqft_end_pct_of_start": energy_left * 100,
            "gas_share_start": gas_share[TREND_START],
            "gas_share_end": gas_share[TREND_END],
            "electricity_factor_start": start_factor,
            "electricity_factor_end": end_factor,
        },
    }


# =============================================================================
# BUILD BASELINE
# =============================================================================


def build_baseline():
    """
    Build the baseline json.

    Inputs: none.
    Output: a dict that is written to baseline.json.
    """
    emissions, energy = load_data()
    factors = calculate_factors(emissions, energy)
    benchmark = summarize_benchmarks(BASELINE_YEAR)
    buildings = split_buildings_by_size(emissions, factors, benchmark)
    industry = build_industry(emissions, factors)

    # Sectors the simulation holds as single blocks, in MMT
    fixed = {
        "transportation_mmt": emissions["Transportation"] / MILLION,
        "waste_mmt": emissions["Waste"] / MILLION,
        "other_mmt": (
            emissions["Fugitive emissions from oil and natural gas systems"]
            + emissions["Energy industries"]
            + emissions["Non-specified source - Calumet WRP biogas flare"]
        )
        / MILLION,
    }
    city_total = emissions["Total"] / MILLION

    # Emissions the groups reproduce to compare with the inventory
    buildings_mmt = sum(
        calculate_emissions(s, factors) for s in buildings.values()
    )
    industry_mmt = calculate_emissions(industry, factors)
    modeled_total = buildings_mmt + industry_mmt + sum(fixed.values())

    return {
        "baseline_year": BASELINE_YEAR,
        "goal_year": GOAL_YEAR,
        "units": {
            "energy": "billion kBtu",
            "factor": "kg CO2e per kBtu",
            "emissions": "million metric tons CO2e",
        },
        "factors": factors,
        "trend": calculate_current_trend(),
        "buildings": buildings,
        "industry": industry,
        "fixed": fixed,
        # Benchmarked emissions from fuels the inventory does not report
        "left_out": {
            "benchmarked_other_fuel_mmt": benchmark["other_fuel_mmt"].sum()
        },
        "totals": {
            "city_mmt": city_total,
            "buildings_mmt": buildings_mmt,
            "industry_mmt": industry_mmt,
            "goal_reduction": GOAL_REDUCTION,
            "goal_mmt": city_total * (1 - GOAL_REDUCTION),
            "modeled_total_mmt": modeled_total,
        },
    }


def main():
    """
    Build the baseline and save it as JSON.

    Inputs: none.
    Output: writes www/data/baseline.json.
    """
    baseline = build_baseline()
    BASELINE_JSON.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_JSON.write_text(json.dumps(baseline, indent=2) + "\n")


if __name__ == "__main__":
    main()
