@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        events = []
        # Loop through database and clean up the ID
        for doc in mongo.db.events.find().sort('_id', -1):
            doc['_id'] = str(doc['_id'])  # <--- CRITICAL FIX: Convert ObjectId to String
            events.append(doc)
        return jsonify(events), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500