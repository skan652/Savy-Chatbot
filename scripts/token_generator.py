# token_generator.py
import requests
import os
import re
from dotenv import load_dotenv, set_key

# Load existing .env file
load_dotenv()

def generate_token(base_url="https://api.savyapp.dev"):
    """
    Generate an authentication token from the Savy API
    """
    try:
        # The endpoint for generating tokens - adjust based on actual API documentation
        # This is a common pattern, but you may need to adjust the endpoint and payload
        endpoint = f"{base_url}/auth/token"
        
        # Common authentication methods - adjust based on actual API requirements
        # Option 1: Client credentials (most common for machine-to-machine)
        payload = {
            "client_id": os.getenv("SAVY_CLIENT_ID", "your_client_id"),
            "client_secret": os.getenv("SAVY_CLIENT_SECRET", "your_client_secret"),
            "grant_type": "client_credentials"
        }
        
        # Option 2: Username/password (if you have user credentials)
        # payload = {
        #     "username": os.getenv("SAVY_USERNAME", "your_username"),
        #     "password": os.getenv("SAVY_PASSWORD", "your_password"),
        #     "grant_type": "password"
        # }
        
        # Option 3: API Key (if the API uses API key authentication)
        # headers = {
        #     "X-API-Key": os.getenv("SAVY_API_KEY", "your_api_key"),
        #     "Content-Type": "application/json"
        # }
        # response = requests.post(endpoint, headers=headers)
        
        print(f"🔄 Attempting to generate token from {endpoint}...")
        
        response = requests.post(endpoint, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        token = data.get("access_token") or data.get("token") or data.get("api_key")
        
        if token:
            print(f"✅ Token generated successfully!")
            print(f"Token: {token[:20]}...")
            return token
        else:
            print(f"⚠️ Token not found in response: {data}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error generating token: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")
        return None

def save_token_to_env(token):
    """Save the token to the .env file"""
    env_file = ".env"
    
    # Read existing .env file
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            content = f.read()
    else:
        content = ""
    
    # Check if SAVY_TOKEN already exists
    if "SAVY_TOKEN=" in content:
        # Update existing token
        content = re.sub(r'SAVY_TOKEN=.*', f'SAVY_TOKEN={token}', content)
        print("✅ Updated existing SAVY_TOKEN in .env")
    else:
        # Add new token
        content += f"\n# Savy API Token\nSAVY_TOKEN={token}\n"
        print("✅ Added SAVY_TOKEN to .env")
    
    # Write back to .env
    with open(env_file, 'w') as f:
        f.write(content)
    
    print(f"✅ Token saved to {env_file}")

def main():
    """Main function to generate and save token"""
    print("=" * 50)
    print("🔐 Savy API Token Generator")
    print("=" * 50)
    
    # Check if token already exists
    load_dotenv()
    existing_token = os.getenv("SAVY_TOKEN")
    if existing_token:
        print(f"⚠️ Token already exists in .env: {existing_token[:20]}...")
        regenerate = input("Do you want to regenerate the token? (y/n): ").strip().lower()
        if regenerate != 'y':
            print("Keeping existing token.")
            return
    
    # Generate new token
    token = generate_token()
    
    if token:
        save_token_to_env(token)
        print("\n" + "=" * 50)
        print("✅ Token setup complete!")
        print("=" * 50)
    else:
        print("\n❌ Failed to generate token. Please check your credentials and try again.")
        print("\nIf you're unsure about the authentication method, please provide:")
        print("1. The API documentation or endpoint for authentication")
        print("2. What credentials are needed (API Key, Username/Password, Client ID/Secret, etc.)")

if __name__ == "__main__":
    main()

