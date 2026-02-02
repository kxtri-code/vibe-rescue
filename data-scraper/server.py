from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename
from google import genai
from google.genai import types
from pymongo import MongoClient
import PIL.Image
import json
import os
import time
import datetime

# --- CONFIGURATION ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# SECURE KEYS (Loaded from Environment)
API_KEY = os.environ.get("GOOGLE_API_KEY")
MONGO_URI = os.environ.get("MONGO_URI") # <--- NEW!

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- DATABASE CONNECTION ---
def get_db():
    client = MongoClient(MONGO_URI)
    db = client.get_database("project_vibe_db")
    return db.events

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- SERVE IMAGES ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- AI PROCESSING ---
def process_image_with_ai(image_path):
    try:
        client = genai.Client(api_key=API_KEY)
        img = PIL.Image.open(image_path)
        
        prompt = """
        Extract event details into a JSON object.
        RULES: 1. If year missing, USE "2026". 2. Format date YYYY-MM-DD.
        {
            "event_name": "Name", "venue": "Location",
            "date": "YYYY-MM-DD", "time": "Time",
            "vibe": ["Tag1", "Tag2", "Tag3"]
        }
        """
        response = client.models.generate_content(
            model="gemini-flash-latest", 
            contents=[img, prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"AI Error: {e}")
        return None

# --- API: GET EVENTS (FROM CLOUD DB) ---
@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        events_collection = get_db()
        # Find all events, sort by date (newest first), and exclude the internal MongoDB ID
        events = list(events_collection.find({}, {'_id': 0}).sort("date", -1))
        return jsonify(events)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- API: SCAN & SAVE (TO CLOUD DB) ---
@app.route('/api/scan', methods=['POST'])
def scan_flyer():
    if 'photo' not in request.files: return jsonify({"error": "No photo"}), 400
    file = request.files['photo']
    
    if file and allowed_file(file.filename):
        # 1. Save Image Locally (Note: Images still reset on free Render plan, but Data is safe)
        filename = f"{int(time.time())}_{secure_filename(file.filename)}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 2. Analyze
        event_data = process_image_with_ai(filepath)
        
        if event_data:
            # 3. Add Image Link
            event_data['image_url'] = f"/uploads/{filename}"
            event_data['created_at'] = datetime.datetime.utcnow()
            
            # 4. SAVE TO MONGODB (The Permanent Vault)
            events_collection = get_db()
            events_collection.insert_one(event_data)
            
            # Remove the non-serializable ID before sending back to phone
            del event_data['_id']
            del event_data['created_at']
            
            return jsonify(event_data)
            
    return jsonify({"error": "Failed"}), 500
# --- NEW: DELETE EVENT ROUTE ---
@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    try:
        # Convert string ID to MongoDB ObjectId
        from bson.objectid import ObjectId
        result = mongo.db.events.delete_one({'_id': ObjectId(event_id)})
        
        if result.deleted_count > 0:
            return jsonify({"message": "Deleted"}), 200
        else:
            return jsonify({"error": "Event not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)