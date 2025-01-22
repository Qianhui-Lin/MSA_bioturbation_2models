from flask import Flask, request, jsonify
from pymongo import MongoClient
import numpy as np
app = Flask(__name__)

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
soil_db = client['soil_database']
plotting_db = client['plotting_database']
soil_profiles_collection = soil_db['soil_profiles']
plotting_collection = plotting_db['plotting']

# Create soil profile
@app.route('/soil-profile', methods=['POST'])
def create_soil_profile():
    data = request.json
    profile_id = soil_profiles_collection.count_documents({}) + 1
    data['profile'] = {"id": profile_id}
    h = data.get('h', 0.2)
    layers = []
    for i, layer_data in enumerate(data['layers'], start=1):
        # Add ID for soil layer
        layer_data['id'] = i
        # Calculate bioturbation rate
        processed_layer = create_soil_layer(layer_data,h)
        if "error" in processed_layer:
            return jsonify(processed_layer), 400
        layers.append(processed_layer)
    
    # Update layer data
    data['layers'] = layers
    # Store in database
    soil_profiles_collection.insert_one(data)

    print(f"Profile {profile_id} has been updated.")
    return jsonify({"id": profile_id}), 201

def create_soil_layer(layer_data,h):
    required_fields = ['id', 'depth', 'initial_conc', 'earthworm_density', 'beta']
    if not all(field in layer_data for field in required_fields):
        return {"error": "Missing required fields"}
    
    diffusion_coefficient = (layer_data['earthworm_density'] * layer_data['beta']) * h
    
    # Return the processed layer data
    return {
        "id": layer_data['id'],
        "depth": layer_data['depth'],
        "conc": layer_data['initial_conc'],
        "earthworm_density": layer_data['earthworm_density'],
        "beta": layer_data['beta'],
        "diffusion_coefficient": diffusion_coefficient,
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

# Model 2 implementation
@app.route('/bioturbation/run', methods=['POST'])
def run_bioturbation():
    data = request.json
    profile_id = data["profile_id"]
    dt = data.get("dt", 86400)/data.get("max_iter", 10000)
    tol = data.get("steady_state_tol", 1e-12)
    max_iter = data.get("max_iter", 10000)

    profile = soil_profiles_collection.find_one({"profile.id": profile_id})
    if not profile:
        return jsonify({"error": "Soil profile not found"}), 404
    
    layers = profile['layers']
    depths = [layer['depth'] for layer in layers]
    initial_conc = [layer['conc'] for layer in layers]
    diffusion_coeffs = [layer['diffusion_coefficient'] for layer in layers]
    Nx = 100  # Number of spatial grid points
    Dx = sum(depths) / Nx
    Nt = max_iter

    total_depth = sum(depths)
    grid_points = np.linspace(0, total_depth, Nx)
    C = np.zeros(Nx)

    # Assign initial concentrations to grid
    start_idx = 0
    for i, depth in enumerate(depths):
        layer_points = int(depth / Dx)
        C[start_idx:start_idx + layer_points] = initial_conc[i]
        start_idx += layer_points

    # Assign spatially varying diffusion coefficients
    D = np.zeros(Nx)
    start_idx = 0
    for i, depth in enumerate(depths):
        layer_points = int(depth / Dx)
        D[start_idx:start_idx + layer_points] = diffusion_coeffs[i]
        start_idx += layer_points

    # Perform simulation
    concentration_history = np.zeros((len(depths), Nt))
    for n in range(Nt):
        C_new = C.copy()
        for i in range(1, Nx - 1):
            D_ip = (D[i] + D[i + 1]) / 2
            D_im = (D[i] + D[i - 1]) / 2
            C_new[i] = C[i] + (dt / Dx**2) * (D_ip * (C[i + 1] - C[i]) - D_im * (C[i] - C[i - 1]))
        C[:] = C_new[:]

        # Record concentrations for each layer
        start_idx = 0
        for i, depth in enumerate(depths):
            layer_points = int(depth / Dx)
            concentration_history[i, n] = np.mean(C[start_idx:start_idx + layer_points])
            start_idx += layer_points

        # Check steady-state
        if np.max(concentration_history[:, n]) - np.min(concentration_history[:, n]) <= tol:
            concentration_history = concentration_history[:, :n + 1]
            break
    # Format results for insertion
    simulation_id = plotting_collection.count_documents({}) + 1
    plotting_data = {
        "simulation_id": simulation_id,
        "model": profile.get("model", "Unknown"),
        "profile_id": profile_id,
        "time_steps": list(range(concentration_history.shape[1])),
        "layers": [
            {"id": i + 1, "conc": concentration_history[i, :].tolist()}
            for i in range(len(depths))
        ]
    }

    # Insert into MongoDB
    plotting_collection.insert_one(plotting_data)

    return jsonify({"message": "Simulation completed", "simulation_id": simulation_id}), 201

if __name__ == '__main__':
    app.run(debug=True,port=5002)