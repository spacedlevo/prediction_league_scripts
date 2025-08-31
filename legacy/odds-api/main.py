import requests
import json
import csv
import statistics
import os
from dotenv import load_dotenv

load_dotenv()


def get_uefa_european_championship_odds(api_key):
    url = "https://api.the-odds-api.com/v4/sports/soccer_uefa_champs_league/odds"
    params = {"regions": "uk", "oddsFormat": "decimal", "apiKey": api_key}

    response = requests.get(url, params=params)

    if response.status_code == 200:
        odds_data = response.json()
        return odds_data
    else:
        print(f"Failed to retrieve data: {response.status_code}")
        return None


def write_to_csv(jsondata):
    # Prepare the header for the CSV
    header = ["id", "Game", "Home Team", "Away Team"]
    bookmakers = set()

    # Extract all unique bookmaker titles
    for match in jsondata:
        for bookmaker in match["bookmakers"]:
            bookmakers.add(bookmaker["title"])

    # Create header columns for each bookmaker's home win, draw, and away win odds
    for bookmaker in bookmakers:
        header.extend(
            [f"{bookmaker} home win", f"{bookmaker} draw", f"{bookmaker} away win"]
        )

    # Add columns for mean and median calculations
    header.extend(
        [
            "home win mean",
            "draw mean",
            "away win mean",
            "home win median",
            "draw median",
            "away win median",
        ]
    )

    # Write data to CSV
    with open("uefa_odds.csv", "w", newline="") as csvfile:
        csvwriter = csv.writer(csvfile)

        # Write the header row
        csvwriter.writerow(header)

        for match in jsondata:
            row = [
                match["id"],
                f"{match['home_team']} vs {match['away_team']}",
                match["home_team"],
                match["away_team"],
            ]
            odds = {
                bookmaker: {"home win": None, "draw": None, "away win": None}
                for bookmaker in bookmakers
            }

            for bookmaker in match["bookmakers"]:
                title = bookmaker["title"]
                for market in bookmaker["markets"]:
                    if market["key"] == "h2h":
                        for outcome in market["outcomes"]:
                            if outcome["name"] == match["home_team"]:
                                odds[title]["home win"] = outcome["price"]
                            elif outcome["name"] == match["away_team"]:
                                odds[title]["away win"] = outcome["price"]
                            elif outcome["name"] == "Draw":
                                odds[title]["draw"] = outcome["price"]

            home_win_odds = [
                odds[bookmaker]["home win"]
                for bookmaker in bookmakers
                if odds[bookmaker]["home win"] is not None
            ]
            draw_odds = [
                odds[bookmaker]["draw"]
                for bookmaker in bookmakers
                if odds[bookmaker]["draw"] is not None
            ]
            away_win_odds = [
                odds[bookmaker]["away win"]
                for bookmaker in bookmakers
                if odds[bookmaker]["away win"] is not None
            ]

            home_win_mean = (
                round(statistics.mean(home_win_odds), 2) if home_win_odds else None
            )
            draw_mean = round(statistics.mean(draw_odds), 2) if draw_odds else None
            away_win_mean = (
                round(statistics.mean(away_win_odds), 2) if away_win_odds else None
            )

            home_win_median = (
                statistics.median(home_win_odds) if home_win_odds else None
            )
            draw_median = statistics.median(draw_odds) if draw_odds else None
            away_win_median = (
                statistics.median(away_win_odds) if away_win_odds else None
            )

            for bookmaker in bookmakers:
                row.extend(
                    [
                        odds[bookmaker]["home win"],
                        odds[bookmaker]["draw"],
                        odds[bookmaker]["away win"],
                    ]
                )

            row.extend(
                [
                    home_win_mean,
                    draw_mean,
                    away_win_mean,
                    home_win_median,
                    draw_median,
                    away_win_median,
                ]
            )

            csvwriter.writerow(row)


if __name__ == "__main__":

    # Replace with your API key
    api_key = os.getenv("MY_API_KEY")

    # Get odds from the API
    odds = get_uefa_european_championship_odds(api_key)

    if odds:
        write_to_csv(odds)
