# Christine Tsai

## Description

I'm interested in exploring and analyzing the energy use and efficiency of buildings in Chicago and doing some comparative analysis between different neighborhoods or between Chicago and San Francisco.

## Data Sources

### Data Source 1: Chicago Energy Benchmarking (Chicago Data Portal)

URL: https://data.cityofchicago.org/Environment-Sustainable-Development/Chicago-Energy-Benchmarking/xq83-jr8c/about_data

Size: **28,330** rows, **30** columns

This dataset is owned by the City of Chicago Sustainability Program and covers the time period of 2014-2023. Benchmarking data is collected annually from municipal, commercial, and residential buildings larger than 50,000 square feet. Data accuracy is verified every three years.

Helpful terms to know:
- Site EUI (Site Energy Use Intensity) is a building's annual energy use divided by its size.

Initial ideas for visuals:
- mix of energy sources over time
- scatter plot of building age vs Site EUI
- site EUI or GHG emissions by neighborhood

### Data Source 2: San Francisco Municipal Energy Benchmarking (DataSF Open Data Portal)

URL: https://data.sf.gov/Energy-and-Environment/San-Francisco-Municipal-Energy-Benchmarking/bfhx-j6n5/about_data

Size: **3,871** rows, **32** columns

This dataset is owned by the San Francisco Public Utilities Commission and covers the time period of 2011 to 2026. Data changes annually and is published monthly. It covers non-municipal buildings which includes commercial buildings larger than 10,000 square feet and multifamily and mixed-use buildings larger than 50,000 square feet.

### Data Source 3: Community Areas (Chicago Data Portal)

URL: https://data.cityofchicago.org/Facilities-Geographic-Boundaries/Boundaries-Community-Areas-Map/cauq-8yn6

Size: **77** rows, **6** columns

This is a dataset containing the geometries of Chicago's community areas. This will be used to map Chicago's buildings to specific community areas.

## Questions

1. I'm mostly interested in comparing energy use between different neighborhoods/community areas in Chicago, but it could also be interesting to do some high-level comparisons with another city that is known to be energy-efficient. Do you think it's interesting or necessary to include the comparative analysis with San Francisco?
2. The Chicago Data Portal has a map for both community areas and neighborhoods. Chicago has 77 distinct community areas which are official boundaries used by the city and over 200 neighborhoods which are unofficial, continuously changing boundaries. Neighborhoods are more colloquially known (e.g. Avondale, Lakeview, Wicker Park) but community areas are more distinct and official. My gut is saying that community areas are best for this use case, but any thoughts between these two boundaries?