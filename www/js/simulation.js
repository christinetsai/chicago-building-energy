/*
 * simulation.js
 *
 * Forecasts Chicago's emissions from 2017 to 2040. It takes the baseline data
 * (data/baseline.json) and the slider settings and returns one result for
 * each year.
 *
 * Units are the same as build_baseline.py:
 *   energy:    billion kBtu
 *   factors:   kg CO2e per kBtu
 *   emissions: million metric tons CO2e (MMT)
 * Energy times a factor gives emissions directly, with no unit conversion,
 * because billion kBtu x kg/kBtu = 1e9 kg = 1 MMT.
 *
 * Author: Christine Tsai
 */

// =========================================================================
// ASSUMPTIONS
// =========================================================================

// TO BE CONFIRMED
// How much of a gas furnace's fuel becomes heat. A typical value.
const FURNACE_EFFICIENCY = 0.8;

// TO BE CONFIRMED
// Units of heat a heat pump delivers per unit of electricity. Typically 2.5
// to 3.
const HEAT_PUMP_COP = 2.8;

// Electricity a heat pump needs to replace one unit of gas heating. For
// example, 100 kBtu of gas heat is replaced by about 29 kBtu of electricity.
const ELECTRICITY_PER_GAS = FURNACE_EFFICIENCY / HEAT_PUMP_COP;

// =========================================================================
// SLIDER SETTINGS
// =========================================================================

// Each setting is the share of change reached by 2040, from 0 to 1. The change
// is added evenly each year, so it is half done at the midpoint (2028.5).
const DEFAULT_SETTINGS = {
  // Lever 1: share of its energy a building saves. At 0.4, a building uses
  // 40% less energy in 2040.
  efficiency: 0,
  // Lever 2: share of building gas switched to electric heat pumps.
  electrification: 0,
  // Lever 3: share of the grid's emissions removed. At 1, electricity has no
  // emissions.
  gridCleaning: 0,
  // Share of industry's energy cut (manufacturing and construction). The grid
  // lever also lowers industry's emissions through its electricity.
  industryCut: 0,
  // Share of transportation and waste emissions cut. Each is treated as one
  // block.
  transportCut: 0,
  wasteCut: 0,
};

// =========================================================================
// HELPERS
// =========================================================================

/*
 * How far a year is from 2017 (0) to 2040 (1). For example, 2028.5 is halfway,
 * so the progress is 0.5.
 */
function getProgress(year, baseline) {
  const yearsSinceStart = year - baseline.baseline_year;
  const totalYears = baseline.goal_year - baseline.baseline_year;
  return yearsSinceStart / totalYears;
}

/*
 * The share of something left in a year if a share `cut` of it is removed by
 * 2040. Multiplying the cut by the progress adds it in evenly. For example, a
 * 40% cut at the midpoint has removed 20%, so 0.8 is left.
 */
function getShareLeft(cut, progress) {
  return 1 - cut * progress;
}

/*
 * Emissions in MMT from an amount of electricity and gas (billion kBtu) and
 * their factors (kg CO2e per kBtu). For example,
 * 7.24 x 0.1653 + 14.69 x 0.0531 = 1.98 MMT.
 */
function getEmissions(elec, gas, elecFactor, gasFactor) {
  return elec * elecFactor + gas * gasFactor;
}

/*
 * The electricity emission factor in a year (kg CO2e per kBtu), after the
 * grid has been cleaned by its share so far (lever 3). For example, 0.6
 * cleaning at the midpoint removes 30%: 0.1653 x 0.7 = 0.1157.
 */
function getGridFactor(settings, progress, factors) {
  return factors.electricity * getShareLeft(settings.gridCleaning, progress);
}

// =========================================================================
// ONE BUILDING SEGMENT IN ONE YEAR
// =========================================================================

/*
 * Energy and emissions of one building segment (such as residential small) in
 * one year, after the three levers.
 *
 * segment:    electricity and gas energy in 2017
 * progress:   0 to 1, from getProgress
 * gridFactor: that year's electricity factor, already lowered by lever 3
 */
function getBuildingYear(segment, settings, progress, factors, gridFactor) {
  // Step 1, efficiency: the building saves a share of its energy, so it has
  // the rest left. Both fuels shrink by the same amount.
  const energyLeft = getShareLeft(settings.efficiency, progress);
  const elecAfterEfficiency = segment.electricity_bkbtu * energyLeft;
  const gasAfterEfficiency = segment.gas_bkbtu * energyLeft;

  // Step 2, electrification: this year's share of gas switched to heat pumps
  // is the setting times the progress. Efficiency comes first, so a better
  // insulated building needs a smaller heat pump.
  const share = settings.electrification * progress;
  const gasMoved = gasAfterEfficiency * share;
  // The switched gas leaves the gas total
  const gas = gasAfterEfficiency - gasMoved;
  // ...and comes back as electricity, but much less of it. A heat pump moves
  // heat instead of making it (ELECTRICITY_PER_GAS is about 0.29).
  const elec = elecAfterEfficiency + gasMoved * ELECTRICITY_PER_GAS;

  // Step 3, emissions: the electricity factor already includes the grid lever,
  // and the gas factor never changes.
  return {
    electricity_bkbtu: elec,
    gas_bkbtu: gas,
    emissions: getEmissions(elec, gas, gridFactor, factors.gas),
  };
}

// =========================================================================
// THE WHOLE CITY IN ONE YEAR
// =========================================================================

/*
 * Everything that emits in one year: each building segment, industry,
 * transportation, waste and other, plus the building and city totals.
 */
function getYear(year, settings, baseline) {
  const progress = getProgress(year, baseline);
  const factors = baseline.factors;
  const gridFactor = getGridFactor(settings, progress, factors);

  // The four building segments, each through the three levers
  const buildings = {};
  let buildingsTotal = 0;
  for (const [name, segment] of Object.entries(baseline.buildings)) {
    buildings[name] = getBuildingYear(
      segment, settings, progress, factors, gridFactor
    );
    buildingsTotal += buildings[name].emissions;
  }

  // Industry: its energy is cut by `industryCut`, then it pays the same grid
  // factor for its electricity. So the grid lever lowers industry's emissions
  // even when industryCut is 0.
  const industryLeft = getShareLeft(settings.industryCut, progress);
  const industry = getEmissions(
    baseline.industry.electricity_bkbtu * industryLeft,
    baseline.industry.gas_bkbtu * industryLeft,
    gridFactor,
    factors.gas
  );

  // Transportation and waste: one number each, cut evenly to 2040.
  const transportation = baseline.fixed.transportation_mmt *
    getShareLeft(settings.transportCut, progress);
  const waste = baseline.fixed.waste_mmt *
    getShareLeft(settings.wasteCut, progress);
  // Leaks and other small sources stay at their 2017 level.
  const other = baseline.fixed.other_mmt;

  return {
    year,
    gridFactor,
    buildings,
    buildingsTotal,
    industry,
    transportation,
    waste,
    other,
    total: buildingsTotal + industry + transportation + waste + other,
  };
}

// =========================================================================
// THE FORECAST + SUMMARY
// =========================================================================

/*
 * Run getYear for every year from 2017 to 2040. `overrides` replaces any of
 * the default settings, so runSimulation({electrification: 0.8}) changes only
 * that setting.
 */
function runSimulation(overrides, baseline) {
  const settings = Object.assign({}, DEFAULT_SETTINGS, overrides);
  const years = [];
  for (let y = baseline.baseline_year; y <= baseline.goal_year; y++) {
    years.push(getYear(y, settings, baseline));
  }
  return years;
}

/*
 * The numbers for the result message under the chart from the forecast.
 *
 * goal:            the city's 2040 target (11.79 MMT, 62% below 2017)
 * gap:             2040 emissions minus the goal (negative means it is met)
 * buildingsDrop:   how much building emissions fell by 2040 (0.4 = 40%)
 * buildingsNeeded: how far buildings would need to fall for the city to meet
 *                  the goal, with the other sectors as set. Above 1 (100%)
 *                  means even zero building emissions would not be enough.
 */
function summarize(forecast, baseline) {
  const first = forecast[0];
  const last = forecast[forecast.length - 1];
  const goal = baseline.totals.goal_mmt;
  // Everything in 2040 that is not buildings
  const notBuildings = last.total - last.buildingsTotal;
  // The most buildings can emit in 2040 and still meet the goal
  const buildingsAllowed = goal - notBuildings;
  return {
    goal,
    total2040: last.total,
    gap: last.total - goal,
    meetsGoal: last.total <= goal,
    buildingsDrop: 1 - last.buildingsTotal / first.buildingsTotal,
    buildingsNeeded: 1 - buildingsAllowed / first.buildingsTotal,
  };
}

// =========================================================================
// PRESETS
// =========================================================================

/*
 * Gets settings for each of the preset buttons. All but "current trend" are
 * fixed numbers. "Current trend" relies on the baseline data which is loaded
 * after this file.
 */
function getPresets(baseline) {
  return {
    // Keep changing at the pace measured in the benchmarking data from 2018 to
    // 2023 (calculate_current_trend in build_baseline.py). Industry,
    // transportation and waste aren't measured in that dataset so they stay at
    // their 2017 levels.
    currentTrend: {
      label: "Current trend",
      settings: baseline.trend.settings,
    },
    electrifyOnly: {
      label: "Electrify, same grid",
      settings: { electrification: 0.8 },
    },
    electrifyAndClean: {
      label: "Electrify and clean the grid",
      settings: { electrification: 0.8, gridCleaning: 0.8 },
    },
  };
}
