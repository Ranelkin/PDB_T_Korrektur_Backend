import uvicorn
from .API.app import app

def main(): 
    uvicorn.run(
        "src.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True  # Optional: enables auto-reload during development
    )

if __name__ == "__main__":
    main()