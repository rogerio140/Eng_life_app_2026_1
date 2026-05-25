import os
from datetime import timedelta

class Config:
    # Chave secreta para sessões Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'sua-chave-secreta-muito-secreta-aqui-2025'
    
    # Configurações do banco de dados PostgreSQL
    DB_HOST = '100.111.89.45'
    DB_NAME = 'englife_db'
    DB_USER = 'englife_user'
    DB_PASSWORD = '449140'
    DB_PORT = 5432
 


    # Configurações de sessão
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Configurações de upload (se necessário no futuro)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Configurações de debug
    DEBUG = True
    TESTING = False

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    # Em produção, use variáveis de ambiente
    DB_HOST = os.environ.get('DB_HOST', 'englifeinfor.ddns.net')
    DB_NAME = os.environ.get('DB_NAME', 'englife_db')
    DB_USER = os.environ.get('DB_USER', 'englife')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'RAEB449140')
    DB_PORT = int(os.environ.get('DB_PORT', '5432'))

class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    DB_NAME = 'englife_test_db'

# Configuração padrão
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
