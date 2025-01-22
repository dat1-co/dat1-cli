import os
from concurrent.futures import ThreadPoolExecutor

import typer
import inquirer
import requests
import yaml
import hashlib
import traceback
from yaspin import yaspin
import globre
# from tqdm.cli import tqdm
from pathlib import Path
from typing import Optional

from dat1 import __app_name__, __version__

app = typer.Typer()
CFG_PTH = Path("~/.dat1/dat1-cfg.yaml").expanduser()
PROJECT_CONFIG_NAME = "dat1.yaml"
UPLOAD_CHUNK_SIZE = 250_000_000


root_url = "https://api.dat1.co/api/v1"
if os.environ.get("DAT1_API_URL"):
    root_url = os.environ.get("DAT1_API_URL")
    print("Using API URL:", root_url)


def usr_api_key_validate(usr_api_key):
    # Make the POST request
    response = requests.post(f'{root_url}/auth', headers={'X-API-Key': usr_api_key})

    # Check if the request was successful
    if response.status_code == 200:
        return True
    else:
        print(f'\nAuthentication failed. Status code: {response.status_code}')
        return False


def should_exclude(file_path, patterns):
    for pattern in patterns:
        if globre.match(pattern, Path(file_path).as_posix()):
            return True
    return False


def calculate_hashes(directory, exclude_patterns=None):
    """ Calculate hashes of files in a given directory, excluding files specified in the exclude list."""
    hashes = []
    exclude_set = set(exclude_patterns) if exclude_patterns else []

    for file_path in Path(directory).rglob('*'):
        if file_path.is_file() and not should_exclude(file_path, exclude_set):
            hasher = hashlib.sha512()
            with file_path.open('rb') as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            hashes.append({"path": str(file_path.relative_to(directory).as_posix()), "hash": hasher.hexdigest()})
    return hashes


@app.command()
def login() -> None:
    """Login and authenticate"""
    print("""Login and authenticate""")
    questions = [
        inquirer.Password('user_api_key', message="Enter your user API key",
                          validate=lambda _, x: usr_api_key_validate(x)),
    ]
    answers = inquirer.prompt(questions)

    if CFG_PTH.is_file():
        with open(CFG_PTH, 'r') as f:
            config = yaml.safe_load(f)
            config['user_api_key'] = answers['user_api_key']
            with open(CFG_PTH, 'w') as f:
                yaml.dump(config, f)
            print('Authentication successful')
    else:
        CFG_PTH.parent.mkdir(exist_ok=True, parents=True)
        config = {"user_api_key": answers["user_api_key"]}
        with open(CFG_PTH, 'w') as f:
            yaml.dump(config, f)
        print('Authentication successful')


@app.command()
def init() -> None:
    """Initialize the model"""
    print("""Initialize the model""")
    questions = [
        inquirer.Text('model_name', message="Enter model name")
    ]
    answers = inquirer.prompt(questions)

    class PrettyDumper(yaml.SafeDumper):
        def increase_indent(self, flow=False, indentless=False):
            return super(PrettyDumper, self).increase_indent(flow, False)

    if Path(PROJECT_CONFIG_NAME).is_file():
        with open(PROJECT_CONFIG_NAME, 'r') as f:
            config = yaml.safe_load(f)
        config["model_name"] = answers["model_name"]
        with open(PROJECT_CONFIG_NAME, 'w') as f:
            yaml.dump(config, f,
                      Dumper=PrettyDumper,
                      default_flow_style=False,
                      sort_keys=False,
                      indent=2,
                      width=80)
        print('Config file edited')
    else:
        print('Config file created')
        config = {"model_name": answers["model_name"], "exclude": ["**.git/**",
                                                                   "**__pycache__/**",
                                                                   ".idea/**",
                                                                   "*.md",
                                                                   "*.jpg",
                                                                   ".dat1.yaml",
                                                                   ".DS_Store"]}
        with open(PROJECT_CONFIG_NAME, 'w') as f:
            yaml.dump(config, f,
                      Dumper=PrettyDumper,
                      default_flow_style=False,
                      sort_keys=False,
                      indent=2,
                      width=80)

def read_file(file_path, part_number):
    start_byte = part_number * UPLOAD_CHUNK_SIZE

    with open(file_path, 'rb') as file:
        file.seek(start_byte)  # Move to the start of the part
        return file.read(UPLOAD_CHUNK_SIZE)


def upload_file_part(upload_url, file_path, part_number):
    response = requests.put(upload_url, data=read_file(file_path, part_number))
    if response.status_code != 200:
        print(f"Failed to upload file: {response.text}")
        exit(1)
    return {"part_number": part_number + 1, "etag": response.headers["ETag"]}


def upload_file(file, api_key, model_name, new_model_version):
    print(f"Uploading new file: {file['path']}")
    file_size = Path(file["path"]).stat().st_size
    parts = file_size // UPLOAD_CHUNK_SIZE + 1

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }

    try:
        create_upload_response = requests.request(
            "POST",
            f"{root_url}/models/{model_name}/versions/{new_model_version}/files?parts={parts}",
            json=file, headers=headers
        ).json()
        upload_url = create_upload_response["uploadUrl"]

        with open(file['path'], "rb") as file_data:
            response = requests.put(upload_url, data=file_data, headers={
                "Content-Type": "application/octet-stream"
            })
            if response.status_code != 200:
                print(f"Failed to upload file: {response.text}")
                exit(1)
            return file

    except Exception as e:
        print(e)
        traceback.print_exc()
        exit(1)


@app.command()
def deploy() -> None:
    with yaspin(text="preparing", color="white") as sp:
        """Deploy the model"""
        "1. Read config"
        if not Path(PROJECT_CONFIG_NAME).is_file():
            print("Config not found, run 'dat1 init' first")
            exit(1)

        with open(CFG_PTH, 'r') as global_cfg:
            api_key = yaml.safe_load(global_cfg)["user_api_key"]
        with open(PROJECT_CONFIG_NAME, 'r') as file:
            config = yaml.safe_load(file)

        url = f"{root_url}/models/{config['model_name']}"
        headers = {"X-API-Key": api_key}

        "2. Get model by name"
        try:
            response = requests.request("GET", url, headers=headers)
        except Exception as e:
            print(e)
            traceback.print_exc()
            exit(1)

        if response.status_code != 200 and response.status_code != 404:
            print(f"Failed to get model: {response.text}")
            exit(1)

        if response.status_code == 404:
            "3. Create new model"
            try:
                response = requests.request("POST", url, headers=headers)
                if response.status_code != 200:
                    print(f"Failed to create model: {response.text}")
                    exit(1)
            except Exception as e:
                print(e)
                traceback.print_exc()
                exit(1)

        "4. Get model versions"
        try:
            versions = requests.request("GET", url + "/versions", headers=headers).json()
            completed_versions = [x for x in versions if x["isCompleted"]]
        except Exception as e:
            print(e)
            traceback.print_exc()
            exit(1)

        "5. Calculate hashes for working version of the model"
        exclude = config.get("exclude") or []
        exclude.append(PROJECT_CONFIG_NAME)
        files_hashes = calculate_hashes("./", exclude_patterns=exclude)
        if completed_versions:
            "6. Find modified and new files"
            latest_version_set = set((x["path"], x["hash"]) for x in completed_versions[-1]["files"])
            current_version_set = set((x["path"], x["hash"]) for x in files_hashes)
            files_to_keep = [x for x in completed_versions[-1]["files"] if (x["path"], x["hash"]) in current_version_set]
            files_to_add = [x for x in files_hashes if (x["path"], x["hash"]) not in latest_version_set]
        else:
            files_to_keep = []
            files_to_add = files_hashes

        "7. Create new version of the model with reusing files"
        url = f"{root_url}/models/{config['model_name']}/versions"
        payload = {"files": files_to_keep}
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key
        }
        try:
            response = requests.request("POST", url, json=payload, headers=headers).json()
            new_model_version = response["version"]
        except Exception as e:
            print(e)
            traceback.print_exc()
            exit(1)
        sp.ok("✅ ")

    "8. Add files to the new version of the model"
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(
            lambda x: upload_file(x, api_key, config["model_name"], new_model_version),
            files_to_add
        )
        try:
            for x in results:
                print(f"Uploaded file: {x['path']}")
        except Exception as e:
            print("Failed to upload file")
            traceback.print_exc()
            exit(1)

    "9. Mark version as complete"
    url = f"{root_url}/models/{config['model_name']}/versions/{new_model_version}/complete"

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }

    try:
        response = requests.request("POST", url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to complete model version: {response.text}")
            exit(1)
    except Exception as e:
        print(e)
        exit(1)

    is_sse_response = config.get('response_type') == 'sse'

    if is_sse_response:
        print(f"✅  model deployed successfully, available at: \n\n    POST https://api.dat1.co/api/v1/inference/{config['model_name']}/invoke-stream\n")
        print(f"Invoke with cURL:")
        print(f"curl --request POST \\\n\
      --url https://api.dat1.co/api/v1/inference/{config['model_name']}/invoke-stream \\\n\
      --header 'Content-Type: application/json' \\\n\
      --header 'X-API-Key: <your api key>' \\\n\
      --data '<your model input>")
        return

    print(f"✅  model deployed successfully, available at: \n\n    POST https://api.dat1.co/api/v1/inference/{config['model_name']}/invoke\n")
    print(f"Invoke with cURL:")
    print(f"curl --request POST \\\n\
  --url https://api.dat1.co/api/v1/inference/{config['model_name']}/invoke \\\n\
  --header 'Content-Type: application/json' \\\n\
  --header 'X-API-Key: <your api key>' \\\n\
  --data '{{\\\n\
    \"input\": <your model input>\\\n\
}}'\\\n")


@app.command()
def serve() -> None:
    """Serve the project locally"""
    import docker
    import sys
    import signal
    import threading
    import os

    client = docker.from_env()

    image_name = "public.ecr.aws/dat1/dat1/runtime:0.6.6"
    container = None  # Global reference for cleanup
    stop_requested = threading.Event()  # Event to signal stop

    def stop_container(signum, frame):
        """Signal handler to stop the container gracefully."""
        print("\nSignal received. Stopping container...")
        stop_requested.set()  # Notify threads to stop
        if container:
            container.kill()
            print("\n✅  container stopped.")
        sys.exit(0)

    def stream_logs(container):
        """Function to stream container logs in a separate thread."""
        try:
            for log in container.logs(stream=True):
                if stop_requested.is_set():
                    break  # Stop streaming if requested
                print(log.decode('utf-8'), end="")
        except Exception as e:
            if not stop_requested.is_set():  # Ignore errors if stopping
                print(f"\nError streaming logs: {e}")

    # Attach the signal handler for SIGINT (Ctrl+C)
    signal.signal(signal.SIGINT, stop_container)

    try:
        # Pull the image
        print(f"Pulling image: {image_name}")
        layer_progress = {}
        for line in client.api.pull(image_name, stream=True, decode=True):
            if 'id' in line:  # Each layer has an 'id'
                layer_id = line['id']
                status = line.get('status', '')
                progress = line.get('progress', '')

                # Update the progress for the layer
                layer_progress[layer_id] = f"{status} {progress}"

                # Clear the screen and redraw the progress table
                sys.stdout.write("\033[H\033[J")  # Clear terminal (Linux/macOS; adjust for Windows)
                print(f"Pulling image: {image_name}\n")
                for layer_id, progress in layer_progress.items():
                    print(f"Layer {layer_id}: {progress}")
                sys.stdout.flush()
            else:
                # Handle general status messages (not layer-specific)
                print(line.get('status', ''))
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n✅  image pulled successfully")

        # Start the container
        print("\n✅  starting container...")
        devices = [docker.types.DeviceRequest(device_ids=[str(gpu_id)], capabilities=[['gpu']]) for gpu_id in [0,]]
        path = str(Path.cwd())
        container = client.containers.run(
            image_name,
            auto_remove=True,
            device_requests=devices,
            volumes=[path + ":/app"],
            ports={8000: 8000},
            detach=True,  # Detach so we can monitor it separately
        )
        print(f"\n✅  container started with ID: {container.id}\nstreaming logs...\n")

        # Start the log streaming in a background thread
        log_thread = threading.Thread(target=lambda: stream_logs(container))
        log_thread.start()

        # Wait for stop signal
        while not stop_requested.is_set():
            log_thread.join(timeout=0.1)  # Allow periodic checking for stop signal

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if container and container.status == "running":
            container.kill()
            print("\n✅  container stopped.")

def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"{__app_name__} v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
        version: Optional[bool] = typer.Option(
            None,
            "--version",
            "-v",
            help="Show CLI version and exit.",
            callback=_version_callback,
            is_eager=True,
        )
) -> None:
    return
