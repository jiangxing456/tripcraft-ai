from dotenv import load_dotenv
from loguru import logger

# Load environment variables
logger.info("Loading environment variables")
load_dotenv()#先加载 .env（读密钥、数据库地址）
logger.info("Environment variables loaded")

# Import and setup logging configuration
from config.logger import setup_logging

# Configure logging with loguru
setup_logging(console_level="INFO")#配置日志 

from api.app import app#导入 FastAPI 应用

if __name__ == "__main__":
    logger.info("Starting TripCraft AI API server")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


