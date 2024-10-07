import typer
import inquirer
import requests
import yaml
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
        config = {"model_name":answers["model_name"]}
        with open('config.yaml', 'w') as f:
            yaml.dump(config, f)
    print(config)


@app.command()
def deploy() -> None:
    """Deploy the model"""
    print("""Deploy the model""")
    "1. Read config"
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
        print(versions)
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
