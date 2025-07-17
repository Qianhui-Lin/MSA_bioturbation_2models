import requests
import json
import sys
import os
import uuid
import time

# URLs for the services
#MODEL1_SERVICE_URL = os.getenv("MODEL1_SERVICE_URL", "http://localhost:5001/")
BASE_ALB_URL = os.getenv("BASE_ALB_URL", "http://bioturbation-alb-new-1479378295.eu-west-2.elb.amazonaws.com")
MODEL1_SERVICE_URL = f"{BASE_ALB_URL}/model"
PLOTTING_SERVICE_URL=f"{BASE_ALB_URL}/plotting"
MODEL2_SERVICE_URL = os.getenv("MODEL2_SERVICE_URL", "http://localhost:5002/")
#PLOTTING_SERVICE_URL = os.getenv("PLOTTING_SERVICE_URL", "http://localhost:5003/plotting")

def main(config_file):
    print(f"Process ID: {os.getpid()}")

    """
    Orchestrator script for running bioturbation and triggering plotting.
    """
    try:
        # Read configuration file
        with open(config_file, 'r') as f:
            config = json.load(f)
        print("Loaded configuration file.")
        # Decide which bioturbation model to run
        model = config.get("model", "").lower()
        if model == "model1":
            model_service_url = MODEL1_SERVICE_URL
        elif model == "model2":
            model_service_url = MODEL2_SERVICE_URL
        else:
            print("Error: Invalid model")
            sys.exit(1)

        #print("Creating soil profile...")
        #start_send = time.time()
        profile_response = requests.post(f"{model_service_url}/soil-profile", json=config)
        #end_receive = time.time()
        #print(f"[Orchestrator] Soil-profile request: Sent at {start_send:.6f}, Received at {end_receive:.6f}")
        if profile_response.status_code != 201:
            print("Error: Failed to create soil profile.")
            print("Details:", profile_response.json())
            sys.exit(1)
        
        profile_id = profile_response.json().get("id")
        print(f"Successfully created soil profile. Profile ID: {profile_id}")

        #print("Running bioturbation...")
        bioturbation_data = {
            "profile_id": profile_id,
            "dt": config.get("dt", 86400),
            "steady_state_tol": config.get("steady_state_tol", 1e-10),
            "max_iter": config.get("max_iter", 10000)
        }
        #start_send = time.time()
        bioturbation_response = requests.post(f"{model_service_url}/bioturbation/run", json=bioturbation_data)
        #end_receive = time.time()
        #print(f"[Orchestrator] Bioturbation request: Sent at {start_send:.6f}, Received at {end_receive:.6f}")
        
        if bioturbation_response.status_code != 201:
            print("Error: Failed to run bioturbation simulation.")
            print("Details:", bioturbation_response.json())
            sys.exit(1)
        
        simulation_id = bioturbation_response.json().get("simulation_id")
        print(f"Bioturbation simulation completed. Simulation ID: {simulation_id}")

        #print("Running plotting service...")
        # plotting_response = requests.post(PLOTTING_SERVICE_URL, json={"simulation_id": simulation_id})
        # if plotting_response.status_code != 200:
        #     print("Error: Failed to trigger plotting service.")
        #     print("Details:", plotting_response.json())
        #     sys.exit(1)

        #print("Plotting completed successfully.")

        # Trigger the plotting service
        #start_send = time.time()
        plotting_response = requests.post(f"{PLOTTING_SERVICE_URL}/plot", json={"simulation_id": simulation_id})
        #end_receive = time.time()
        #print(f"[Orchestrator] Plotting request: Sent at {start_send:.6f}, Received at {end_receive:.6f}")
        if plotting_response.status_code != 200:
            print("Error: Failed to trigger plotting service.")
            print("Details:", plotting_response.json())
            sys.exit(1)

        # Get the download URL from the plotting service response
        download_url = plotting_response.json().get("download_url")
        if not download_url:
            print("Error: No download URL returned from plotting service.")
            sys.exit(1)
        
        # Set target directory (relative to orchestrator script)
        output_dir = os.path.join("microservice", "plotting", "plots")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"bioturbation_plot_{simulation_id}_{uuid.uuid4().hex}.png")

        # Download the image to local machine
        #output_path = f"bioturbation_plot_{simulation_id}.png"
        img_response = requests.get(download_url)
        if img_response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(img_response.content)
            print(f" Plot image downloaded to: {output_path}")
        else:
            print("Error: Failed to download the plot image from S3.")
            sys.exit(1)


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

