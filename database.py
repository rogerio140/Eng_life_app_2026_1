import psycopg
import hashlib
from config import Config

class Database:
    def __init__(self):
        self.connection = None

    def get_connection(self):
        """Estabelece conexão com o banco de dados"""
        try:
            if not self.connection or self.connection.closed:
                self.connection = psycopg.connect(
                    host=Config.DB_HOST,
                    dbname=Config.DB_NAME,
                    user=Config.DB_USER,
                    password=Config.DB_PASSWORD,
                    port=Config.DB_PORT,
                    connect_timeout=10
                )
                print(f"✅ Conectado ao banco: {Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}")
            return self.connection
        except Exception as e:
            print(f"❌ Erro de conexão com o banco {Config.DB_HOST}:{Config.DB_PORT}: {e}")
            return None

    def verificar_usuario(self, email, senha):
        """Verifica se as credenciais do usuário estão corretas"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, nome, email, senha_hash, salt, tipo, ativo
                    FROM usuarios
                    WHERE email = %s AND ativo = true
                """, (email,))
                usuario = cursor.fetchone()

                if usuario:
                    usuario_id, nome, email_db, senha_hash, salt, tipo, ativo = usuario

                    # Verificar senha usando hash
                    senha_salt = senha + salt
                    senha_hash_input = hashlib.sha256(senha_salt.encode()).hexdigest()

                    if senha_hash_input == senha_hash:
                        return {
                            'id': usuario_id,
                            'nome': nome,
                            'email': email_db,
                            'tipo': tipo,
                            'ativo': ativo
                        }
                    else:
                        print(f"❌ Senha incorreta para usuário: {email}")
                else:
                    print(f"❌ Usuário não encontrado ou inativo: {email}")

                return None

        except Exception as e:
            print(f"❌ Erro ao verificar usuário: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def obter_localizacoes_usuario(self, usuario_id):
        """Obtém as localizações associadas a um usuário"""
        conn = self.get_connection()
        if not conn:
            return []

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT l.id, l.nome, l.descricao, l.tipo
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                    ORDER BY l.nome
                """, (usuario_id,))
                localizacoes = cursor.fetchall()

                # Converter para lista de dicionários
                return [
                    {
                        'id': loc[0],
                        'nome': loc[1],
                        'descricao': loc[2],
                        'tipo': loc[3]
                    }
                    for loc in localizacoes
                ]

        except Exception as e:
            print(f"❌ Erro ao buscar localizações do usuário: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def fechar_conexao(self):
        """Fecha a conexão com o banco"""
        if self.connection and not self.connection.closed:
            self.connection.close()
            self.connection = None
