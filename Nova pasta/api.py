from flask import Blueprint, request, jsonify, session
from database import Database
from utils import validar_mac_address, processar_dados_sensores, buscar_config_datalogger_simples, criar_limites_padrao
from datetime import datetime
from psycopg2.extras import RealDictCursor

api_bp = Blueprint("api", __name__, url_prefix="/api")
db = Database()

# ============================================
# ROTAS DA API PARA DATALOGGER
# ============================================

@api_bp.route("/datalogger/autocadastro", methods=["POST"])
def autocadastro_datalogger():
    """Endpoint para autocadastro de dataloggers e alimentadores (ESP32)"""
    try:
        if not request.is_json:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Content-Type deve ser application/json'
            }), 400
        
        data = request.get_json()
        
        if not data or 'identificacao' not in data:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Campo "identificacao" é obrigatório'
            }), 400
        
        identificacao = data['identificacao']
        localizacao_info = data.get('localizacao')
        dados_sensores = data.get('dados', [])
        
        mac_address = identificacao.get('mac_address', '').strip().upper()
        tipo = identificacao.get('tipo', 'datalogger')
        
        if not mac_address:
            return jsonify({
                'status': 'erro',
                'mensagem': 'mac_address é obrigatório na identificação'
            }), 400
        
        if not validar_mac_address(mac_address):
            return jsonify({
                'status': 'erro',
                'mensagem': 'Formato de MAC address inválido. Use: XX:XX:XX:XX:XX:XX'
            }), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Erro de conexão com o banco de dados'
            }), 500
        
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT d.id, d.tipo, d.nome, d.localizacao_id, 
                       dl.id as datalogger_id, a.id as alimentador_id, d.online
                FROM dispositivos d
                LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id AND d.tipo = 'datalogger'
                LEFT JOIN alimentadores a ON d.id = a.dispositivo_id AND d.tipo = 'alimentador'
                WHERE d.mac_address = %s
            """, (mac_address,))
            
            equipamento_existente = cursor.fetchone()
            
            dispositivo_id = None
            datalogger_id = None
            alimentador_id = None
            localizacao_id = None
            
            if equipamento_existente:
                dispositivo_id, tipo_existente, nome_existente, localizacao_id, datalogger_id, alimentador_id, online = equipamento_existente
                
                if tipo_existente != tipo:
                    return jsonify({
                        'status': 'erro',
                        'mensagem': f'Equipamento já existe com tipo diferente: {tipo_existente}'
                    }), 400
                
                print(f"✅ Equipamento existente encontrado: {nome_existente} (ID: {dispositivo_id})")
                
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = true, ultima_comunicacao = %s,
                        versao_firmware = COALESCE(%s, versao_firmware)
                    WHERE id = %s
                """, (datetime.now(), identificacao.get('versao_firmware'), dispositivo_id))
                
            else:
                print(f"🔧 Criando novo equipamento com MAC: {mac_address}")
                
                if localizacao_info:
                    nome_localizacao = localizacao_info.get('nome', f'Localização {mac_address}')
                    cursor.execute("""
                        SELECT id FROM localizacoes WHERE nome = %s
                    """, (nome_localizacao,))
                    
                    localizacao = cursor.fetchone()
                    
                    if localizacao:
                        localizacao_id = localizacao[0]
                        print(f"📍 Usando localização existente (ID: {localizacao_id})")
                    else:
                        tipo_localizacao = localizacao_info.get('tipo', 'estufa')
                        descricao_localizacao = localizacao_info.get('descricao', '')
                        
                        cursor.execute("""
                            INSERT INTO localizacoes (nome, tipo, descricao)
                            VALUES (%s, %s, %s)
                            RETURNING id
                        """, (nome_localizacao, tipo_localizacao, descricao_localizacao))
                        
                        localizacao_id = cursor.fetchone()[0]
                        
                        cursor.execute("""
                            SELECT id FROM usuarios WHERE tipo = 'admin' LIMIT 1
                        """)
                        
                        admin_id = cursor.fetchone()[0] if cursor.rowcount > 0 else None
                        
                        if admin_id:
                            cursor.execute("""
                                INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                                VALUES (%s, %s)
                            """, (admin_id, localizacao_id))
                        
                        print(f"📍 Nova localização criada (ID: {localizacao_id})")
                
                if not localizacao_id:
                    cursor.execute("SELECT id FROM localizacoes LIMIT 1")
                    localizacao_id = cursor.fetchone()[0] if cursor.rowcount > 0 else None
                
                nome_equipamento = identificacao.get('nome', f'Equipamento {mac_address}')
                modelo = identificacao.get('modelo', '')
                versao_firmware = identificacao.get('versao_firmware', '')
                
                cursor.execute("""
                    INSERT INTO dispositivos (
                        localizacao_id, nome, descricao, mac_address,
                        tipo, modelo, versao_firmware, online, ultima_comunicacao
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s)
                    RETURNING id
                """, (
                    localizacao_id, nome_equipamento, identificacao.get('descricao', ''), mac_address,
                    tipo, modelo, versao_firmware, datetime.now()
                ))
                
                dispositivo_id = cursor.fetchone()[0]
                print(f"✅ Dispositivo {nome_equipamento} (ID: {dispositivo_id}) criado.")
                
                if tipo == 'datalogger':
                    cursor.execute("""
                        INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                        VALUES (%s, %s, %s)
                        RETURNING id
                    """, (dispositivo_id, identificacao.get('quantidade_sensores', 3), identificacao.get('intervalo_leitura', 60)))
                    
                    datalogger_id = cursor.fetchone()[0]
                    print(f"✅ Datalogger (ID: {datalogger_id}) criado.")
                    
                    sensores_base = data.get('sensores', [
                        {'nome': 'Sensor Água', 'tipo': 'temperatura', 'unidade': '°C', 'posicao': 'agua', 'endereco': f'DS18B20_agua'},
                        {'nome': 'Sensor Estufa', 'tipo': 'temperatura', 'unidade': '°C', 'posicao': 'estufa', 'endereco': f'DS18B20_estufa'},
                        {'nome': 'Sensor Externa', 'tipo': 'temperatura', 'unidade': '°C', 'posicao': 'externa', 'endereco': f'DS18B20_externa'}
                    ])
                    
                    for s in sensores_base:
                        cursor.execute("""
                            INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (datalogger_id, s['nome'], s['tipo'], s['unidade'], s['posicao'], s['endereco']))
                    print(f"✅ {len(sensores_base)} sensores criados para datalogger {datalogger_id}.")
                    
                    criar_limites_padrao(cursor, localizacao_id)
                    print(f"✅ Limites padrão de temperatura criados para localização {localizacao_id}.")

                elif tipo == 'alimentador':
                    capacidade_racao = identificacao.get('capacidade_racao', 1000)
                    nivel_racao_atual = identificacao.get('nivel_racao_atual', capacidade_racao)
                    vazao_media = identificacao.get('vazao_media', 0)

                    cursor.execute("""
                        INSERT INTO alimentadores (dispositivo_id, capacidade_racao, vazao_media, nivel_racao_atual)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (dispositivo_id, capacidade_racao, vazao_media, nivel_racao_atual))
                    alimentador_id = cursor.fetchone()[0]
                    print(f"✅ Alimentador (ID: {alimentador_id}) criado.")

                    cursor.execute("""
                        INSERT INTO config_alimentadores (alimentador_id, ativa)
                        VALUES (%s, false)
                    """, (alimentador_id,))
                    print(f"✅ Configuração padrão de alimentador criada.")

                    cursor.execute("""
                        INSERT INTO calibracao_alimentadores (alimentador_id)
                        VALUES (%s)
                    """, (alimentador_id,))
                    print(f"✅ Calibração padrão de alimentador criada.")

                    # Associar a um datalogger da mesma localização (se existir)
                    cursor.execute("""
                        SELECT dl.id as datalogger_id, d.id as dispositivo_id
                        FROM dataloggers dl
                        JOIN dispositivos d ON dl.dispositivo_id = d.id
                        WHERE d.localizacao_id = %s AND d.tipo = 'datalogger' AND d.online = true
                        LIMIT 1
                    """, (localizacao_id,))
                    
                    datalogger_associado = cursor.fetchone()
                    
                    if datalogger_associado:
                        datalogger_id_assoc = datalogger_associado[0]
                        cursor.execute("""
                            INSERT INTO alimentador_datalogger (alimentador_id, datalogger_id)
                            VALUES (%s, %s)
                            ON CONFLICT (alimentador_id) DO UPDATE SET
                                datalogger_id = EXCLUDED.datalogger_id
                        """, (alimentador_id, datalogger_id_assoc))
                        print(f"✅ Alimentador associado ao datalogger ID: {datalogger_id_assoc}")
                    else:
                        print(f"⚠️ Nenhum datalogger encontrado na localização {localizacao_info.get('nome')} para associar")

            # Processar dados de sensores se for um datalogger
            if tipo == 'datalogger' and datalogger_id and dados_sensores:
                processar_dados_sensores(cursor, datalogger_id, dados_sensores, localizacao_id)
                print(f"✅ {len(dados_sensores)} leituras de sensores processadas.")

            # Processar dados de alimentador
            if tipo == 'alimentador' and alimentador_id:
                nivel_racao_atual = data.get('alimentador_info', {}).get('nivel_racao_atual')
                motor_ligado = data.get('alimentador_info', {}).get('motor_ligado')
                capacidade_racao = data.get('alimentador_info', {}).get('capacidade_racao')

                if nivel_racao_atual is not None:
                    cursor.execute("""
                        UPDATE alimentadores SET nivel_racao_atual = %s WHERE id = %s
                    """, (nivel_racao_atual, alimentador_id))

                    # Gerar alertas de ração
                    if capacidade_racao and capacidade_racao > 0:
                        percentual = (nivel_racao_atual / capacidade_racao) * 100
                        agora = datetime.now()

                        cursor.execute("""
                            SELECT timestamp FROM alertas
                            WHERE dispositivo_id = %s
                              AND tipo = 'racao'
                            ORDER BY timestamp DESC
                            LIMIT 1
                        """, (dispositivo_id,))

                        ultimo_alerta = cursor.fetchone()
                        gerar_alerta = False

                        if not ultimo_alerta:
                            gerar_alerta = True
                        else:
                            tempo_desde_ultimo = (agora - ultimo_alerta[0]).total_seconds()
                            if tempo_desde_ultimo > 1800:  # 30 min
                                gerar_alerta = True

                        if gerar_alerta:
                            if percentual < 10:
                                cursor.execute("""
                                    INSERT INTO alertas 
                                    (dispositivo_id, tipo, severidade, mensagem, timestamp)
                                    VALUES (%s, %s, %s, %s, %s)
                                """, (
                                    dispositivo_id, 'racao', 'critico',
                                    f'Nível de ração CRÍTICO: {nivel_racao_atual:.0f}g ({percentual:.0f}%)',
                                    agora
                                ))

                            elif percentual < 20:
                                cursor.execute("""
                                    INSERT INTO alertas 
                                    (dispositivo_id, tipo, severidade, mensagem, timestamp)
                                    VALUES (%s, %s, %s, %s, %s)
                                """, (
                                    dispositivo_id, 'racao', 'medio',
                                    f'Nível de ração BAIXO: {nivel_racao_atual:.0f}g ({percentual:.0f}%)',
                                    agora
                                ))

                # Histórico (opcional mas recomendado)
                cursor.execute("""
                    INSERT INTO historico_status 
                    (dispositivo_id, nivel_racao, motor_ligado, timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (
                    dispositivo_id,
                    nivel_racao_atual,
                    motor_ligado or False,
                    datetime.now()
                ))

            conn.commit()
            
            resposta = {
                'status': 'sucesso',
                'mensagem': f'Equipamento {tipo} (ID: {dispositivo_id}) processado com sucesso.',
                'dispositivo_id': dispositivo_id,
                'datalogger_id': datalogger_id,
                'alimentador_id': alimentador_id
            }
            
            if tipo == 'datalogger':
                config = buscar_config_datalogger_simples(cursor, dispositivo_id)
                resposta['config'] = config

            return jsonify(resposta), 200

    except Exception as e:
        print(f"❌ Erro no autocadastro: {e}")
        if conn:
            conn.rollback()
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500
    finally:
        if conn:
            conn.close()

@api_bp.route("/datalogger/dados", methods=["POST"])
def receber_dados_datalogger():
    """Recebe dados de leitura de sensores de um datalogger (ESP32)"""
    try:
        if not request.is_json:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Content-Type deve ser application/json'
            }), 400
        
        data = request.get_json()
        
        mac_address = data.get('mac_address', '').strip().upper()
        dados_sensores = data.get('dados', [])
        
        if not mac_address:
            return jsonify({
                'status': 'erro',
                'mensagem': 'mac_address é obrigatório'
            }), 400
        
        if not validar_mac_address(mac_address):
            return jsonify({
                'status': 'erro',
                'mensagem': 'Formato de MAC address inválido. Use: XX:XX:XX:XX:XX:XX'
            }), 400
        
        if not dados_sensores:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Nenhum dado de sensor recebido'
            }), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Erro de conexão com o banco de dados'
            }), 500
        
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT d.id, dl.id as datalogger_id, d.localizacao_id
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.mac_address = %s AND d.tipo = 'datalogger'
            """, (mac_address,))
            
            dispositivo_info = cursor.fetchone()
            
            if not dispositivo_info:
                return jsonify({
                    'status': 'erro',
                    'mensagem': 'Datalogger não encontrado ou MAC Address incorreto'
                }), 404
            
            dispositivo_id = dispositivo_info[0]
            datalogger_id = dispositivo_info[1]
            localizacao_id = dispositivo_info[2]

            # Atualizar status online e última comunicação
            cursor.execute("""
                UPDATE dispositivos 
                SET online = true, ultima_comunicacao = %s
                WHERE id = %s
            """, (datetime.now(), dispositivo_id))

            processar_dados_sensores(cursor, datalogger_id, dados_sensores, localizacao_id)
            
            conn.commit()
            
            return jsonify({
                'status': 'sucesso',
                'mensagem': f'{len(dados_sensores)} leituras de sensores registradas para {mac_address}'
            }), 200

    except Exception as e:
        print(f"❌ Erro ao receber dados do datalogger: {e}")
        if conn:
            conn.rollback()
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500
    finally:
        if conn:
            conn.close()

@api_bp.route("/datalogger/config", methods=["GET"])
def get_config_datalogger():
    """Retorna as configurações de um datalogger (ESP32)"""
    try:
        mac_address = request.args.get('mac_address', '').strip().upper()
        
        if not mac_address:
            return jsonify({'error': 'mac_address é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT d.id, d.nome, d.localizacao_id, dl.intervalo_leitura
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.mac_address = %s AND d.tipo = 'datalogger'
            """, (mac_address,))
            
            dispositivo = cursor.fetchone()
            
            if not dispositivo:
                return jsonify({'error': 'Datalogger não encontrado'}), 404
            
            # Buscar limites de temperatura
            cursor.execute("""
                SELECT tipo_sensor, maximo, minimo
                FROM limites_temperatura
                WHERE localizacao_id = %s
            """, (dispositivo['localizacao_id'],))
            
            limites = cursor.fetchall()
            
            limites_dict = {}
            for limite in limites:
                limites_dict[limite['tipo_sensor']] = {
                    'max': float(limite['maximo']),
                    'min': float(limite['minimo'])
                }
            
            return jsonify({
                'status': 'sucesso',
                'config': {
                    'intervalo_leitura': dispositivo['intervalo_leitura'],
                    'limites': limites_dict
                }
            }), 200
            
    except Exception as e:
        print(f"❌ Erro ao obter configuração do datalogger: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@api_bp.route("/equipamento/config", methods=["GET"])
def obter_config_equipamento():
    """Retorna configurações atuais do equipamento (alimentador)"""
    try:
        mac_address = request.args.get('mac_address', '').strip().upper()
        
        if not mac_address:
            return jsonify({'error': 'mac_address é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT d.id, d.nome, d.modelo, d.versao_firmware,
                           a.id as alimentador_id, a.capacidade_racao, a.vazao_media,
                           a.nivel_racao_atual
                    FROM dispositivos d
                    JOIN alimentadores a ON d.id = a.dispositivo_id
                    WHERE d.mac_address = %s AND d.tipo = 'alimentador'
                """, (mac_address,))
                
                dispositivo = cursor.fetchone()
                
                if not dispositivo:
                    return jsonify({'error': 'Alimentador não encontrado'}), 404
                
                cursor.execute("""
                    SELECT ativa, horario_inicio, horario_fim, 
                           intervalo_alimentacao, quantidade_por_alimentacao, dias_semana
                    FROM config_alimentadores
                    WHERE alimentador_id = %s
                """, (dispositivo['alimentador_id'],))
                
                config = cursor.fetchone()
                
                cursor.execute("""
                    SELECT constante_a, constante_b, tempo_acionamento
                    FROM calibracao_alimentadores
                    WHERE alimentador_id = %s
                """, (dispositivo['alimentador_id'],))
                
                calibracao = cursor.fetchone()
                
                cursor.execute("""
                    SELECT comando, parametros, id
                    FROM comandos_pendentes
                    WHERE mac_address = %s AND executado = false
                    ORDER BY criado_em ASC
                """, (mac_address,))
                
                comandos_pendentes = cursor.fetchall()
                
                resposta = {
                    'status': 'sucesso',
                    'equipamento': {
                        'id': dispositivo['id'],
                        'nome': dispositivo['nome'],
                        'modelo': dispositivo['modelo'],
                        'versao_firmware': dispositivo['versao_firmware']
                    },
                    'alimentador': {
                        'id': dispositivo['alimentador_id'],
                        'capacidade_racao': float(dispositivo['capacidade_racao']),
                        'vazao_media': float(dispositivo['vazao_media']),
                        'nivel_racao_atual': float(dispositivo['nivel_racao_atual'])
                    }
                }
                
                if config:
                    resposta['configuracao'] = {
                        'ativa': config['ativa'],
                        'horario_inicio': config['horario_inicio'].strftime('%H:%M:%S') if config['horario_inicio'] else '08:00:00',
                        'horario_fim': config['horario_fim'].strftime('%H:%M:%S') if config['horario_fim'] else '18:00:00',
                        'intervalo_alimentacao': config['intervalo_alimentacao'],
                        'quantidade_por_alimentacao': float(config['quantidade_por_alimentacao']),
                        'dias_semana': config['dias_semana']
                    }
                
                if calibracao:
                    resposta['calibracao'] = {
                        'constante_a': float(calibracao['constante_a']),
                        'constante_b': float(calibracao['constante_b']),
                        'tempo_acionamento': float(calibracao['tempo_acionamento'])
                    }
                
                if comandos_pendentes:
                    resposta['comandos_pendentes'] = [
                        {'id': c['id'], 'comando': c['comando'], 'parametros': c['parametros']} for c in comandos_pendentes
                    ]
                
                return jsonify(resposta), 200
                
        except Exception as e:
            print(f"❌ Erro interno: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route("/equipamento/status/<mac_address>", methods=["GET"])
def obter_status_equipamento(mac_address):
    """Retorna o status atual de um equipamento"""
    try:
        mac_address = mac_address.strip().upper()
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT d.id, d.nome, d.tipo, d.online, d.ultima_comunicacao,
                           EXTRACT(EPOCH FROM (NOW() - d.ultima_comunicacao)) as segundos_desde_ultima_comunicacao
                    FROM dispositivos d
                    WHERE d.mac_address = %s
                """, (mac_address,))
                
                dispositivo = cursor.fetchone()
                
                if not dispositivo:
                    return jsonify({'error': 'Equipamento não encontrado'}), 404
                
                segundos_offline = dispositivo['segundos_desde_ultima_comunicacao'] if dispositivo['segundos_desde_ultima_comunicacao'] else None
                
                return jsonify({
                    'status': 'sucesso',
                    'equipamento': {
                        'id': dispositivo['id'],
                        'nome': dispositivo['nome'],
                        'tipo': dispositivo['tipo'],
                        'online': dispositivo['online'],
                        'ultima_comunicacao': dispositivo['ultima_comunicacao'].isoformat() if dispositivo['ultima_comunicacao'] else None,
                        'segundos_offline': int(segundos_offline) if segundos_offline else 0
                    }
                }), 200
                
        except Exception as e:
            print(f"❌ Erro ao buscar status: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return jsonify({'error': str(e)}), 500

@api_bp.route("/configuracoes/datalogger/<int:datalogger_id>", methods=["PUT"])
def atualizar_config_datalogger(datalogger_id):
    """API para atualizar configurações do datalogger"""
    try:
        data = request.get_json()
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            # Verificar permissão (simplificado para o contexto da API, mas pode ser mais robusto)
            # Assumindo que a autenticação de API já foi feita ou que esta rota é para admins/dispositivos
            
            # Atualizar dispositivo
            if 'nome' in data:
                cursor.execute("""
                    UPDATE dispositivos 
                    SET nome = %s, modelo = %s, descricao = %s, localizacao_id = %s
                    WHERE id = %s
                """, (data['nome'], data.get('modelo'), data.get('descricao'), 
                      data.get('localizacao_id'), datalogger_id))
            
            # Atualizar intervalo do datalogger
            if 'intervalo_leitura' in data:
                cursor.execute("""
                    UPDATE dataloggers 
                    SET intervalo_leitura = %s
                    WHERE dispositivo_id = %s
                """, (data['intervalo_leitura'], datalogger_id))
            
            # Atualizar limites de temperatura
            if 'limites' in data:
                cursor.execute("SELECT localizacao_id FROM dispositivos WHERE id = %s", (datalogger_id,))
                localizacao_id = cursor.fetchone()[0]
                
                limites = data['limites']
                for posicao, valores in limites.items():
                    cursor.execute("""
                        INSERT INTO limites_temperatura (localizacao_id, tipo_sensor, maximo, minimo)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (localizacao_id, tipo_sensor) DO UPDATE SET
                            maximo = EXCLUDED.maximo,
                            minimo = EXCLUDED.minimo,
                            updated_at = CURRENT_TIMESTAMP
                    """, (localizacao_id, posicao, valores['max'], valores['min']))
            
            conn.commit()
            
            # Enviar comando para o ESP32 recarregar configurações (se necessário)
            cursor.execute("""
                SELECT mac_address FROM dispositivos WHERE id = %s
            """, (datalogger_id,))
            
            mac_result = cursor.fetchone()
            if mac_result:
                mac_address = mac_result[0]
                # Este comando seria para o dispositivo recarregar suas configs
                # cursor.execute("""
                #     INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                #     VALUES (%s, %s, %s, %s)
                # """, (mac_address, 'configurar', '{"recarregar": true}', session.get('usuario_id', 'API')))
                # conn.commit()
            
            return jsonify({'status': 'sucesso', 'mensagem': 'Configurações atualizadas'}), 200
            
    except Exception as e:
        print(f"❌ Erro ao atualizar configuração do datalogger: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@api_bp.route("/configuracoes/alimentador/<int:alimentador_id>", methods=["PUT"])
def atualizar_config_alimentador(alimentador_id):
    """API para atualizar configurações do alimentador"""
    try:
        data = request.get_json()
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            # Verificar permissão
            # if session['usuario_tipo'] != 'admin': # Se for necessário autenticação de sessão
            #     return jsonify({'error': 'Acesso negado'}), 403
            
            # Atualizar dispositivo
            if 'nome' in data:
                cursor.execute("""
                    UPDATE dispositivos 
                    SET nome = %s, modelo = %s, descricao = %s, localizacao_id = %s
                    WHERE id = (SELECT dispositivo_id FROM alimentadores WHERE id = %s)
                """, (data['nome'], data.get('modelo'), data.get('descricao'), 
                      data.get('localizacao_id'), alimentador_id))
            
            # Atualizar alimentador
            if 'capacidade_racao' in data:
                cursor.execute("""
                    UPDATE alimentadores 
                    SET capacidade_racao = %s, vazao_media = %s
                    WHERE id = %s
                """, (data['capacidade_racao'], data.get('vazao_media'), alimentador_id))
            
            # Atualizar configuração do alimentador
            if 'configuracao' in data:
                config_data = data['configuracao']
                cursor.execute("""
                    INSERT INTO config_alimentadores (alimentador_id, ativa, horario_inicio, horario_fim, 
                                                    intervalo_alimentacao, quantidade_por_alimentacao, dias_semana)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (alimentador_id) DO UPDATE SET
                        ativa = EXCLUDED.ativa,
                        horario_inicio = EXCLUDED.horario_inicio,
                        horario_fim = EXCLUDED.horario_fim,
                        intervalo_alimentacao = EXCLUDED.intervalo_alimentacao,
                        quantidade_por_alimentacao = EXCLUDED.quantidade_por_alimentacao,
                        dias_semana = EXCLUDED.dias_semana,
                        updated_at = CURRENT_TIMESTAMP
                """, (alimentador_id, config_data.get('ativa'), config_data.get('horario_inicio'), 
                      config_data.get('horario_fim'), config_data.get('intervalo_alimentacao'), 
                      config_data.get('quantidade_por_alimentacao'), config_data.get('dias_semana')))
            
            # Atualizar calibração do alimentador
            if 'calibracao' in data:
                calibracao_data = data['calibracao']
                cursor.execute("""
                    INSERT INTO calibracao_alimentadores (alimentador_id, constante_a, constante_b, tempo_acionamento)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (alimentador_id) DO UPDATE SET
                        constante_a = EXCLUDED.constante_a,
                        constante_b = EXCLUDED.constante_b,
                        tempo_acionamento = EXCLUDED.tempo_acionamento,
                        updated_at = CURRENT_TIMESTAMP
                """, (alimentador_id, calibracao_data.get('constante_a'), calibracao_data.get('constante_b'), 
                      calibracao_data.get('tempo_acionamento')))
            
            conn.commit()
            
            return jsonify({'status': 'sucesso', 'mensagem': 'Configurações do alimentador atualizadas'}), 200
            
    except Exception as e:
        print(f"❌ Erro ao atualizar configuração do alimentador: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@api_bp.route("/comandos/executado", methods=["POST"])
def comando_executado():
    """Endpoint para dispositivos informarem que um comando pendente foi executado"""
    try:
        if not request.is_json:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Content-Type deve ser application/json'
            }), 400
        
        data = request.get_json()
        comando_id = data.get('comando_id')
        mac_address = data.get('mac_address', '').strip().upper()
        
        if not comando_id or not mac_address:
            return jsonify({
                'status': 'erro',
                'mensagem': 'comando_id e mac_address são obrigatórios'
            }), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE comandos_pendentes
                SET executado = true, executado_em = %s
                WHERE id = %s AND mac_address = %s
            """, (datetime.now(), comando_id, mac_address))
            conn.commit()
            
            if cursor.rowcount == 0:
                return jsonify({'status': 'erro', 'mensagem': 'Comando não encontrado ou MAC Address incorreto'}), 404
            
            return jsonify({'status': 'sucesso', 'mensagem': f'Comando {comando_id} marcado como executado'}), 200
            
    except Exception as e:
        print(f"❌ Erro ao marcar comando como executado: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@api_bp.route("/comandos/enviar", methods=["POST"])
def enviar_comando():
    """Endpoint para enviar um comando para um dispositivo específico"""
    try:
        if not request.is_json:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Content-Type deve ser application/json'
            }), 400
        
        data = request.get_json()
        mac_address = data.get('mac_address', '').strip().upper()
        comando = data.get('comando')
        parametros = data.get('parametros', {})
        
        if not mac_address or not comando:
            return jsonify({
                'status': 'erro',
                'mensagem': 'mac_address e comando são obrigatórios'
            }), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (mac_address, comando, jsonify(parametros).get_data(as_text=True), session.get('usuario_id', 'API')))
            comando_id = cursor.fetchone()[0]
            conn.commit()
            
            return jsonify({'status': 'sucesso', 'mensagem': 'Comando enviado com sucesso', 'comando_id': comando_id}), 200
            
    except Exception as e:
        print(f"❌ Erro ao enviar comando: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()
