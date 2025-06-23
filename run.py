from flask import send_from_directory
import os
from app import create_app

app = create_app()

# ✅ Serve service-worker.js from the root
@app.route('/service-worker.js')
def service_worker():
    return send_from_directory(os.path.join(app.root_path, 'static', 'js'), 'service-worker.js')

# ✅ Run the app on all interfaces (required for iPhone access)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
