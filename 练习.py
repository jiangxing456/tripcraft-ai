from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn
@asynccontextmanager
async def lifespan(app:FastAPI):
    print("服务启动")


    yield


    print("服务关闭")
app=FastAPI(

     title="小妹",
     description="可爱",
     lifespan=lifespan
)
@app.get("/hello")
async def hello():
    return {"兄奥秘":"你好","留下":"bushi1"}


    
if __name__=="__main__":
    uvicorn.run(app,host="127.0.0.1",port=8003)