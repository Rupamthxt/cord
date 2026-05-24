import uvicorn
from backend.api.app import app

if __name__ == "__main__":
    logger_config = uvicorn.config.LOGGING_CONFIG
    logger_config["formatters"]["access"]["fmt"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logger_config["formatters"]["default"]["fmt"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    print("Starting Organizational Memory Backend Server...")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)