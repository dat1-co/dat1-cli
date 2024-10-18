from concurrent.futures import ThreadPoolExecutor

import typer
import inquirer
import requests
import yaml
import hashlib
import traceback
from yaspin import yaspin
# from tqdm.cli import tqdm
from pathlib import Path
from typing import Optional

from dat1 import __app_name__, __version__

app = typer.Typer()
CFG_PTH = Path("~/.dat1/dat1-cfg.yaml").expanduser()
PROJECT_CONFIG_NAME = "dat1.yaml"
UPLOAD_CHUNK_SIZE = 250_000_000


def usr_api_key_validate(usr_api_key):
    # Make the POST request
    response = requests.post('https://api.dat1.co/api/v1/auth', headers={'X-API-Key': usr_api_key})

    # Check if the request was successful
    if response.status_code == 200:
        return True
    else:
        print(f'\nAuthentication failed. Status code: {response.status_code}')
        return False


def calculate_hashes(directory, exclude_file_names=None):
    """ Calculate hashes of files in a given directory, excluding files specified in the exclude list."""
    hashes = []
    exclude_set = set(exclude_file_names) if exclude_file_names else []

    for file_path in Path(directory).iterdir():
        if file_path.is_file() and file_path.name not in exclude_set:
            hasher = hashlib.sha512()
            with file_path.open('rb') as f:
                while chunk := f.read(8192):
                    hasher.update(chunk)
            hashes.append({"path": str(file_path.relative_to(directory)), "hash": hasher.hexdigest()})
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
    if Path(PROJECT_CONFIG_NAME).is_file():
        with open(PROJECT_CONFIG_NAME, 'r') as f:
            config = yaml.safe_load(f)
        config["model_name"] = answers["model_name"]
        with open(PROJECT_CONFIG_NAME, 'w') as f:
            yaml.dump(config, f)
        print('Config file edited')
    else:
        print('Config file created')
        config = {"model_name": answers["model_name"], "exclude": []}
        with open(PROJECT_CONFIG_NAME, 'w') as f:
            yaml.dump(config, f)
    print(config)


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
            f"https://api.dat1.co/api/v1/models/{model_name}/versions/{new_model_version}/files?parts={parts}",
            json=file, headers=headers
        ).json()
        upload_urls = create_upload_response["uploadUrls"]
        upload_id = create_upload_response["uploadId"]
        s3_key = create_upload_response["s3Key"]
    except Exception as e:
        print(e)
        traceback.print_exc()
        exit(1)

    tasks = enumerate(upload_urls)
    file_size = Path(file["path"]).stat().st_size

    def process_part(x):
        return upload_file_part(x[1], file['path'], x[0])

    if len(upload_urls) > 4:
        with ThreadPoolExecutor(max_workers=4) as pool:
            parts_data = list(pool.map(process_part, tasks))
    else:
        parts_data = list(map(process_part, tasks))

    parts_data.sort(key=lambda x: x["part_number"])


    res = requests.request(
        "POST",
        f"https://api.dat1.co/api/v1/models/uploads/{upload_id}/complete",
        json={"parts": parts_data, "s3_key": s3_key},
        headers=headers
    )

    if res.status_code != 200:
        print(f"Failed to complete upload: {res.text}")
        exit(1)


@app.command()
def deploy() -> None:
    with yaspin(text="Preparing", color="white") as sp:
        """Deploy the model"""
        "1. Read config"
        if not Path(PROJECT_CONFIG_NAME).is_file():
            print("Config not found, run 'dat1 init' first")
            exit(1)

        with open(CFG_PTH, 'r') as global_cfg:
            api_key = yaml.safe_load(global_cfg)["user_api_key"]
        with open(PROJECT_CONFIG_NAME, 'r') as file:
            config = yaml.safe_load(file)

        url = f"https://api.dat1.co/api/v1/models/{config['model_name']}"
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
        files_hashes = calculate_hashes("./", exclude_file_names=exclude)
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
        url = f"https://api.dat1.co/api/v1/models/{config['model_name']}/versions"
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
        executor.map(lambda x: upload_file(x, api_key, config["model_name"], new_model_version), files_to_add)

    "9. Mark version as complete"
    url = f"https://api.dat1.co/api/v1/models/{config['model_name']}/versions/{new_model_version}/complete"

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


@app.command()
def serve() -> None:
    """Serve the project locally"""
    print("""Serve the project locally""")


@app.command()
def destroy() -> None:
    """Destroy the project"""
    print("""Destroy the project""")


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
