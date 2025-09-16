import uvicorn
from api.app import app

def main(): 
    """Application entry point 
    """
    uvicorn.run(
        "main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=True  
    )

if __name__ == "__main__":
    main()