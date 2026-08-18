-- Season League Table for Predictions League
-- Scoring: 1 point for correct result + 3 points for correct score
-- Players who did not submit a prediction for a fixture receive 0 points for that fixture

WITH prediction_points AS (
    SELECT
        pl.player_name,
        p.fixture_id,
        p.home_goals,
        p.away_goals,
        r.home_goals AS actual_home,
        r.away_goals AS actual_away,
        r.result,

        -- Calculate predicted result
        CASE
            WHEN p.home_goals > p.away_goals THEN 'H'
            WHEN p.home_goals < p.away_goals THEN 'A'
            WHEN p.home_goals = p.away_goals THEN 'D'
        END AS predicted_result,

        -- Points for correct result (1 point)
        CASE
            WHEN (p.home_goals > p.away_goals AND r.result = 'H') OR
                 (p.home_goals < p.away_goals AND r.result = 'A') OR
                 (p.home_goals = p.away_goals AND r.result = 'D')
            THEN 1
            ELSE 0
        END AS result_points,

        -- Points for correct score (3 points)
        CASE
            WHEN p.home_goals = r.home_goals AND p.away_goals = r.away_goals
            THEN 3
            ELSE 0
        END AS score_points

    FROM predictions p
    JOIN fixtures f ON p.fixture_id = f.fixture_id
    JOIN players pl ON p.player_id = pl.player_id
		AND pundit <> 1
    JOIN results r ON f.fixture_id = r.fixture_id
    WHERE f.season = '2025/2026'
      AND r.home_goals IS NOT NULL
      AND r.away_goals IS NOT NULL
      AND r.result IS NOT NULL
),

player_totals AS (
    SELECT
        player_name,
        COUNT(*) AS games_predicted,
        SUM(result_points) AS correct_results,
        SUM(score_points) AS correct_scores,
        SUM(result_points + score_points) AS total_points

    FROM prediction_points
    GROUP BY player_name
)

SELECT
    ROW_NUMBER() OVER (ORDER BY total_points DESC, correct_scores DESC, games_predicted DESC) AS position,
    player_name,
    total_points,
    correct_results,
    correct_scores,
    games_predicted,

    -- Calculate percentages
    ROUND(CAST(correct_results AS FLOAT) / games_predicted * 100, 1) AS result_accuracy_pct,
    ROUND(CAST(correct_scores AS FLOAT) / games_predicted * 100, 1) AS score_accuracy_pct,
    ROUND(CAST(total_points AS FLOAT) / games_predicted, 2) AS points_per_game

FROM player_totals
WHERE games_predicted > 0
ORDER BY total_points DESC, correct_scores DESC, games_predicted DESC;