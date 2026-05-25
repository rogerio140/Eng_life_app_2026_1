import hashlib
import secrets
from datetime import datetime, timedelta
import re

def hash_password(senha, salt=None):
    """Gera hash da senha usando salt"""
    if salt is None:
        salt = secrets.token_hex(16)
    
    senha_salt = senha + salt
    senha_hash = hashlib.sha256(senha_salt.encode()).hexdigest()
    return senha_hash, salt

def processar_dados_grafico(dados):
    """Processa os dados para formato adequado para gráficos"""
    if not dados:
        return {}
    
    dados_por_sensor = {}
    
    for sensor_id, sensor_nome, posicao, unidade, valor, timestamp in dados:
        if posicao not in dados_por_sensor:
            dados_por_sensor[posicao] = {
                'nome': sensor_nome,
                'unidade': unidade,
                'dados': []
            }
        
        if isinstance(timestamp, datetime):
            timestamp_str = timestamp.isoformat()
        elif hasattr(timestamp, 'isoformat'):
            timestamp_str = timestamp.isoformat()
        else:
            timestamp_str = str(timestamp)
        
        dados_por_sensor[posicao]['dados'].append({
            'x': timestamp_str,
            'y': float(valor)
        })
    
    return dados_por_sensor

def calcular_estatisticas(dados):
    """Calcula estatísticas básicas dos dados"""
    if not dados:
        return {}
    
    estatisticas = {}
    
    dados_por_sensor = {}
    for sensor_id, sensor_nome, posicao, unidade, valor, timestamp in dados:
        if posicao not in dados_por_sensor:
            dados_por_sensor[posicao] = {
                'nome': sensor_nome,
                'unidade': unidade,
                'valores': []
            }
        dados_por_sensor[posicao]['valores'].append(float(valor))
    
    for posicao, info in dados_por_sensor.items():
        valores = info['valores']
        if valores:
            estatisticas[posicao] = {
                'nome': info['nome'],
                'unidade': info['unidade'],
                'media': round(sum(valores) / len(valores), 2),
                'maxima': round(max(valores), 2),
                'minima': round(min(valores), 2),
                'total_leituras': len(valores)
            }
    
    return estatisticas

def validar_mac_address(mac_address):
    """Valida o formato de um MAC Address (XX:XX:XX:XX:XX:XX)"""
    if not mac_address:
        return False
    return re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', mac_address) is not None

def processar_dados_sensores(cursor, datalogger_id, dados_sensores, localizacao_id):
    """Processa os dados de sensores recebidos e insere no banco de dados"""
    for dado_sensor in dados_sensores:
        sensor_endereco = dado_sensor.get('sensor_endereco')
        valor = dado_sensor.get('valor')
        timestamp_str = dado_sensor.get('timestamp')

        if not sensor_endereco or valor is None or timestamp_str is None:
            print(f"⚠️ Dado de sensor inválido: {dado_sensor}")
            continue

        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except ValueError:
            print(f"⚠️ Timestamp inválido: {timestamp_str}")
            continue

        cursor.execute("""
            SELECT id, nome, tipo, posicao FROM sensores WHERE datalogger_id = %s AND endereco = %s
        """, (datalogger_id, sensor_endereco))
        sensor_info = cursor.fetchone()

        if sensor_info:
            sensor_id, sensor_nome, tipo_sensor, posicao_sensor = sensor_info
            cursor.execute("""
                INSERT INTO leituras_sensores (sensor_id, valor, timestamp)
                VALUES (%s, %s, %s)
            """, (sensor_id, valor, timestamp))
            
            # Verificar limites de temperatura
            if tipo_sensor == 'temperatura':
                verificar_limites_temperatura_simples(cursor, localizacao_id, posicao_sensor, valor, sensor_nome, timestamp)

        else:
            print(f"⚠️ Sensor com endereço {sensor_endereco} não encontrado para datalogger {datalogger_id}")

def buscar_config_datalogger_simples(cursor, dispositivo_id):
    """Busca configurações básicas do datalogger"""
    cursor.execute("""
        SELECT d.localizacao_id, dl.intervalo_leitura
        FROM dispositivos d
        JOIN dataloggers dl ON d.id = dl.dispositivo_id
        WHERE d.id = %s
    """, (dispositivo_id,))
    
    resultado = cursor.fetchone()
    if not resultado:
        return {'intervalo_leitura': 60, 'limites': {}}
    
    cursor.execute("""
        SELECT tipo_sensor, maximo, minimo
        FROM limites_temperatura
        WHERE localizacao_id = %s
    """, (resultado['localizacao_id'],))
    
    limites = cursor.fetchall()
    limites_dict = {}
    for limite in limites:
        limites_dict[limite['tipo_sensor']] = {
            'max': float(limite['maximo']),
            'min': float(limite['minimo'])
        }
    
    return {
        'intervalo_leitura': resultado['intervalo_leitura'],
        'limites': limites_dict
    }

def criar_limites_padrao(cursor, localizacao_id):
    """Cria limites de temperatura padrão"""
    limites_padrao = [
        ('agua', 30.0, 20.0),
        ('estufa', 35.0, 25.0),
        ('externa', 40.0, 15.0)
    ]
    
    for tipo, maximo, minimo in limites_padrao:
        cursor.execute("""
            INSERT INTO limites_temperatura (localizacao_id, tipo_sensor, maximo, minimo)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (localizacao_id, tipo_sensor) DO NOTHING
        """, (localizacao_id, tipo, maximo, minimo))

def verificar_limites_temperatura_simples(cursor, localizacao_id, posicao, valor, sensor_nome, timestamp):
    """Verifica limites de temperatura e gera alertas"""
    try:
        cursor.execute("""
            SELECT maximo, minimo 
            FROM limites_temperatura 
            WHERE localizacao_id = %s AND tipo_sensor = %s
        """, (localizacao_id, posicao))
        
        limite = cursor.fetchone()
        
        if limite and (valor > limite['maximo'] or valor < limite['minimo']):
            tipo_alerta = "TEMPERATURA_ALTA" if valor > limite['maximo'] else "TEMPERATURA_BAIXA"
            
            mensagem = (
                f"Temperatura {posicao} ({sensor_nome}): {valor:.1f}°C "
                f"{'acima' if valor > limite['maximo'] else 'abaixo'} do limite "
                f"({limite['maximo'] if valor > limite['maximo'] else limite['minimo']}°C)"
            )
            
            cursor.execute("""
                INSERT INTO alertas (localizacao_id, tipo, severidade, mensagem, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, (localizacao_id, tipo_alerta, 'MEDIA', mensagem, timestamp))
            print(f"⚠️ Alerta: {mensagem}")
            
    except Exception as e:
        print(f"⚠️ Erro ao verificar limites: {e}")
