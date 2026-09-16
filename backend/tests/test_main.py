from fastapi.testclient import TestClient

from backend.api.main import app


def test_unhandled_exception_still_carries_cors_headers():
    """The motivating bug: a route handler raising before producing any response
    (e.g. /chat's provider-selection step failing) used to be caught by Starlette's
    own outermost ServerErrorMiddleware, which sits *around* CORSMiddleware
    regardless of registration order - so the 500 carried no CORS headers and a
    browser reported it as an opaque "Failed to fetch" instead of a readable error.
    `UnhandledExceptionMiddleware` (added before CORSMiddleware, so it ends up
    positioned inside it) catches the exception itself and returns a plain Response
    that flows back out through CORSMiddleware normally."""

    @app.get("/__test_boom")
    def boom():
        raise RuntimeError("deliberate test crash")

    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/__test_boom", headers={"Origin": "http://localhost:8080"})

        assert response.status_code == 500
        assert response.headers.get("access-control-allow-origin") == "http://localhost:8080"
        assert response.json() == {"detail": "Internal server error"}
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/__test_boom"]
