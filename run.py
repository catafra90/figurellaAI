import os
from flask import send_from_directory, render_template
from app import create_app

# 1) Create the Flask app
app = create_app()
app.config['PROPAGATE_EXCEPTIONS'] = True  # Enable full traceback display

# Service worker
@app.route('/service-worker.js')
def service_worker():
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'js'),
        'service-worker.js'
    )

# Fallback route for "/"
@app.route('/')
def index():
    try:
        return render_template('index.html')
    except:
        return '✅ Platform is running. Use the navigation menu.'

# Print all routes on startup for verification
print("\n📦 Registered Routes:")
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    print(f"🔗 {rule.rule:<30} → {rule.endpoint}")
print()

# Run the app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
