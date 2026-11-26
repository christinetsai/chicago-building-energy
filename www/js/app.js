/*
 * app.js
 *
 * Connects the interactive page to the simulation in simulation.js. Builds the
 * sliders and preset buttons. If any of these changes, this re-runs the
 * simulation and redraws the chart. Uses d3 for the chart.
 *
 * d3 and simulation.js need to be loaded before this file. The data in
 * data/baseline.json is fetched in this file, which requires a live web server.
 *
 * Author: Christine Tsai
 */

// =========================================================================
// SLIDERS
// =========================================================================

// One entry per slider. `key` is the setting in simulation.js it controls. The
// slider shows whole percentages. SCALE converts the percentage into a 0 to 1
// share for the simulation to use.
const SCALE = 0.01;
const SLIDERS = [
  {
    group: "buildings",
    key: "efficiency",
    label: "Energy efficiency",
    min: 0, max: 60, step: 5,
    unit: "% less energy per building by 2040",
    context: "Insulation, windows and better equipment, for residential and " +
      "commercial buildings. It stops at 60% because buildings still need " +
      "energy to heat, light and run them.<sup><a href=\"#note-efficiency\">4</a></sup>",
  },
  {
    group: "buildings",
    key: "electrification",
    label: "Electrification",
    min: 0, max: 100, step: 5,
    unit: "% of building gas switched to electric heat pumps by 2040",
    context: "Replaces gas furnaces and water heaters with electric heat pumps.",
  },
  {
    group: "buildings",
    key: "gridCleaning",
    label: "Cleaner electric grid",
    min: 0, max: 100, step: 5,
    unit: "% less emissions per unit of electricity by 2040",
    context: "More wind, solar and nuclear on the grid. Also lowers industry's " +
      "electricity emissions.",
  },
  {
    group: "other",
    key: "industryCut",
    label: "Industry",
    min: 0, max: 100, step: 5,
    unit: "% less industrial energy by 2040",
    context: "Manufacturing and construction, treated as one block.",
  },
  {
    group: "other",
    key: "transportCut",
    label: "Transportation",
    min: 0, max: 100, step: 5,
    unit: "% less emissions by 2040",
    context: "Cars, trucks, transit and planes, treated as one block.",
  },
  {
    group: "other",
    key: "wasteCut",
    label: "Waste",
    min: 0, max: 100, step: 5,
    unit: "% less emissions by 2040",
    context: "Landfilled waste and wastewater, treated as one block.",
  },
];

/*
 * Build the HTML for every slider inside its group (buildings or other).
 */
function buildSliders() {
  for (const s of SLIDERS) {
    const sliderBox = d3.select(`#sliders-${s.group}`)
      .append("div").attr("class", "slider-box");
    sliderBox.append("label")
      .attr("for", `slider-${s.key}`)
      .html(`<span class="slider-label">${s.label}</span>` +
        `<span class="slider-unit">${s.unit}</span>` +
        `<span class="slider-context">${s.context}</span>`);
    const sliderControl = sliderBox.append("div").attr("class", "slider-control");
    sliderControl.append("input")
      .attr("type", "range")
      .attr("id", `slider-${s.key}`)
      .attr("min", s.min).attr("max", s.max).attr("step", s.step)
      .attr("value", 0)
      .on("input", () => {
        clearActivePreset();
        update();
      });
    sliderControl.append("output")
      .attr("id", `value-${s.key}`)
      .attr("for", `slider-${s.key}`);
  }
}

/*
 * Read the slider positions and scale the values to create a settings object
 * for the simulation (e.g. {efficiency: 0.4, electrification: 0.8, ...}).
 */
function readSliderPositions() {
  const settings = {};
  for (const s of SLIDERS) {
    const value = +document.getElementById(`slider-${s.key}`).value;
    settings[s.key] = value * SCALE;
    document.getElementById(`value-${s.key}`).textContent = value + "%";
  }
  return settings;
}

/*
 * Move every slider to a preset's settings. Unused sliders are set back to 0.
 */
function applyPreset(presetKey) {
  const settings = Object.assign(
    {}, DEFAULT_SETTINGS, PRESETS[presetKey].settings
  );
  for (const s of SLIDERS) {
    const percent = settings[s.key] / SCALE;
    document.getElementById(`slider-${s.key}`).value =
      Math.round(percent / s.step) * s.step;
  }
  setActivePreset(presetKey);
  update();
}

// =========================================================================
// PRESET BUTTONS
// =========================================================================

function buildPresetButtons() {
  const box = d3.select("#presets");
  for (const [key, preset] of Object.entries(PRESETS)) {
    box.append("button")
      .attr("type", "button")
      .attr("class", "preset")
      .attr("data-preset", key)
      .text(preset.label)
      .on("click", () => applyPreset(key));
  }
}

/*
 * Highlight the preset button whose data-preset equals `key` and un-highlight
 * the others by setting an "active" class.
 */
function setActivePreset(key) {
  d3.selectAll(".preset")
    .classed("active", function () {
      return this.dataset.preset === key;
    })
    .attr("aria-pressed", function () {
      return this.dataset.preset === key;
    });
}

/* 
 * Resets all presets to be inactive by passing in a null preset key.
 */
function clearActivePreset() {
  setActivePreset(null);
}

// =========================================================================
// CHART
// =========================================================================

// The areas stacked in the chart, bottom to top. Residential and commercial
// buildings are blues (the sectors the sliders above act on in detail); the
// rest are grays.
const AREAS = [
  { key: "residential", label: "Residential buildings", color: "#1C7FB5" },
  { key: "commercial", label: "Commercial buildings", color: "#41B6E6" },
  { key: "industry", label: "Industry", color: "#4A5568" },
  { key: "transportation", label: "Transportation", color: "#8D99AE" },
  { key: "waste", label: "Waste and other", color: "#C9CFD8" },
];
const GOAL_COLOR = "#E4002B";

/*
 * Turn one year of model output into the five chart values in MMT.
 * Large and small buildings are combined.
 */
function convertToAreas(yearResult) {
  const bldgs = yearResult.buildings;
  return {
    year: yearResult.year,
    residential: bldgs.residential_large.emissions + bldgs.residential_small.emissions,
    commercial: bldgs.commercial_large.emissions + bldgs.commercial_small.emissions,
    industry: yearResult.industry,
    transportation: yearResult.transportation,
    waste: yearResult.waste + yearResult.other,
  };
}

const MARGIN = { top: 16, right: 24, bottom: 36, left: 52 };
const CHART_ASPECT = 0.55; // height as a share of width
const MIN_CHART_HEIGHT = 300;
const X_AXIS_YEARS = [2017, 2020, 2025, 2030, 2035, 2040];
// Room above the 2017 total so the area doesn't touch the top edge
const Y_HEADROOM = 1.08;

/*
 * Draw the stacked chart and goal line.
 */
function drawChart(forecast) {
  const holder = document.getElementById("chart");
  const width = holder.clientWidth;
  const height = Math.max(MIN_CHART_HEIGHT, width * CHART_ASPECT);
  const innerW = width - MARGIN.left - MARGIN.right;
  const innerH = height - MARGIN.top - MARGIN.bottom;

  d3.select(holder).selectAll("*").remove();
  const svg = d3.select(holder).append("svg")
    .attr("width", width).attr("height", height)
    .attr("role", "img")
    .attr("aria-label", "Stacked area chart of Chicago greenhouse gas " +
      "emissions by sector from 2017 to 2040, with the 2040 goal line");
  const g = svg.append("g")
    .attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

  const x = d3.scaleLinear()
    .domain([BASELINE.baseline_year, BASELINE.goal_year]).range([0, innerW]);
  // The y scale is fixed to the 2017 total so the chart doesn't move with
  // changes to the sliders.
  const y = d3.scaleLinear()
    .domain([0, BASELINE.totals.city_mmt * Y_HEADROOM]).range([innerH, 0]);

  // Gridlines and axes
  g.append("g").attr("class", "grid")
    .call(d3.axisLeft(y).ticks(6).tickSize(-innerW).tickFormat(""));
  g.append("g").attr("class", "axis")
    .attr("transform", `translate(0,${innerH})`)
    .call(d3.axisBottom(x).tickFormat(d3.format("d")).tickValues(X_AXIS_YEARS));
  g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(6));
  g.append("text").attr("class", "axis-title")
    .attr("transform", "rotate(-90)")
    .attr("x", -innerH / 2).attr("y", -MARGIN.left + 14)
    .attr("text-anchor", "middle")
    .text("Million metric tons CO2e per year");

  // Stacked areas
  const rows = forecast.map(convertToAreas);
  const stack = d3.stack().keys(AREAS.map((a) => a.key));
  const area = d3.area()
    .x((d) => x(d.data.year))
    .y0((d) => y(d[0])).y1((d) => y(d[1]));
  g.selectAll("path.area")
    .data(stack(rows))
    .join("path")
    .attr("class", "area")
    .attr("d", area)
    .attr("fill", (_, i) => AREAS[i].color);

  // The goal line
  const goal = BASELINE.totals.goal_mmt;
  g.append("line").attr("class", "goal-line")
    .attr("x1", 0).attr("x2", innerW)
    .attr("y1", y(goal)).attr("y2", y(goal))
    .attr("stroke", GOAL_COLOR);
  g.append("text").attr("class", "goal-label")
    .attr("x", innerW - 4).attr("y", y(goal) - 6)
    .attr("text-anchor", "end").attr("fill", GOAL_COLOR)
    .text(`2040 goal: ${goal.toFixed(1)} MMT (62% below 2017)`);

  // Labels for the start and end totals
  const start = forecast[0].total;
  const end = forecast[forecast.length - 1].total;
  g.append("text").attr("class", "total-label")
    .attr("x", x(BASELINE.baseline_year) + 6).attr("y", y(start) - 6)
    .text(`${start.toFixed(1)} in 2017`);
  g.append("text").attr("class", "total-label")
    .attr("x", x(BASELINE.goal_year) - 4).attr("y", y(end) - 6)
    .attr("text-anchor", "end")
    .text(`${end.toFixed(1)} in 2040`);
}

/*
 * Fill the legend above the chart with the color and name for each area.
 */
function buildLegend() {
  const items = d3.select("#legend").selectAll("span")
    .data(AREAS).join("span").attr("class", "legend-item");
  items.append("span").attr("class", "swatch")
    .style("background", (d) => d.color);
  items.append("span").text((d) => d.label);
}

// =========================================================================
// RESULT MESSAGE
// =========================================================================

const PERCENT = 100;

/*
 * Display a result message under the chart.
 */
function displayResult(forecast) {
  const result = summarize(forecast, BASELINE);
  const below = (1 - result.total2040 / BASELINE.totals.city_mmt) * PERCENT;
  const resultBox = document.getElementById("result");
  resultBox.classList.toggle("met", result.meetsGoal);
  resultBox.classList.toggle("missed", !result.meetsGoal);

  const title = result.meetsGoal
    ? `Goal met: ${Math.abs(result.gap).toFixed(1)} MMT under the target.`
    : `Goal missed by ${result.gap.toFixed(1)} MMT.`;

  let needed;
  if (result.buildingsNeeded > 1) {
    needed = "Buildings alone cannot reach the goal. Even zero building " +
      "emissions would leave the city above the goal unless the other " +
      "sectors fall too.";
  } else {
    needed = "For the city to meet the 2040 goal with the other sectors as " +
      `set, buildings would need to fall ${(result.buildingsNeeded * PERCENT)
        .toFixed(0)}%.`;
  }

  resultBox.innerHTML =
    `<p class="title">${title}</p>` +
    `<p>Based on the selected emissions reduction efforts, the city emits` +
    `<strong>${result.total2040.toFixed(1)} MMT</strong> in 2040, ` +
    `<strong>${below.toFixed(0)}% below</strong> 2017 emissions. The goal is ` +
    `${result.goal.toFixed(1)} MMT (62% below).</p>` +
    `<p>Residential and commercial buildings reduce emissions by  <strong>` +
    `${(result.buildingsDrop * PERCENT).toFixed(0)}%</strong>. ${needed}</p>`;
}

// =========================================================================
// RUN THE PAGE
// =========================================================================


// Set once the data has loaded.
let BASELINE;
let PRESETS;

/*
 * Start the page with the loaded data and the "current trend" preset.
 */
function start(baseline) {
  BASELINE = baseline;
  PRESETS = getPresets(baseline);
  buildSliders();
  buildPresetButtons();
  buildLegend();
  applyPreset("currentTrend");
  // Redraw at the new width when the window is resized
  window.addEventListener("resize", update);
}

/*
 * Reads the slider positions, runs the simulation, and redraws everything.
 */
function update() {
  const forecast = runSimulation(readSliderPositions(), BASELINE);
  drawChart(forecast);
  displayResult(forecast);
}

// Fetching only works over http, not when the file is opened from disk
fetch("data/baseline.json")
  .then((response) => {
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  })
  .then(start)
  .catch((error) => {
    document.getElementById("result").innerHTML =
      "<p class=\"result\">Could not load data/baseline.json (" +
      error.message + "). Open this page through a web server, for " +
      "example VS Code's Live Server, instead of opening the file " +
      "directly.</p>";
  });
