SELECT 
	player_name
	,SUM(total_points) [pts]
FROM 
	player_scores
WHERE	
	gameweek BETWEEN 20 AND 23
GROUP BY 
	player_name
ORDER BY 2 DESC