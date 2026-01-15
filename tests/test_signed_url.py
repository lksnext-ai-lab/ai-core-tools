import os
import shutil
import sys
from fastapi.testclient import TestClient

# Ensure backend package is importable
BACKEND_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.append(BACKEND_PATH)

# Configure environment for test run
TMP_BASE_DIR = os.path.join("tests", "tmp_static")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ["TMP_BASE_FOLDER"] = TMP_BASE_DIR

from main import app  # noqa: E402  (imports after sys.path manipulation)
from utils.security import generate_signature  # noqa: E402

client = TestClient(app)


def _prepare_test_image() -> str:
    os.makedirs(TMP_BASE_DIR, exist_ok=True)
    test_file = os.path.join(TMP_BASE_DIR, "test_image.png")
    with open(test_file, "w", encoding="utf-8") as handle:
        handle.write("dummy image content")
    # File path is relative to TMP base folder in app
    return "test_image.png"


def test_signed_url_access():
    print("\n--- Starting Signed URL Test ---")
    file_path = _prepare_test_image()
    user = "testuseruser@example.com"

    sig = generate_signature(file_path, user)
    print(f"Generated signature: {sig}")

    valid_url = f"/static/{file_path}?user={user}&sig={sig}"
    valid_response = client.get(valid_url)
    print(f"Valid request status: {valid_response.status_code}")
    assert valid_response.status_code == 200
    assert valid_response.content == b"dummy image content"

    invalid_sig_resp = client.get(f"/static/{file_path}?user={user}&sig=invalid_sig")
    print(f"Invalid sig status: {invalid_sig_resp.status_code}")
    assert invalid_sig_resp.status_code == 403

    wrong_user_resp = client.get(f"/static/{file_path}?user=other@example.com&sig={sig}")
    print(f"Wrong user status: {wrong_user_resp.status_code}")
    assert wrong_user_resp.status_code == 403

    missing_params_resp = client.get(f"/static/{file_path}")
    print(f"No params status: {missing_params_resp.status_code}")
    assert missing_params_resp.status_code == 403

    print("--- All tests passed! ---")


if __name__ == "__main__":
    try:
        test_signed_url_access()
    finally:
        shutil.rmtree(TMP_BASE_DIR, ignore_errors=True)
