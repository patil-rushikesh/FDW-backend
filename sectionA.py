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


# get request to get the section A
@app.route('/<department>/<user_id>/A', methods=['GET'])
def get_section_A(department, user_id):
    try:
        collection = department_collections.get(department)
        if collection is not None:
            user = collection.find_one({"_id": user_id})
            if user:
                return jsonify(user.get("A"))
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        


if __name__ == '__main__':
    app.run(debug=True)