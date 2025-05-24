# dat1-cli

![PyPI - Version](https://img.shields.io/pypi/v/dat1-cli)

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

This will create a `dat1.yaml` file in the root directory of your project. This file contains the configuration for your model:

```yaml

model_name: <your model name>
exclude:
  - '**/.git/**'
  - '**/.idea/**'
  - '*.md'
  - '*.jpg'
  - .dat1.yaml
  - .DS_Store
```

Exclude uses glob patterns to exclude files from being uploaded to the platform.

To upload your model to the platform:

```bash
dat1 deploy
```

A good starting point for your model is using one of the [example models](https://github.com/dat1-co/dat1-model-examples).

Otherwise, the platform expects a `handler.py` file in the root directory of your project that contains a FastAPI app with two endpoints: GET `/` for healthchecks and POST `/infer` for inference.
An example handler is shown below:

```python
from fastapi import Request, FastAPI
from vllm import LLM, SamplingParams
import os

# Model initialization Code
# This code should be placed before the FastAPI app is initialized

llm = LLM(model=os.path.expanduser('./'), load_format="safetensors", enforce_eager=True)

app = FastAPI()

@app.get("/")
async def root():
    return "OK"

@app.post("/infer")
async def infer(request: Request):
    # Inference Code
    request = await request.json()
    prompts = request["prompt"]
    sampling_params = SamplingParams(temperature=0.8, top_p=0.95)
    outputs = llm.generate(prompts, sampling_params)
    return { "response" : outputs[0].outputs[0].text }
```

### Streaming Responses with Server-Sent Events

To stream responses to the client, you can use Server-Sent Events (SSE).
To specify that the response should be streamed, you need to add `response_type: sse` to the model definition in the `dat1.yaml` file.

```yaml
model_name: chat_completion
response_type: sse
exclude:
  - '**/.git/**'
  - '**/.idea/**'
  - '*.md'
  - '*.jpg'
  - .dat1.yaml
```

The handler code should be modified to return a generator that yields the responses:

```python
from fastapi import Request, FastAPI
from sse_starlette.sse import EventSourceResponse
import json

app = FastAPI()

@app.get("/")
async def root():
    return "OK"

async def response_generator():
    for i in range(10):
        yield json.dumps({"response": f"Response {i}"})  

@app.post("/infer")
async def infer(request: Request):
    return EventSourceResponse(response_generator(), sep="\n")
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
