-- Migration script to add Over/Under 2.5 odds to fixture_odds_summary table
-- Author: Claude Code  
-- Date: 2025-09-10

-- Add new columns for Over/Under 2.5 odds averages
ALTER TABLE fixture_odds_summary ADD COLUMN avg_over_2_5_odds REAL DEFAULT NULL;
ALTER TABLE fixture_odds_summary ADD COLUMN avg_under_2_5_odds REAL DEFAULT NULL;

-- Create index for efficient totals queries
CREATE INDEX IF NOT EXISTS idx_fixture_odds_totals ON fixture_odds_summary(avg_over_2_5_odds, avg_under_2_5_odds);

-- Update existing records with totals data from odds table
UPDATE fixture_odds_summary 
SET 
    avg_over_2_5_odds = (
        SELECT AVG(price) 
        FROM odds o 
        WHERE o.fixture_id = fixture_odds_summary.fixture_id 
        AND o.bet_type = 'over' 
        AND o.total_line = 2.5
        AND o.price IS NOT NULL
    ),
    avg_under_2_5_odds = (
        SELECT AVG(price) 
        FROM odds o 
        WHERE o.fixture_id = fixture_odds_summary.fixture_id 
        AND o.bet_type = 'under' 
        AND o.total_line = 2.5  
        AND o.price IS NOT NULL
    );

-- Verify the migration worked
-- SELECT fixture_id, avg_over_2_5_odds, avg_under_2_5_odds 
-- FROM fixture_odds_summary 
-- WHERE avg_over_2_5_odds IS NOT NULL 
-- LIMIT 5;