from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import google.generativeai as genai
from bson.objectid import ObjectId
import json
import re

# 1. SETUP
load_dotenv()
app = Flask(__name__)
CORS(app)

# 2. DATABASE
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client.get_database('project_vibe') 

# 3. AI CONFIGURATION
GENAI_API_KEY = os.getenv("GENAI_API_KEY")
if not GENAI_API_KEY:
    print("⚠️ CRITICAL: GENAI_API_KEY is missing from Environment Variables!")
else:
    genai.configure(api_key=GENAI_API_KEY)

# 4. UPLOAD FOLDER
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- SMART MODEL SELECTOR ---
def generate_event_details(file_path):
    possible_models = [
        "gemini-flash-latest",    # Fast & New
        "gemini-1.5-flash",       # Standard
        "gemini-1.5-pro",         # High Intelligence
        "gemini-pro"              # Old Reliable
    ]
    
    myfile = genai.upload_file(file_path)
    
    # --- CRITICAL FIX: We force the AI to use specific JSON keys ---
    prompt = """
    Analyze this event flyer. Extract details and return ONLY a JSON object.
    Use these EXACT keys:
    - "event_name" (String)
    - "venue" (String)
    - "date" (String, format YYYY-MM-DD)
    - "time" (String)
    - "vibe" (Array of 3 strings max)
    
    Do not add markdown formatting. Just the raw JSON.
    """

    last_error = None
    for model_name in possible_models:
        try:
            print(f"🤖 Trying model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            result = model.generate_content([myfile, prompt])
            print(f"✅ Success with {model_name}!")
            return result.text
        except Exception as e:
            print(f"⚠️ Failed with {model_name}: {e}")
            last_error = e
            continue 
    raise last_error

# --- ROUTES ---

@app.route('/')
def home():
    return "Project Vibe Brain is Active! 🧠"

@app.route('/api/scan', methods=['POST'])
def scan_flyer():
    try:
        if 'photo' not in request.files:
            return jsonify({"error": "No photo uploaded"}), 400
        
        file = request.files['photo']
        filename = f"{os.urandom(4).hex()}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # AI PROCESSING
        ai_text = generate_event_details(filepath)
        
        # CLEANUP: Remove ```json and ``` if the AI adds them
        clean_text = re.sub(r'```json\s*|\s*```', '', ai_text).strip()
        
        # PARSE JSON
        try:
            data = json.loads(clean_text)
        except json.JSONDecodeError:
            # Fallback: try to find the JSON object inside the text
            start = clean_text.find('{')
            end = clean_text.rfind('}') + 1
            if start != -1 and end != -1:
                data = json.loads(clean_text[start:end])
            else:
                raise ValueError("AI did not return valid JSON")

        # Add image URL and Save
        data['image_url'] = f"/uploads/{filename}"
        new_id = db.events.insert_one(data).inserted_id
        
        data['_id'] = str(new_id)
        return jsonify(data), 200

    except Exception as e:
        print(f"SERVER ERROR: {e}")
        return jsonify({"error": f"AI Failed: {str(e)}"}), 500

@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        events = []
        for doc in db.events.find().sort('_id', -1):
            doc['_id'] = str(doc['_id']) 
            events.append(doc)
        return jsonify(events), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    try:
        result = db.events.delete_one({'_id': ObjectId(event_id)})
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/uploads/<path:filename>')
def serve_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)