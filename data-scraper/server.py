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
if not MONGO_URI: print("⚠️ WARNING: MONGO_URI is missing!")
client = MongoClient(MONGO_URI)
db = client.get_database('project_vibe') 

# 3. AI CONFIG
GENAI_API_KEY = os.getenv("GENAI_API_KEY")
if not GENAI_API_KEY: print("⚠️ CRITICAL: GENAI_API_KEY is missing!")
else: genai.configure(api_key=GENAI_API_KEY)

# 4. FOLDERS
UPLOAD_FOLDER = 'uploads'
PROFILE_FOLDER = 'profiles'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROFILE_FOLDER, exist_ok=True)

# --- HELPER: GENERATE DETAILS ---
def generate_event_details(file_path):
    # Try multiple models in case one is deprecated/unavailable
    possible_models = ["gemini-1.5-flash", "gemini-pro", "gemini-1.5-pro-latest"]
    myfile = genai.upload_file(file_path)
    prompt = "Analyze this flyer. Extract details into JSON. Keys: event_name, venue, date (YYYY-MM-DD), time, vibe (Array of 3 strings)."
    
    last_error = None
    for model_name in possible_models:
        try:
            print(f"Trying model: {model_name}")
            model = genai.GenerativeModel(model_name)
            result = model.generate_content([myfile, prompt])
            return result.text
        except Exception as e:
            print(f"Model {model_name} failed: {e}")
            last_error = e
            continue
    raise last_error

# --- ROUTES ---

@app.route('/')
def home(): return "Project Vibe Brain is Active! 🧠"

# A. SCANNER
@app.route('/api/scan', methods=['POST'])
def scan_flyer():
    try:
        if 'photo' not in request.files: return jsonify({"error": "No photo"}), 400
        file = request.files['photo']
        user_email = request.form.get('user_email', 'Anonymous')
        filename = f"{os.urandom(4).hex()}_{file.filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        ai_text = generate_event_details(filepath)
        # Clean potential markdown
        clean_text = re.sub(r'```json\s*|\s*```', '', ai_text).strip()
        try: data = json.loads(clean_text)
        except: data = json.loads(clean_text[clean_text.find('{'):clean_text.rfind('}')+1])

        data['image_url'] = f"/uploads/{filename}"
        data['created_by'] = user_email
        data['likes'] = [] 
        data['checkins'] = []
        user_doc = db.users.find_one({"email": user_email})
        if user_doc: data['creator_avatar'] = user_doc.get('avatar_url')

        new_id = db.events.insert_one(data).inserted_id
        data['_id'] = str(new_id)
        return jsonify(data), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# B. GET EVENTS
@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        events = []
        for doc in db.events.find().sort('_id', -1):
            doc['_id'] = str(doc['_id']) 
            if 'likes' not in doc: doc['likes'] = []
            if 'checkins' not in doc: doc['checkins'] = []
            events.append(doc)
        return jsonify(events), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

# L. 🤖 VIBE AI CONCIERGE (FIXED)
@app.route('/api/ask-ai', methods=['POST'])
def ask_ai():
    try:
        data = request.json
        query = data.get('query')
        print(f"🤖 AI Query Received: {query}")
        
        # 1. Fetch Events Context
        events = list(db.events.find())
        if not events:
            return jsonify({"reply": "There are no events in the database yet! Upload one first."}), 200

        context = "Here is the database of current events:\n"
        for e in events:
            context += f"- EVENT: {e.get('event_name')} | VENUE: {e.get('venue')} | DATE: {e.get('date')} | VIBE: {e.get('vibe')}\n"
        
        # 2. Stronger Prompt
        prompt = f"""
        You are VibeAI, a cool nightlife assistant.
        User asks: "{query}"
        
        Database:
        {context}
        
        INSTRUCTIONS:
        - Recommend the BEST matching event from the database.
        - If nothing matches perfectly, suggest the coolest alternative.
        - Be short, hype, and use emojis.
        - Do NOT say "I cannot find". Pick something!
        """
        
        # 3. Use standard model
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        
        if not response.text:
            return jsonify({"reply": "I'm having trouble reading the vibes right now. Try again!"}), 200
            
        return jsonify({"reply": response.text}), 200

    except Exception as e:
        print(f"❌ AI ERROR: {str(e)}")
        return jsonify({"reply": f"My brain fried. Error: {str(e)}"}), 200

# STANDARD ROUTES (Delete, Like, Update, etc.)
@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    db.events.delete_one({'_id': ObjectId(event_id)})
    return jsonify({"message": "Deleted"}), 200

@app.route('/api/events/<event_id>/like', methods=['PUT'])
def toggle_like(event_id):
    data = request.json
    user = data.get('user_email')
    event = db.events.find_one({'_id': ObjectId(event_id)})
    if user in event.get('likes', []): db.events.update_one({'_id': ObjectId(event_id)}, {'$pull': {'likes': user}})
    else: db.events.update_one({'_id': ObjectId(event_id)}, {'$addToSet': {'likes': user}})
    return jsonify({"message": "Updated"}), 200

@app.route('/api/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    data = request.json
    allowed = ['event_name', 'venue', 'date', 'time', 'ticket_link']
    db.events.update_one({'_id': ObjectId(event_id)}, {'$set': {k: v for k, v in data.items() if k in allowed}})
    return jsonify({"message": "Updated"}), 200

@app.route('/api/events/<event_id>/comment', methods=['POST'])
def add_comment(event_id):
    data = request.json
    user_doc = db.users.find_one({"email": data.get("user")})
    avatar = user_doc.get('avatar_url') if user_doc else None
    comment = {"id": os.urandom(4).hex(), "user": data.get("user"), "text": data.get("text"), "avatar": avatar, "timestamp": datetime.now().isoformat()}
    db.events.update_one({'_id': ObjectId(event_id)}, {'$push': {'comments': comment}})
    return jsonify(comment), 200

@app.route('/api/events/<event_id>/comment/<comment_id>', methods=['DELETE'])
def delete_comment(event_id, comment_id):
    db.events.update_one({'_id': ObjectId(event_id)}, {'$pull': {'comments': {'id': comment_id}}})
    return jsonify({"message": "Deleted"}), 200

@app.route('/api/user/profile', methods=['POST'])
def upload_avatar():
    file = request.files['photo']
    email = request.form.get('email')
    filename = f"avatar_{os.urandom(4).hex()}.jpg"
    file.save(os.path.join(PROFILE_FOLDER, filename))
    url = f"/profiles/{filename}"
    db.users.update_one({"email": email}, {"$set": {"avatar_url": url, "email": email}}, upsert=True)
    return jsonify({"avatar_url": url}), 200

@app.route('/api/user/<email>', methods=['GET'])
def get_user(email):
    user = db.users.find_one({"email": email})
    if user: return jsonify({"avatar_url": user.get("avatar_url")}), 200
    return jsonify({"avatar_url": None}), 404

@app.route('/api/events/<event_id>/checkin', methods=['POST'])
def check_in(event_id):
    data = request.json
    db.events.update_one({'_id': ObjectId(event_id)}, {'$addToSet': {'checkins': data.get('user')}})
    return jsonify({"message": "Checked in"}), 200

# SERVE IMAGES
@app.route('/uploads/<path:filename>')
def serve_uploads(filename): return send_from_directory(UPLOAD_FOLDER, filename)
@app.route('/profiles/<path:filename>')
def serve_profiles(filename): return send_from_directory(PROFILE_FOLDER, filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)