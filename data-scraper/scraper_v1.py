from google import genai
from google.genai import types
import PIL.Image
import json
import os
import datetime

# --- PASTE YOUR KEY HERE ---
API_KEY = "AIzaSyBFtqVzgYZQBB7FAPSCVVPv6-ZIfs71Ogs"

def analyze_flyer(image_path):
    print(f"🚀 Processing: {image_path}...")
    
    if not os.path.exists(image_path):
        print(f"❌ Error: Cannot find '{image_path}'")
        return

    try:
        client = genai.Client(api_key=API_KEY)
        img = PIL.Image.open(image_path)

        # UPDATED PROMPT: We are stricter about the year now
        prompt = """
        Extract event details into a JSON object.
        RULES:
        1. If the year is missing, USE "2026". Do NOT use "YYYY".
        2. Format date strictly as YYYY-MM-DD.
        3. Output JSON only.

        {
            "event_name": "Name of event",
            "venue": "Location name",
            "date": "YYYY-MM-DD",
            "time": "Start time",
            "vibe": ["3", "words", "describing", "vibe"]
        }
        """

        response = client.models.generate_content(
            model="gemini-flash-latest", 
            contents=[img, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        # Parse the text into a real Python dictionary
        new_event = json.loads(response.text)
        
        # --- NEW PART: SAVE TO DATABASE FILE ---
        db_file = "events_db.json"
        
        # 1. Read existing data (if any)
        if os.path.exists(db_file):
            with open(db_file, "r") as f:
                try:
                    database = json.load(f)
                except:
                    database = [] # Start fresh if file is broken
        else:
            database = []

        # 2. Add the new event
        database.append(new_event)

        # 3. Save it back
        with open(db_file, "w") as f:
            json.dump(database, f, indent=4)

        print("\n✅ SAVED TO DATABASE! Here is your data:")
        print(json.dumps(new_event, indent=4))

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    analyze_flyer("test.jpg")