import subprocess
import sys
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_switch_simulator_html_endpoint():
    response = client.get("/switch-simulator")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "shop-sharma-kirana" in html
    assert "ca-office" in html
    assert "vendor-dispute-desk" in html
    assert "Kacha Counter Slip" in html
    assert "Wispr Voice Note" in html


def test_demo_switch_live_script_execution():
    result = subprocess.run(
        [sys.executable, "scripts/demo_switch_live.py"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    output = result.stdout
    assert "BEAT 1/12" in output
    assert "BEAT 12/12" in output
    assert "ALL 12 DEMO BEATS COMPLETED SUCCESSFULLY" in output

