#!/usr/bin/env python3
"""
Dropbox OAuth2 Setup Helper

This script helps you set up proper OAuth2 tokens (access token + refresh token) 
for the Dropbox prediction cleaning system, following the Dropbox OAuth guide:
https://developers.dropbox.com/oauth-guide

The script will:
1. Load your app credentials from keys.json 
2. Guide you through the OAuth2 authorization flow
3. Exchange authorization code for access token + refresh token
4. Update keys.json with the new tokens

This replaces the legacy long-lived token with proper refreshable tokens.
"""

import json
import requests
import webbrowser
import urllib.parse
import tempfile
import os
import shutil
from pathlib import Path

# Configuration
keys_file = Path(__file__).parent.parent.parent / "keys.json"

def load_config():
    """Load current configuration from keys.json"""
    with open(keys_file, 'r') as f:
        return json.load(f)

def save_config(config):
    """Safely save configuration to keys.json"""
    # Create temporary file in same directory for atomic update
    temp_file = tempfile.NamedTemporaryFile(
        mode='w', 
        dir=keys_file.parent, 
        delete=False,
        suffix='.tmp'
    )
    
    try:
        # Write updated config to temp file
        json.dump(config, temp_file, indent=2)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()
        
        # Atomic move to replace original file, preserving permissions
        # Capture original file permissions before replacing
        original_stat = os.stat(keys_file)
        shutil.move(temp_file.name, keys_file)
        # Restore original permissions and ownership
        os.chmod(keys_file, original_stat.st_mode)
        os.chown(keys_file, original_stat.st_uid, original_stat.st_gid)
        print("✅ Successfully updated keys.json (permissions preserved)")
        return True
        
    except Exception as e:
        temp_file.close()
        # Clean up temp file if something went wrong
        try:
            os.unlink(temp_file.name)
        except:
            pass
        print(f"❌ Failed to update keys.json: {e}")
        return False

def generate_auth_url(app_key):
    """Generate Dropbox OAuth2 authorization URL"""
    # For OAuth2 with refresh tokens, we need 'offline' access
    auth_url = "https://www.dropbox.com/oauth2/authorize"
    
    params = {
        'client_id': app_key,
        'response_type': 'code',
        'token_access_type': 'offline',  # This is key for getting refresh token
        # No redirect_uri - this will show the code directly on the page
    }
    
    return f"{auth_url}?{urllib.parse.urlencode(params)}"

def exchange_code_for_tokens(app_key, app_secret, auth_code):
    """Exchange authorization code for access token + refresh token"""
    token_url = "https://api.dropboxapi.com/oauth2/token"
    
    data = {
        'code': auth_code,
        'grant_type': 'authorization_code',
        'client_id': app_key,
        'client_secret': app_secret,
        # No redirect_uri needed when none was specified in auth request
    }
    
    try:
        print("🔄 Exchanging authorization code for tokens...")
        response = requests.post(token_url, data=data)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ Token exchange failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ Error during token exchange: {e}")
        return None

def main():
    """Main OAuth2 setup process"""
    print("🔐 Dropbox OAuth2 Setup Helper")
    print("=" * 40)
    
    # Load existing configuration
    try:
        config = load_config()
        print("✅ Loaded existing keys.json")
    except Exception as e:
        print(f"❌ Failed to load keys.json: {e}")
        return
    
    # Check for required app credentials
    app_key = config.get('dropbox_app_key')
    app_secret = config.get('dropbox_app_secret')
    
    if not app_key or not app_secret:
        print("❌ Missing dropbox_app_key or dropbox_app_secret in keys.json")
        print("Please add these credentials from your Dropbox app settings:")
        print("https://www.dropbox.com/developers/apps")
        return
    
    print(f"✅ Found app credentials (App Key: {app_key[:8]}...)")
    
    # Generate authorization URL
    auth_url = generate_auth_url(app_key)
    
    print("\n📝 OAuth2 Authorization Steps:")
    print("1. Your browser will open to the Dropbox authorization page")
    print("2. Click 'Allow' to authorize the app")
    print("3. Dropbox will show an authorization code directly on the page")
    print("4. Copy the entire authorization code and paste it here")
    print("\nExample: You'll see something like: 'ABC123XYZ456'")
    print("Copy the entire code")
    
    input("\nPress Enter to open the authorization URL...")
    
    # Open browser
    try:
        webbrowser.open(auth_url)
        print(f"🌐 Opened: {auth_url}")
    except Exception as e:
        print(f"❌ Could not open browser: {e}")
        print(f"Please manually open: {auth_url}")
    
    # Get authorization code from user
    print("\n" + "=" * 50)
    auth_code = input("📋 Paste the authorization code here: ").strip()
    
    if not auth_code:
        print("❌ No authorization code provided")
        return
    
    # Exchange code for tokens
    token_data = exchange_code_for_tokens(app_key, app_secret, auth_code)
    
    if not token_data:
        print("❌ Failed to get tokens")
        return
    
    # Validate token response
    if 'access_token' not in token_data or 'refresh_token' not in token_data:
        print("❌ Invalid token response - missing access_token or refresh_token")
        print(f"Response: {token_data}")
        return
    
    # Update configuration
    print("✅ Successfully obtained tokens!")
    print(f"✅ Access Token: {token_data['access_token'][:20]}...")
    print(f"✅ Refresh Token: {token_data['refresh_token'][:20]}...")
    
    # Update the config with new tokens
    # Keep the old token as backup temporarily
    if 'dropbox_oath_token' in config:
        config['dropbox_oath_token_backup'] = config['dropbox_oath_token']
    
    # Add new OAuth2 tokens  
    config['dropbox_oath_token'] = token_data['access_token']
    config['dropbox_refresh_token'] = token_data['refresh_token']
    
    # Also store token metadata
    config['dropbox_token_type'] = token_data.get('token_type', 'bearer')
    
    if 'expires_in' in token_data:
        from datetime import datetime, timedelta
        expires_at = datetime.now() + timedelta(seconds=token_data['expires_in'])
        config['dropbox_token_expires_at'] = expires_at.isoformat()
    
    # Save updated configuration
    if save_config(config):
        print("\n🎉 Setup Complete!")
        print("✅ keys.json updated with new OAuth2 tokens")
        print("✅ The prediction cleaning script can now refresh tokens automatically")
        print("\n🔧 Next Steps:")
        print("1. Test the setup: python scripts/prediction_league/clean_predictions_dropbox.py --dry-run")
        print("2. The old token was backed up as 'dropbox_oath_token_backup' (can be removed later)")
        print("3. Tokens will auto-refresh when they expire")
    else:
        print("❌ Failed to save configuration")

if __name__ == "__main__":
    main()