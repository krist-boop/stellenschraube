"""Start: python app.py  →  http://localhost:5050"""
import os
from stellenschraube.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", 5050)), debug=True)
