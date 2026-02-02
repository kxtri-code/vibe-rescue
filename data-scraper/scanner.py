from google import genai
import os

# --- PASTE YOUR KEY HERE ---
# Use the COPY button in your browser to avoid typos!
API_KEY = "AIzaSyBFtqVzgYZQBB7FAPSCVVPv6-ZIfs71Ogs" 

client = genai.Client(api_key=API_KEY)

print("🔍 Connecting to Google...")

try:
    # We just grab the list. No filters. No if-statements.
    # We convert the iterator to a list so we can see it clearly.
    all_models = list(client.models.list())
    
    print(f"✅ FOUND {len(all_models)} MODELS:\n")
    
    for model in all_models:
        # We print the 'name' and 'display_name' to be sure
        print(f"👉 ID: {model.name}")

except Exception as e:
    print(f"❌ Error: {e}")