from google import genai
import os

# --- PASTE YOUR KEY HERE (Make sure it is the one you copied!) ---
API_KEY = "AIzaSyBFtqVzgYZQBB7FAPSCVVPv6-Zlfs71Ogs"

client = genai.Client(api_key=API_KEY)

print("🔍 Scanning for available models...")
try:
    # Just grab every model and print its name
    for model in client.models.list():
        print(f"- {model.name}")
            
except Exception as e:
    print(f"❌ Error: {e}")