import psycopg2
from psycopg2.extras import RealDictCursor
from config import Config
from utils import hash_password

class Database:
    def __init__(self):
        self.conn_string = Config.DATABASE_URL

    def get_connection(self):
        try:
            conn = psycopg2.connect(self.conn_string)
            return conn
        except Exception as e:
            print(f"❌ Erro ao conectar ao banco de dados: {e}")
            return None

    def verificar_usuario(self, email, senha):
        conn = self.get_connection()
        if not conn:
            return None
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT id, nome, email, senha_hash, salt, tipo FROM usuarios WHERE email = %s AND ativo = true", (email,))
                usuario = cursor.fetchone()
                if usuario:
                    senha_hash_digitada, _ = hash_password(senha, usuario["salt"])
                    if senha_hash_digitada == usuario["senha_hash"]:
                        return usuario
            return None
        except Exception as e:
            print(f"❌ Erro ao verificar usuário: {e}")
            return None
        finally:
            conn.close()
