from flask import Flask

def create_app():
    app = Flask(__name__, static_folder='static', static_url_path='/static_files')

    # Registrar blueprints
    from app.controllers.CEC_controller import redis_bp
    app.register_blueprint(redis_bp, url_prefix='/')

    from app.controllers.main_controller import main_bp
    app.register_blueprint(main_bp, url_prefix='/')

    from app.controllers.weather_controller import weather_bp
    app.register_blueprint(weather_bp, url_prefix='/')

    from app.controllers.ENTSOE_controller import entsoe_bp
    app.register_blueprint(entsoe_bp, url_prefix='/')

    from app.controllers.pvlib_controller import pvlib_bp
    app.register_blueprint(pvlib_bp, url_prefix='/')

    from app.controllers.mix_controller import mix_bp
    app.register_blueprint(mix_bp, url_prefix='/')
    
    from app.controllers.advice_controller import advice_bp
    app.register_blueprint(advice_bp, url_prefix='/')

    return app
