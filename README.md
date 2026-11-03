# Chicago Building Energy Analysis

### Author: Christine Tsai

## Description

This project seeks to find where Chicago can potentially cut emissions from its
buildings, which produce about two-thirds of the City's greenhouse gas
emissions. This analysis uses Chicago Energy Benchmarking data to examine trends
in the City's large building energy use over time and by property types. It
shows where the reporting buildings are and how their emissions changed from
2018 to 2023, then compares fuels and property types to see what drives
emissions. It ends by picking out the biggest emitters, and the poorly rated
buildings among them, as places to start reducing emissions.

![Screenshot of the final page](static-viz/final-screenshot.png)

## How to run

From the repository root, run two commands. The first reads the files in `data/` and writes all nine charts as PNG files to `static-viz/charts/`:

```
uv run python src/final_graphs.py
```

The second calculates every number quoted in the page text, saves them to `static-viz/text_numbers.json`, and fills them into the page template `static-viz/index_template.html` to write `static-viz/index.html`:

```
uv run python src/text_numbers.py
```


## Data Sources

- City of Chicago. (2025). *Chicago Energy Benchmarking* [Data set]. Chicago Data Portal. https://data.cityofchicago.org/Environment-Sustainable-Development/Chicago-Energy-Benchmarking/xq83-jr8c
  - Used for every chart except the sector totals. Saved in `data/Chicago_Energy_Benchmarking_20261001.csv` (downloaded October 1, 2026; last updated by the city February 5, 2025). Most charts use the 2023 data year, and the trend uses 2018 to 2023.
- Chicago Metropolitan Agency for Planning. (2022). *Regional greenhouse gas emissions inventory: Updated with 2019 data*. https://cmap.illinois.gov/wp-content/uploads/Greenhouse_Gas_Emission_Inventory_2022.pdf
  - Used for the citywide emissions by sector chart. The City of Chicago column of the report's "Regional greenhouse gas inventory" table (page 14, million metric tons CO2e) is saved in `data/cmap_2019_ghg_inventory.csv`. `data/chicago_emissions_by_sector_2019.csv` groups those rows into the pieces the chart shows:
    - Residential buildings, commercial and institutional buildings, on-road vehicles, and waste are copied directly from the table.
    - "Industry & other" is shown as its own sector, separate from buildings. It is the stationary energy total (18.72) minus residential (6.55) and commercial and institutional (10.45), which leaves 1.72 (mostly manufacturing, wastewater, and fugitive emissions).
    - "Other" transportation is the transportation total (7.76) minus on-road (5.11), which leaves 2.65 (aviation, rail, and off-road).
    - The six pieces add up to CMAP's citywide total of 27.49.
- City of Chicago. (2026). *Boundaries - Community Areas* [Data set]. Chicago Data Portal. https://data.cityofchicago.org/resource/igwz-8jzy
  - Used for the community area shapes and centers in the bubble map. Saved in `data/chicago_community_areas.geojson`; `src/final_graphs.py` downloads it from the portal if the file is missing. Last updated by the city March 25, 2026.
- U.S. Environmental Protection Agency. (2026). *Greenhouse Gas Equivalencies Calculator: Calculations and References* (last updated August 4, 2026; accessed October 2026). https://www.epa.gov/energy/greenhouse-gases-equivalencies-calculator-calculations-and-references
  - Used for the "equivalent cars driven for a year" comparison: 4.29 metric tons CO2e per gasoline-powered passenger vehicle per year (`TONS_CO2E_PER_CAR_YEAR` in `src/final_graphs.py`).


## How feedback was incorporated

The draft charts and peer feedback are in `milestones/`.

| Current figure | Draft chart | What changed |
|---|---|---|
| Figure 1, emissions by sector | New (no draft) | Added for context |
| Figure 2, bubble map | 1. Building dot map; 2.2 Choropleth; 7. Rating stacked bar | Dot map replaced by a bubble map by community area to reduce clutter, notable areas labeled, emissions removed from the chart |
| Figure 3, same-building trend | 9. Same-building trend | Each building compared with its own 2018 level, plain line names instead of "Site EUI" and "GHG intensity", plain y-axis title, labeled line ends, dashed line showing emissions if the grid had stayed at its 2018 level, terms box defining the emission factor |
| Figure 4, fuel mix | 8. Fuel mix | Stacked bars by building category replaced by two donuts for all buildings, one for energy and one for emissions, small fuels grouped and labeled as "Other fuels", unused fuels left out of the legend |
| Figure 5, emissions by type | 4. Emissions by type | Top 15 property types shown, largest two highlighted, bars labeled, long names shortened, second axis converting tons to equivalent cars per year, average emissions per building added beside the totals |
| Figure 6, emissions per square foot | 5. Box plot by type | Six building categories replaced by ten property types to reduce clutter, sorted by median, building counts in the labels, labeled dashed line at the median of all buildings, outliers removed, caption explaining the box, median line and whiskers |
| Figure 7, cumulative curve | 10. Pareto curve | Three marked points (top 1%, 5% and 10%) labeled with building counts and shares of emissions, percent signs on the axes, title rewritten to describe the chart |
| Figure 8, top emitters and poorly rated buildings | 11. Priority buildings | Kept as a scatter with plain labels, one dot size for highlighted buildings, a labeled dashed line where top emitters begin, the largest buildings in both groups named, log axes kept on purpose with a subtitle explaining them, poorly rated limited to 1 star because 0 stars mark missing reports |
| Figure 9, reduction potential | New (no draft) | Added as a closing view of where the reducible emissions are |
| Removed | 2.1 Choropleth; 3. GHG choropleth; 6. Building age scatter | Removed |
