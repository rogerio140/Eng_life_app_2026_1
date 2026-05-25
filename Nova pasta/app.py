from flask import Flask
from config import Config
from auth import auth_bp, iniciar_verificador_offline
from routes import routes_bp
from api import api_bp

app = Flask(__name__)
app.config.from_object(Config)

# Registrar Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(routes_bp)
app.register_blueprint(api_bp)

if __name__ == "__main__":
    # Iniciar o verificador de equipamentos offline em background
    iniciar_verificador_offline()
    app.run(debug=True, host="0.0.0.0", port=5000)
