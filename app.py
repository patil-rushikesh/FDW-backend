from flask import Flask, request, jsonify, send_file, make_response, send_from_directory
from flask_pymongo import PyMongo
from bson.json_util import dumps
import os
import bcrypt
from dotenv import load_dotenv
from mail import send_username_password_mail
from flask_cors import CORS  # Add this import
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
import json
import requests
from docx import Document
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader
import cloudinary.api
# Add these imports at the top
from gridfs import GridFS
from bson.objectid import ObjectId


# Load environment variables
load_dotenv()

app = Flask(__name__)
# Configure CORS
CORS(app, resources={
    r"/*": {
        "origins": ["http://localhost:5173"],  # Your React app's URL
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
    }
})

# MongoDB Configuration
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
app.config["MONGO_URI_FDW"] = os.getenv("MONGO_URI_FDW")

mongo = PyMongo(app, uri=app.config["MONGO_URI"])
mongo_fdw = PyMongo(app, uri=app.config["MONGO_URI_FDW"])

# Collections
db_users = mongo.db.users
db_signin = mongo.db.signin

# GridFS instance
fs = GridFS(mongo_fdw.db)

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

# Health check
@app.route('/', methods=['GET'])
def health_check():
    return jsonify({"message": "Welcome to FDW project"}), 200

# Create a new user
@app.route('/users', methods=['POST'])
def add_user():
    data = request.json
    required_fields = ["_id", "name", "role", "dept", "mail", "mob"]

    if not data or not all(k in data for k in required_fields):
        return jsonify({"error": "Missing required fields"}), 400
    
    if "desg" not in data:
        data["desg"] = "Faculty"
        

    try:
        #status, Final total marks
        # Insert into users collection
        db_users.insert_one(data)

        # Hash the password (use _id as the password initially)
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(data["_id"].encode('utf-8'), salt)

        # Insert into signin collection
        db_signin.insert_one({"_id": data["_id"], "password": hashed_password})

        # Get the correct department collection
        department = data["dept"]
        collection = department_collections.get(department)

        if collection is not None:
            collection.update_one(
                {"_id": "lookup"},
                {"$set": {f"data.{data['_id']}": data["role"]}},
                upsert=True
            )

            return jsonify({"message": f"User added successfully to {department}"}), 201
        else:
            return jsonify({"error": "Invalid department"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get all users
@app.route('/users', methods=['GET'])
def get_users():
    users = db_users.find()
    return dumps(users), 200

# Get a user by ID
@app.route('/users/<string:user_id>', methods=['GET'])
def get_user(user_id):
    user = db_users.find_one({"_id": user_id})
    if user:
        return dumps(user), 200
    return jsonify({"error": "User not found"}), 404

# Update a user by ID
@app.route('/users/<string:user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.json
    allowed_fields = ["name", "role", "dept", "mail", "mob"]
    updated_data = {k: v for k, v in data.items() if k in allowed_fields}
    
    if "desg" not in data:
       data["desg"] = "Faculty"

    if not updated_data:
        return jsonify({"error": "No valid fields to update"}), 400

    result = db_users.update_one({"_id": user_id}, {"$set": updated_data})

    if result.modified_count:
        return jsonify({"message": "User updated successfully"}), 200
    return jsonify({"error": "User not found or no changes made"}), 404

# Delete a user by ID
@app.route('/users/<string:user_id>', methods=['DELETE'])
def delete_user(user_id):
    result = db_users.delete_one({"_id": user_id})
    db_signin.delete_one({"_id": user_id})  # Remove from signin collection
    
    if result.deleted_count:
        return jsonify({"message": "User deleted successfully"}), 200
    return jsonify({"error": "User not found"}), 404

# Migrate all users to signin collection
@app.route('/migrate_users', methods=['POST'])
def migrate_users():
    users = db_users.find()
    migrated_count = 0

    for user in users:
        user_id = user["_id"]
        if not db_signin.find_one({"_id": user_id}):
            salt = bcrypt.gensalt()
            hashed_password = bcrypt.hashpw(user_id.encode('utf-8'), salt)
            db_signin.insert_one({"_id": user_id, "password": hashed_password})
            migrated_count += 1
        department = user["dept"]
        collection = department_collections.get(department)
        if collection is not None:
            collection.update_one(
                {"_id": "lookup"},
                {"$set": {f"data.{user_id}": user["role"]}},
                upsert=True
            )
            

    return jsonify({"message": f"Migrated {migrated_count} users to signin collection"}), 200

# User login
@app.route('/login', methods=['POST', 'OPTIONS'])  # Added OPTIONS method
def login():
    # Handle preflight request
    if request.method == 'OPTIONS':
        response = app.make_default_options_response()
        return response

    data = request.json
    if not data or not all(k in data for k in ["_id", "password"]):
        return jsonify({"error": "Missing required fields"}), 400

    user = db_signin.find_one({"_id": data["_id"]})
    if user and bcrypt.checkpw(data["password"].encode('utf-8'), user["password"]):
        user_data = db_users.find_one({"_id": data["_id"]})
        response = app.response_class(
            response=dumps(user_data),
            status=200,
            mimetype='application/json'
        )
        return response

    return jsonify({"error": "Invalid credentials"}), 401



#Section Data Adding Start here
@app.route('/<department>/<user_id>/A', methods=['POST'])
def handle_post_A(department, user_id):
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
        
        

#Section B Data Adding Start here
@app.route('/<department>/<user_id>/B', methods=['POST'])
def handle_post_B(department, user_id):
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
            {"$set": {"B": data}},
            upsert=True
        )
        
        if result.matched_count > 0:
            message = "Data updated successfully"
        else:
            message = "Data inserted successfully"
        
        return jsonify({"message": message}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/<user_id>/B', methods=['GET'])
def get_section_B(department, user_id):
    try:
        collection = department_collections.get(department)
        if collection is not None:
            user = collection.find_one({"_id": user_id})
            if user:
                return jsonify(user.get("B"))
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

#Section C Data Adding Start here
@app.route('/<department>/<user_id>/C', methods=['POST'])
def handle_post_C(department, user_id):
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
            {"$set": {"C": data}},
            upsert=True
        )
        
        if result.matched_count > 0:
            message = "Data updated successfully"
        else:
            message = "Data inserted successfully"
        
        return jsonify({"message": message}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/<user_id>/C', methods=['GET'])
def get_section_C(department, user_id):
    try:
        collection = department_collections.get(department)
        if collection is not None:
            user = collection.find_one({"_id": user_id})
            if user:
                return jsonify(user.get("C"))
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
                
#Section B Data Adding Start here
@app.route('/<department>/<user_id>/D', methods=['POST'])
def handle_post_D(department, user_id):
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
            {"$set": {"D": data}},
            upsert=True
        )
        
        if result.matched_count > 0:
            message = "Data updated successfully"
        else:
            message = "Data inserted successfully"
        
        return jsonify({"message": message}), 200
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/<department>/<user_id>/D', methods=['GET'])
def get_section_D(department, user_id):
    try:
        collection = department_collections.get(department)
        if collection is not None:
            user = collection.find_one({"_id": user_id})
            if user:
                return jsonify(user.get("D"))
            return jsonify({"error": "User not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
def fill_template_document(data, user_id, department):
    try:
        # Get user details directly from MongoDB
        user_data = db_users.find_one({"_id": user_id})
        if not user_data:
            raise Exception("User not found")

        # Load the template document
        doc = Document("FDW.docx")
        
        # Initial placeholders with user details
        placeholders = {
            '{faculty_name}': user_data.get('name', ''),
            '{faculty_designation}': user_data.get('desg', ''),
            '{faculty_department}': user_data.get('dept', ''),
        }
        
        # Add all other placeholders using the data parameter
        
            # Rest of your existing code...

        # Placeholders and their corresponding values from different sections
        placeholders.update({
            # Section A placeholders (keeping these as they were)
            '{result_analysis_marks}': str(round(data['A']['1']['total_marks'], 2)),
            '{course_outcome_marks}': str(round(data['A']['2']['total_marks'], 2)),
            '{elearning_content_marks}': str(round(data['A']['3']['total_marks'], 2)),
            '{academic_engagement_marks}': str(round(data['A']['4']['total_marks'], 2)),
            '{teaching_load_marks}': str(round(data['A']['5']['total_marks'], 2)),
            '{projects_guided_marks}': str(round(data['A']['6']['total_marks'], 2)),
            '{student_feedback_marks}': str(round(data['A']['7']['total_marks'], 2)),
            '{ptg_meetings_marks}': str(round(data['A']['8']['total_marks'], 2)),
            '{section_a_total}': str(round(data['A']['9']['total'], 2)),
            
            # Section B detailed placeholders
            # 1. Papers Published
            # '{sci_papers_count}': str(data['B']['papers']['sci']['count']),
            '{sci_papers_marks}': str(data['B']['papers']['sci']['count'] * 100),
            # '{esci_papers_count}': str(data['B']['papers']['esci']['count']),
            '{esci_papers_marks}': str(data['B']['papers']['esci']['count'] * 50),
            # '{scopus_papers_count}': str(data['B']['papers']['scopus']['count']),
            '{scopus_papers_marks}': str(data['B']['papers']['scopus']['count'] * 50),
            # '{ugc_papers_count}': str(data['B']['papers']['ugc']['count']),
            '{ugc_papers_marks}': str(data['B']['papers']['ugc']['count'] * 10),
            # '{other_papers_count}': str(data['B']['papers']['other']['count']),
            '{other_papers_marks}': str(data['B']['papers']['other']['count'] * 5),
            '{papers_published_marks}': str(data['B']['papers']['marks']),
            
            # 2. Conferences
            # '{scopus_conf_count}': str(data['B']['conferences']['scopus']['count']),
            '{scopus_conf_marks}': str(data['B']['conferences']['scopus']['count'] * 30),
            # '{other_conf_count}': str(data['B']['conferences']['other']['count']),
            '{other_conf_marks}': str(data['B']['conferences']['other']['count'] * 5),
            '{conferences_marks}': str(data['B']['conferences']['marks']),
            
            # 3. Book Chapters
            # '{scopus_chapter_count}': str(data['B']['bookChapters']['scopus']['count']),
            '{scopus_chapter_marks}': str(data['B']['bookChapters']['scopus']['count'] * 30),
            # '{other_chapter_count}': str(data['B']['bookChapters']['other']['count']),
            '{other_chapter_marks}': str(data['B']['bookChapters']['other']['count'] * 5),
            '{book_chapters_marks}': str(data['B']['bookChapters']['marks']),
            
            # 4. Books
            # '{scopus_books_count}': str(data['B']['books']['scopus']['count']),
            '{scopus_books_marks}': str(data['B']['books']['scopus']['count'] * 100),
            # '{national_books_count}': str(data['B']['books']['national']['count']),
            '{national_books_marks}': str(data['B']['books']['national']['count'] * 30),
            # '{local_books_count}': str(data['B']['books']['local']['count']),
            '{local_books_marks}': str(data['B']['books']['local']['count'] * 10),
            '{books_marks}': str(data['B']['books']['marks']),
            
            # 5. Citations
            # '{wos_citations_count}': str(data['B']['citations']['wos']['count']),
            '{wos_citations_marks}': str(data['B']['citations']['wos']['count'] // 3 * 3),
            # '{scopus_citations_count}': str(data['B']['citations']['scopus']['count']),
            '{scopus_citations_marks}': str(data['B']['citations']['scopus']['count'] // 3 * 3),
            # '{google_citations_count}': str(data['B']['citations']['google']['count']),
            '{google_citations_marks}': str(data['B']['citations']['google']['count'] // 3 * 1),
            '{citations_marks}': str(data['B']['citations']['marks']),
            
            # 6. Patents
            # '{individual_commercialized_count}': str(data['B']['patents']['individualCommercialized']['count']),
            '{individual_commercialized_marks}': str(data['B']['patents']['individualCommercialized']['count'] * 20),
            # '{individual_granted_count}': str(data['B']['patents']['individualGranted']['count']),
            '{individual_granted_marks}': str(data['B']['patents']['individualGranted']['count'] * 15),
            # '{college_commercialized_count}': str(data['B']['patents']['collegeCommercialized']['count']),
            '{college_commercialized_marks}': str(data['B']['patents']['collegeCommercialized']['count'] * 100),
            # '{college_granted_count}': str(data['B']['patents']['collegeGranted']['count']),
            '{college_granted_marks}': str(data['B']['patents']['collegeGranted']['count'] * 30),
            '{patents_marks}': str(data['B']['patents']['marks']),
            
            # 7. Training Revenue
            '{training_amount}': str(data['B']['training']['revenue']['amount']),
            '{training_marks}': str(data['B']['training']['marks']),
            
            # 8. Non-Research Grants
            '{nonresearch_grants_amount}': str(data['B']['nonResearchGrants']['amount']['value']),
            '{nonresearch_grants_marks}': str(data['B']['nonResearchGrants']['marks']),
            
            # 9. Products
            # '{commercialized_products_count}': str(data['B']['products']['commercialized']['count']),
            '{commercialized_products_marks}': str(data['B']['products']['commercialized']['count'] * 100),
            # '{developed_products_count}': str(data['B']['products']['developed']['count']),
            '{developed_products_marks}': str(data['B']['products']['developed']['count'] * 40),
            # '{poc_products_count}': str(data['B']['products']['poc']['count']),
            '{poc_products_marks}': str(data['B']['products']['poc']['count'] * 10),
            '{products_marks}': str(data['B']['products']['marks']),
            
            # 10. Awards
            # '{international_awards_count}': str(data['B']['awards']['international']['count']),
            '{international_awards_marks}': str(data['B']['awards']['international']['count'] * 30),
            # '{government_awards_count}': str(data['B']['awards']['government']['count']),
            '{government_awards_marks}': str(data['B']['awards']['government']['count'] * 20),
            # '{national_awards_count}': str(data['B']['awards']['national']['count']),
            '{national_awards_marks}': str(data['B']['awards']['national']['count'] * 5),
            # '{international_fellowship_count}': str(data['B']['awards']['internationalFellowship']['count']),
            '{international_fellowship_marks}': str(data['B']['awards']['internationalFellowship']['count'] * 50),
            # '{national_fellowship_count}': str(data['B']['awards']['nationalFellowship']['count']),
            '{national_fellowship_marks}': str(data['B']['awards']['nationalFellowship']['count'] * 30),
            '{awards_marks}': str(data['B']['awards']['marks']),
            
            # 11. Grants and Revenue
            # '{research_grants_amount}': str(data['B']['grantsAndRevenue']['researchGrants']['amount']),
            '{research_grants_marks}': str(data['B']['grantsAndRevenue']['researchGrants']['amount'] // 200000 * 10),
            # '{consultancy_revenue_amount}': str(data['B']['grantsAndRevenue']['consultancyRevenue']['amount']),
            '{consultancy_revenue_marks}': '0',  # Calculate based on specific formula if needed
            # '{patent_revenue_amount}': str(data['B']['grantsAndRevenue']['patentCommercialRevenue']['amount']),
            '{patent_revenue_marks}': '0',  # Calculate based on specific formula if needed
            # '{product_revenue_amount}': str(data['B']['grantsAndRevenue']['productCommercialRevenue']['amount']),
            '{product_revenue_marks}': '0',  # Calculate based on specific formula if needed
            # '{startup_revenue_amount}': str(data['B']['grantsAndRevenue']['startupRevenue']['amount']),
            '{startup_revenue_marks}': '0',  # Calculate based on specific formula if needed
            # '{startup_funding_amount}': str(data['B']['grantsAndRevenue']['startupFunding']['amount']),
            '{startup_funding_marks}': '0',  # Calculate based on specific formula if needed
            '{grants_revenue_marks}': str(data['B']['grantsAndRevenue']['marks']),
            
            # 12. Startup PCCOE
            # '{startup_revenue_pccoe_amount}': str(data['B']['startupPCCOE']['revenue']['amount']),
            '{startup_revenue_pccoe_marks}': '0',  # Calculate if amount > 50000: 100 marks
            # '{startup_funding_pccoe_amount}': str(data['B']['startupPCCOE']['funding']['amount']),
            '{startup_funding_pccoe_marks}': '0',  # Calculate if amount > 500000: 100 marks
            # '{startup_products_count}': str(data['B']['startupPCCOE']['products']['count']),
            '{startup_products_marks}': str(data['B']['startupPCCOE']['products']['count'] * 40),
            # '{startup_poc_count}': str(data['B']['startupPCCOE']['poc']['count']),
            '{startup_poc_marks}': str(data['B']['startupPCCOE']['poc']['count'] * 10),
            # '{startup_registered_count}': str(data['B']['startupPCCOE']['registered']['count']),
            '{startup_registered_marks}': str(data['B']['startupPCCOE']['registered']['count'] * 5),
            '{startup_pccoe_marks}': str(data['B']['startupPCCOE']['marks']),
            
            # 13. Industry Interaction
            # '{active_mou_count}': str(data['B']['industryInteraction']['activeMOU']['count']),
            '{active_mou_marks}': str(data['B']['industryInteraction']['activeMOU']['count'] * 10),
            # '{lab_development_count}': str(data['B']['industryInteraction']['labDevelopment']['count']),
            '{lab_development_marks}': str(data['B']['industryInteraction']['labDevelopment']['count'] * 20),
            '{industry_interaction_marks}': str(data['B']['industryInteraction']['marks']),
            
            # 14. Industry Association
            # '{internships_placements_count}': str(data['B']['industryAssociation']['internshipsAndPlacements']['count']),
            '{internships_placements_marks}': str(data['B']['industryAssociation']['internshipsAndPlacements']['count'] * 10),
            '{industry_association_marks}': str(data['B']['industryAssociation']['marks']),
            
            # Total Section B
            '{section_b_total}': str(data['B']['total_marks']),
            
            # Section C placeholders (keeping these as they were)
            '{qualification_marks}': str(data['C']['1']['qualification']['marks']),
            '{training_attended_marks}': str(data['C']['2']['trainingAttended']['marks']),
            '{training_organized_marks}': str(data['C']['3']['trainingOrganized']['marks']),
            '{phd_guided_marks}': str(data['C']['4']['phdGuided']['marks']),
            '{section_c_total}': str(data['C']['total_marks'])
        })
        
        # Replace placeholders in paragraphs and tables
        for paragraph in doc.paragraphs:
            for placeholder, value in placeholders.items():
                if placeholder in paragraph.text:
                    paragraph.text = paragraph.text.replace(placeholder, value)
        
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for placeholder, value in placeholders.items():
                            if placeholder in paragraph.text:
                                paragraph.text = paragraph.text.replace(placeholder, value)
        
        return doc

    except Exception as e:
        raise Exception(f"Error in fill_template_document: {str(e)}")

@app.route('/<department>/<user_id>/generate-doc', methods=['GET'])
def generate_filled_document(department, user_id):
    output_path = None
    try:
        # Get the department collection
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        # Get user data directly from MongoDB
        user_doc = collection.find_one({"_id": user_id})
        if not user_doc:
            return jsonify({"error": "User data not found"}), 404

        # Create data structure
        data = {
            'A': user_doc.get('A', {}),
            'B': user_doc.get('B', {}),
            'C': user_doc.get('C', {})
        }

        # Generate document
        doc = fill_template_document(data, user_id, department)
        
        # Create a safe filename
        safe_filename = secure_filename(f"filled_appraisal_{user_id}.docx")
        
        # Save to a temporary directory
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.join(temp_dir, safe_filename)
        
        # Save the document
        doc.save(output_path)
        
        # Send file
        return send_file(
            output_path,
            as_attachment=True,
            download_name=safe_filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        
    except Exception as e:
        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        return jsonify({"error": str(e)}), 500
    
from docx2pdf import convert
import tempfile

import cloudinary
import cloudinary.uploader
# Add after app initialization
cloudinary.config(
    cloud_name="dfbuztt4g",  # Add your cloud name
    api_key="768753868147243",
    api_secret="BD0XqxX5uuEis4JdmvsJerqEArA"    # Add your API secret
)

@app.route('/<department>/<user_id>/generate-doc/<format>', methods=['GET'])
def generate_document(department, user_id, format):
    if format not in ['pdf', 'docx']:
        return jsonify({"error": "Invalid format. Use 'pdf' or 'docx'"}), 400
        
    output_path = None
    temp_docx = None
    try:
        # Initialize COM for this thread
        pythoncom.CoInitialize()
        
        # Get user data and generate document
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400

        user_doc = collection.find_one({"_id": user_id})
        if not user_doc:
            return jsonify({"error": "User data not found"}), 404

        data = {
            'A': user_doc.get('A', {}),
            'B': user_doc.get('B', {}),
            'C': user_doc.get('C', {})
        }

        doc = fill_template_document(data, user_id, department)
        
        # Create temporary directory
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        if format == 'pdf':
            # Handle PDF generation
            safe_filename_docx = secure_filename(f"temp_{user_id}.docx")
            safe_filename = secure_filename(f"filled_appraisal_{user_id}.pdf")
            temp_docx = os.path.join(temp_dir, safe_filename_docx)
            output_path = os.path.join(temp_dir, safe_filename)
            
            # Save and convert to PDF
            doc.save(temp_docx)
            convert(temp_docx, output_path)
            
            # Store PDF in GridFS
            with open(output_path, 'rb') as pdf_file:
                file_id = fs.put(
                    pdf_file,
                    filename=safe_filename,
                    user_id=user_id,
                    department=department,
                    content_type='application/pdf'
                )
            
            # Update user document with file reference
            collection.update_one(
                {"_id": user_id},
                {"$set": {
                    "appraisal_pdf": {
                        "file_id": str(file_id),
                        "filename": safe_filename,
                        "upload_date": datetime.now()
                    }
                }}
            )
            
            mimetype = 'application/pdf'
            
        else:
            # Handle DOCX generation
            safe_filename = secure_filename(f"filled_appraisal_{user_id}.docx")
            output_path = os.path.join(temp_dir, safe_filename)
            doc.save(output_path)
            
            # Store DOCX in GridFS
            with open(output_path, 'rb') as docx_file:
                file_id = fs.put(
                    docx_file,
                    filename=safe_filename,
                    user_id=user_id,
                    department=department,
                    content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                )
            
            # Update user document with file reference
            collection.update_one(
                {"_id": user_id},
                {"$set": {
                    "appraisal_docx": {
                        "file_id": str(file_id),
                        "filename": safe_filename,
                        "upload_date": datetime.now()
                    }
                }}
            )
            
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

        # Send file
        return send_file(
            output_path,
            as_attachment=True,
            download_name=safe_filename,
            mimetype=mimetype
        )

    except Exception as e:
        # Cleanup on error
        for path in [temp_docx, output_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        return jsonify({"error": str(e)}), 500
    finally:
        # Cleanup temporary files and uninitialize COM
        for path in [temp_docx, output_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        pythoncom.CoUninitialize()

# Add a download endpoint to handle direct file downloads
@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_from_directory(
            os.path.join(os.getcwd(), 'temp'),
            filename,
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 404

# Add this function to clean up old temporary files
def cleanup_temp_files():
    temp_dir = os.path.join(os.getcwd(), 'temp')
    if os.path.exists(temp_dir):
        for file in os.listdir(temp_dir):
            try:
                file_path = os.path.join(temp_dir, file)
                # Remove files older than 1 hour
                if os.path.getmtime(file_path) < time.time() - 3600:
                    os.remove(file_path)
            except:
                continue

# Add these imports at the top of your file
import time
from apscheduler.schedulers.background import BackgroundScheduler
import pythoncom
from datetime import datetime

# Add this after your app initialization
scheduler = BackgroundScheduler()
scheduler.add_job(func=cleanup_temp_files, trigger="interval", minutes=60)
scheduler.start()

@app.route('/<department>/<user_id>/download/<format>', methods=['GET'])
def get_stored_document(department, user_id, format):
    try:
        collection = department_collections.get(department)
        if collection is None:
            return jsonify({"error": "Invalid department"}), 400
            
        user_doc = collection.find_one({"_id": user_id})
        if not user_doc:
            return jsonify({"error": "User not found"}), 404
            
        # Get file reference based on format
        file_ref = user_doc.get(f"appraisal_{format}")
        if not file_ref:
            return jsonify({"error": "Document not found"}), 404
            
        # Get file from GridFS
        file_id = ObjectId(file_ref['file_id'])
        grid_out = fs.get(file_id)
        
        # Return the file
        return send_file(
            io.BytesIO(grid_out.read()),
            as_attachment=True,
            download_name=file_ref['filename'],
            mimetype=grid_out.content_type
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)