#!/usr/bin/env python3
"""
Test script to verify the automated predictions script is using the correct 1-0 strategy.

This script tests:
1. Strategy retrieval from season_recommendations table
2. Prediction generation with real odds data
3. Edge cases and error handling
4. Complete prediction string formatting
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from automated_predictions import (
    get_current_season_recommendation,
    create_predictions_string,
    get_gameweek_odds,
    setup_logging,
    CURRENT_SEASON
)

def test_strategy_retrieval():
    """Test that the strategy retrieval returns '1-0'"""
    print("=== Testing Strategy Retrieval ===")
    logger = setup_logging()

    strategy = get_current_season_recommendation(CURRENT_SEASON, logger)
    print(f"Retrieved strategy: {strategy}")

    if strategy == '1-0':
        print("✅ PASS: Strategy retrieval returns '1-0' as expected")
        return True
    else:
        print(f"❌ FAIL: Expected '1-0', got '{strategy}'")
        return False

def test_prediction_generation():
    """Test prediction generation with real odds data"""
    print("\n=== Testing Prediction Generation ===")
    logger = setup_logging()

    # Get real odds data for gameweek 5
    odds_data = get_gameweek_odds(5, logger)

    if not odds_data:
        print("❌ No odds data available for testing")
        return False

    print(f"Testing with {len(odds_data)} fixtures from gameweek 5")

    # Generate predictions
    predictions_string = create_predictions_string(odds_data, logger)
    print(f"\nGenerated predictions:\n{predictions_string}")

    # Analyze predictions
    lines = predictions_string.split('\n')
    predictions = [line for line in lines if ' ' in line and ('-' in line or 'v' in line)]

    print(f"\nAnalyzing {len(predictions)} predictions:")

    one_zero_count = 0
    zero_one_count = 0
    other_count = 0

    for prediction in predictions:
        if '1-0' in prediction:
            one_zero_count += 1
            print(f"✅ 1-0 prediction: {prediction}")
        elif '0-1' in prediction:
            zero_one_count += 1
            print(f"✅ 0-1 prediction: {prediction}")
        else:
            other_count += 1
            print(f"⚠️  Other prediction: {prediction}")

    print(f"\nSummary:")
    print(f"  1-0 predictions (home favorites): {one_zero_count}")
    print(f"  0-1 predictions (away favorites): {zero_one_count}")
    print(f"  Other predictions: {other_count}")

    # Check if we're using 1-0 strategy correctly
    if one_zero_count > 0 or zero_one_count > 0:
        print("✅ PASS: 1-0 strategy is being used for favorites")
        return True
    else:
        print("❌ FAIL: No 1-0 predictions found")
        return False

def test_specific_odds():
    """Test with specific known odds scenarios"""
    print("\n=== Testing Specific Odds Scenarios ===")
    logger = setup_logging()

    # Test data: [home_team, away_team, home_odds, away_odds]
    test_cases = [
        ['Liverpool', 'Everton', 1.43, 6.95],  # Strong home favorite
        ['Bournemouth', 'Newcastle', 2.44, 2.75],  # Slight home favorite
        ['Brighton', 'Spurs', 2.25, 2.98],  # Home favorite
        ['Arsenal', 'City', 3.50, 1.80],  # Away favorite
    ]

    predictions_data = []
    for case in test_cases:
        predictions_data.append(case)

    predictions_string = create_predictions_string(predictions_data, logger)
    print(f"Test predictions:\n{predictions_string}")

    lines = predictions_string.split('\n')
    actual_predictions = [line for line in lines if any(team in line for team in ['Liverpool', 'Bournemouth', 'Brighton', 'Arsenal'])]

    expected_results = [
        ('Liverpool', '1-0'),  # Home favorite
        ('Bournemouth', '1-0'),  # Home favorite
        ('Brighton', '1-0'),  # Home favorite
        ('Arsenal', '0-1'),  # Away favorite (City)
    ]

    all_correct = True
    for i, (team, expected_score) in enumerate(expected_results):
        if i < len(actual_predictions):
            prediction = actual_predictions[i]
            if expected_score in prediction:
                print(f"✅ {team}: {prediction}")
            else:
                print(f"❌ {team}: Expected {expected_score}, got {prediction}")
                all_correct = False
        else:
            print(f"❌ Missing prediction for {team}")
            all_correct = False

    if all_correct:
        print("✅ PASS: All specific odds scenarios correct")
        return True
    else:
        print("❌ FAIL: Some specific odds scenarios incorrect")
        return False

def test_edge_cases():
    """Test edge cases like missing odds"""
    print("\n=== Testing Edge Cases ===")
    logger = setup_logging()

    # Test with missing odds
    test_data = [
        ['Team A', 'Team B', None, None],  # No odds
        ['Team C', 'Team D', 2.0, 2.0],   # Equal odds
    ]

    predictions_string = create_predictions_string(test_data, logger)
    print(f"Edge case predictions:\n{predictions_string}")

    if '1-1' in predictions_string:
        print("✅ PASS: Default 1-1 used for missing odds")
        return True
    else:
        print("❌ FAIL: Default 1-1 not used for missing odds")
        return False

def run_all_tests():
    """Run all tests and provide summary"""
    print("🧪 Testing Automated Predictions 1-0 Strategy")
    print("=" * 50)

    tests = [
        test_strategy_retrieval,
        test_prediction_generation,
        test_specific_odds,
        test_edge_cases,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            results.append(False)

    print("\n" + "=" * 50)
    print("📊 TEST SUMMARY")
    print("=" * 50)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("🎉 ALL TESTS PASSED - 1-0 strategy is working correctly!")
    else:
        print("⚠️  SOME TESTS FAILED - Check output above for details")

    return passed == total

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)