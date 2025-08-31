SELECT
	ht.team_name [Home Team]
	,at.team_name [Away Team]
	,avg_home_win_odds
	,avg_away_win_odds
	,kickoff_dttm
	,gameweek
	,season
FROM
	fixture_odds_summary AS FOS
		JOIN teams AS HT on HT.team_id = FOS.home_team_id
		JOIN teams AS AT on AT.team_id = FOS.away_team_id
		JOIN fixtures AS F ON F.fixture_id = FOS.fixture_id
WHERE 
	season = ?
	AND gameweek = ?