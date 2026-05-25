from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from datetime import datetime, timedelta
import json
import re
import threading
import time

app = Flask(__name__)
CORS(app)

# Configuração do banco de dados
DB_CONFIG = {
    'host': 'dpg-d76l6opr0fns73cdg0rg-a.virginia-postgres.render.com',
    'database': 'somos_educa_2026_1',
    'user': 'somos_educa_2026_1_user',
    'password': 'hzfrbePX4Kpt9FNfxH1OEJsEnHfGHW4Z',
    'port': 5432,
    'connect_timeout': 5
}

# Configurações de timeout
HEARTBEAT_TIMEOUT = 120  # Segundos sem heartbeat para considerar offline
CHECK_INTERVAL = 30  # Verificar a cada 30 segundos

def get_db_connection():
    """Cria conexão com o banco de dados"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar ao banco: {e}")
        return None

def validar_mac_address(mac):
    """Valida formato do MAC address"""
    pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', re.IGNORECASE)
    return pattern.match(mac) is not None

def atualizar_status_offline():
    """Thread para verificar dispositivos sem heartbeat recente"""
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            
            conn = get_db_connection()
            if not conn:
                continue
            
            cursor = conn.cursor()
            
            # Calcula o tempo limite
            limite_tempo = datetime.now() - timedelta(seconds=HEARTBEAT_TIMEOUT)
            
            # Atualiza dispositivos que passaram do timeout para offline
            cursor.execute("""
                UPDATE dispositivos 
                SET online = false,
                    updated_at = CURRENT_TIMESTAMP
                WHERE online = true 
                AND ultima_comunicacao < %s
                RETURNING id, nome, mac_address
            """, (limite_tempo,))
            
            dispositivos_offline = cursor.fetchall()
            
            if dispositivos_offline:
                print(f"\n⚠️ {len(dispositivos_offline)} dispositivo(s) ficaram offline:")
                for disp in dispositivos_offline:
                    print(f"   • ID: {disp[0]}, Nome: {disp[1]}, MAC: {disp[2]}")
                
                # Cria alertas para dispositivos offline
                for disp in dispositivos_offline:
                    try:
                        cursor.execute("""
                            INSERT INTO alertas (localizacao_id, dispositivo_id, tipo, severidade, mensagem, timestamp)
                            SELECT localizacao_id, %s, 'comunicacao', 'alto', 
                                   'Dispositivo offline: ' || nome, CURRENT_TIMESTAMP
                            FROM dispositivos WHERE id = %s
                        """, (disp[0], disp[0]))
                    except Exception as e:
                        print(f"   ⚠️ Erro ao criar alerta: {e}")
                
                conn.commit()
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"❌ Erro no monitoramento de status: {e}")

# Inicia a thread de monitoramento
monitor_thread = threading.Thread(target=atualizar_status_offline, daemon=True)
monitor_thread.start()

@app.route('/teste', methods=['GET'])
def teste():
    """Endpoint simples para testar se a API está rodando"""
    return jsonify({
        'status': 'ok',
        'mensagem': 'API está funcionando!',
        'timestamp': datetime.now().isoformat(),
        'heartbeat_timeout': HEARTBEAT_TIMEOUT
    }), 200

@app.route('/api/registrar', methods=['POST'])
def registrar_ou_atualizar():
    """
    Registra novo dispositivo ou atualiza se já existir
    """
    try:
        dados = request.json
        
        print("\n" + "="*50)
        print("📥 Dados recebidos do ESP32:")
        print("="*50)
        print(json.dumps(dados, indent=2))
        
        # Valida campos obrigatórios
        if 'mac_address' not in dados:
            return jsonify({'erro': 'MAC address é obrigatório'}), 400
        
        if 'nome' not in dados:
            return jsonify({'erro': 'Nome do dispositivo é obrigatório'}), 400
        
        if not validar_mac_address(dados['mac_address']):
            return jsonify({'erro': 'Formato de MAC address inválido'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cursor = conn.cursor()
        
        # Verifica se dispositivo já existe
        cursor.execute("""
            SELECT id, nome, tipo, localizacao_id 
            FROM dispositivos 
            WHERE mac_address = %s
        """, (dados['mac_address'],))
        
        dispositivo_existente = cursor.fetchone()
        
        localizacao_id = dados.get('localizacao_id', 1)
        nome = dados['nome']
        descricao = dados.get('descricao', f"Dispositivo {dados.get('tipo', 'datalogger')}")
        ip_address = dados.get('ip_address')
        tipo = dados.get('tipo', 'datalogger')
        modelo = dados.get('modelo', 'ESP32')
        versao_firmware = dados.get('versao_firmware', '1.0')
        online = True  # Sempre online no momento do registro
        
        if dispositivo_existente:
            # ATUALIZA DISPOSITIVO EXISTENTE
            dispositivo_id = dispositivo_existente[0]
            
            cursor.execute("""
                UPDATE dispositivos 
                SET online = true,
                    ip_address = %s,
                    ultima_comunicacao = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP,
                    versao_firmware = %s,
                    modelo = %s
                WHERE id = %s
                RETURNING id
            """, (ip_address, versao_firmware, modelo, dispositivo_id))
            
            conn.commit()
            mensagem = f"Dispositivo atualizado: {dispositivo_existente[1]}"
            status_code = 200
            acao = "atualizado"
            
            print(f"✅ Dispositivo atualizado: {dispositivo_existente[1]}")
            
        else:
            # CRIA NOVO DISPOSITIVO
            print(f"🆕 Criando novo dispositivo: {nome}")
            
            # Verifica/cria localização
            cursor.execute("SELECT id FROM localizacoes WHERE id = %s", (localizacao_id,))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO localizacoes (id, nome, descricao, tipo)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (nome) DO NOTHING
                """, (localizacao_id, f"Local_{localizacao_id}", "Automática", "estufa"))
                conn.commit()
            
            # Insere dispositivo
            cursor.execute("""
                INSERT INTO dispositivos 
                (localizacao_id, nome, descricao, mac_address, ip_address, 
                 tipo, modelo, versao_firmware, online, ultima_comunicacao)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                RETURNING id
            """, (localizacao_id, nome, descricao, dados['mac_address'], 
                  ip_address, tipo, modelo, versao_firmware))
            
            dispositivo_id = cursor.fetchone()[0]
            conn.commit()
            
            # Cria registros específicos
            if tipo == 'alimentador':
                cursor.execute("""
                    INSERT INTO alimentadores (dispositivo_id, capacidade_racao, vazao_media)
                    VALUES (%s, %s, %s)
                """, (dispositivo_id, dados.get('capacidade_racao', 50.0), dados.get('vazao_media', 10.0)))
                conn.commit()
                
            elif tipo == 'datalogger':
                cursor.execute("""
                    INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                    VALUES (%s, %s, %s)
                """, (dispositivo_id, dados.get('quantidade_sensores', 3), dados.get('intervalo_leitura', 60)))
                conn.commit()
            
            mensagem = f"Novo dispositivo registrado: {nome}"
            status_code = 201
            acao = "criado"
            
            print(f"✅ Dispositivo criado com ID: {dispositivo_id}")
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'sucesso',
            'mensagem': mensagem,
            'id': dispositivo_id,
            'mac_address': dados['mac_address'],
            'nome': nome,
            'tipo': tipo,
            'online': True,
            'acao': acao,
            'timestamp': datetime.now().isoformat()
        }), status_code
        
    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """
    Endpoint para o ESP32 enviar heartbeat periódico
    Mantém o dispositivo como online
    """
    try:
        dados = request.json
        
        if 'mac_address' not in dados:
            return jsonify({'erro': 'MAC address é obrigatório'}), 400
        
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cursor = conn.cursor()
        
        # Atualiza o timestamp da última comunicação
        cursor.execute("""
            UPDATE dispositivos 
            SET online = true,
                ultima_comunicacao = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE mac_address = %s
            RETURNING id, nome
        """, (dados['mac_address'],))
        
        resultado = cursor.fetchone()
        
        if not resultado:
            cursor.close()
            conn.close()
            return jsonify({
                'erro': 'Dispositivo não encontrado. Faça o registro primeiro.'
            }), 404
        
        dispositivo_id, nome = resultado
        conn.commit()
        
        # Resolve alertas de offline se houver
        cursor.execute("""
            UPDATE alertas 
            SET resolvido = true 
            WHERE dispositivo_id = %s AND tipo = 'comunicacao' AND resolvido = false
        """, (dispositivo_id,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        print(f"💓 Heartbeat recebido - {nome} (MAC: {dados['mac_address']})")
        
        return jsonify({
            'status': 'online',
            'mensagem': 'Heartbeat recebido com sucesso',
            'id': dispositivo_id,
            'nome': nome,
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"❌ Erro no heartbeat: {e}")
        return jsonify({'erro': str(e)}), 500

@app.route('/api/dispositivos', methods=['GET'])
def listar_dispositivos():
    """Lista todos os dispositivos com status online/offline"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cursor = conn.cursor()
        
        # Calcula tempo desde última comunicação
        cursor.execute("""
            SELECT d.id, d.nome, d.mac_address, d.tipo, d.online, 
                   d.modelo, d.versao_firmware,
                   d.ip_address,
                   TO_CHAR(d.ultima_comunicacao, 'DD/MM/YYYY HH24:MI:SS') as ultima_comunicacao,
                   COALESCE(l.nome, 'Não definida') as localizacao,
                   EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - d.ultima_comunicacao)) as segundos_desde_ultima_comunicacao
            FROM dispositivos d
            LEFT JOIN localizacoes l ON d.localizacao_id = l.id
            ORDER BY d.online DESC, d.ultima_comunicacao DESC
        """)
        
        dispositivos = []
        for row in cursor.fetchall():
            segundos = row[10] if row[10] else None
            
            # Determina status legível
            if row[4]:  # online true
                status_texto = "Online"
                status_cor = "verde"
            else:
                status_texto = "Offline"
                status_cor = "vermelho"
            
            dispositivos.append({
                'id': row[0],
                'nome': row[1],
                'mac_address': row[2],
                'tipo': row[3],
                'online': row[4],
                'status_texto': status_texto,
                'status_cor': status_cor,
                'modelo': row[5],
                'versao_firmware': row[6],
                'ip_address': row[7] or 'N/A',
                'ultima_comunicacao': row[8] or 'Nunca',
                'tempo_offline': f"{int(segundos)} segundos" if segundos and not row[4] else None,
                'localizacao': row[9]
            })
        
        # Estatísticas
        total = len(dispositivos)
        online_count = sum(1 for d in dispositivos if d['online'])
        offline_count = total - online_count
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'quantidade': total,
            'online': online_count,
            'offline': offline_count,
            'dispositivos': dispositivos
        }), 200
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/dispositivo/<mac_address>', methods=['GET'])
def buscar_dispositivo(mac_address):
    """Busca um dispositivo específico pelo MAC com status detalhado"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.id, d.nome, d.mac_address, d.tipo, d.online, 
                   d.modelo, d.versao_firmware, d.ip_address, d.descricao,
                   TO_CHAR(d.ultima_comunicacao, 'DD/MM/YYYY HH24:MI:SS') as ultima_comunicacao,
                   COALESCE(l.nome, 'Não definida') as localizacao,
                   EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - d.ultima_comunicacao)) as segundos_desde_ultima_comunicacao
            FROM dispositivos d
            LEFT JOIN localizacoes l ON d.localizacao_id = l.id
            WHERE d.mac_address = %s
        """, (mac_address,))
        
        dispositivo = cursor.fetchone()
        
        if not dispositivo:
            return jsonify({'erro': 'Dispositivo não encontrado'}), 404
        
        resultado = {
            'id': dispositivo[0],
            'nome': dispositivo[1],
            'mac_address': dispositivo[2],
            'tipo': dispositivo[3],
            'online': dispositivo[4],
            'modelo': dispositivo[5],
            'versao_firmware': dispositivo[6],
            'ip_address': dispositivo[7] or 'N/A',
            'descricao': dispositivo[8],
            'ultima_comunicacao': dispositivo[9],
            'localizacao': dispositivo[10],
            'tempo_desde_ultima_comunicacao': f"{int(dispositivo[11])} segundos" if dispositivo[11] else None
        }
        
        cursor.close()
        conn.close()
        
        return jsonify(resultado), 200
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

@app.route('/api/estatisticas', methods=['GET'])
def estatisticas():
    """Retorna estatísticas detalhadas do sistema"""
    try:
        conn = get_db_connection()
        if not conn:
            return jsonify({'erro': 'Erro ao conectar ao banco'}), 500
        
        cursor = conn.cursor()
        
        # Total de dispositivos
        cursor.execute("SELECT COUNT(*) FROM dispositivos")
        total = cursor.fetchone()[0]
        
        # Online/Offline
        cursor.execute("SELECT COUNT(*) FROM dispositivos WHERE online = true")
        online = cursor.fetchone()[0]
        
        # Por tipo
        cursor.execute("""
            SELECT tipo, COUNT(*) as quantidade,
                   SUM(CASE WHEN online THEN 1 ELSE 0 END) as online_count
            FROM dispositivos 
            GROUP BY tipo
        """)
        por_tipo = []
        for row in cursor.fetchall():
            por_tipo.append({
                'tipo': row[0],
                'total': row[1],
                'online': row[2],
                'offline': row[1] - row[2]
            })
        
        # Últimos heartbeats
        cursor.execute("""
            SELECT nome, TO_CHAR(ultima_comunicacao, 'HH24:MI:SS') as ultimo_heartbeat
            FROM dispositivos 
            WHERE online = true
            ORDER BY ultima_comunicacao DESC
            LIMIT 5
        """)
        ultimos_heartbeats = [{'nome': row[0], 'horario': row[1]} for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'total_dispositivos': total,
            'online': online,
            'offline': total - online,
            'percentual_online': round((online / total * 100), 2) if total > 0 else 0,
            'por_tipo': por_tipo,
            'ultimos_heartbeats': ultimos_heartbeats,
            'configuracoes': {
                'heartbeat_timeout': HEARTBEAT_TIMEOUT,
                'check_interval': CHECK_INTERVAL
            },
            'timestamp': datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'erro': str(e)}), 500

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 API COMPLETA COM MONITORAMENTO DE STATUS")
    print("="*70)
    print(f"📡 Servidor rodando em: http://192.168.50.241:5000")
    print(f"\n⏱️  Configurações de timeout:")
    print(f"   • Heartbeat timeout: {HEARTBEAT_TIMEOUT} segundos")
    print(f"   • Verificação a cada: {CHECK_INTERVAL} segundos")
    print(f"\n📋 Endpoints disponíveis:")
    print(f"   GET  /teste                    - Testar API")
    print(f"   POST /api/registrar            - Registrar dispositivo")
    print(f"   POST /api/heartbeat            - Enviar heartbeat")
    print(f"   GET  /api/dispositivos         - Listar dispositivos")
    print(f"   GET  /api/dispositivo/<MAC>    - Buscar dispositivo")
    print(f"   GET  /api/estatisticas         - Estatísticas")
    print("="*70)
    print("\n💡 Funcionamento:")
    print("   • ESP32 envia heartbeat a cada 30 segundos")
    print("   • API mantém dispositivo como ONLINE")
    print("   • Se passar 120s sem heartbeat → muda para OFFLINE")
    print("   • Cria alerta automático quando fica offline")
    print("="*70)
    
    app.run(host='0.0.0.0', port=5000, debug=True)