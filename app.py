import os
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from dotenv import load_dotenv

# Import browser scraper (Playwright-based)
from browser_scraper import search_ao3_sync

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)  # Enable Cross-Origin Resource Sharing

# --- CONFIGURATION ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key')
app.config['CACHE_TYPE'] = 'SimpleCache' 
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # Cache results for 5 minutes

# --- SETUP EXTENSIONS ---
cache = Cache(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# --- ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/generate', methods=['POST'])
@limiter.limit("10 per minute")  # Specific limit for the expensive action
def generate():
    data = request.json
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    tags = data.get('tags', [])
    categories = data.get('categories', [])
    fandom = data.get('fandom', '')

    # Basic Validation
    if not tags and not fandom and not categories:
        return jsonify({"error": "Please provide at least one tag, fandom, or category."}), 400

    # Use browser-based scraper (Playwright)
    result = search_ao3_sync(tags, categories, fandom)
    
    # Handle error case
    if result.get('error'):
        error_msg = result['error']
        if "No works found" in error_msg:
            return jsonify({"error": error_msg}), 404
        else:
            return jsonify({"error": error_msg}), 502
    
    # Success
    return jsonify(result)


@app.route('/autocomplete/fandom', methods=['GET'])
def autocomplete_fandom():
    """Proxy for AO3's fandom autocomplete API."""
    term = request.args.get('term', '')
    if not term or len(term) < 2:
        return jsonify([])
    
    try:
        import requests
        response = requests.get(
            'https://archiveofourown.org/autocomplete/fandom',
            params={'term': term},
            timeout=10
        )
        if response.status_code == 200:
            return jsonify(response.json())
        return jsonify([])
    except Exception as e:
        print(f"Autocomplete error: {e}")
        return jsonify([])



# Error handler for Rate Limiting
@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Rate limit exceeded. Please try again in a minute."}), 429


if __name__ == '__main__':
    # Use generic host for Docker/Render compatibility
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))