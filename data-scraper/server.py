from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import google.generativeai as genai
from bson.objectid import ObjectId

# 1. SETUP
load_dotenv()
app = Flask(__name__)
CORS(app)

# 2. DATABASE CONNECTION
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("⚠️ WARNING: MONGO_URI is missing!")
client = MongoClient(MONGO_URI)
db = client.get_database('project_vibe') 

# 3. AI CONFIGURATION
GENAI_API_KEY = os.getenv("GENAI_API_KEY")
if not GENAI_API_KEY:
    print("⚠️ WARNING: GENAI_API_KEY is missing!")
else:
    genai.configure(api_key=GENAI_API_KEY)

# 4. UPLOAD FOLDER
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- ROUTES ---

@app.route('/')
def home():
    return "Project Vibe Brain is Active! 🧠"

# A. SCANNER (The "Eye")
@app.route('/api/scan', methods=['POST'])
def scan_flyer():
    try:
        if 'photo' not in request.files:
            return jsonify({"error": "No photo uploaded"}), 400
        
        file = request.files['photo']
        filename = f"{os.urandom(4).hex()}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # Upload to Gemini AI
        myfile = genai.upload_file(filepath)
        
        # --- CRITICAL FIX: Use the specific model version ---
        model = genai.GenerativeModel("gemini-1.5-flash-001") 
        
        # Ask AI to extract details
        result = model.generate_content(
            [myfile, "\n\nExtract event details: Event Name, Venue, Date (YYYY-MM-DD), Time, and Vibe (3 words max). Return JSON."]
        )
        
        # Clean AI response
        import json
        text = result.text.replace('```json', '').replace('```', '')
        data = json.loads(text)
        
        # Add image URL so app can see it
        data['image_url'] = f"/uploads/{filename}"
        
        # Save to Database
        new_id = db.events.insert_one(data).inserted_id
        
        # Return cleaned data with String ID
        data['_id'] = str(new_id)
        return jsonify(data), 200

    except Exception as e:
        print(f"ERROR: {e}") # Print error to logs
        return jsonify({"error": str(e)}), 500

# B. GET EVENTS (The "Memory")
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

# C. DELETE EVENT (The "Janitor")
@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    try:
        result = db.events.delete_one({'_id': ObjectId(event_id)})
        if result.deleted_count > 0:
            return jsonify({"message": "Deleted"}), 200
        else:
            return jsonify({"error": "Event not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# D. SERVE IMAGES
@app.route('/uploads/<path:filename>')
def serve_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)