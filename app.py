from flask import Flask, request, jsonify

app = Flask(__name__)

# Health check endpoint
@app.route('/', methods=['GET'])
def ping():
    return jsonify({"message": "Welcome to FDW project"}), 200



if __name__ == '__main__':
    app.run(debug=True)
