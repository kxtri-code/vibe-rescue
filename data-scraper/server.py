from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
import os
from dotenv import load_dotenv
import google.generativeai as genai
from bson.objectid import ObjectId
import json
import re
from datetime import datetime

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
    print("⚠️ CRITICAL: GENAI_API_KEY is missing!")
else:
    genai.configure(api_key=GENAI_API_KEY)

# 4. UPLOAD FOLDER
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- SMART MODEL SELECTOR ---
def generate_event_details(file_path):
    possible_models = ["gemini-flash-latest", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    myfile = genai.upload_file(file_path)
    
    prompt = """
    Analyze this flyer. Extract details into JSON.
    Keys: "event_name", "venue", "date" (YYYY-MM-DD), "time", "vibe" (Array of 3 strings).
    Do not use markdown.
    """

    last_error = None
    for model_name in possible_models:
        try:
            print(f"🤖 Trying model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            result = model.generate_content([myfile, prompt])
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

# A. SCANNER (Now saves WHO created it)
@app.route('/api/scan', methods=['POST'])
def scan_flyer():
    try:
        if 'photo' not in request.files:
            return jsonify({"error": "No photo uploaded"}), 400
        
        file = request.files['photo']
        user_email = request.form.get('user_email', 'Anonymous') # <--- CAPTURE CREATOR
        
        filename = f"{os.urandom(4).hex()}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # AI PROCESSING
        ai_text = generate_event_details(filepath)
        clean_text = re.sub(r'```json\s*|\s*```', '', ai_text).strip()
        
        try:
            data = json.loads(clean_text)
        except:
            start = clean_text.find('{')
            end = clean_text.rfind('}') + 1
            data = json.loads(clean_text[start:end])

        # Add Metadata
        data['image_url'] = f"/uploads/{filename}"
        data['created_by'] = user_email  # <--- SAVE CREATOR
        
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

# B. DELETE (Only works if logic allows, mainly handled on frontend for now)
@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    try:
        # Ideally, we would check the user here too, but let's start with frontend protection
        result = db.events.delete_one({'_id': ObjectId(event_id)})
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/<event_id>/like', methods=['PUT'])
def toggle_like(event_id):
    try:
        event = db.events.find_one({'_id': ObjectId(event_id)})
        if not event: return jsonify({"error": "Not found"}), 404
        new_status = not event.get('liked', False)
        db.events.update_one({'_id': ObjectId(event_id)}, {'$set': {'liked': new_status}})
        return jsonify({"message": "Updated", "liked": new_status}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/<event_id>/comment', methods=['POST'])
def add_comment(event_id):
    try:
        data = request.json
        comment = {
            "id": os.urandom(4).hex(),
            "user": data.get("user", "Anonymous"),
            "text": data.get("text", ""),
            "timestamp": datetime.now().isoformat()
        }
        db.events.update_one({'_id': ObjectId(event_id)}, {'$push': {'comments': comment}})
        return jsonify(comment), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    try:
        data = request.json
        allowed = ['event_name', 'venue', 'date', 'time']
        update_data = {k: v for k, v in data.items() if k in allowed}
        db.events.update_one({'_id': ObjectId(event_id)}, {'$set': update_data})
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/uploads/<path:filename>')
def serve_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)