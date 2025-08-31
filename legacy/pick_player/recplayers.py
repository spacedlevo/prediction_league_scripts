import sqlite3
import pandas as pd


def connect_db(db_path="fpl_players.db"):
    """Connect to SQLite database."""
    return sqlite3.connect(db_path)


def get_current_team(conn):
    """Retrieve the list of players currently in the team."""
    query = """
    SELECT * FROM players WHERE in_team = 1
    """
    return pd.read_sql(query, conn)


def get_transfer_candidates(conn):
    """Retrieve potential transfer candidates who are not in the team."""
    query = """
    SELECT p.*, t.strength FROM players p
    JOIN teams t ON p.team = t.team_id
    WHERE 
        p.in_team = 0 AND p.chance_of_playing_next_round >= 75
        AND p.position != 'MNG'
        AND p.minutes > 300
    ORDER BY p.form DESC, p.points_per_game DESC
    """
    return pd.read_sql(query, conn)


def get_fixtures(conn):
    """Retrieve upcoming fixtures."""
    query = """
    SELECT * FROM fixtures WHERE finished = 0
    """
    return pd.read_sql(query, conn)


def recommend_transfers(conn, budget=100, max_per_team=3):
    """Recommend players based on form, budget, and fixture difficulty."""
    current_team = get_current_team(conn)
    transfer_candidates = get_transfer_candidates(conn)
    fixtures = get_fixtures(conn)

    # Calculate available budget
    # spent_budget = current_team["now_cost"].sum() / 10  # Convert to million format
    # available_budget = budget - spent_budget

    # Team count to enforce max 3 players per team
    team_counts = current_team["team"].value_counts().to_dict()

    # Filter candidates based on budget and team constraints
    valid_transfers = []
    for _, player in transfer_candidates.iterrows():
        team_id = player["team"]
        if team_counts.get(team_id, 0) < max_per_team:
            valid_transfers.append(player)

    # Sort recommendations by form, expected goals, and fixture difficulty
    recommended_players = sorted(
        valid_transfers,
        key=lambda x: (-x["form"], -x["expected_goal_involvement"], x["team"]),
        reverse=False,
    )

    return recommended_players[:5]  # Return top 5 recommendations


def main():
    conn = connect_db()
    recommendations = recommend_transfers(conn)

    print("Top Transfer Recommendations:")
    for player in recommendations:
        print(
            f"{player['first_name']} {player['second_name']} - {player['position']} - Cost: {player['now_cost']/10}M - Form: {player['form']}"
        )

    conn.close()


if __name__ == "__main__":
    main()
