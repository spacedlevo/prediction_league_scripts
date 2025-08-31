WITH CTE AS (
    SELECT 
        p.web_name,
        p.total_points,
        p.minutes,
        p.minutes / 90 AS per90,
        p.form,
        p.selected_by_percent,
        p.goals_scored,
        ps.expected_goals,
        p.assists,
        ps.expected_assists,
        ps.expected_goal_involvements,
        p.now_cost,
        p.bps,
        p.bonus
    FROM 
        players AS p
    JOIN player_scores AS ps ON ps.player_id = p.id
    WHERE 
        p.position = 'MID'
        AND p.chance_of_playing_next_round = 100
		AND now_cost <= 84
    ORDER BY 
        p.form DESC
)
SELECT 
    web_name,
    total_points,
    minutes,
    per90,
    form,
    selected_by_percent,
    goals_scored,
    SUM(expected_goals) AS xG,
	assists,
    SUM(expected_assists) AS xA,
    SUM(expected_goal_involvements) AS xGI,
    now_cost,
    bps,
    bonus
FROM 
    CTE
GROUP BY 
    web_name,
    total_points,
    minutes,
    per90,
    form,
    selected_by_percent,
    goals_scored,
    assists,
    now_cost,
    bps,
    bonus
ORDER BY form DESC
