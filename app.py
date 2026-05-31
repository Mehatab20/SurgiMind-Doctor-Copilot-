import os
import sys
from flask import Flask, request, jsonify

# Ensure the root project folder is in the Python path for importing services
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from services.prediction_service import predict_risk
except ImportError as e:
    print("Error: Could not import predict_risk from services. Make sure you run 'python training/train_model.py' first.")
    raise e

app = Flask(__name__)

# Health check route to ensure the server is running
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "project": "SurgiMind API"}), 200

# Main Prediction Endpoint
@app.route("/api/predict", methods=["POST"])
def predict():
    data = request.get_json()

    # 1. Validation: Ensure all required fields are provided
    required_fields = ["diagnosis", "admission_type", "gender", "age"]
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        return jsonify({
            "error": "Bad Request",
            "message": f"Missing required fields: {', '.join(missing_fields)}"
        }), 400

    try:
        # 2. Extract data from the request payload
        diagnosis = data["diagnosis"]
        admission_type = data["admission_type"]
        gender = data["gender"]
        age = int(data["age"]) # Ensure age is an integer

        # 3. Call your project's prediction service
        result = predict_risk(
            diagnosis=diagnosis,
            admission_type=admission_type,
            gender=gender,
            age=age
        )

        # 4. Return successful prediction JSON
        return jsonify(result), 200

    except Exception as e:
        # Handle unexpected errors gracefully without crashing the server
        return jsonify({
            "error": "Internal Server Error",
            "message": str(e)
        }), 500

if __name__ == "__main__":
    # Host '0.0.0.0' allows external connections (essential for frontend/team integration)
    # Port 5000 is the default flask port
    app.run(host="0.0.0.0", port=5000, debug=True)
