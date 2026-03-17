#!/usr/bin/env python3
"""
Simple performance test for the webapp analysis endpoints
"""

import time
import requests
import threading
from concurrent.futures import ThreadPoolExecutor

# Test configuration
BASE_URL = 'http://localhost:5000'
ENDPOINTS_TO_TEST = [
    '/api/analysis/standings?season=2025/2026',
    '/api/analysis/scoreline-heatmap?season=2025/2026',
    '/api/analysis/gameweek-trends?season=2025/2026',
    '/api/analysis/seasons',
    '/api/analysis/top-performers?season=2025/2026&limit=5',
    '/api/analysis/result-types?season=2025/2026'
]

def test_endpoint(url):
    """Test a single endpoint and return timing info"""
    start_time = time.time()
    try:
        response = requests.get(f"{BASE_URL}{url}", timeout=30)
        end_time = time.time()
        
        return {
            'url': url,
            'status_code': response.status_code,
            'response_time': round(end_time - start_time, 2),
            'size_kb': round(len(response.content) / 1024, 2),
            'success': response.status_code == 200
        }
    except Exception as e:
        end_time = time.time()
        return {
            'url': url,
            'status_code': 0,
            'response_time': round(end_time - start_time, 2),
            'size_kb': 0,
            'success': False,
            'error': str(e)
        }

def run_performance_test():
    """Run performance tests on analysis endpoints"""
    print("🚀 Starting webapp analysis performance test...")
    print("=" * 60)
    
    # Test endpoints sequentially first
    print("\n📊 Sequential Loading Test:")
    sequential_start = time.time()
    for url in ENDPOINTS_TO_TEST:
        result = test_endpoint(url)
        status = "✅" if result['success'] else "❌"
        print(f"{status} {result['url']:<40} {result['response_time']}s ({result['size_kb']}KB)")
        if not result['success'] and 'error' in result:
            print(f"   Error: {result['error']}")
    sequential_total = time.time() - sequential_start
    print(f"\n⏱️  Sequential total time: {sequential_total:.2f}s")
    
    # Test concurrent loading (simulating page load)
    print("\n⚡ Concurrent Loading Test (simulating page load):")
    concurrent_start = time.time()
    
    with ThreadPoolExecutor(max_workers=len(ENDPOINTS_TO_TEST)) as executor:
        futures = [executor.submit(test_endpoint, url) for url in ENDPOINTS_TO_TEST]
        results = [future.result() for future in futures]
    
    concurrent_total = time.time() - concurrent_start
    
    for result in results:
        status = "✅" if result['success'] else "❌"
        print(f"{status} {result['url']:<40} {result['response_time']}s ({result['size_kb']}KB)")
        if not result['success'] and 'error' in result:
            print(f"   Error: {result['error']}")
    
    print(f"\n⏱️  Concurrent total time: {concurrent_total:.2f}s")
    print(f"🎯 Performance improvement: {((sequential_total - concurrent_total) / sequential_total * 100):.1f}% faster")
    
    # Test caching
    print("\n🗃️  Cache Test (second request):")
    cache_start = time.time()
    cache_result = test_endpoint(ENDPOINTS_TO_TEST[0])  # Test first endpoint again
    cache_total = time.time() - cache_start
    
    status = "✅" if cache_result['success'] else "❌"
    print(f"{status} {cache_result['url']:<40} {cache_result['response_time']}s ({cache_result['size_kb']}KB)")
    print(f"🚀 Cache speedup: Expected sub-second response time")
    
    print("\n" + "=" * 60)
    print("✅ Performance test completed!")

if __name__ == "__main__":
    print("⚠️  Make sure the webapp is running on http://localhost:5000")
    print("   Run: source venv/bin/activate && python webapp/app.py")
    input("   Press Enter when ready to test...")
    run_performance_test()