from flask import Flask, request, jsonify
from flask_pymongo import PyMongo 
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

app.config["MONGO_URI_FDW"] = os.getenv("MONGO_URI_FDW")
mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])


# Department-based collections in the FDW database
department_collections = {
    "AIML": mongo_fdw.db.AIML,
    "ASH": mongo_fdw.db.ASH,
    "Civil": mongo_fdw.db.Civil,
    "Computer": mongo_fdw.db.Computer,
    "Computer(Regional)": mongo_fdw.db.Computer_Regional,
    "ENTC": mongo_fdw.db.ENTC,
    "IT": mongo_fdw.db.IT,
    "Mechanical": mongo_fdw.db.Mechanical
}

@app.route('/<department>/<user_id>/A', methods=['POST'])
def handle_post(department, user_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Invalid JSON data"}), 400
        
        # Access the collection named after the department
        collection = department_collections.get(department)
        
        #first we have to verify from lookup that the user exist in that department or not then only add data
        
        
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400
        
        lookup = collection.find_one({"_id": "lookup"}).get("data")
        print(lookup)
        if lookup is None:
            return jsonify({"error": "Invalid department"}), 400
        user = lookup.get(user_id)
        if user is None:
            return jsonify({"error": "Invalid user"}), 400
        
        # Update the document for the given user_id
        result = collection.update_one(
            {"_id": user_id},
            {"$set": {"A": data}},
            upsert=True
        )
        
        if result.matched_count > 0:
            message = "Data updated successfully"
        else:
            message = "Data inserted successfully"
        
        return jsonify({"message": message}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)