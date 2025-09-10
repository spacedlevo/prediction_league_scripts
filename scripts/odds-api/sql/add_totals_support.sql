-- Migration script to add over/under (totals) market support to odds table
-- Author: Claude Code
-- Date: 2025-09-10

-- Add new columns to support totals markets
ALTER TABLE odds ADD COLUMN total_line REAL DEFAULT NULL;
ALTER TABLE odds ADD COLUMN outcome_type TEXT DEFAULT NULL;

-- Create index for efficient totals queries
CREATE INDEX IF NOT EXISTS idx_odds_totals ON odds(bet_type, total_line, outcome_type);

-- Update bet_type to support new market types:
-- Existing: 'home win', 'away win', 'draw'  
-- New: 'over', 'under'

-- total_line examples: 2.5, 3.5, 1.5 (goals line)
-- outcome_type examples: 'over', 'under' (for totals markets)

-- For h2h markets: total_line=NULL, outcome_type=NULL (existing behavior)
-- For totals markets: bet_type='over'/'under', total_line=2.5, outcome_type='over'/'under'

-- Verify the migration worked
-- SELECT name, type FROM pragma_table_info('odds') WHERE name IN ('total_line', 'outcome_type');