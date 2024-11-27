# dat1-cli

A command line interface for the [dat1](dat1.co) platform.

## Installation

```bash
pip install dat1-cli
```


## Usage

Initialize with your API key:

```bash
dat1 login
```

To initialize a new model project, run in the root directory of your project:

```bash
dat1 init
```

To upload your model to the platform:

```bash
dat1 deploy
```

A good starting point for your model is using the [example model](https://github.com/dat1-co/dat1-docker/tree/main/example).

Otherwise, the platform expects a `handler.py` file in the root directory of your project that contains a FastAPI app with two endpoints: GET `/` for healthchecks and POST `/infer` for inference.
An example handler is shown below:

```python
from fastapi import Request, FastAPI
from vllm import LLM, SamplingParams
import os

llm = LLM(model=os.path.expanduser('./'), load_format="safetensors", enforce_eager=True)

app = FastAPI()

@app.get("/")
async def root():
    return "OK"

@app.post("/infer")
async def infer(request: Request):
    request = await request.json()
    prompts = request["prompt"]
    sampling_params = SamplingParams(temperature=0.8, top_p=0.95)
    outputs = llm.generate(prompts, sampling_params)
    return { "response" : outputs[0].outputs[0].text }
```

## Launching Locally

### Pre-requisites

- Docker
- CUDA-compatible GPU 
- NVIDIA Container Toolkit

To launch your model locally, run:

```bash
dat1 serve
```

## License

MIT
