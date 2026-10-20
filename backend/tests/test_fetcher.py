import pytest

from app.ingestion.fetcher import UnsafeURL, assert_safe_url


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.org/x",
        "http://localhost/admin",
        "http://127.0.0.1:8000/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://metadata.internal/",
    ],
)
async def test_ssrf_blocked(url):
    with pytest.raises(UnsafeURL):
        await assert_safe_url(url)
