"""Shared constants for the SENTINEL platform."""

DISTRICTS = ["Central", "North", "South", "East", "West", "Harbor"]

# District centroids (must match data-generator/generate.py).
DISTRICT_CENTERS = {
    "Central": (40.758, -73.973),
    "North":   (40.802, -73.965),
    "South":   (40.705, -73.992),
    "East":    (40.752, -73.918),
    "West":    (40.751, -74.018),
    "Harbor":  (40.690, -74.040),
}

# Assumed responder capacity per district (max incidents/hour before strain).
# Used for the demand-vs-capacity forecast.
CAPACITY = {
    "Central": 8,
    "North": 6,
    "South": 5,
    "East": 5,
    "West": 5,
    "Harbor": 4,
}

TYPES = ["medical", "fire", "police", "hazmat", "traffic"]
