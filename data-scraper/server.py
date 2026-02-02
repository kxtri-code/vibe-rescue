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

# 2. DATABASE CONNECTION
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    print("⚠️ WARNING: MONGO_URI is missing!")
client = MongoClient(MONGO_URI)
db = client.get_database('project_vibe') 

# 3. AI CONFIGURATION
GENAI_API_KEY = os.getenv("GENAI_API_KEY")
if not GENAI_API_KEY:
    print("⚠️ CRITICAL: GENAI_API_KEY is missing!")
else:
    genai.configure(api_key=GENAI_API_KEY)

# 4. UPLOAD FOLDERS
UPLOAD_FOLDER = 'uploads'
PROFILE_FOLDER = 'profiles'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROFILE_FOLDER, exist_ok=True)

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

# A. SCANNER (Creates Event + Tags Creator)
@app.route('/api/scan', methods=['POST'])
def scan_flyer():
    try:
        if 'photo' not in request.files:
            return jsonify({"error": "No photo uploaded"}), 400
        
        file = request.files['photo']
        user_email = request.form.get('user_email', 'Anonymous')
        
        filename = f"{os.urandom(4).hex()}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        # AI Processing
        ai_text = generate_event_details(filepath)
        clean_text = re.sub(r'```json\s*|\s*```', '', ai_text).strip()
        
        try:
            data = json.loads(clean_text)
        except:
            # Fallback JSON extraction
            start = clean_text.find('{')
            end = clean_text.rfind('}') + 1
            data = json.loads(clean_text[start:end])

        # Add Metadata
        data['image_url'] = f"/uploads/{filename}"
        data['created_by'] = user_email
        data['likes'] = [] # Initialize empty likes list
        
        # Look up creator's avatar to stamp on the event
        user_doc = db.users.find_one({"email": user_email})
        if user_doc:
            data['creator_avatar'] = user_doc.get('avatar_url')

        new_id = db.events.insert_one(data).inserted_id
        data['_id'] = str(new_id)
        return jsonify(data), 200

    except Exception as e:
        print(f"SERVER ERROR: {e}")
        return jsonify({"error": f"AI Failed: {str(e)}"}), 500

# B. GET EVENTS (Returns All)
@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        events = []
        for doc in db.events.find().sort('_id', -1):
            doc['_id'] = str(doc['_id']) 
            # Ensure 'likes' is always a list for the frontend
            if 'likes' not in doc: doc['likes'] = []
            events.append(doc)
        return jsonify(events), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# C. DELETE EVENT
@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    try:
        result = db.events.delete_one({'_id': ObjectId(event_id)})
        return jsonify({"message": "Deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# D. TOGGLE LIKE (Multi-User List)
@app.route('/api/events/<event_id>/like', methods=['PUT'])
def toggle_like(event_id):
    try:
        data = request.json
        user_email = data.get('user_email')
        if not user_email: return jsonify({"error": "User email required"}), 400

        event = db.events.find_one({'_id': ObjectId(event_id)})
        if not event: return jsonify({"error": "Not found"}), 404
        
        current_likes = event.get('likes', [])
        
        if user_email in current_likes:
            # Unlike
            db.events.update_one({'_id': ObjectId(event_id)}, {'$pull': {'likes': user_email}})
            action = "unliked"
        else:
            # Like
            db.events.update_one({'_id': ObjectId(event_id)}, {'$addToSet': {'likes': user_email}})
            action = "liked"
            
        return jsonify({"message": action}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# E. UPDATE EVENT (Edit Mode + Ticket Link)
@app.route('/api/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    try:
        data = request.json
        allowed = ['event_name', 'venue', 'date', 'time', 'ticket_link']
        update_data = {k: v for k, v in data.items() if k in allowed}
        
        if not update_data:
             return jsonify({"error": "No valid fields"}), 400

        db.events.update_one({'_id': ObjectId(event_id)}, {'$set': update_data})
        return jsonify({"message": "Updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# F. ADD COMMENT (With User Avatar)
@app.route('/api/events/<event_id>/comment', methods=['POST'])
def add_comment(event_id):
    try:
        data = request.json
        # Fetch user avatar to store with comment
        user_doc = db.users.find_one({"email": data.get("user")})
        avatar = user_doc.get('avatar_url') if user_doc else None

        comment = {
            "id": os.urandom(4).hex(),
            "user": data.get("user", "Anonymous"),
            "text": data.get("text", ""),
            "avatar": avatar,
            "timestamp": datetime.now().isoformat()
        }
        
        if not comment["text"]: return jsonify({"error": "Empty comment"}), 400

        db.events.update_one({'_id': ObjectId(event_id)}, {'$push': {'comments': comment}})
        return jsonify(comment), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# G. DELETE COMMENT
@app.route('/api/events/<event_id>/comment/<comment_id>', methods=['DELETE'])
def delete_comment(event_id, comment_id):
    try:
        db.events.update_one(
            {'_id': ObjectId(event_id)}, 
            {'$pull': {'comments': {'id': comment_id}}}
        )
        return jsonify({"message": "Comment deleted"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# H. USER PROFILE (Upload Avatar)
@app.route('/api/user/profile', methods=['POST'])
def upload_avatar():
    try:
        if 'photo' not in request.files: return jsonify({"error": "No photo"}), 400
        file = request.files['photo']
        email = request.form.get('email')
        
        filename = f"avatar_{os.urandom(4).hex()}.jpg"
        filepath = os.path.join(PROFILE_FOLDER, filename)
        file.save(filepath)
        
        avatar_url = f"/profiles/{filename}"
        
        # Save User to DB
        db.users.update_one(
            {"email": email},
            {"$set": {"avatar_url": avatar_url, "email": email}},
            upsert=True
        )
        return jsonify({"avatar_url": avatar_url}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# I. GET USER INFO
@app.route('/api/user/<email>', methods=['GET'])
def get_user(email):
    try:
        user = db.users.find_one({"email": email})
        if user: return jsonify({"avatar_url": user.get("avatar_url")}), 200
        return jsonify({"avatar_url": None}), 404
    except Exception as e: return jsonify({"error": str(e)}), 500

# J. SERVE IMAGES
@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/profiles/<path:filename>')
def serve_profiles(filename):
    return send_from_directory(PROFILE_FOLDER, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)