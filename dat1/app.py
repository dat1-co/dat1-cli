import typer
import inquirer
import requests
import yaml
import hashlib
# from tqdm.cli import tqdm
from pathlib import Path
from typing import Optional

from dat1 import __app_name__, __version__


app = typer.Typer()
CFG_PTH = Path("~/.dat1/dat1-cfg.yaml").expanduser()


def usr_api_key_validate(usr_api_key):
    # Make the POST request
    response = requests.post('https://api.dat1.co/api/v1/auth', headers= {'X-API-Key': usr_api_key})

    # Check if the request was successful
    if response.status_code == 200:
        print('\nAuthentication successful')
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
            hashes.append({"path": str(file_path.relative_to(directory)), "hash":hasher.hexdigest()})
    return hashes


@app.command()
def login() -> None:
    """Login and authenticate"""
    print("""Login and authenticate""")
    questions = [
        inquirer.Password('usr_api_key', message="Enter your user API key", 
                          validate=lambda _, x: usr_api_key_validate(x)),
    ]
    answers = inquirer.prompt(questions)

    if CFG_PTH.is_file():
        with open(CFG_PTH, 'r') as f:
            config = yaml.safe_load(f)
        if config['user_api_key'] == answers['user_api_key']:
            print("This user is already authenticated")
        else:
            config['user_api_key'] = answers['user_api_key']
            with open(CFG_PTH, 'w') as f:
                yaml.dump(config, f)
            print('New user authenticated, old user removed')
    else:
        CFG_PTH.parent.mkdir(exist_ok=True, parents=True)
        config = {"user_api_key": answers["usr_api_key"]}
        with open(CFG_PTH, 'w') as f:
            yaml.dump(config, f)
        print('Authentication successful, user config file created')


@app.command()
def init() -> None:
    """Initialize the model"""
    print("""Initialize the model""")
    questions = [
        inquirer.Text('model_name', message="Enter model name")
    ]
    answers = inquirer.prompt(questions)
    if Path("config.yaml").is_file():
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        config["model_name"] = answers["model_name"]
        with open('config.yaml', 'w') as f:
            yaml.dump(config, f)
        print('Config file edited')
    else:
        print('Config file created')
        config = {"model_name":answers["model_name"], "exclude":[]}
        with open('config.yaml', 'w') as f:
            yaml.dump(config, f)
    print(config)


@app.command()
def deploy() -> None:
    """Deploy the model"""
    print("""Deploy the model""")
    "1. Read config"
    # print(calculate_hashes("./"))
    # return
    if Path("config.yaml").is_file():
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)

        url = f"https://dev-api.dat1.co/api/v1/models/{config['model_name']}"
        headers = {"X-API-Key": config["user_api_key"]}
        
        "2. Get model by name"
        try:
            model = requests.request("GET", url, data="", headers=headers).text
        except Exception:
            print(Exception)

        if model:
            print(model)
        else:
            "3. Create new model"
            try:
                model = requests.request("POST", url, data="", headers=headers).text
            except Exception:
                print(Exception)
        
        "4. Get model versions"
        try:
            versions = requests.request("GET", url + "/versions", data="", headers=headers).text
        except Exception:
            print(Exception)
        # print(versions)
        "5. Calculate hashes for working version of the model"
        files_hashes = calculate_hashes("./", exclude_file_names=config["exclude"])
        if versions:
            "6. Find modified and new files"
            latest_version_set = set((x["path"], x["hash"]) for x in versions[-1]["files"])
            current_version_set = set((x["path"], x["hash"]) for x in files_hashes)
            files_to_keep = [x for x in versions[-1]["files"] if (x["path"], x["hash"]) in current_version_set]
            files_to_add = [x for x in files_hashes if (x["path"], x["hash"]) not in latest_version_set]
        else:
            files_to_keep = []
            files_to_add = files_hashes
            
        "7. Create new version of the model with reusing files"
        url = f"https://dev-api.dat1.co/api/v1/models/{config["model_name"]}/versions"
        payload = {"files": files_to_keep}
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": config["user_api_key"]
        }
        try:
            new_model_version = requests.request("POST", url, json=payload, headers=headers).text["version"]
        except Exception:
            print(Exception)
        
        "8. Add files to the new version of the model"
        for f in files_to_add:
            url = f"https://dev-api.dat1.co/api/v1/models/{config["model_name"]}/versions/{new_model_version}/files"

            headers = {
                "Content-Type": "application/json",
                "X-API-Key": "wehtpo2u38tlijgiwlrjg"
            }

            try:
                upload_url = requests.request("POST", url, json=f, headers=headers).text["uploadUrl"]
            except Exception:
                print(Exception)
            with open(f["path"], 'rb') as bf:
                files = {'file': (f["path"], bf)}
                http_response = requests.post(upload_url, data=result['fields'], files=files).text # FIX
        
        "9. Mark version as complete"
        url = f"https://dev-api.dat1.co/api/v1/models/{config["model_name"]}/versions/{new_model_version}/complete"

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": config["user_api_key"]
        }

        try:
            response = requests.request("POST", url, headers=headers).text
        except Exception:
                print(Exception)



    else:
        print("You must init model first")



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
