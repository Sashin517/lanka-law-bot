from __future__ import annotations

import logging
from dotenv import load_dotenv

# Load environment variables before any other imports so LangSmith picks them up
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.api_routes import api_router
from app.core.config import settings
from app.database.session import init_db

import subprocess
import time
import urllib.request
import urllib.error
from scripts.build_graph import build_graph

def ensure_neo4j():
    container_name = "lankalawbot-neo4j"
    logger.info("Checking Neo4j Docker container...")
    check_cmd = f"docker ps -a -q -f name={container_name}"
    result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout.strip():
        subprocess.run(f"docker start {container_name}", shell=True, capture_output=True)
    else:
        logger.info("Neo4j container not found. Starting a new one (this will download the Neo4j image if you don't have it, which may take a few minutes)...")
        # Do not capture output so the user can see the docker pull progress in their terminal
        subprocess.run(f"docker run -d --name {container_name} -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/password neo4j:latest", shell=True)

    url = "http://localhost:7474"
    for i in range(30):
        try:
            response = urllib.request.urlopen(url)
            if response.getcode() == 200:
                logger.info("Neo4j is up and running!")
                return
        except urllib.error.URLError:
            pass
        time.sleep(1)
    logger.warning("Timed out waiting for Neo4j. Graph RAG might be unavailable.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-30s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger(__name__)

# FastAPI App
app = FastAPI(
    title="LankaLawBot API",
    description="AI-powered Sri Lankan legal research assistant",
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


app.include_router(api_router)


@app.on_event("startup")
def startup() -> None:
    init_db()
    try:
        ensure_neo4j()
        build_graph()
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j or Graph RAG: {e}")
