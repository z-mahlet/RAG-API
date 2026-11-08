import sys
import time
import requests

BASE_URL = "http://127.0.0.1:8000"

def test_health():
    print("[1/3] Testing /health endpoint...")
    res = requests.get(f"{BASE_URL}/health")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert data["status"] == "healthy", "Health status is not healthy"
    assert data["indexed_records"] > 0, "No records found in vector DB!"
    print(f"      [✓] Health check passed. Indexed records: {data['indexed_records']}")

def test_grounded_query():
    print("[2/3] Testing /api/chat with in-domain query...")
    payload = {
        "message": "What is the mandatory minimum vacation threshold per year?",
        "top_k": 2
    }
    start = time.time()
    res = requests.post(f"{BASE_URL}/api/chat", json=payload)
    duration = time.time() - start

    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    # Assert JSON schema
    assert "reply" in data and "sources" in data
    assert len(data["sources"]) > 0, "No sources retrieved"
    
    # Assert factual correctness
    reply = data["reply"].lower()
    assert "15" in reply or "fifteen" in reply, f"Expected '15 days' in answer, got: {data['reply']}"
    print(f"      [✓] Grounded query passed in {duration:.2f}s. Source: {data['sources'][0]['metadata']['source']}")

def test_hallucination_boundary():
    print("[3/3] Testing /api/chat with out-of-domain query (Hallucination Defense)...")
    payload = {
        "message": "What is the policy for corporate jet rentals?",
        "top_k": 2
    }
    res = requests.post(f"{BASE_URL}/api/chat", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    
    reply = data["reply"].lower()
    # Ensure system guardrail triggered
    assert "do not have sufficient information" in reply or "not present" in reply or "insufficient" in reply, \
        f"Model failed guardrail! Output was: {data['reply']}"
    print("      [✓] Guardrail test passed: Model refused out-of-scope query.")

if __name__ == "__main__":
    print("--- Running Backend Integration Tests ---")
    try:
        test_health()
        test_grounded_query()
        test_hallucination_boundary()
        print("\n[✓] ALL INTEGRATION TESTS PASSED SUCCESSFULLY!")
    except AssertionError as err:
        print(f"\n[X] TEST FAILURE: {err}")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("\n[X] CONNECTION ERROR: Is the FastAPI server running on port 8000?")
        sys.exit(1)