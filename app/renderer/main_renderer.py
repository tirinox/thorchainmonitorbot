import json
import logging
import os
import signal
import sys
import time
import traceback
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, Response, Request
from fastapi.staticfiles import StaticFiles
from jinja2 import TemplateNotFound
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from .const import DEVICE_SCALE_FACTOR
from .demo import demo_template_parameters, available_demo_templates
from .engine import RendererEngine

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# todo: get it from env or something like that...
LOC_HOST_BASE = 'http://127.0.0.1:8404'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)


class RenderRequest(BaseModel):
    template_name: str = Field(..., json_schema_extra={"example": "example.jinja2"})
    parameters: Dict = Field(..., json_schema_extra={
        "example": {"title": "Test", "heading": "Hello", "message": "This is a test."}})


renderer = RendererEngine(templates_dir=TEMPLATES_DIR, device_scale_factor=DEVICE_SCALE_FACTOR,
                          resource_base_url=LOC_HOST_BASE)


# Initialize FastAPI with Lifespan
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize Renderer
    global renderer

    # Attach Renderer to app state for access within routes
    # app.state.renderer = renderer

    # Start Renderer
    await renderer.start()
    logging.info("Renderer started.")

    try:
        yield  # This is where the application runs
    finally:
        # Stop Renderer
        await renderer.stop()
        logging.info("Renderer stopped.")


# Initialize FastAPI
app = FastAPI(title="HTML to PNG Renderer", lifespan=lifespan)

# Mount the static directory
app.mount("/static", StaticFiles(directory="data/renderer/static"), name="static")
app.mount("/logo", StaticFiles(directory="data/asset_logo"), name="asset_logo")


async def render_full_pipeline(template_name, parameters):
    # Render the template
    try:
        result = renderer.render_template_to_html(template_name, parameters)
    except TemplateNotFound:
        return Response(status_code=404, content=f"Template '{template_name}' not found.")

    # Render the HTML to PNG
    start_time = time.monotonic()
    png_bytes = await renderer.render_html_to_png(result)
    end_time = time.monotonic()
    print(f"Rendered Demo PNG image {template_name!r} in {end_time - start_time:.2f} seconds.")
    return Response(png_bytes)


def _response_no_template_found(template_name: str):
    return Response(status_code=404,
                    content=f"Template '{template_name}' not found. Available templates:\n "
                            f"{'\n'.join(available_demo_templates())}",
                    media_type="text/text")


@app.get("/render/demo-html/{name}")
async def render_just_html(name: str, req: Request):
    logging.info(f"Rendering Demo HTML {name}")

    template_name, parameters = demo_template_parameters(name)
    if not template_name:
        return _response_no_template_found(name)

    if req and req.query_params:
        logging.info(f"Query parameters: {req.query_params}")

        # Values that are numbers are converted to int or float
        for key, value in req.query_params.items():
            if value.isdigit():
                parameters[key] = int(value)
            elif value.replace(".", "", 1).isdigit():
                parameters[key] = float(value)
            elif isinstance(parameters.get(key), list):
                parameters[key] = value.split(",")
            else:
                parameters[key] = value

    rendered_html = renderer.render_template_to_html(template_name, parameters, override_resource_dir='')
    return Response(content=rendered_html.html_content, media_type="text/html")


@app.post("/render", response_class=Response, responses={200: {"content": {"image/png": {}}}})
async def render_html_to_png(request: RenderRequest):
    """
    Renders an HTML template with provided parameters and returns a PNG image.
    """
    template_name = request.template_name
    parameters = request.parameters
    logging.info(f"Rendering '{template_name}' with parameters:\n{json.dumps(parameters, indent=4)}")
    return await render_full_pipeline(template_name, parameters)


@app.get("/render/demo/{name}", response_class=Response, responses={200: {"content": {"image/png": {}}}})
async def render_demo_template(name: str, req: Request):
    """
    Renders a demo HTML template with the given name and returns a PNG image.
    """

    template_name, parameters = demo_template_parameters(name)

    if req and req.query_params:
        logging.info(f"Query parameters: {req.query_params}")
        parameters.update(req.query_params)

    if not template_name:
        return _response_no_template_found(name)

    return await render_full_pipeline(template_name, parameters)


@app.exception_handler(Exception)
async def unicorn_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=418,
        content={
            "message": f"Oops! {exc!r} did something. There goes a rainbow...",
            "detail": traceback.format_exc().split("\n")
        },
    )


def handle_shutdown(sig, frame):
    print(f"Received signal {sig}. Shutting down...")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)
