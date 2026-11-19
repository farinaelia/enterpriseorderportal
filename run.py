"""Start the portal.

Run it with:        python run.py
Or pick a port:     python run.py 8080
Then open the address it prints.
"""
import sys

from portal import create_app

app = create_app()

if __name__ == "__main__":
    # Optional port number after the command, e.g.  python run.py 8080
    # Port 5000 cant be open on Mac
    # Always use port 8001
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"\n  Open http://127.0.0.1:{port}\n")

    # debug=True reloads the server whenever you save a file and shows
    # detailed error pages. Never use debug=True on a real public server.
    app.run(host="127.0.0.1", port=port, debug=True)
