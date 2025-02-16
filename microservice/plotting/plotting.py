from pymongo import MongoClient
import numpy as np
import pandas as pd
import plotly.express as px
from flask import Flask, request, jsonify, send_file
import io
import os
app = Flask(__name__)
port = int(os.getenv("PORT", 5003))# Read port dynamically 

client = MongoClient("mongodb://localhost:27017/")
soil_db = client['soil_database']
plotting_db = client['plotting_database']
#soil_layers_collection = db['soil_layers']
soil_profiles_collection = soil_db['soil_profiles']
plotting_collection = plotting_db['plotting']

def get_data_by_simulation_id(simulation_id):
    """Retrieve data from the database by simulation_id."""
    record = plotting_collection.find_one({"simulation_id": simulation_id})
    if not record:
        raise ValueError(f"No data found for simulation_id: {simulation_id}")
    return record

def as_df(data, time_steps):
    """Convert data to a DataFrame."""
    concentrations = [layer['conc'] for layer in data]
    df = pd.DataFrame(
        np.swapaxes(np.array(concentrations), 0, 1),
        columns=[f'soil_layer_{layer["id"]}' for layer in data]
    )
    df['time'] = time_steps
    return df

def create_plot(data):
    fig = px.line(
        data.melt(id_vars='time', var_name='Layer', value_name='Concentration'),
        x='time',
        y='Concentration',
        color='Layer',
        labels={'time': 'Time Steps', 'Concentration': 'Concentration'}
    )
    return fig

@app.route('/plot', methods=['POST'])
def plot():
    data = request.json
    simulation_id = data.get('simulation_id')
    if not simulation_id:
        return jsonify({"error": "simulation_id parameter is required"}), 400

    try:
        # Retrieve data
        record = get_data_by_simulation_id(simulation_id)
        time_steps = record['time_steps']
        layers = record['layers']

        # Convert to DataFrame and create plot
        df = as_df(layers, time_steps)
        fig = create_plot(df)

        # Generate the plot as a PNG image
        buffer = io.BytesIO()
        fig.write_image(buffer, format='png')  
        buffer.seek(0)

        unique_filename = f"bioturbation_plot_{simulation_id}.png"
        file_path = os.path.join(os.getcwd(), unique_filename)
        with open(file_path, 'wb') as f:
            f.write(buffer.read())
        print("Plot generated and saved")
        return jsonify({"message": "Plot generated and saved", "file_path": file_path}), 200
    
    except ValueError as e:
        return jsonify({"error": str(e)}), 404

    except Exception as e:
        return jsonify({"error": "An unexpected error occurred"}), 500
    
if __name__ == "__main__":
    app.run(debug=True, port=port)