"""
categories.py

Groups the benchmarking data's property types into six broader building
categories, and gives long property type names shorter display names.
"""

import pandas as pd

# Category for any property type that is not listed below
FALLBACK_CATEGORY = "Specialty & Other"

# Category display order, used for chart panels and sorting
CATEGORY_ORDER = [
    "Residential",
    "Office",
    "Retail & Hospitality",
    "Education & Civic",
    "Healthcare",
    "Specialty & Other",
]

# The property types in each category
CATEGORY_MEMBERS = {
    "Residential": [
        "Multifamily Housing",
        "Senior Living Community",
        "Senior Care Community",
        "Residence Hall/Dormitory",
        "Residential Care Facility",
        "Other - Lodging/Residential",
    ],
    "Office": [
        "Office",
        "Financial Office",
        "Bank Branch",
    ],
    "Retail & Hospitality": [
        "Hotel",
        "Supermarket/Grocery Store",
        "Retail Store",
        "Commerce de détail",
        "Strip Mall",
        "Enclosed Mall",
        "Lifestyle Center",
        "Other - Mall",
        "Wholesale Club/Supercenter",
        "Vehicle Dealership",
        "Automobile Dealership",
        "Repair Services (Vehicle, Shoe, Locksmith, etc.)",
    ],
    "Education & Civic": [
        "K-12 School",
        "College/University",
        "Adult Education",
        "Pre-school/Daycare",
        "Other - Education",
        "Library",
        "Museum",
        "Performing Arts",
        "Movie Theater",
        "Worship Facility",
        "Social/Meeting Hall",
        "Convention Center",
        "Fitness Center/Health Club/Gym",
        "Ice/Curling Rink",
        "Indoor Arena",
        "Stadium (Open)",
        "Other - Entertainment/Public Assembly",
        "Other - Recreation",
        "Courthouse",
        "Prison/Incarceration",
        "Other - Public Services",
    ],
    "Healthcare": [
        "Hospital (General Medical & Surgical)",
        "Other - Specialty Hospital",
        "Medical Office",
        "Outpatient Rehabilitation/Physical Therapy",
        "Urgent Care/Clinic/Other Outpatient",
        "Ambulatory Surgical Center",
    ],
    "Specialty & Other": [
        "Laboratory",
        "Data Center",
        "Distribution Center",
        "Mixed Use Property",
        "Other",
        "Other - Services",
        "Not Available",
    ],
}

# Reverse lookup (property type -> category), built once when imported
PROPERTY_TYPE_TO_CATEGORY = {
    property_type: category
    for category, members in CATEGORY_MEMBERS.items()
    for property_type in members
}

# Shorter display names for property types with long or all-caps labels
SHORT_TYPE_NAMES = {
    "Multifamily Housing": "Multifamily housing",
    "Senior Living Community": "Senior living",
    "Residence Hall/Dormitory": "Dormitory",
    "Residential Care Facility": "Residential care",
    "Strip Mall": "Strip mall",
    "Enclosed Mall": "Enclosed mall",
    "Retail Store": "Retail store",
    "Supermarket/Grocery Store": "Supermarket",
    "Wholesale Club/Supercenter": "Wholesale club",
    "K-12 School": "K-12 school",
    "College/University": "College/university",
    "Performing Arts": "Performing arts",
    "Movie Theater": "Movie theater",
    "Worship Facility": "Worship facility",
    "Fitness Center/Health Club/Gym": "Fitness center",
    "Hospital (General Medical & Surgical)": "Hospital",
    "Other - Specialty Hospital": "Specialty hospital",
    "Medical Office": "Medical office",
    "Outpatient Rehabilitation/Physical Therapy": "Outpatient rehab",
    "Urgent Care/Clinic/Other Outpatient": "Urgent care/clinic",
    "Other - Entertainment/Public Assembly": "Entertainment venue",
    "Data Center": "Data center",
    "Convention Center": "Convention center",
    "Mixed Use Property": "Mixed use",
}


def add_category_column(df):
    """
    Add the building category and a short display name for each building.

    Inputs: a DataFrame with a "primary_property_type" column.
    Output: a copy with two added columns: "category" (an ordered
        categorical following CATEGORY_ORDER) and "type_label" (the short
        display name of the property type). Property types not listed
        above get FALLBACK_CATEGORY and keep their original name.
    """
    result = df.copy()
    categories = result["primary_property_type"].map(PROPERTY_TYPE_TO_CATEGORY)
    result["category"] = pd.Categorical(
        categories.fillna(FALLBACK_CATEGORY),
        categories=CATEGORY_ORDER,
        ordered=True,
    )
    result["type_label"] = result["primary_property_type"].replace(
        SHORT_TYPE_NAMES
    )
    return result
