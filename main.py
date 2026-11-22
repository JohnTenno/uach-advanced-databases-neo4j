import os

from app import create_app
from app.database import config

app = create_app()
# 5000 is taken by the macOS AirPlay receiver.
PORT = int(os.getenv("PORT", "5050"))

if __name__ == "__main__":
    print(f"Blog Neo4j - {config.db_target}")
    print(f"Open http://127.0.0.1:{PORT}")
    # The debugger shows code and allows running it, so it only turns on with FLASK_DEBUG=1.
    app.run(port=PORT, debug=os.getenv("FLASK_DEBUG") == "1")
