import requests
import pandas as pd
import numpy as np

# Fetch data from the FPL API
FPL_API_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
response = requests.get(FPL_API_URL)
data = response.json()

# Load data into DataFrames
players = pd.DataFrame(data["elements"])
teams = pd.DataFrame(data["teams"])
element_types = pd.DataFrame(data["element_types"])

# Add team and position information to the players DataFrame
players["team"] = players["team"].map(teams.set_index("id")["name"])
players["position"] = players["element_type"].map(
    element_types.set_index("id")["singular_name"]
)

# Select relevant columns for analysis
players = players[
    [
        "id",
        "first_name",
        "second_name",
        "team",
        "position",
        "now_cost",
        "total_points",
        "points_per_game",
        "form",
        "selected_by_percent",
        "minutes",
        "expected_goals",
        "expected_assists",
        "influence",
        "creativity",
        "threat",
    ]
]

# Rename columns for better readability
players.rename(
    columns={
        "first_name": "First Name",
        "second_name": "Second Name",
        "now_cost": "Cost",
        "total_points": "Total Points",
        "points_per_game": "PPG",
        "form": "Form",
        "selected_by_percent": "Ownership",
        "expected_goals": "xG",
        "expected_assists": "xA",
    },
    inplace=True,
)

# Convert cost to millions (e.g., 100 -> 10.0)
players["Cost"] = players["Cost"] / 10

# Filter out players with very few minutes played
MIN_MINUTES = 300
players = players[players["minutes"] > MIN_MINUTES]

# Print out column names and data types
print(players.dtypes)
# Convert Form and PPG to floats
players["Form"] = players["Form"].astype(float)
players["PPG"] = players["PPG"].astype(float)


# Sort players by a custom metric (e.g., Form + PPG per Cost)
def calculate_metric(row):
    return (row["Form"] + row["PPG"]) / row["Cost"]


players["Value Metric"] = players.apply(calculate_metric, axis=1)
players = players.sort_values("Value Metric", ascending=False)


# Recommend top players by position
def recommend_players_by_position(players, position, top_n=5):
    position_players = players[players["position"] == position]
    return position_players.head(top_n)


# Output recommendations
print("Top 5 Forwards:")
print(recommend_players_by_position(players, "Forward"))

print("\nTop 5 Midfielders:")
print(recommend_players_by_position(players, "Midfielder"))

print("\nTop 5 Defenders:")
print(recommend_players_by_position(players, "Defender"))

print("\nTop 5 Goalkeepers:")
print(recommend_players_by_position(players, "Goalkeeper"))

# Save the recommendations to an Excel file
with pd.ExcelWriter("player_recommendations.xlsx") as writer:
    recommend_players_by_position(players, "Forward").to_excel(
        writer, sheet_name="Top 5 Forwards", index=False
    )
    recommend_players_by_position(players, "Midfielder").to_excel(
        writer, sheet_name="Top 5 Midfielders", index=False
    )
    recommend_players_by_position(players, "Defender").to_excel(
        writer, sheet_name="Top 5 Defenders", index=False
    )
    recommend_players_by_position(players, "Goalkeeper").to_excel(
        writer, sheet_name="Top 5 Goalkeepers", index=False
    )
