"""
theme.py

Shared visual theme for every chart: the color palette, the color scale
for fuels, and the Altair theme (fonts, axes, legends, and titles).

Usage: call apply_theme() once before building any chart
"""

import altair as alt

# Theme based off Chicago flag colors with energy adjacent accents (amber = electricity, flame = natural gas, green = clean energy)
FLAG_BLUE = "#41B6E6"
STAR_RED = "#E4002B"
DEEP_BLUE = "#1C7FB5"
AMBER = "#F5B700"
FLAME = "#F2792B"
GREEN = "#2E9E6B"
GRAY = "#8D99AE"
CHARCOAL = "#4A5568"

# Poorly rated buildings (1 star) use this red on the map and the priority chart
POOR_RATING_COLOR = STAR_RED
INK, MUTED, GRID = "#1B2A3A", "#6B7785", "#E6E9ED"

def build_theme_config():
    """
    Altair theme used by every chart: fonts, axes, legends, and titles.

    Inputs: none.
    Output: an Altair theme configuration.
    """
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


def apply_theme():
    """
    Register the project's Altair theme and make it the active theme.

    Inputs: none.
    Output: none (changes Altair's active theme).
    """
    alt.theme.register("chi_bench_theme", enable=True)(build_theme_config)
