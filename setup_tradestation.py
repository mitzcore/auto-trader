#!/usr/bin/env python3
"""
TradeStation OAuth Setup Script

This script completes the initial OAuth authorization code flow to obtain
a refresh token for the TradeStation API. Run this ONCE to get your
refresh token, then add it to config.py.

Usage:
    python setup_tradestation.py

Requirements:
    - Your API Key (client_id) and Secret from TradeStation Developer Portal
    - A web browser for authentication

The script will:
1. Start a local web server on port 3000
2. Open your browser to TradeStation's login page
3. After you log in, capture the authorization code
4. Exchange it for access + refresh tokens
5. Fetch your account ID
6. Print all values to add to config.py
"""

import http.server
import socketserver
import threading
import webbrowser
import urllib.parse
import requests
import sys
import time
import secrets
import socket

# =============================================================================
# CONFIGURATION - Update these with your API credentials
# =============================================================================
CLIENT_ID = "n7HNDAkgFa3dvfzY9CO3DFPfYBY1AYqg"
CLIENT_SECRET = "0myfbMgbButqbFHcbUw0eml5_ZX3EbzQwudbu5pFdBZwRA-SbdB3x7YiZDM2ebzK"

# OAuth endpoints
AUTH_URL = "https://signin.tradestation.com/authorize"
TOKEN_URL = "https://signin.tradestation.com/oauth/token"
API_BASE_URL = "https://api.tradestation.com/v3"

# Local callback server
# IMPORTANT: redirect_uri must exactly match TradeStation's whitelisted URLs
# Allowed: http://localhost, http://localhost:3000, http://localhost:3001, http://localhost:8080
REDIRECT_URI = "http://localhost:3001"
PORT = 3001

# =============================================================================
# Global to capture the auth code and state
# =============================================================================
auth_code = None
oauth_state = None  # Generated state for CSRF protection
server_should_stop = False
server_ready = False  # Flag to indicate server is listening
server_error = None   # Capture server errors


class OAuthCallbackHandler(http.server.SimpleHTTPRequestHandler):
    """Handle OAuth callback and capture authorization code."""

    def do_GET(self):
        global auth_code, oauth_state, server_should_stop

        parsed = urllib.parse.urlparse(self.path)

        # Handle callback at root path (redirect_uri = http://localhost:3000)
        if parsed.path == "/" or parsed.path == "":
            query_params = urllib.parse.parse_qs(parsed.query)

            # Verify state parameter to prevent CSRF attacks
            returned_state = query_params.get("state", [None])[0]
            if returned_state != oauth_state:
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"""
                <html>
                <head><title>TradeStation Auth Error</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: red;">Security Error</h1>
                    <p>State parameter mismatch - possible CSRF attack.</p>
                    <p>Please try again.</p>
                </body>
                </html>
                """)
                server_should_stop = True
                return

            if "code" in query_params:
                auth_code = query_params["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"""
                <html>
                <head><title>TradeStation Auth Success</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: green;">Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
                """)
                server_should_stop = True
            elif "error" in query_params:
                error = query_params.get("error", ["Unknown"])[0]
                error_desc = query_params.get("error_description", [""])[0]
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(f"""
                <html>
                <head><title>TradeStation Auth Error</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: red;">Authorization Failed</h1>
                    <p>Error: {error}</p>
                    <p>{error_desc}</p>
                </body>
                </html>
                """.encode())
                server_should_stop = True
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def is_port_available(port):
    """Check if a port is available."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def start_callback_server():
    """Start local server to receive OAuth callback."""
    global server_should_stop, server_ready, server_error

    try:
        # Allow port reuse to avoid "Address already in use" errors
        socketserver.TCPServer.allow_reuse_address = True

        with socketserver.TCPServer(("127.0.0.1", PORT), OAuthCallbackHandler) as httpd:
            httpd.timeout = 1
            server_ready = True
            print(f"Callback server listening on http://127.0.0.1:{PORT}")

            while not server_should_stop:
                httpd.handle_request()

    except OSError as e:
        server_error = str(e)
        print(f"\nServer error: {e}")
    except Exception as e:
        server_error = str(e)
        print(f"\nUnexpected server error: {e}")


def get_authorization_url():
    """Build the authorization URL for user login."""
    global oauth_state

    # Generate secure random state for CSRF protection
    oauth_state = secrets.token_urlsafe(32)

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "audience": "https://api.tradestation.com",
        "state": oauth_state,
        "scope": "openid offline_access profile MarketData ReadAccount Trade Matrix OptionSpreads",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(params)}"


def check_dns_resolution(hostname="signin.tradestation.com"):
    """Verify DNS resolution before making requests."""
    try:
        socket.gethostbyname(hostname)
        return True
    except socket.gaierror:
        return False


def exchange_code_for_tokens(code):
    """Exchange authorization code for access and refresh tokens with retry logic."""
    # Check DNS before making request
    print("Verifying network connectivity...")
    if not check_dns_resolution():
        print("DNS resolution failed for signin.tradestation.com")
        print("Waiting 2 seconds and retrying...")
        time.sleep(2)
        if not check_dns_resolution():
            print("\nERROR: Cannot resolve signin.tradestation.com")
            print("Please check your internet connection and try again.")
            return None

    max_retries = 3
    retry_delay = 2  # seconds

    for attempt in range(max_retries):
        try:
            response = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30
            )

            if response.status_code != 200:
                print(f"\nError exchanging code: {response.status_code}")
                print(response.text)
                return None

            return response.json()

        except requests.exceptions.ConnectionError as e:
            if attempt < max_retries - 1:
                print(f"\nConnection error (attempt {attempt + 1}/{max_retries}): {e}")
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print(f"\nFailed after {max_retries} attempts.")
                print("This is usually a DNS or network issue. Try:")
                print("  1. Check your internet connection")
                print("  2. Run: ping signin.tradestation.com")
                print("  3. Flush DNS: sudo dscacheutil -flushcache (macOS)")
                print("  4. Try again in a few seconds")
                raise
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                print(f"\nRequest timeout (attempt {attempt + 1}/{max_retries})")
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"\nRequest timed out after {max_retries} attempts.")
                raise

    return None


def get_accounts(access_token):
    """Fetch account information."""
    response = requests.get(
        f"{API_BASE_URL}/brokerage/accounts",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    if response.status_code != 200:
        print(f"\nError fetching accounts: {response.status_code}")
        print(response.text)
        return None

    return response.json()


def main():
    global auth_code, server_ready, server_error

    print("=" * 60)
    print("TradeStation OAuth Setup")
    print("=" * 60)
    print()
    print(f"Client ID: {CLIENT_ID[:20]}...")
    print()

    # Verify credentials are set
    if not CLIENT_ID or CLIENT_ID == "YOUR_CLIENT_ID":
        print("ERROR: Please update CLIENT_ID in this script")
        sys.exit(1)
    if not CLIENT_SECRET or CLIENT_SECRET == "YOUR_CLIENT_SECRET":
        print("ERROR: Please update CLIENT_SECRET in this script")
        sys.exit(1)

    # Check if port is available
    print(f"Checking if port {PORT} is available...")
    if not is_port_available(PORT):
        print(f"\nERROR: Port {PORT} is already in use!")
        print("Try one of these solutions:")
        print(f"  1. Kill the process using port {PORT}:")
        print(f"     lsof -ti:{PORT} | xargs kill -9")
        print("  2. Or wait a few seconds and try again")
        sys.exit(1)
    print(f"Port {PORT} is available.")

    # Start callback server in background
    print(f"Starting callback server...")
    server_thread = threading.Thread(target=start_callback_server, daemon=True)
    server_thread.start()

    # Wait for server to be ready (up to 5 seconds)
    for _ in range(50):
        if server_ready:
            break
        if server_error:
            print(f"\nERROR: Server failed to start: {server_error}")
            sys.exit(1)
        time.sleep(0.1)

    if not server_ready:
        print("\nERROR: Server failed to start within timeout")
        sys.exit(1)

    # Verify server is actually responding
    time.sleep(0.2)
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(2)
        result = test_sock.connect_ex(('127.0.0.1', PORT))
        test_sock.close()
        if result != 0:
            print(f"\nERROR: Server started but not accepting connections (error: {result})")
            sys.exit(1)
        print("Server is accepting connections.")
    except Exception as e:
        print(f"\nERROR: Could not verify server: {e}")
        sys.exit(1)

    # Open browser for authentication
    auth_url = get_authorization_url()
    print("\nOpening browser for TradeStation login...")
    print("(If browser doesn't open, visit this URL manually:)")
    print(f"\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for callback
    print("Waiting for authorization...")
    timeout = 300  # 5 minutes
    start_time = time.time()

    while auth_code is None and (time.time() - start_time) < timeout:
        time.sleep(0.5)

    if auth_code is None:
        print("\nTimeout waiting for authorization. Please try again.")
        sys.exit(1)

    print(f"\nAuthorization code received!")

    # Exchange code for tokens
    print("\nExchanging code for tokens...")
    tokens = exchange_code_for_tokens(auth_code)

    if not tokens:
        print("Failed to get tokens. Please try again.")
        sys.exit(1)

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")

    print(f"Access token received (expires in {expires_in}s)")

    if not refresh_token:
        print("\nWARNING: No refresh token received!")
        print("Make sure 'offline_access' scope was included.")

    # Fetch account information
    print("\nFetching account information...")
    accounts_data = get_accounts(access_token)

    accounts = []
    if accounts_data and "Accounts" in accounts_data:
        accounts = accounts_data["Accounts"]
        print(f"\nFound {len(accounts)} account(s):")
        for acc in accounts:
            print(f"  - {acc.get('AccountID')}: {acc.get('AccountType')} ({acc.get('Status')})")

    # Print configuration values
    print("\n" + "=" * 60)
    print("SUCCESS! Add these values to config.py:")
    print("=" * 60)
    print()
    print("# TradeStation API connectivity (Auth0/v3)")
    print(f'TRADESTATION_CLIENT_ID = "{CLIENT_ID}"')
    print(f'TRADESTATION_CLIENT_SECRET = "{CLIENT_SECRET}"')
    print(f'TRADESTATION_REFRESH_TOKEN = "{refresh_token}"')

    if accounts:
        # Use first account by default
        account_id = accounts[0].get("AccountID", "")
        print(f'TRADESTATION_ACCOUNT_ID = "{account_id}"')

        if len(accounts) > 1:
            print(f"\n# Note: You have {len(accounts)} accounts. Using first one.")
            print("# Available accounts:")
            for acc in accounts:
                print(f'#   "{acc.get("AccountID")}" - {acc.get("AccountType")}')
    else:
        print('TRADESTATION_ACCOUNT_ID = ""  # Could not fetch - set manually')

    print()
    print("=" * 60)
    print()
    print("IMPORTANT NOTES:")
    print("1. Keep these credentials secure - never commit to git!")
    print("2. Refresh token is valid indefinitely (unless rotation enabled)")
    print("3. Access tokens expire in 20 minutes (auto-refreshed by client)")
    print()


if __name__ == "__main__":
    main()
