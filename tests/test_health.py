def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Nhạc" in resp.text
    assert "shows" in resp.text  # statbar


def test_fonts_self_hosted_with_correct_mime(client):
    """Regression test.

    Fonts must be self-hosted, not loaded from the Google Fonts CDN — an
    ad-blocker, privacy browser, or restricted network silently blocking
    that CDN would collapse the entire display-font-driven visual identity
    to a generic system font with zero error shown to the user. Also checks
    the woff2 MIME type, which Windows' default mimetypes database doesn't
    know (main.py registers it explicitly) — a wrong content-type can cause
    strict browsers to refuse the font.
    """
    home = client.get("/").text
    assert "fonts.googleapis.com" not in home
    assert "fonts.gstatic.com" not in home

    font = client.get("/static/fonts/anton-latin.woff2")
    assert font.status_code == 200
    assert font.headers["content-type"] == "font/woff2"
