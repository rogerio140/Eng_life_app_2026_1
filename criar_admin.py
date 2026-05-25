#!/usr/bin/env python3
"""
Script para criar usuário administrador com acesso total
"""

import psycopg
import hashlib
import secrets
from config import Config

def hash_password(senha, salt=None):
    """Gera hash da senha usando salt"""
    if salt is None:
        salt = secrets.token_hex(16)
    
    senha_salt = senha + salt
    senha_hash = hashlib.sha256(senha_salt.encode()).hexdigest()
    return senha_hash, salt

def criar_usuario_admin():
    """Cria usuário administrador com acesso total"""
    
    db_config = Config.DB_CONFIG
    
    try:
        # Conectar ao banco
        conn = psycopg.connect(**db_config)
        cursor = conn.cursor()
        
        print("🔧 Configurando usuário administrador...")
        
        # Verificar se já existe um admin
        cursor.execute("SELECT id FROM usuarios WHERE email = 'admin@englife.com'")
        admin_existente = cursor.fetchone()
        
        if admin_existente:
            print("⚠️  Usuário admin já existe. Atualizando senha...")
            
            # Atualizar senha do admin existente
            nova_senha = input("Digite a nova senha para o admin (min 6 caracteres): ").strip()
            if len(nova_senha) < 6:
                print("❌ Senha deve ter pelo menos 6 caracteres!")
                return False
                
            senha_hash, salt = hash_password(nova_senha)
            
            cursor.execute("""
                UPDATE usuarios 
                SET senha_hash = %s, salt = %s, tipo = 'admin', ativo = true 
                WHERE email = 'admin@englife.com'
            """, (senha_hash, salt))
            
            print("✅ Senha do admin atualizada com sucesso!")
            
        else:
            # Criar novo usuário admin
            senha = input("Digite a senha para o usuário admin (min 6 caracteres): ").strip()
            if len(senha) < 6:
                print("❌ Senha deve ter pelo menos 6 caracteres!")
                return False
                
            senha_hash, salt = hash_password(senha)
            
            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha_hash, salt, tipo, ativo)
                VALUES ('Administrador Sistema', 'admin@englife.com', %s, %s, 'admin', true)
            """, (senha_hash, salt))
            
            print("✅ Usuário admin criado com sucesso!")
        
        # Garantir que o admin tenha acesso a todas as localizações
        print("🔗 Concedendo acesso a todas as localizações...")
        
        # Obter ID do admin
        cursor.execute("SELECT id FROM usuarios WHERE email = 'admin@englife.com'")
        admin_id = cursor.fetchone()[0]
        
        # Obter todas as localizações
        cursor.execute("SELECT id FROM localizacoes")
        localizacoes = cursor.fetchall()
        
        # Conceder acesso do admin a todas as localizações
        for loc_id in localizacoes:
            cursor.execute("""
                INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                VALUES (%s, %s)
                ON CONFLICT (usuario_id, localizacao_id) DO NOTHING
            """, (admin_id, loc_id[0]))
        
        print(f"✅ Admin tem acesso a {len(localizacoes)} localizações")
        
        # Commit das alterações
        conn.commit()
        
        # Mostrar informações
        cursor.execute("""
            SELECT u.nome, u.email, u.tipo, COUNT(ul.localizacao_id) as localizacoes
            FROM usuarios u
            LEFT JOIN usuario_localizacao ul ON u.id = ul.usuario_id
            WHERE u.email = 'admin@englife.com'
            GROUP BY u.id, u.nome, u.email, u.tipo
        """)
        
        admin_info = cursor.fetchone()
        print("\n📋 Informações do Admin:")
        print(f"   Nome: {admin_info[0]}")
        print(f"   Email: {admin_info[1]}")
        print(f"   Tipo: {admin_info[2]}")
        print(f"   Localizações com acesso: {admin_info[3]}")
        
        cursor.close()
        conn.close()
        
        print("\n🎉 Configuração do admin concluída!")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao configurar admin: {e}")
        return False

def verificar_estrutura_banco():
    """Verifica se as tabelas necessárias existem"""
    
    db_config = Config.DB_CONFIG
    
    try:
        conn = psycopg.connect(**db_config)
        cursor = conn.cursor()
        
        # Verificar se tabela de usuários existe
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'usuarios'
            )
        """)
        
        tabela_existe = cursor.fetchone()[0]
        
        if not tabela_existe:
            print("❌ Tabela 'usuarios' não encontrada!")
            print("💡 Execute primeiro o script de criação do banco de dados.")
            return False
        
        # Verificar se existem localizações
        cursor.execute("SELECT COUNT(*) FROM localizacoes")
        count_localizacoes = cursor.fetchone()[0]
        
        if count_localizacoes == 0:
            print("⚠️  Nenhuma localização encontrada no banco.")
            print("💡 O admin será criado, mas sem localizações associadas.")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Erro ao verificar estrutura do banco: {e}")
        return False

def main():
    """Função principal"""
    print("🌱 EngLife - Configuração do Usuário Administrador")
    print("=" * 50)
    
    # Verificar estrutura do banco
    if not verificar_estrutura_banco():
        return
    
    # Criar/atualizar usuário admin
    if criar_usuario_admin():
        print("\n✅ Pronto! Use as credenciais configuradas para fazer login.")
    else:
        print("\n❌ Falha na configuração do admin.")

if __name__ == "__main__":
    main()