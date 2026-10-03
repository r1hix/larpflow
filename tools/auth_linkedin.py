"""Helper script to authorize LinkedIn via a local OAuth callback server."""
import http.server
import json
import secrets
import sys
import urllib.parse
import webbrowser
import requests

PORT = 8080
REDIRECT_URI = f"http://localhost:{PORT}/callback"

code_received = None
state_sent = secrets.token_hex(16)


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global code_received
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            state = params.get("state", [""])[0]
            if state != state_sent:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"State mismatch error.")
                return

            code_received = params.get("code", [""])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<h1>LinkedIn Authorization Successful!</h1><p>You can close this tab and check your terminal.</p>"
            )

    def log_message(self, format, *args):
        pass  # quiet


def main():
    if len(sys.argv) < 3:
        print("Usage: python tools/auth_linkedin.py <CLIENT_ID> <CLIENT_SECRET>")
        sys.exit(1)

    client_id = sys.argv[1].strip()
    client_secret = sys.argv[2].strip()

    scopes = "w_member_social openid profile"
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "state": state_sent,
        "scope": scopes,
    }
    auth_url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(params)

    print("\n" + "=" * 60)
    print("Opening browser for LinkedIn Authorization...")
    print("If it doesn't open automatically, visit this URL:")
    print(auth_url)
    print("=" * 60 + "\n")

    server = http.server.HTTPServer(("127.0.0.1", PORT), OAuthCallbackHandler)
    server.timeout = 120

    webbrowser.open(auth_url)

    while not code_received:
        server.handle_request()

    print("\nAuthorization code received! Exchanging for Access Token...")

    # Exchange code for access token
    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    payload = {
        "grant_type": "authorization_code",
        "code": code_received,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    resp = requests.post(token_url, data=payload, timeout=30)
    if resp.status_code != 200:
        print(f"Failed to fetch token: {resp.status_code} - {resp.text}")
        sys.exit(1)

    token_data = resp.json()
    access_token = token_data.get("access_token")

    print("\nFetching your LinkedIn profile info (Person URN)...")
    headers = {"Authorization": f"Bearer {access_token}"}
    userinfo_resp = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers, timeout=30)
    
    person_urn = ""
    if userinfo_resp.status_code == 200:
        sub = userinfo_resp.json().get("sub")
        person_urn = f"urn:li:person:{sub}"
        print(f"Detected sub: {sub} -> Person URN: {person_urn}")
    else:
        print(f"Note: userinfo returned {userinfo_resp.status_code}. Person URN will need manual check if not provided.")

    print("\n" + "=" * 60)
    print("SUCCESS! Add these lines to your .env file:")
    print("=" * 60)
    print(f"LINKEDIN_ACCESS_TOKEN={access_token}")
    if person_urn:
        print(f"LINKEDIN_PERSON_URN={person_urn}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
