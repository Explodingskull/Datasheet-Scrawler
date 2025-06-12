import requests

def test_key():
    params = {
        "api_key": "ON1AYDAA2T08NN71GFA2OPUDKGUW29MZ8TZ2PXPV9FBNQJ2ULXRNQ5TBSL594PM6W6D0HFTGWKGQMITU",
        "url": "https://httpbin.org/anything"  # Simple test URL
    }
    resp = requests.get("https://app.scrapingbee.com/api/v1/", params=params)
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text}")  # Debug output

test_key()
