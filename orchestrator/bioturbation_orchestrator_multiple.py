import requests
import json
import sys
import os

# URLs for the services
MODEL1_SERVICE_URL = os.getenv("MODEL1_SERVICE_URL", "http://localhost:5001/")
MODEL2_SERVICE_URL = os.getenv("MODEL2_SERVICE_URL", "http://localhost:5002/")
PLOTTING_SERVICE_URL = os.getenv("PLOTTING_SERVICE_URL", "http://localhost:5003/plot")

def process_input(config):
    """process a single input configuration"""
    model = config.get("model", "").lower()
    if model == "model1":
        model_service_url = MODEL1_SERVICE_URL
    elif model == "model2":
        model_service_url = MODEL2_SERVICE_URL
    else:
        print("Error: Invalid model")
        return
    
    print("Creating soil profile...")
    profile_response = requests.post(f"{model_service_url}/soil-profile", json=config)
    if profile_response.status_code != 201:
        print("Error: Failed to create soil profile.")
        print("Details:", profile_response.json())
        return 
    
    profile_id = profile_response.json().get("id")
    print(f"Successfully created soil profile. Profile ID: {profile_id}")  

    print("Running bioturbation...")
    bioturbation_data = {
            "profile_id": profile_id,
            "dt": config.get("dt", 86400),
            "steady_state_tol": config.get("steady_state_tol", 1e-12),
            "max_iter": config.get("max_iter", 10000)
        }
    bioturbation_response = requests.post(f"{model_service_url}/bioturbation/run", json=bioturbation_data) 

    if bioturbation_response.status_code != 201:
        print("Error: Failed to run bioturbation simulation.")
        print("Details:", bioturbation_response.json())
        return
    
    simulation_id = bioturbation_response.json().get("simulation_id")
    print(f"Bioturbation simulation completed. Simulation ID: {simulation_id}")

    print("Running plotting service...")
    plotting_response = requests.post(PLOTTING_SERVICE_URL, json={"simulation_id": simulation_id})
    if plotting_response.status_code != 200:
        print("Error: Failed to trigger plotting service.")
        print("Details:", plotting_response.json())
        return

    print("Plotting completed successfully.")

def main(config_file):
    """
    Orchestrator script for running bioturbation and triggering plotting.
    """
    try:
        # Read configuration file
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        inputs = config.get("inputs", [])
        if not inputs:
            print("Error: No inputs found in the configuration file.")
            sys.exit(1)

        for i, input_config in enumerate(inputs, start=1):
            print(f"\nProcessing input {i}/{len(inputs)}...\n")
            process_input(input_config)

        print("\nAll inputs processed successfully.")

    except FileNotFoundError:
        print(f"Error: Config file '{config_file}' not found.")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Failed to parse JSON from config file '{config_file}'.")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Error: Failed to communicate with services. Details: {e}")
        sys.exit(1)
    

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python orchestrator.py <config_file>")
        sys.exit(1)

    # Pass the config file as a command-line argument
    config_file = sys.argv[1]
    main(config_file)

