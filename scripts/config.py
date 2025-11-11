"""
Central configuration for all scripts in the Prediction League project.

This module provides season-related configuration that is used across multiple scripts.
Update CURRENT_SEASON here when transitioning to a new season.
"""

# Current Premier League season
CURRENT_SEASON = "2025/2026"


def get_football_data_url_code():
    """
    Convert season to football-data.co.uk URL format.

    The football-data.co.uk API uses a specific URL pattern:
    https://www.football-data.co.uk/mmz4281/XXYY/E0.csv

    Where XXYY is the last 2 digits of both years in the season.

    Examples:
        2025/2026 season -> '2526'
        2026/2027 season -> '2627'

    Returns:
        str: Four-digit code for the current season (e.g., '2526')
    """
    year1, year2 = CURRENT_SEASON.split('/')
    return year1[-2:] + year2[-2:]


def get_season_dropbox_format():
    """
    Convert season to Dropbox directory format.

    Dropbox directories use underscores instead of slashes.

    Examples:
        2025/2026 -> '2025_26'
        2026/2027 -> '2026_27'

    Returns:
        str: Season formatted for Dropbox paths (e.g., '2025_26')
    """
    return CURRENT_SEASON.replace('/', '_')


def get_season_database_format():
    """
    Get season in database format.

    The database uses the standard slash format.
    This function exists for completeness and clarity.

    Returns:
        str: Season formatted for database queries (e.g., '2025/2026')
    """
    return CURRENT_SEASON
