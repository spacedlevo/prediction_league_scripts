SELECT 
	match_id
	,ht.name [home_team]
	,at.name [away_team]
	,bet_type
	,kickoffTime
	,B.name [bookmaker]
FROM 
	odds AS O
	JOIN team AS HT on HT.id = O.home_team_id
	JOIN team AS AT ON AT.id = O.away_team_id
	JOIN bookmaker AS B on B.id = O.bookmaker_id
WHERE 
	market = 'soccer_epl'