#!/usr/bin/env python3
"""
Gameweek Validation Utility

Validates current gameweek accuracy by checking deadlines against current time.
Detects when FPL API hasn't updated gameweek flags after deadline passes.

FUNCTIONALITY:
- Compare deadline timestamps with current time
- Identify gameweeks that should be current but aren't marked as such
- Detect finished gameweeks that should be marked as finished
- Provide recommendations for gameweek updates

USAGE:
- Called by fetch_fixtures_gameweeks.py for validation
- Can be run standalone for debugging
- Returns validation results and recommended actions
"""

import sqlite3 as sql
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Paths
db_path = Path(__file__).parent.parent.parent / "data" / "database.db"

def setup_logging():
    """Setup basic logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def get_gameweek_status(cursor) -> List[Dict]:
    """Get all gameweeks with their current status and deadlines"""
    cursor.execute("""
        SELECT 
            gameweek,
            deadline_dttm,
            current_gameweek,
            next_gameweek,
            finished
        FROM gameweeks
        ORDER BY gameweek
    """)
    
    gameweeks = []
    for row in cursor.fetchall():
        gameweek_data = {
            'gameweek': row[0],
            'deadline_dttm': row[1],
            'current_gameweek': bool(row[2]),
            'next_gameweek': bool(row[3]),
            'finished': bool(row[4])
        }
        gameweeks.append(gameweek_data)
    
    return gameweeks

def parse_deadline(deadline_str: str) -> Optional[datetime]:
    """Parse deadline string to datetime object"""
    if not deadline_str:
        return None
        
    try:
        # Handle FPL API deadline format (with or without 'Z')
        deadline_clean = deadline_str.replace('Z', '')
        deadline_dt = datetime.fromisoformat(deadline_clean)
        
        # Ensure timezone is UTC
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
            
        return deadline_dt
    except (ValueError, TypeError) as e:
        return None

def validate_current_gameweek(gameweeks: List[Dict], logger) -> Dict:
    """Validate which gameweek should be current based on deadlines"""
    now_utc = datetime.now(timezone.utc)
    validation_results = {
        'is_valid': True,
        'current_gameweek': None,
        'should_be_current': None,
        'issues': [],
        'recommendations': []
    }
    
    # Find currently marked gameweek
    current_marked = None
    for gw in gameweeks:
        if gw['current_gameweek']:
            current_marked = gw['gameweek']
            validation_results['current_gameweek'] = current_marked
            break
    
    # Determine which gameweek should be current based on deadlines
    should_be_current = None
    
    # Find the gameweek where deadline has not passed yet (future deadline)
    # or the most recent gameweek if all deadlines have passed
    future_gameweeks = []
    past_gameweeks = []
    
    for gw in gameweeks:
        deadline_dt = parse_deadline(gw['deadline_dttm'])
        if not deadline_dt:
            continue
            
        if deadline_dt > now_utc:
            future_gameweeks.append((gw['gameweek'], deadline_dt))
        else:
            past_gameweeks.append((gw['gameweek'], deadline_dt))
    
    if future_gameweeks:
        # Current gameweek is the one with the earliest future deadline
        future_gameweeks.sort(key=lambda x: x[1])
        should_be_current = future_gameweeks[0][0]
    elif past_gameweeks:
        # All deadlines have passed, current should be the latest gameweek
        past_gameweeks.sort(key=lambda x: x[1], reverse=True)
        should_be_current = past_gameweeks[0][0]
    
    validation_results['should_be_current'] = should_be_current
    
    # Compare marked vs calculated current gameweek
    if current_marked != should_be_current:
        validation_results['is_valid'] = False
        validation_results['issues'].append({
            'type': 'current_gameweek_mismatch',
            'message': f"Gameweek {current_marked} marked as current, but gameweek {should_be_current} should be current based on deadlines",
            'severity': 'high'
        })
        validation_results['recommendations'].append({
            'action': 'update_current_gameweek',
            'details': f"Update current_gameweek flag: set {should_be_current} to TRUE, others to FALSE"
        })
    
    return validation_results

def validate_finished_gameweeks(gameweeks: List[Dict], logger) -> Dict:
    """Validate which gameweeks should be marked as finished"""
    now_utc = datetime.now(timezone.utc)
    validation_results = {
        'is_valid': True,
        'issues': [],
        'recommendations': []
    }
    
    for gw in gameweeks:
        deadline_dt = parse_deadline(gw['deadline_dttm'])
        if not deadline_dt:
            continue
            
        # Check if deadline has passed but gameweek not marked as finished
        if deadline_dt < now_utc and not gw['finished']:
            # Only mark as issue if this is not the current gameweek
            # (current gameweek can have passed deadline but still be active)
            if not gw['current_gameweek']:
                validation_results['is_valid'] = False
                validation_results['issues'].append({
                    'type': 'unfinished_past_gameweek',
                    'message': f"Gameweek {gw['gameweek']} deadline passed but not marked as finished",
                    'severity': 'medium',
                    'gameweek': gw['gameweek'],
                    'deadline': deadline_dt.isoformat()
                })
                validation_results['recommendations'].append({
                    'action': 'mark_gameweek_finished',
                    'details': f"Set gameweek {gw['gameweek']} finished flag to TRUE"
                })
    
    return validation_results

def validate_next_gameweek(gameweeks: List[Dict], current_gameweek: Optional[int], logger) -> Dict:
    """Validate which gameweek should be marked as next"""
    validation_results = {
        'is_valid': True,
        'issues': [],
        'recommendations': []
    }
    
    if not current_gameweek:
        return validation_results
        
    # Next gameweek should be current + 1
    expected_next = current_gameweek + 1
    
    # Find currently marked next gameweek
    marked_next = None
    for gw in gameweeks:
        if gw['next_gameweek']:
            marked_next = gw['gameweek']
            break
    
    # Check if expected next gameweek exists
    next_gameweek_exists = any(gw['gameweek'] == expected_next for gw in gameweeks)
    
    if next_gameweek_exists and marked_next != expected_next:
        validation_results['is_valid'] = False
        validation_results['issues'].append({
            'type': 'next_gameweek_mismatch',
            'message': f"Gameweek {marked_next} marked as next, but gameweek {expected_next} should be next",
            'severity': 'low'
        })
        validation_results['recommendations'].append({
            'action': 'update_next_gameweek',
            'details': f"Update next_gameweek flag: set {expected_next} to TRUE, others to FALSE"
        })
    
    return validation_results

def perform_full_validation(logger) -> Dict:
    """Perform complete gameweek validation"""
    conn = sql.connect(db_path)
    cursor = conn.cursor()
    
    try:
        gameweeks = get_gameweek_status(cursor)
        
        if not gameweeks:
            logger.warning("No gameweeks found in database")
            return {
                'is_valid': False,
                'issues': [{'type': 'no_gameweeks', 'message': 'No gameweeks found in database', 'severity': 'high'}],
                'recommendations': [{'action': 'fetch_gameweeks', 'details': 'Run fetch_fixtures_gameweeks.py to populate gameweeks table'}]
            }
        
        # Validate current gameweek
        current_validation = validate_current_gameweek(gameweeks, logger)
        
        # Validate finished gameweeks
        finished_validation = validate_finished_gameweeks(gameweeks, logger)
        
        # Validate next gameweek
        next_validation = validate_next_gameweek(gameweeks, current_validation['should_be_current'], logger)
        
        # Combine all validation results
        combined_results = {
            'is_valid': current_validation['is_valid'] and finished_validation['is_valid'] and next_validation['is_valid'],
            'current_gameweek': current_validation['current_gameweek'],
            'should_be_current': current_validation['should_be_current'],
            'total_gameweeks': len(gameweeks),
            'validation_timestamp': datetime.now(timezone.utc).isoformat(),
            'issues': current_validation['issues'] + finished_validation['issues'] + next_validation['issues'],
            'recommendations': current_validation['recommendations'] + finished_validation['recommendations'] + next_validation['recommendations']
        }
        
        # Log validation summary
        if combined_results['is_valid']:
            logger.info(f"Gameweek validation passed - Current: GW{combined_results['current_gameweek']}")
        else:
            logger.warning(f"Gameweek validation failed - {len(combined_results['issues'])} issues found")
            for issue in combined_results['issues']:
                logger.warning(f"  {issue['severity'].upper()}: {issue['message']}")
        
        return combined_results
        
    except Exception as e:
        logger.error(f"Error during gameweek validation: {e}")
        return {
            'is_valid': False,
            'issues': [{'type': 'validation_error', 'message': str(e), 'severity': 'high'}],
            'recommendations': [{'action': 'check_database', 'details': 'Verify database connectivity and gameweeks table structure'}]
        }
    finally:
        conn.close()

def should_trigger_api_refresh(validation_results: Dict) -> bool:
    """Determine if FPL API refresh should be triggered based on validation results"""
    if validation_results['is_valid']:
        return False
    
    # Trigger refresh for high severity issues
    high_severity_issues = [issue for issue in validation_results['issues'] if issue.get('severity') == 'high']
    
    return len(high_severity_issues) > 0

def main():
    """Main execution for standalone usage"""
    logger = setup_logging()
    logger.info("Starting gameweek validation...")
    
    validation_results = perform_full_validation(logger)
    
    print(f"\n=== GAMEWEEK VALIDATION REPORT ===")
    print(f"Validation Status: {'PASSED' if validation_results['is_valid'] else 'FAILED'}")
    print(f"Current Gameweek (marked): {validation_results.get('current_gameweek', 'None')}")
    print(f"Should Be Current: {validation_results.get('should_be_current', 'Unknown')}")
    print(f"Total Gameweeks: {validation_results.get('total_gameweeks', 0)}")
    print(f"Validation Time: {validation_results.get('validation_timestamp', 'Unknown')}")
    
    if validation_results['issues']:
        print(f"\n=== ISSUES FOUND ({len(validation_results['issues'])}) ===")
        for i, issue in enumerate(validation_results['issues'], 1):
            print(f"{i}. [{issue.get('severity', 'unknown').upper()}] {issue.get('message', 'Unknown issue')}")
    
    if validation_results['recommendations']:
        print(f"\n=== RECOMMENDATIONS ({len(validation_results['recommendations'])}) ===")
        for i, rec in enumerate(validation_results['recommendations'], 1):
            print(f"{i}. {rec.get('action', 'unknown')}: {rec.get('details', 'No details')}")
    
    if should_trigger_api_refresh(validation_results):
        print(f"\n⚠️  RECOMMENDATION: Trigger FPL API refresh to correct gameweek data")
    else:
        print(f"\n✅ No immediate API refresh needed")
    
    logger.info("Gameweek validation completed")

if __name__ == "__main__":
    main()