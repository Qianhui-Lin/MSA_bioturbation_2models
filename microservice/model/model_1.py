from flask import Flask, request, jsonify
from pymongo import MongoClient
import requests
import numpy as np

app = Flask(__name__)
#soil_layers = {}  # In-memory storage 
#soil_profiles = {}  # In-memory storage 

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
soil_db = client['soil_database']
plotting_db = client['plotting_database']
#soil_layers_collection = db['soil_layers']
soil_profiles_collection = soil_db['soil_profiles']
plotting_collection = plotting_db['plotting']

# Create soil profile
@app.route('/soil-profile', methods=['POST'])
def create_soil_profile():
    data = request.json
    profile_id = soil_profiles_collection.count_documents({}) + 1
    data['profile'] = {"id": profile_id}
    layers = []
    for i, layer_data in enumerate(data['layers'], start=1):
        # Add ID for soil layer
        layer_data['id'] = i
        # Calculate bioturbation rate
        processed_layer = create_soil_layer(layer_data)
        if "error" in processed_layer:
            return jsonify(processed_layer), 400
        layers.append(processed_layer)
    
    # Update layer data
    data['layers'] = layers
    # Store in database
    soil_profiles_collection.insert_one(data)

    print(f"Profile {profile_id} has been updated.")
    return jsonify({"id": profile_id}), 201

def create_soil_layer(layer_data):
    required_fields = ['id', 'depth', 'initial_conc', 'earthworm_density', 'beta']
    if not all(field in layer_data for field in required_fields):
        return {"error": "Missing required fields"}
    try:
        bioturbation_rate = (layer_data['earthworm_density'] * layer_data['beta']) / layer_data['depth']
    except ZeroDivisionError:
        return {"error": "Depth cannot be zero"}
    # Return the processed layer data
    return {
        "id": layer_data['id'],
        "depth": layer_data['depth'],
        "conc": layer_data['initial_conc'],
        "earthworm_density": layer_data['earthworm_density'],
        "beta": layer_data['beta'],
        "bioturbation_rate": bioturbation_rate
    }

# Get soil profile by ID
@app.route('/soil-profile/<int:profile_id>', methods=['GET'])
def get_soil_profile(profile_id):
    profile = soil_profiles_collection.find_one({"profile.id": profile_id})
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    # Convert MongoDB object to JSON-friendly format
    profile["_id"] = str(profile["_id"])
    return jsonify(profile), 200

# Delete soil profile data by ID
@app.route('/soil-profile/<int:profile_id>', methods=['DELETE'])
def delete_soil_profile(profile_id):
    result = soil_profiles_collection.delete_one({"profile.id": profile_id})

    if result.deleted_count == 0:
        return jsonify({"error": "Profile not found"}), 404

    return jsonify({"message": "Profile deleted successfully"}), 200

# Update soil profile by ID 
@app.route('/soil-profile/<int:profile_id>', methods=['PUT'])
def update_soil_profile(profile_id):
    data = request.json

    # Find profile
    profile = soil_profiles_collection.find_one({"profile.id": profile_id})
    if not profile:
        return jsonify({"error": "Profile not found"}), 404

    if "layers" in data:
        updated_layers = []
        for i, layer_data in enumerate(data["layers"], start=1):
            layer_data["id"] = i

            # Validate and process the layer
            processed_layer = create_soil_layer(layer_data)
            if "error" in processed_layer:
                return jsonify(processed_layer), 400

            updated_layers.append(processed_layer)

        # Update the layers in the profile
        data["layers"] = updated_layers

    # Update the profile with new data
    update_result = soil_profiles_collection.update_one(
        {"profile.id": profile_id},
        {"$set": data}
    )

    return jsonify({"message": "Profile updated successfully"}), 200

# Model 1 implementation
def bioturbation(soil_layers, dt):
    """
    Perform bioturbation for the soil layers for the given time step.
    Modifies the concentrations of the layers in-place.
    """
    for l, layer in enumerate(soil_layers):
        fraction_of_layer_to_mix = layer["bioturbation_rate"] * dt
        if l < len(soil_layers) - 1:  # Skip the last layer
            delta = fraction_of_layer_to_mix * (soil_layers[l + 1]["conc"] - layer["conc"])
            layer["conc"] += delta
            soil_layers[l + 1]["conc"] -= delta


def equal(lst, tol=1e-12):
    """
    Check if the concentrations in the list are equal within the specified tolerance.
    """
    return abs(max(lst) - min(lst)) < tol


@app.route('/bioturbation/run', methods=['POST'])
def run_bioturbation():
    """
    Perform bioturbation calculations for the specified soil profile.
    """
    data = request.json
    profile_id = data["profile_id"]
    dt = data.get("dt", 86400)
    tol = data.get("steady_state_tol", 1e-12)
    max_iter = data.get("max_iter", 10000)

    # Fetch the soil profile from MongoDB
    profile = soil_profiles_collection.find_one({"profile.id": profile_id})
    if not profile:
        return jsonify({"error": "Soil profile not found"}), 404

    # Extract layers and initialize variables
    soil_layers = profile["layers"]
    data_t = [layer["conc"] for layer in soil_layers]
    data_matrix = [[layer["conc"]] for layer in soil_layers]
    t = 0
    time_steps = [0] 
    # Perform bioturbation until concentrations are equal
    while t < max_iter + 1 and not equal(data_t, tol=tol):
        bioturbation(soil_layers, dt)
        for l, layer in enumerate(soil_layers):
            data_matrix[l].append(layer["conc"])
        data_t = [layer["conc"] for layer in soil_layers]
        t += 1
        time_steps.append(t)

        if t > max_iter:
            return jsonify({"error": "Steady state not reached after max iterations"}), 400

    # Preparing the data for inserting plotting db
    simulation_id = plotting_collection.count_documents({}) + 1
    plotting_data = {
        "simulation_id": simulation_id,
        "model": profile["model"],
        "profile_id": profile_id,
        "time_steps": time_steps,
        "layers": [
            {"id": layer["id"], "conc": data_matrix[idx]}
            for idx, layer in enumerate(soil_layers)
        ]
    }

    plotting_collection.insert_one(plotting_data)

    # Return the results
    return jsonify({
        "profile_id": profile_id,
        "iterations": t,
        "simulation_id": simulation_id,
        "message": "Bioturbation simulation completed and results stored."
    }), 201


if __name__ == '__main__':
    app.run(debug=True,port=5001)