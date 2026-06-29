from dotenv import load_dotenv
load_dotenv()
from flask import Flask
import config
from storage import db as dbmod
from routes.web import bp
import os

def create_app():
    app = Flask(__name__)

    # NECESAR pentru login/session
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

    # config în app
    app.config["GEMINI_API_KEY"] = config.GEMINI_API_KEY
    app.config["GEMINI_MODEL"] = config.GEMINI_MODEL
    app.config["HF_TOKEN"] = config.HF_TOKEN
    app.config["HF_MODEL"] = config.HF_MODEL
    # DB init
    conn = dbmod.connect(config.DB_PATH)
    dbmod.init_db(conn)
    dbmod.ensure_default_admin(conn)   # creează admin dacă nu există
    app.config["DB_CONN"] = conn

    app.register_blueprint(bp)
    return app

if __name__ == "__main__":
    if __name__ == "__main__":
    # Ia portul oferit de Render sau folosește 5000 ca fallback local
        port = int(os.environ.get("PORT", 5000))
        create_app().run(host="0.0.0.0", port=port, debug=False)
