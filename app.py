from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from database import Database
from config import Config
import hashlib
import secrets
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from database import Database
from config import Config
import hashlib
import secrets
from datetime import datetime, timedelta  # ← ADICIONE ESTA LINHA!
# No topo do arquivo, junto com as outras importações
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.SECRET_KEY

# Inicializar banco de dados
db = Database()

# Função de hash (mantenha esta função no app.py)
def hash_password(senha, salt=None):
    """Gera hash da senha usando salt"""
    if salt is None:
        salt = secrets.token_hex(16)
    
    senha_salt = senha + salt
    senha_hash = hashlib.sha256(senha_salt.encode()).hexdigest()
    return senha_hash, salt


# Funções auxiliares
def processar_dados_grafico(dados):
    """Processa os dados para formato adequado para gráficos"""
    if not dados:
        return {}
    
    # Agrupar dados por sensor
    dados_por_sensor = {}
    
    for sensor_id, sensor_nome, posicao, unidade, valor, timestamp in dados:
        if posicao not in dados_por_sensor:
            dados_por_sensor[posicao] = {
                'nome': sensor_nome,
                'unidade': unidade,
                'dados': []
            }
        
        # Formatar timestamp para ISO string
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
    
    # Agrupar por sensor
    dados_por_sensor = {}
    for sensor_id, sensor_nome, posicao, unidade, valor, timestamp in dados:
        if posicao not in dados_por_sensor:
            dados_por_sensor[posicao] = {
                'nome': sensor_nome,
                'unidade': unidade,
                'valores': []
            }
        dados_por_sensor[posicao]['valores'].append(float(valor))
    
    # Calcular estatísticas para cada sensor
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

# ====================
# ROTAS DE AUTENTICAÇÃO
# ====================

@app.route('/')
def index():
    """Página inicial - redireciona para login ou dashboard"""
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    # Se já está logado, redireciona para dashboard
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        if not email or not senha:
            flash('Por favor, preencha todos os campos.', 'danger')
            return render_template('login.html')
        
        # Verificar usuário no banco
        usuario = db.verificar_usuario(email, senha)
        
        if usuario:
            # Login bem-sucedido
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = usuario['nome']
            session['usuario_email'] = usuario['email']
            session['usuario_tipo'] = usuario['tipo']
            
            flash(f'Bem-vindo, {usuario["nome"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Email ou senha incorretos.', 'danger')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    """Dashboard principal após login"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return render_template('dashboard.html', 
                             usuario=session,
                             localizacoes=[],
                             stats={})
    
    try:
        with conn.cursor() as cursor:
            usuario_id = session['usuario_id']
            usuario_tipo = session['usuario_tipo']
            
            # Buscar estatísticas baseadas no tipo de usuário
            if usuario_tipo == 'admin':
                # Admin vê estatísticas de todo o sistema
                
                # Total de localizações
                cursor.execute("SELECT COUNT(*) FROM localizacoes")
                total_localizacoes = cursor.fetchone()[0]
                
                # Total de equipamentos
                cursor.execute("SELECT COUNT(*) FROM dispositivos")
                total_equipamentos = cursor.fetchone()[0]
                
                # Equipamentos online
                cursor.execute("SELECT COUNT(*) FROM dispositivos WHERE online = true")
                equipamentos_online = cursor.fetchone()[0]
                
                # Total de usuários
                cursor.execute("SELECT COUNT(*) FROM usuarios WHERE ativo = true")
                total_usuarios = cursor.fetchone()[0]
                
                # Total de alimentadores
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM alimentadores a 
                    JOIN dispositivos d ON a.dispositivo_id = d.id
                """)
                total_alimentadores = cursor.fetchone()[0]
                
                # Total de dataloggers
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM dataloggers dl 
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                """)
                total_dataloggers = cursor.fetchone()[0]
                
                # Últimos equipamentos cadastrados
                cursor.execute("""
                    SELECT d.id, d.nome, d.tipo, d.online, l.nome as localizacao_nome,
                           CASE 
                               WHEN a.id IS NOT NULL THEN 'alimentador'
                               WHEN dl.id IS NOT NULL THEN 'datalogger'
                               ELSE 'dispositivo'
                           END as tipo_especifico
                    FROM dispositivos d
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    ORDER BY d.created_at DESC
                    LIMIT 5
                """)
                ultimos_equipamentos = cursor.fetchall()
                
            else:
                # Usuário normal vê apenas suas estatísticas
                
                # Total de localizações do usuário
                cursor.execute("""
                    SELECT COUNT(DISTINCT l.id) 
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                """, (usuario_id,))
                total_localizacoes = cursor.fetchone()[0]
                
                # Total de equipamentos do usuário
                cursor.execute("""
                    SELECT COUNT(DISTINCT d.id)
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                """, (usuario_id,))
                total_equipamentos = cursor.fetchone()[0]
                
                # Equipamentos online do usuário
                cursor.execute("""
                    SELECT COUNT(DISTINCT d.id)
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s AND d.online = true
                """, (usuario_id,))
                equipamentos_online = cursor.fetchone()[0]
                
                # Total de usuários (apenas o próprio para usuários normais)
                total_usuarios = 1
                
                # Total de alimentadores do usuário
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM alimentadores a
                    JOIN dispositivos d ON a.dispositivo_id = d.id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                """, (usuario_id,))
                total_alimentadores = cursor.fetchone()[0]
                
                # Total de dataloggers do usuário
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                """, (usuario_id,))
                total_dataloggers = cursor.fetchone()[0]
                
                # Últimos equipamentos do usuário
                cursor.execute("""
                    SELECT d.id, d.nome, d.tipo, d.online, l.nome as localizacao_nome,
                           CASE 
                               WHEN a.id IS NOT NULL THEN 'alimentador'
                               WHEN dl.id IS NOT NULL THEN 'datalogger'
                               ELSE 'dispositivo'
                           END as tipo_especifico
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    WHERE ul.usuario_id = %s
                    ORDER BY d.created_at DESC
                    LIMIT 5
                """, (usuario_id,))
                ultimos_equipamentos = cursor.fetchall()
            
            # Calcular porcentagem de equipamentos online
            porcentagem_online = 0
            if total_equipamentos > 0:
                porcentagem_online = (equipamentos_online / total_equipamentos) * 100
            
            # Preparar estatísticas para o template
            stats = {
                'total_localizacoes': total_localizacoes,
                'total_equipamentos': total_equipamentos,
                'equipamentos_online': equipamentos_online,
                'porcentagem_online': round(porcentagem_online, 1),
                'total_usuarios': total_usuarios,
                'total_alimentadores': total_alimentadores,
                'total_dataloggers': total_dataloggers,
                'ultimos_equipamentos': ultimos_equipamentos
            }
            
            # Obter localizações do usuário (para o card de localizações)
            localizacoes = db.obter_localizacoes_usuario(usuario_id)
            
    except Exception as e:
        print(f"❌ Erro ao buscar estatísticas do dashboard: {e}")
        stats = {
            'total_localizacoes': 0,
            'total_equipamentos': 0,
            'equipamentos_online': 0,
            'porcentagem_online': 0,
            'total_usuarios': 0,
            'total_alimentadores': 0,
            'total_dataloggers': 0,
            'ultimos_equipamentos': []
        }
        localizacoes = []
    finally:
        conn.close()
    
    return render_template('dashboard.html', 
                         usuario=session,
                         localizacoes=localizacoes,
                         stats=stats)


@app.route('/logout')
def logout():
    """Faz logout do usuário"""
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

# ====================
# ROTA DE SAÚDE
# ====================

@app.route('/health')
def health_check():
    """Verifica se a aplicação e banco estão funcionando"""
    try:
        # Testar conexão com banco tentando buscar um usuário
        usuario = db.verificar_usuario('admin@englife.com', 'teste')
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'message': 'Sistema de autenticação funcionando',
            'session_active': 'usuario_id' in session
        }), 200
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# ====================
# MIDDLEWARE - Verificar autenticação
# ====================

@app.before_request
# ====================
# MIDDLEWARE - Verificar autenticação
# ====================

@app.before_request
def check_authentication():
    """Verifica autenticação para rotas protegidas
    
    print(f"\n🔍 DEBUG MIDDLEWARE:")
    print(f"  Path: {request.path}")
    print(f"  Method: {request.method}")
    print(f"  Endpoint: {request.endpoint}")
    print(f"  Content-Type: {request.content_type}")
    """
    # PERMITE TODAS AS ROTAS API SEM AUTENTICAÇÃO
    if request.path.startswith('/api/'):
        print("  ✅ Rota API - acesso permitido")
        return
    
    # Rotas que não precisam de autenticação
    public_routes = ['login', 'logout', 'health', 'static', 'index']
    
    if request.endpoint and request.endpoint not in public_routes:
        if 'usuario_id' not in session:
            print(f"  ❌ Não autenticado - redirecionando para login")
            if request.endpoint != 'index':
                flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
    
    print("  ✅ Acesso permitido")

# ====================
# ROTAS DE CADASTRO DE EQUIPAMENTOS
# ====================

@app.route('/equipamentos')
def equipamentos():
    """Página principal de equipamentos"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return render_template('equipamentos.html', dispositivos=[])
    
    try:
        with conn.cursor() as cursor:
            if session['usuario_tipo'] == 'admin':
                # Admin vê todos os dispositivos
                cursor.execute("""
                    SELECT DISTINCT d.*, l.nome as localizacao_nome,
                           CASE 
                               WHEN a.id IS NOT NULL THEN 'alimentador'
                               WHEN dl.id IS NOT NULL THEN 'datalogger'
                               ELSE 'dispositivo'
                           END as tipo_especifico
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    ORDER BY d.nome
                """)
            else:
                # Usuário normal vê apenas dispositivos das suas localizações
                cursor.execute("""
                    SELECT DISTINCT d.*, l.nome as localizacao_nome,
                           CASE 
                               WHEN a.id IS NOT NULL THEN 'alimentador'
                               WHEN dl.id IS NOT NULL THEN 'datalogger'
                               ELSE 'dispositivo'
                           END as tipo_especifico
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    WHERE ul.usuario_id = %s
                    ORDER BY d.nome
                """, (session['usuario_id'],))
            
            dispositivos = cursor.fetchall()
            
            # Converter para lista de dicionários
            colunas = ['id', 'localizacao_id', 'nome', 'descricao', 'mac_address', 
                      'ip_address', 'tipo', 'modelo', 'online', 'ultima_comunicacao',
                      'created_at', 'updated_at', 'localizacao_nome', 'tipo_especifico']
            
            dispositivos_dict = [dict(zip(colunas, dispositivo)) for dispositivo in dispositivos]
            
    except Exception as e:
        print(f"❌ Erro ao buscar dispositivos: {e}")
        dispositivos_dict = []
    finally:
        conn.close()
    
    return render_template('equipamentos.html', dispositivos=dispositivos_dict)


@app.route('/equipamentos/cadastrar')
def cadastrar_equipamento():
    """Formulário para cadastrar novo equipamento"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('equipamentos'))
    
    try:
        with conn.cursor() as cursor:
            if session['usuario_tipo'] == 'admin':
                # Admin vê todas as localizações
                cursor.execute("""
                    SELECT id, nome, descricao, tipo 
                    FROM localizacoes 
                    ORDER BY nome
                """)
            else:
                # Usuário normal vê apenas suas localizações
                cursor.execute("""
                    SELECT l.id, l.nome, l.descricao, l.tipo
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                    ORDER BY l.nome
                """, (session['usuario_id'],))
            
            localizacoes = cursor.fetchall()
            
            localizacoes_dict = [
                {
                    'id': loc[0],
                    'nome': loc[1],
                    'descricao': loc[2],
                    'tipo': loc[3]
                }
                for loc in localizacoes
            ]
            
    except Exception as e:
        print(f"❌ Erro ao buscar localizações: {e}")
        localizacoes_dict = []
    finally:
        conn.close()
    
    return render_template('cadastrar_equipamento.html', localizacoes=localizacoes_dict)



@app.route('/equipamentos/salvar', methods=['POST'])
def salvar_equipamento():
    """Salva um novo equipamento"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    try:
        nome = request.form['nome']
        descricao = request.form.get('descricao', '')
        mac_address = request.form['mac_address']
        ip_address = request.form.get('ip_address', '')
        tipo = request.form['tipo']
        modelo = request.form.get('modelo', '')
        localizacao_id = request.form['localizacao_id']  # Agora obrigatório
        
        # Validar campos obrigatórios
        if not localizacao_id:
            flash('A localização é obrigatória.', 'danger')
            return redirect(url_for('cadastrar_equipamento'))
        
        conn = db.get_connection()
        if not conn:
            flash('Erro de conexão com o banco de dados', 'danger')
            return redirect(url_for('cadastrar_equipamento'))
        
        with conn.cursor() as cursor:
            # Verificar se o usuário tem acesso à localização
            if session['usuario_tipo'] != 'admin':
                # Para usuários não-admin, verificar se a localização pertence ao usuário
                cursor.execute("""
                    SELECT 1 FROM usuario_localizacao 
                    WHERE usuario_id = %s AND localizacao_id = %s
                """, (session['usuario_id'], localizacao_id))
                
                if not cursor.fetchone():
                    flash('Você não tem acesso a esta localização.', 'danger')
                    return redirect(url_for('cadastrar_equipamento'))
            
            # Verificar se MAC Address já existe
            cursor.execute("SELECT id FROM dispositivos WHERE mac_address = %s", (mac_address,))
            if cursor.fetchone():
                flash('MAC Address já está em uso. Por favor, use um endereço único.', 'danger')
                return redirect(url_for('cadastrar_equipamento'))
            
            # Inserir dispositivo
            cursor.execute("""
                INSERT INTO dispositivos (localizacao_id, nome, descricao, mac_address, ip_address, tipo, modelo)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (localizacao_id, nome, descricao, mac_address, ip_address, tipo, modelo))
            
            dispositivo_id = cursor.fetchone()[0]
            
            # Criar registro específico baseado no tipo
            if tipo == 'alimentador':
                cursor.execute("""
                    INSERT INTO alimentadores (dispositivo_id, capacidade_racao, vazao_media)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (dispositivo_id, 0, 0))
                
                alimentador_id = cursor.fetchone()[0]
                
                # Criar configuração padrão
                cursor.execute("""
                    INSERT INTO config_alimentadores (alimentador_id, ativa)
                    VALUES (%s, false)
                """, (alimentador_id,))
                
                # Criar calibração padrão
                cursor.execute("""
                    INSERT INTO calibracao_alimentadores (alimentador_id)
                    VALUES (%s)
                """, (alimentador_id,))
                
                flash('Alimentador cadastrado com sucesso!', 'success')
                
            elif tipo == 'datalogger':
                cursor.execute("""
                    INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (dispositivo_id, 3, 60))
                
                datalogger_id = cursor.fetchone()[0]
                
                # Criar sensores automáticos apenas para dataloggers
                sensores_base = [
                    ('Sensor Água', 'temperatura', '°C', 'agua'),
                    ('Sensor Estufa', 'temperatura', '°C', 'estufa'),
                    ('Sensor Externa', 'temperatura', '°C', 'externa')
                ]
                
                for nome_sensor, tipo_sensor, unidade, posicao in sensores_base:
                    endereco = f"DS18B20_{datalogger_id}_{posicao}"
                    cursor.execute("""
                        INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco))
                
                flash('Datalogger cadastrado com sucesso! 3 sensores de temperatura criados automaticamente.', 'success')
            
            conn.commit()
            
    except Exception as e:
        print(f"❌ Erro ao salvar equipamento: {e}")
        flash(f'Erro ao cadastrar equipamento: {str(e)}', 'danger')
        return redirect(url_for('cadastrar_equipamento'))
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('equipamentos'))

@app.route('/equipamentos/<int:dispositivo_id>')
def ver_equipamento(dispositivo_id):
    """Visualizar detalhes de um equipamento"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('equipamentos'))
    
    try:
        with conn.cursor() as cursor:
            if session['usuario_tipo'] == 'admin':
                # Admin pode ver qualquer dispositivo
                cursor.execute("""
                    SELECT d.*, l.nome as localizacao_nome,
                           CASE 
                               WHEN a.id IS NOT NULL THEN 'alimentador'
                               WHEN dl.id IS NOT NULL THEN 'datalogger'
                               ELSE 'dispositivo'
                           END as tipo_especifico,
                           a.id as alimentador_id,
                           dl.id as datalogger_id
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    WHERE d.id = %s
                """, (dispositivo_id,))
            else:
                # Usuário normal só vê dispositivos das suas localizações
                cursor.execute("""
                    SELECT d.*, l.nome as localizacao_nome,
                           CASE 
                               WHEN a.id IS NOT NULL THEN 'alimentador'
                               WHEN dl.id IS NOT NULL THEN 'datalogger'
                               ELSE 'dispositivo'
                           END as tipo_especifico,
                           a.id as alimentador_id,
                           dl.id as datalogger_id
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    WHERE d.id = %s AND ul.usuario_id = %s
                """, (dispositivo_id, session['usuario_id']))
            
            dispositivo = cursor.fetchone()
            
            if not dispositivo:
                flash('Equipamento não encontrado ou acesso negado.', 'danger')
                return redirect(url_for('equipamentos'))
            
            # Resto do código permanece igual...
            # Converter para dicionário
            colunas = ['id', 'localizacao_id', 'nome', 'descricao', 'mac_address', 
                      'ip_address', 'tipo', 'modelo', 'online', 'ultima_comunicacao',
                      'created_at', 'updated_at', 'localizacao_nome', 'tipo_especifico',
                      'alimentador_id', 'datalogger_id']
            
            dispositivo_dict = dict(zip(colunas, dispositivo))
            
            # Buscar sensores se for datalogger
            sensores = []
            if dispositivo_dict['tipo_especifico'] == 'datalogger':
                cursor.execute("""
                    SELECT id, nome, tipo, unidade, posicao, endereco, ativo
                    FROM sensores 
                    WHERE datalogger_id = %s
                    ORDER BY posicao
                """, (dispositivo_dict['datalogger_id'],))
                
                sensores = cursor.fetchall()
            
    except Exception as e:
        print(f"❌ Erro ao buscar equipamento: {e}")
        flash('Erro ao carregar equipamento.', 'danger')
        return redirect(url_for('equipamentos'))
    finally:
        conn.close()
    
    return render_template('ver_equipamento.html', 
                         dispositivo=dispositivo_dict, 
                         sensores=sensores)


@app.route('/equipamentos/<int:dispositivo_id>/adicionar-sensor', methods=['POST'])
def adicionar_sensor(dispositivo_id):
    """Adiciona um sensor a um datalogger"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    try:
        nome = request.form['nome']
        tipo = request.form['tipo']
        unidade = request.form['unidade']
        posicao = request.form['posicao']
        endereco = request.form.get('endereco', '')
        
        conn = db.get_connection()
        if not conn:
            flash('Erro de conexão com o banco de dados', 'danger')
            return redirect(url_for('ver_equipamento', dispositivo_id=dispositivo_id))
        
        with conn.cursor() as cursor:
            # Verificar se é um datalogger e se o usuário tem acesso
            cursor.execute("""
                SELECT dl.id
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                JOIN localizacoes l ON d.localizacao_id = l.id
                JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                WHERE d.id = %s AND ul.usuario_id = %s AND d.tipo = 'datalogger'
            """, (dispositivo_id, session['usuario_id']))
            
            datalogger = cursor.fetchone()
            
            if not datalogger:
                flash('Datalogger não encontrado ou acesso negado.', 'danger')
                return redirect(url_for('equipamentos'))
            
            datalogger_id = datalogger[0]
            
            # Inserir sensor
            cursor.execute("""
                INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (datalogger_id, nome, tipo, unidade, posicao, endereco))
            
            conn.commit()
            flash('Sensor adicionado com sucesso!', 'success')
            
    except Exception as e:
        print(f"❌ Erro ao adicionar sensor: {e}")
        flash(f'Erro ao adicionar sensor: {str(e)}', 'danger')
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('ver_equipamento', dispositivo_id=dispositivo_id))

@app.route('/equipamentos/<int:dispositivo_id>/excluir', methods=['POST'])
def excluir_equipamento(dispositivo_id):
    """Exclui um equipamento e todos os dados relacionados"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('equipamentos'))
    
    try:
        with conn.cursor() as cursor:
            # Verificar se o usuário tem permissão para excluir este equipamento
            if session['usuario_tipo'] == 'admin':
                # Admin pode excluir qualquer dispositivo
                cursor.execute("""
                    SELECT d.id, d.nome, d.tipo, l.nome as localizacao_nome
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    WHERE d.id = %s
                """, (dispositivo_id,))
            else:
                # Usuário normal só pode excluir dispositivos das suas localizações
                cursor.execute("""
                    SELECT d.id, d.nome, d.tipo, l.nome as localizacao_nome
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s
                """, (dispositivo_id, session['usuario_id']))
            
            dispositivo = cursor.fetchone()
            
            if not dispositivo:
                flash('Equipamento não encontrado ou acesso negado.', 'danger')
                return redirect(url_for('equipamentos'))
            
            dispositivo_id, dispositivo_nome, dispositivo_tipo, localizacao_nome = dispositivo
            
            # Excluir o dispositivo (as relações em cascata cuidarão do resto)
            cursor.execute("DELETE FROM dispositivos WHERE id = %s", (dispositivo_id,))
            
            conn.commit()
            
            flash(f'Equipamento "{dispositivo_nome}" excluído com sucesso!', 'success')
            
    except Exception as e:
        print(f"❌ Erro ao excluir equipamento: {e}")
        conn.rollback()
        flash(f'Erro ao excluir equipamento: {str(e)}', 'danger')
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('equipamentos'))


# ====================
# ROTAS DE LOCALIZAÇÕES
# ====================

@app.route('/localizacoes')
def localizacoes():
    """Página principal de localizações"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return render_template('localizacoes.html', localizacoes=[])
    
    try:
        with conn.cursor() as cursor:
            if session['usuario_tipo'] == 'admin':
                # Admin vê todas as localizações
                cursor.execute("""
                    SELECT l.*, 
                           COUNT(DISTINCT d.id) as total_equipamentos,
                           COUNT(DISTINCT u.id) as total_usuarios
                    FROM localizacoes l
                    LEFT JOIN dispositivos d ON l.id = d.localizacao_id
                    LEFT JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN usuarios u ON ul.usuario_id = u.id
                    GROUP BY l.id
                    ORDER BY l.nome
                """)
            else:
                # Usuário normal vê apenas suas localizações
                cursor.execute("""
                    SELECT l.*, 
                           COUNT(DISTINCT d.id) as total_equipamentos,
                           COUNT(DISTINCT u.id) as total_usuarios
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN dispositivos d ON l.id = d.localizacao_id
                    LEFT JOIN usuario_localizacao ul2 ON l.id = ul2.localizacao_id
                    LEFT JOIN usuarios u ON ul2.usuario_id = u.id
                    WHERE ul.usuario_id = %s
                    GROUP BY l.id
                    ORDER BY l.nome
                """, (session['usuario_id'],))
            
            localizacoes = cursor.fetchall()
            
            # Converter para lista de dicionários
            colunas = ['id', 'nome', 'descricao', 'tipo', 'created_at', 'total_equipamentos', 'total_usuarios']
            localizacoes_dict = [dict(zip(colunas, localizacao)) for localizacao in localizacoes]
            
    except Exception as e:
        print(f"❌ Erro ao buscar localizações: {e}")
        localizacoes_dict = []
    finally:
        conn.close()
    
    return render_template('localizacoes.html', localizacoes=localizacoes_dict)

@app.route('/localizacoes/cadastrar')
def cadastrar_localizacao():
    """Formulário para cadastrar nova localização"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    return render_template('cadastrar_localizacao.html')

@app.route('/localizacoes/salvar', methods=['POST'])
def salvar_localizacao():
    """Salva uma nova localização"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    try:
        nome = request.form['nome']
        descricao = request.form.get('descricao', '')
        tipo = request.form['tipo']
        
        conn = db.get_connection()
        if not conn:
            flash('Erro de conexão com o banco de dados', 'danger')
            return redirect(url_for('cadastrar_localizacao'))
        
        with conn.cursor() as cursor:
            # Verificar se já existe uma localização com o mesmo nome
            cursor.execute("SELECT id FROM localizacoes WHERE nome = %s", (nome,))
            if cursor.fetchone():
                flash('Já existe uma localização com este nome.', 'danger')
                return redirect(url_for('cadastrar_localizacao'))
            
            # Inserir nova localização
            cursor.execute("""
                INSERT INTO localizacoes (nome, descricao, tipo)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (nome, descricao, tipo))
            
            localizacao_id = cursor.fetchone()[0]
            
            # Se for admin, associar automaticamente a todos os usuários
            if session['usuario_tipo'] == 'admin':
                cursor.execute("SELECT id FROM usuarios")
                usuarios = cursor.fetchall()
                
                for usuario in usuarios:
                    cursor.execute("""
                        INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                        VALUES (%s, %s)
                        ON CONFLICT (usuario_id, localizacao_id) DO NOTHING
                    """, (usuario[0], localizacao_id))
            else:
                # Usuário normal: associar apenas a si mesmo
                cursor.execute("""
                    INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                    VALUES (%s, %s)
                """, (session['usuario_id'], localizacao_id))
            
            conn.commit()
            flash('Localização cadastrada com sucesso!', 'success')
            
    except Exception as e:
        print(f"❌ Erro ao salvar localização: {e}")
        flash(f'Erro ao cadastrar localização: {str(e)}', 'danger')
        return redirect(url_for('cadastrar_localizacao'))
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('localizacoes'))

@app.route('/localizacoes/<int:localizacao_id>')
def ver_localizacao(localizacao_id):
    """Visualizar detalhes de uma localização"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('localizacoes'))
    
    try:
        with conn.cursor() as cursor:
            if session['usuario_tipo'] == 'admin':
                # Admin pode ver qualquer localização
                cursor.execute("""
                    SELECT l.*,
                           COUNT(DISTINCT d.id) as total_equipamentos,
                           COUNT(DISTINCT u.id) as total_usuarios
                    FROM localizacoes l
                    LEFT JOIN dispositivos d ON l.id = d.localizacao_id
                    LEFT JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN usuarios u ON ul.usuario_id = u.id
                    WHERE l.id = %s
                    GROUP BY l.id
                """, (localizacao_id,))
            else:
                # Usuário normal só pode ver localizações que tem acesso
                cursor.execute("""
                    SELECT l.*,
                           COUNT(DISTINCT d.id) as total_equipamentos,
                           COUNT(DISTINCT u.id) as total_usuarios
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN dispositivos d ON l.id = d.localizacao_id
                    LEFT JOIN usuario_localizacao ul2 ON l.id = ul2.localizacao_id
                    LEFT JOIN usuarios u ON ul2.usuario_id = u.id
                    WHERE l.id = %s AND ul.usuario_id = %s
                    GROUP BY l.id
                """, (localizacao_id, session['usuario_id']))
            
            localizacao = cursor.fetchone()
            
            if not localizacao:
                flash('Localização não encontrada ou acesso negado.', 'danger')
                return redirect(url_for('localizacoes'))
            
            # Converter para dicionário
            colunas = ['id', 'nome', 'descricao', 'tipo', 'created_at', 'total_equipamentos', 'total_usuarios']
            localizacao_dict = dict(zip(colunas, localizacao))
            
            # Buscar equipamentos da localização
            cursor.execute("""
                SELECT d.*,
                       CASE 
                           WHEN a.id IS NOT NULL THEN 'alimentador'
                           WHEN dl.id IS NOT NULL THEN 'datalogger'
                           ELSE 'dispositivo'
                       END as tipo_especifico
                FROM dispositivos d
                LEFT JOIN alimentadores a ON d.id = a.dispositivo_id
                LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.localizacao_id = %s
                ORDER BY d.nome
            """, (localizacao_id,))
            
            equipamentos = cursor.fetchall()
            colunas_equip = ['id', 'localizacao_id', 'nome', 'descricao', 'mac_address', 
                            'ip_address', 'tipo', 'modelo', 'online', 'ultima_comunicacao',
                            'created_at', 'updated_at', 'tipo_especifico']
            equipamentos_dict = [dict(zip(colunas_equip, equipamento)) for equipamento in equipamentos]
            
    except Exception as e:
        print(f"❌ Erro ao buscar localização: {e}")
        flash('Erro ao carregar localização.', 'danger')
        return redirect(url_for('localizacoes'))
    finally:
        conn.close()
    
    return render_template('ver_localizacao.html', 
                         localizacao=localizacao_dict, 
                         equipamentos=equipamentos_dict)

# ====================
# ROTAS DE USUÁRIOS (APENAS ADMIN)
# ====================

@app.route('/usuarios')
def usuarios():
    """Página de gerenciamento de usuários (apenas admin)"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    # Verificar se é admin
    if session['usuario_tipo'] != 'admin':
        flash('Acesso negado. Apenas administradores podem acessar esta página.', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return render_template('usuarios.html', usuarios=[])
    
    try:
        with conn.cursor() as cursor:
            # Buscar todos os usuários
            cursor.execute("""
                SELECT id, nome, email, tipo, ativo, created_at
                FROM usuarios
                ORDER BY nome
            """)
            
            usuarios = cursor.fetchall()
            
            # Converter para lista de dicionários
            colunas = ['id', 'nome', 'email', 'tipo', 'ativo', 'created_at']
            usuarios_dict = [dict(zip(colunas, usuario)) for usuario in usuarios]
            
    except Exception as e:
        print(f"❌ Erro ao buscar usuários: {e}")
        usuarios_dict = []
    finally:
        conn.close()
    
    return render_template('usuarios.html', usuarios=usuarios_dict)

@app.route('/usuarios/cadastrar')
def cadastrar_usuario():
    """Formulário para cadastrar novo usuário (apenas admin)"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    # Verificar se é admin
    if session['usuario_tipo'] != 'admin':
        flash('Acesso negado. Apenas administradores podem acessar esta página.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Buscar localizações para associar ao usuário
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return render_template('cadastrar_usuario.html', localizacoes=[])
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, nome, tipo, descricao
                FROM localizacoes
                ORDER BY nome
            """)
            localizacoes = cursor.fetchall()
            
            localizacoes_dict = [
                {
                    'id': loc[0],
                    'nome': loc[1],
                    'tipo': loc[2],
                    'descricao': loc[3]
                }
                for loc in localizacoes
            ]
            
    except Exception as e:
        print(f"❌ Erro ao buscar localizações: {e}")
        localizacoes_dict = []
    finally:
        conn.close()
    
    return render_template('cadastrar_usuario.html', localizacoes=localizacoes_dict)

@app.route('/usuarios/salvar', methods=['POST'])
def salvar_usuario():
    """Salva um novo usuário (apenas admin)"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    # Verificar se é admin
    if session['usuario_tipo'] != 'admin':
        flash('Acesso negado. Apenas administradores podem acessar esta página.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']
        tipo = request.form['tipo']
        localizacoes = request.form.getlist('localizacoes')  # Lista de localizações selecionadas
        
        # Validar senha
        if len(senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
            return redirect(url_for('cadastrar_usuario'))
        
        # Gerar hash da senha
        senha_hash, salt = hash_password(senha)
        
        conn = db.get_connection()
        if not conn:
            flash('Erro de conexão com o banco de dados', 'danger')
            return redirect(url_for('cadastrar_usuario'))
        
        with conn.cursor() as cursor:
            # Verificar se email já existe
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            if cursor.fetchone():
                flash('Já existe um usuário com este email.', 'danger')
                return redirect(url_for('cadastrar_usuario'))
            
            # Inserir novo usuário
            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha_hash, salt, tipo)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (nome, email, senha_hash, salt, tipo))
            
            usuario_id = cursor.fetchone()[0]
            
            # Associar localizações ao usuário
            for localizacao_id in localizacoes:
                cursor.execute("""
                    INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                    VALUES (%s, %s)
                """, (usuario_id, localizacao_id))
            
            conn.commit()
            flash('Usuário cadastrado com sucesso!', 'success')
            
    except Exception as e:
        print(f"❌ Erro ao salvar usuário: {e}")
        flash(f'Erro ao cadastrar usuário: {str(e)}', 'danger')
        return redirect(url_for('cadastrar_usuario'))
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('usuarios'))

# Atualize a rota atualizar_usuario para não modificar a senha
@app.route('/usuarios/<int:usuario_id>/atualizar', methods=['POST'])
def atualizar_usuario(usuario_id):
    """Atualiza dados do usuário (apenas admin)"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    # Verificar se é admin
    if session['usuario_tipo'] != 'admin':
        flash('Acesso negado. Apenas administradores podem acessar esta página.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        nome = request.form['nome']
        email = request.form['email']
        tipo = request.form['tipo']
        ativo = 'ativo' in request.form  # Checkbox
        localizacoes = request.form.getlist('localizacoes')
        
        conn = db.get_connection()
        if not conn:
            flash('Erro de conexão com o banco de dados', 'danger')
            return redirect(url_for('editar_usuario', usuario_id=usuario_id))
        
        with conn.cursor() as cursor:
            # Verificar se email já existe em outro usuário
            cursor.execute("SELECT id FROM usuarios WHERE email = %s AND id != %s", (email, usuario_id))
            if cursor.fetchone():
                flash('Já existe outro usuário com este email.', 'danger')
                return redirect(url_for('editar_usuario', usuario_id=usuario_id))
            
            # Atualizar dados do usuário (sem modificar a senha)
            cursor.execute("""
                UPDATE usuarios 
                SET nome = %s, email = %s, tipo = %s, ativo = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (nome, email, tipo, ativo, usuario_id))
            
            # Atualizar localizações do usuário
            # Primeiro remover todas as associações
            cursor.execute("DELETE FROM usuario_localizacao WHERE usuario_id = %s", (usuario_id,))
            
            # Depois adicionar as novas
            for localizacao_id in localizacoes:
                cursor.execute("""
                    INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                    VALUES (%s, %s)
                """, (usuario_id, localizacao_id))
            
            conn.commit()
            flash('Usuário atualizado com sucesso!', 'success')
            
    except Exception as e:
        print(f"❌ Erro ao atualizar usuário: {e}")
        flash(f'Erro ao atualizar usuário: {str(e)}', 'danger')
        return redirect(url_for('editar_usuario', usuario_id=usuario_id))
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('usuarios'))

# Adicione uma rota para redefinir senha (opcional)
@app.route('/usuarios/<int:usuario_id>/redefinir-senha', methods=['POST'])
def redefinir_senha_usuario(usuario_id):
    """Redefine a senha de um usuário (apenas admin)"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    # Verificar se é admin
    if session['usuario_tipo'] != 'admin':
        flash('Acesso negado. Apenas administradores podem acessar esta página.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        nova_senha = request.form['nova_senha']
        confirmar_senha = request.form['confirmar_senha']
        
        # Validar senhas
        if len(nova_senha) < 6:
            flash('A senha deve ter pelo menos 6 caracteres.', 'danger')
            return redirect(url_for('editar_usuario', usuario_id=usuario_id))
        
        if nova_senha != confirmar_senha:
            flash('As senhas não coincidem.', 'danger')
            return redirect(url_for('editar_usuario', usuario_id=usuario_id))
        
        # Gerar novo hash da senha
        senha_hash, salt = hash_password(nova_senha)
        
        conn = db.get_connection()
        if not conn:
            flash('Erro de conexão com o banco de dados', 'danger')
            return redirect(url_for('editar_usuario', usuario_id=usuario_id))
        
        with conn.cursor() as cursor:
            # Atualizar senha
            cursor.execute("""
                UPDATE usuarios 
                SET senha_hash = %s, salt = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (senha_hash, salt, usuario_id))
            
            conn.commit()
            flash('Senha redefinida com sucesso!', 'success')
            
    except Exception as e:
        print(f"❌ Erro ao redefinir senha: {e}")
        flash(f'Erro ao redefinir senha: {str(e)}', 'danger')
        return redirect(url_for('editar_usuario', usuario_id=usuario_id))
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('editar_usuario', usuario_id=usuario_id))




@app.route('/usuarios/<int:usuario_id>/editar')
def editar_usuario(usuario_id):
    """Formulário para editar usuário (apenas admin)"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    # Verificar se é admin
    if session['usuario_tipo'] != 'admin':
        flash('Acesso negado. Apenas administradores podem acessar esta página.', 'danger')
        return redirect(url_for('dashboard'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('usuarios'))
    
    try:
        with conn.cursor() as cursor:
            # Buscar dados do usuário
            cursor.execute("""
                SELECT id, nome, email, tipo, ativo
                FROM usuarios
                WHERE id = %s
            """, (usuario_id,))
            
            usuario = cursor.fetchone()
            
            if not usuario:
                flash('Usuário não encontrado.', 'danger')
                return redirect(url_for('usuarios'))
            
            usuario_dict = {
                'id': usuario[0],
                'nome': usuario[1],
                'email': usuario[2],
                'tipo': usuario[3],
                'ativo': usuario[4]
            }
            
            # Buscar todas as localizações
            cursor.execute("""
                SELECT id, nome, tipo, descricao
                FROM localizacoes
                ORDER BY nome
            """)
            todas_localizacoes = cursor.fetchall()
            
            # Buscar localizações do usuário
            cursor.execute("""
                SELECT localizacao_id
                FROM usuario_localizacao
                WHERE usuario_id = %s
            """, (usuario_id,))
            
            localizacoes_usuario = [row[0] for row in cursor.fetchall()]
            
            localizacoes_dict = [
                {
                    'id': loc[0],
                    'nome': loc[1],
                    'tipo': loc[2],
                    'descricao': loc[3],
                    'selecionada': loc[0] in localizacoes_usuario
                }
                for loc in todas_localizacoes
            ]
            
    except Exception as e:
        print(f"❌ Erro ao buscar usuário: {e}")
        flash('Erro ao carregar usuário.', 'danger')
        return redirect(url_for('usuarios'))
    finally:
        conn.close()
    
    return render_template('editar_usuario.html', 
                         usuario=usuario_dict, 
                         localizacoes=localizacoes_dict)



@app.route('/usuarios/<int:usuario_id>/excluir', methods=['POST'])
def excluir_usuario(usuario_id):
    """Exclui um usuário (apenas admin)"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    # Verificar se é admin
    if session['usuario_tipo'] != 'admin':
        flash('Acesso negado. Apenas administradores podem acessar esta página.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Não permitir excluir a si mesmo
    if usuario_id == session['usuario_id']:
        flash('Você não pode excluir sua própria conta.', 'danger')
        return redirect(url_for('usuarios'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('usuarios'))
    
    try:
        with conn.cursor() as cursor:
            # Buscar nome do usuário para mensagem
            cursor.execute("SELECT nome FROM usuarios WHERE id = %s", (usuario_id,))
            usuario = cursor.fetchone()
            
            if not usuario:
                flash('Usuário não encontrado.', 'danger')
                return redirect(url_for('usuarios'))
            
            usuario_nome = usuario[0]
            
            # Excluir usuário (as relações em cascata cuidarão das associações)
            cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
            
            conn.commit()
            flash(f'Usuário "{usuario_nome}" excluído com sucesso!', 'success')
            
    except Exception as e:
        print(f"❌ Erro ao excluir usuário: {e}")
        conn.rollback()
        flash(f'Erro ao excluir usuário: {str(e)}', 'danger')
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for('usuarios'))


# ====================
# ROTAS DE RELATÓRIOS
# ====================
# ====================
# ROTAS DE RELATÓRIOS - CORRIGIDAS
# ====================

@app.route('/relatorios')
def relatorios():
    """Página principal de relatórios"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return render_template('relatorios.html', dataloggers=[], dados={})
    
    try:
        with conn.cursor() as cursor:
            if session['usuario_tipo'] == 'admin':
                # Admin vê todos os dataloggers
                cursor.execute("""
                    SELECT d.id, d.nome, l.nome as localizacao_nome, dl.quantidade_sensores,
                           d.mac_address, d.online
                    FROM dispositivos d
                    JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    WHERE d.tipo = 'datalogger'
                    ORDER BY d.nome
                """)
            else:
                # Usuário normal vê apenas dataloggers das suas localizações
                cursor.execute("""
                    SELECT d.id, d.nome, l.nome as localizacao_nome, dl.quantidade_sensores,
                           d.mac_address, d.online
                    FROM dispositivos d
                    JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.tipo = 'datalogger' AND ul.usuario_id = %s
                    ORDER BY d.nome
                """, (session['usuario_id'],))
            
            dataloggers_raw = cursor.fetchall()
            
            # Converter para lista de dicionários
            colunas = ['id', 'nome', 'localizacao_nome', 'quantidade_sensores', 'mac_address', 'online']
            dataloggers_dict = []
            
            for datalogger in dataloggers_raw:
                datalogger_dict = dict(zip(colunas, datalogger))
                
                # Buscar período de dados disponíveis para este datalogger
                cursor.execute("""
                    SELECT MIN(ls.timestamp), MAX(ls.timestamp), COUNT(ls.id)
                    FROM leituras_sensores ls
                    JOIN sensores s ON ls.sensor_id = s.id
                    WHERE s.datalogger_id = (
                        SELECT dl.id FROM dataloggers dl
                        JOIN dispositivos d ON dl.dispositivo_id = d.id
                        WHERE d.id = %s
                    )
                """, (datalogger_dict['id'],))
                
                periodo = cursor.fetchone()
                
                # Formatar datas de forma segura
                if periodo and periodo[0] and periodo[1]:
                    try:
                        # Se já é datetime
                        if hasattr(periodo[0], 'strftime'):
                            inicio = periodo[0].strftime('%d/%m/%Y %H:%M')
                            fim = periodo[1].strftime('%d/%m/%Y %H:%M')
                        else:
                            # Converter string para datetime
                            inicio_dt = datetime.strptime(str(periodo[0]), '%Y-%m-%d %H:%M:%S')
                            fim_dt = datetime.strptime(str(periodo[1]), '%Y-%m-%d %H:%M:%S')
                            inicio = inicio_dt.strftime('%d/%m/%Y %H:%M')
                            fim = fim_dt.strftime('%d/%m/%Y %H:%M')
                            
                        datalogger_dict['periodo_inicio'] = inicio
                        datalogger_dict['periodo_fim'] = fim
                        datalogger_dict['total_leituras'] = periodo[2] or 0
                    except Exception as e:
                        print(f"⚠️ Erro ao formatar datas: {e}")
                        datalogger_dict['periodo_inicio'] = str(periodo[0])[:16]  # Limitar para mostrar apenas data/hora
                        datalogger_dict['periodo_fim'] = str(periodo[1])[:16]
                        datalogger_dict['total_leituras'] = periodo[2] or 0
                else:
                    datalogger_dict['periodo_inicio'] = None
                    datalogger_dict['periodo_fim'] = None
                    datalogger_dict['total_leituras'] = 0
                
                # Buscar sensores deste datalogger
                cursor.execute("""
                    SELECT s.nome, s.posicao, s.tipo, s.ativo, 
                           COUNT(ls.id) as leituras_sensor
                    FROM sensores s
                    LEFT JOIN leituras_sensores ls ON s.id = ls.sensor_id
                    WHERE s.datalogger_id = (
                        SELECT dl.id FROM dataloggers dl
                        JOIN dispositivos d ON dl.dispositivo_id = d.id
                        WHERE d.id = %s
                    )
                    GROUP BY s.id, s.nome, s.posicao, s.tipo, s.ativo
                    ORDER BY s.posicao
                """, (datalogger_dict['id'],))
                
                sensores = cursor.fetchall()
                datalogger_dict['sensores'] = [
                    {
                        'nome': s[0],
                        'posicao': s[1],
                        'tipo': s[2],
                        'ativo': s[3],
                        'leituras': s[4]
                    } for s in sensores
                ]
                
                dataloggers_dict.append(datalogger_dict)
            
    except Exception as e:
        print(f"❌ Erro ao buscar dataloggers: {e}")
        dataloggers_dict = []
    finally:
        conn.close()
    
    return render_template('relatorios.html', 
                         dataloggers=dataloggers_dict, 
                         dados={})

@app.route('/relatorios/dados', methods=['POST'])
def obter_dados_relatorio():
    """Obtém dados para o relatório baseado nos filtros"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    try:
        datalogger_id = request.form.get('datalogger_id')
        data_inicio = request.form.get('data_inicio')
        data_fim = request.form.get('data_fim')
        
        if not datalogger_id:
            return jsonify({'error': 'Selecione um datalogger'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        with conn.cursor() as cursor:
            # Verificar se o usuário tem acesso a este datalogger
            if session['usuario_tipo'] != 'admin':
                cursor.execute("""
                    SELECT 1 
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s AND d.tipo = 'datalogger'
                """, (datalogger_id, session['usuario_id']))
                
                if not cursor.fetchone():
                    return jsonify({'error': 'Acesso negado a este datalogger'}), 403
            
            # Primeiro, obter período de dados disponíveis
            cursor.execute("""
                SELECT MIN(ls.timestamp), MAX(ls.timestamp), COUNT(ls.id)
                FROM leituras_sensores ls
                JOIN sensores s ON ls.sensor_id = s.id
                WHERE s.datalogger_id = (
                    SELECT dl.id FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    WHERE d.id = %s
                )
            """, (datalogger_id,))
            
            periodo_disponivel = cursor.fetchone()
            
            # Se não houver dados disponíveis
            if not periodo_disponivel or not periodo_disponivel[0] or periodo_disponivel[2] == 0:
                return jsonify({
                    'error': 'Nenhum dado disponível para este datalogger no período selecionado',
                    'dados': {},
                    'estatisticas': {},
                    'periodo_disponivel': None
                })
            
            min_data, max_data, total_leituras = periodo_disponivel
            
            # Ajustar datas do filtro com base no período disponível
            if data_inicio:
                try:
                    data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d')
                    # Converter min_data para datetime se for string
                    if isinstance(min_data, str):
                        min_data = datetime.strptime(min_data, '%Y-%m-%d %H:%M:%S')
                    if data_inicio_dt < min_data:
                        data_inicio_sql = min_data
                    else:
                        data_inicio_sql = data_inicio_dt
                except ValueError:
                    data_inicio_sql = min_data
            else:
                # Últimos 7 dias por padrão, mas dentro do período disponível
                if isinstance(max_data, str):
                    max_data = datetime.strptime(max_data, '%Y-%m-%d %H:%M:%S')
                data_inicio_sql = max(min_data, max_data - timedelta(days=7))
            
            if data_fim:
                try:
                    data_fim_dt = datetime.strptime(data_fim, '%Y-%m-%d')
                    data_fim_dt = data_fim_dt.replace(hour=23, minute=59, second=59)
                    if isinstance(max_data, str):
                        max_data = datetime.strptime(max_data, '%Y-%m-%d %H:%M:%S')
                    if data_fim_dt > max_data:
                        data_fim_sql = max_data
                    else:
                        data_fim_sql = data_fim_dt
                except ValueError:
                    data_fim_sql = max_data
            else:
                data_fim_sql = max_data
            
            # Buscar dados dos sensores
            cursor.execute("""
                SELECT 
                    s.id as sensor_id,
                    s.nome as sensor_nome,
                    s.posicao,
                    s.unidade,
                    ls.valor,
                    ls.timestamp
                FROM sensores s
                JOIN leituras_sensores ls ON s.id = ls.sensor_id
                WHERE s.datalogger_id = (
                    SELECT dl.id 
                    FROM dataloggers dl 
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    WHERE d.id = %s
                )
                AND ls.timestamp BETWEEN %s AND %s
                ORDER BY ls.timestamp, s.posicao
            """, (datalogger_id, data_inicio_sql, data_fim_sql))
            
            dados = cursor.fetchall()
            
            # Buscar informações do datalogger para o relatório
            cursor.execute("""
                SELECT d.nome, l.nome as localizacao_nome, dl.quantidade_sensores
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                JOIN localizacoes l ON d.localizacao_id = l.id
                WHERE d.id = %s
            """, (datalogger_id,))
            
            datalogger_info = cursor.fetchone()
            
            # Processar dados para o gráfico
            dados_processados = processar_dados_grafico(dados)
            
            # Estatísticas básicas
            estatisticas = calcular_estatisticas(dados)
            
        conn.close()
        
        # Formatar datas para resposta
        def formatar_data_resposta(data):
            if isinstance(data, datetime):
                return data.strftime('%d/%m/%Y %H:%M')
            elif hasattr(data, 'strftime'):
                return data.strftime('%d/%m/%Y %H:%M')
            else:
                try:
                    dt = datetime.strptime(str(data), '%Y-%m-%d %H:%M:%S')
                    return dt.strftime('%d/%m/%Y %H:%M')
                except:
                    return str(data)[:16]  # Limitar para mostrar apenas data/hora
        
        return jsonify({
            'success': True,
            'dados': dados_processados,
            'estatisticas': estatisticas,
            'datalogger': {
                'nome': datalogger_info[0] if datalogger_info else 'Desconhecido',
                'localizacao': datalogger_info[1] if datalogger_info else 'Desconhecida',
                'sensores': datalogger_info[2] if datalogger_info else 0
            },
            'filtros': {
                'data_inicio': formatar_data_resposta(data_inicio_sql),
                'data_fim': formatar_data_resposta(data_fim_sql),
                'total_leituras': len(dados)
            },
            'periodo_disponivel': {
                'inicio': formatar_data_resposta(min_data),
                'fim': formatar_data_resposta(max_data),
                'total_disponivel': total_leituras
            }
        })
        
    except Exception as e:
        print(f"❌ Erro ao buscar dados do relatório: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/relatorios/periodo/<int:datalogger_id>', methods=['GET'])
def obter_periodo_datalogger(datalogger_id):
    """Obtém o período de dados disponíveis para um datalogger"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    conn = db.get_connection()
    if not conn:
        return jsonify({'error': 'Erro de conexão'}), 500
    
    try:
        with conn.cursor() as cursor:
            # Verificar acesso
            if session['usuario_tipo'] != 'admin':
                cursor.execute("""
                    SELECT 1 
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s AND d.tipo = 'datalogger'
                """, (datalogger_id, session['usuario_id']))
                
                if not cursor.fetchone():
                    return jsonify({'error': 'Acesso negado'}), 403
            
            # Obter período de dados
            cursor.execute("""
                SELECT MIN(ls.timestamp), MAX(ls.timestamp), COUNT(ls.id)
                FROM leituras_sensores ls
                JOIN sensores s ON ls.sensor_id = s.id
                WHERE s.datalogger_id = (
                    SELECT dl.id FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    WHERE d.id = %s
                )
            """, (datalogger_id,))
            
            resultado = cursor.fetchone()
            
            if resultado and resultado[0]:
                # Formatar datas
                def formatar_data_sql(data):
                    if isinstance(data, datetime):
                        return data.strftime('%Y-%m-%d %H:%M:%S')
                    elif hasattr(data, 'strftime'):
                        return data.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        return str(data)
                
                return jsonify({
                    'success': True,
                    'periodo': {
                        'inicio': formatar_data_sql(resultado[0]),
                        'fim': formatar_data_sql(resultado[1]),
                        'total_leituras': resultado[2]
                    }
                })
            else:
                return jsonify({
                    'success': False,
                    'message': 'Nenhum dado disponível para este datalogger'
                })
            
    except Exception as e:
        print(f"❌ Erro ao obter período: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/relatorios/resumo')
def resumo_dados():
    """Mostra um resumo de todos os dados disponíveis"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão', 'danger')
        return redirect(url_for('relatorios'))
    
    try:
        with conn.cursor() as cursor:
            # Dados gerais
            cursor.execute("SELECT COUNT(*) FROM leituras_sensores")
            total_leituras = cursor.fetchone()[0]
            
            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM leituras_sensores")
            periodo_geral = cursor.fetchone()
            
            # Por sensor
            cursor.execute("""
                SELECT s.nome, s.posicao, s.tipo, 
                       COUNT(ls.id) as leituras,
                       MIN(ls.timestamp) as primeira,
                       MAX(ls.timestamp) as ultima,
                       ROUND(AVG(ls.valor), 2) as media,
                       MIN(ls.valor) as minima,
                       MAX(ls.valor) as maxima
                FROM sensores s
                LEFT JOIN leituras_sensores ls ON s.id = ls.sensor_id
                GROUP BY s.id, s.nome, s.posicao, s.tipo
                ORDER BY leituras DESC
            """)
            
            sensores = cursor.fetchall()
            
            # Por datalogger
            cursor.execute("""
                SELECT d.nome, l.nome as localizacao,
                       COUNT(DISTINCT s.id) as sensores,
                       COUNT(ls.id) as leituras,
                       MIN(ls.timestamp) as primeira,
                       MAX(ls.timestamp) as ultima
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                JOIN localizacoes l ON d.localizacao_id = l.id
                LEFT JOIN sensores s ON dl.id = s.datalogger_id
                LEFT JOIN leituras_sensores ls ON s.id = ls.sensor_id
                WHERE d.tipo = 'datalogger'
                GROUP BY d.id, d.nome, l.nome
                ORDER BY leituras DESC
            """)
            
            dataloggers = cursor.fetchall()
            
            return render_template('resumo_dados.html',
                                 total_leituras=total_leituras,
                                 periodo_geral=periodo_geral,
                                 sensores=sensores,
                                 dataloggers=dataloggers)
            
    except Exception as e:
        print(f"❌ Erro ao gerar resumo: {e}")
        flash(f'Erro ao gerar resumo: {str(e)}', 'danger')
        return redirect(url_for('relatorios'))
    finally:
        conn.close()

# Adicione esta função após as importações ou antes das rotas
@app.template_filter('split')
def split_filter(s, delimiter=' '):
    """Filtro para dividir strings no template"""
    if not s:
        return []
    return s.split(delimiter)
# ====================
# ROTA DE TESTE PARA VERIFICAR DADOS
# ====================

@app.route('/relatorios/teste/<int:datalogger_id>')
def teste_dados_relatorio(datalogger_id):
    """Rota de teste para verificar se há dados no banco"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    conn = db.get_connection()
    if not conn:
        return jsonify({'error': 'Erro de conexão'}), 500
    
    try:
        with conn.cursor() as cursor:
            # 1. Verificar informações do datalogger
            cursor.execute("""
                SELECT d.nome, d.tipo, l.nome as localizacao, dl.quantidade_sensores
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                JOIN localizacoes l ON d.localizacao_id = l.id
                WHERE d.id = %s
            """, (datalogger_id,))
            
            datalogger_info = cursor.fetchone()
            
            if not datalogger_info:
                return jsonify({'error': 'Datalogger não encontrado'}), 404
            
            nome, tipo, localizacao, qtd_sensores = datalogger_info
            
            # 2. Verificar sensores deste datalogger
            cursor.execute("""
                SELECT s.id, s.nome, s.posicao, s.tipo, s.ativo, 
                       COUNT(ls.id) as total_leituras,
                       MIN(ls.timestamp) as primeira_leitura,
                       MAX(ls.timestamp) as ultima_leitura
                FROM sensores s
                LEFT JOIN leituras_sensores ls ON s.id = ls.sensor_id
                WHERE s.datalogger_id = (
                    SELECT dl.id FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    WHERE d.id = %s
                )
                GROUP BY s.id, s.nome, s.posicao, s.tipo, s.ativo
                ORDER BY s.posicao
            """, (datalogger_id,))
            
            sensores = cursor.fetchall()
            
            # 3. Verificar algumas leituras
            cursor.execute("""
                SELECT ls.id, s.nome, ls.valor, ls.timestamp
                FROM leituras_sensores ls
                JOIN sensores s ON ls.sensor_id = s.id
                WHERE s.datalogger_id = (
                    SELECT dl.id FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    WHERE d.id = %s
                )
                ORDER BY ls.timestamp DESC
                LIMIT 10
            """, (datalogger_id,))
            
            ultimas_leituras = cursor.fetchall()
            
            # 4. Contar total de leituras
            cursor.execute("""
                SELECT COUNT(*)
                FROM leituras_sensores ls
                JOIN sensores s ON ls.sensor_id = s.id
                WHERE s.datalogger_id = (
                    SELECT dl.id FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    WHERE d.id = %s
                )
            """, (datalogger_id,))
            
            total_leituras = cursor.fetchone()[0]
            
            # Preparar resposta
            resposta = {
                'datalogger': {
                    'id': datalogger_id,
                    'nome': nome,
                    'tipo': tipo,
                    'localizacao': localizacao,
                    'quantidade_sensores': qtd_sensores
                },
                'sensores': [],
                'total_leituras': total_leituras,
                'ultimas_leituras': []
            }
            
            for sensor in sensores:
                resposta['sensores'].append({
                    'id': sensor[0],
                    'nome': sensor[1],
                    'posicao': sensor[2],
                    'tipo': sensor[3],
                    'ativo': sensor[4],
                    'total_leituras': sensor[5],
                    'primeira_leitura': str(sensor[6]) if sensor[6] else None,
                    'ultima_leitura': str(sensor[7]) if sensor[7] else None
                })
            
            for leitura in ultimas_leituras:
                resposta['ultimas_leituras'].append({
                    'id': leitura[0],
                    'sensor': leitura[1],
                    'valor': float(leitura[2]),
                    'timestamp': str(leitura[3]) if leitura[3] else None
                })
            
            return jsonify(resposta)
            
    except Exception as e:
        print(f"❌ Erro no teste de dados: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# ====================
# ROTA PARA VERIFICAR SE HÁ DADOS NO BANCO
# ====================

@app.route('/relatorios/verificar-dados')
def verificar_dados():
    """Verifica se há dados no banco para gerar relatórios"""
    if 'usuario_id' not in session:
        flash('Por favor, faça login.', 'warning')
        return redirect(url_for('login'))
    
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão', 'danger')
        return redirect(url_for('relatorios'))
    
    try:
        with conn.cursor() as cursor:
            # Verificar dados gerais
            cursor.execute("SELECT COUNT(*) FROM leituras_sensores")
            total_leituras = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM sensores WHERE tipo = 'temperatura'")
            total_sensores_temp = cursor.fetchone()[0]
            
            cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM leituras_sensores")
            periodo = cursor.fetchone()
            
            cursor.execute("""
                SELECT s.nome, s.posicao, COUNT(ls.id) as leituras
                FROM sensores s
                LEFT JOIN leituras_sensores ls ON s.id = ls.sensor_id
                WHERE s.tipo = 'temperatura'
                GROUP BY s.id, s.nome, s.posicao
                ORDER BY s.posicao
            """)
            
            sensores = cursor.fetchall()
            
            return render_template('verificar_dados.html',
                                 total_leituras=total_leituras,
                                 total_sensores_temp=total_sensores_temp,
                                 periodo=periodo,
                                 sensores=sensores)
            
    except Exception as e:
        print(f"❌ Erro ao verificar dados: {e}")
        flash(f'Erro ao verificar dados: {str(e)}', 'danger')
        return redirect(url_for('relatorios'))
    finally:
        conn.close()




# ====================
# ROTAS PARA RECEBER DADOS DOS DATALOGGERS
# ====================

@app.route('/api/datalogger/leitura', methods=['POST'])
def receber_leitura_datalogger():
    """
    Rota para receber leituras de sensores dos dataloggers
    Formato esperado do JSON:
    {
        "mac_address": "AA:BB:CC:DD:EE:01",
        "leituras": [
            {
                "endereco_sensor": "DS18B20_1_agua",
                "valor": 25.5,
                "timestamp": "2025-01-15 10:30:00"
            },
            {
                "endereco_sensor": "DS18B20_1_estufa", 
                "valor": 28.3,
                "timestamp": "2025-01-15 10:30:00"
            }
        ]
    }
    """
    try:
        # Verificar se é uma requisição JSON
        if not request.is_json:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Content-Type deve ser application/json'
            }), 400
        
        data = request.get_json()
        
        # Validar campos obrigatórios
        if not data or 'mac_address' not in data or 'leituras' not in data:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Campos obrigatórios: mac_address e leituras'
            }), 400
        
        mac_address = data['mac_address'].strip().upper()
        leituras = data['leituras']
        
        if not leituras:
            return jsonify({
                'status': 'erro', 
                'mensagem': 'Lista de leituras vazia'
            }), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Erro de conexão com o banco de dados'
            }), 500
        
        with conn.cursor() as cursor:
            # Verificar se o datalogger existe e está ativo
            cursor.execute("""
                SELECT d.id, d.nome, dl.id as datalogger_id, d.localizacao_id
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.mac_address = %s AND d.tipo = 'datalogger' AND d.online = true
            """, (mac_address,))
            
            datalogger = cursor.fetchone()
            
            if not datalogger:
                return jsonify({
                    'status': 'erro',
                    'mensagem': 'Datalogger não encontrado ou inativo'
                }), 404
            
            dispositivo_id, dispositivo_nome, datalogger_id, localizacao_id = datalogger
            
            leituras_processadas = 0
            leituras_com_erro = []
            
            # Processar cada leitura
            for leitura in leituras:
                try:
                    endereco_sensor = leitura.get('endereco_sensor', '').strip()
                    valor = leitura.get('valor')
                    timestamp_str = leitura.get('timestamp')
                    
                    # Validar leitura
                    if not endereco_sensor or valor is None:
                        leituras_com_erro.append({
                            'endereco_sensor': endereco_sensor,
                            'erro': 'Campos endereco_sensor e valor são obrigatórios'
                        })
                        continue
                    
                    # Buscar sensor pelo endereço
                    cursor.execute("""
                        SELECT id, nome, tipo, unidade, ativo
                        FROM sensores 
                        WHERE endereco = %s AND datalogger_id = %s
                    """, (endereco_sensor, datalogger_id))
                    
                    sensor = cursor.fetchone()
                    
                    if not sensor:
                        leituras_com_erro.append({
                            'endereco_sensor': endereco_sensor,
                            'erro': 'Sensor não encontrado para este datalogger'
                        })
                        continue
                    
                    sensor_id, sensor_nome, sensor_tipo, unidade, ativo = sensor
                    
                    if not ativo:
                        leituras_com_erro.append({
                            'endereco_sensor': endereco_sensor,
                            'erro': 'Sensor inativo'
                        })
                        continue
                    
                    # Converter timestamp
                    if timestamp_str:
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        except ValueError:
                            timestamp = datetime.now()
                    else:
                        timestamp = datetime.now()
                    
                    # Inserir leitura
                    cursor.execute("""
                        INSERT INTO leituras_sensores (sensor_id, valor, timestamp)
                        VALUES (%s, %s, %s)
                    """, (sensor_id, float(valor), timestamp))
                    
                    leituras_processadas += 1
                    
                    # Verificar limites de temperatura e gerar alertas se necessário
                    if sensor_tipo == 'temperatura':
                        verificar_limites_temperatura(
                            cursor, 
                            localizacao_id, 
                            sensor_id, 
                            float(valor), 
                            sensor_nome,
                            timestamp
                        )
                        
                except Exception as e:
                    leituras_com_erro.append({
                        'endereco_sensor': leitura.get('endereco_sensor', 'desconhecido'),
                        'erro': str(e)
                    })
                    continue
            
            # Atualizar última comunicação do dispositivo
            cursor.execute("""
                UPDATE dispositivos 
                SET ultima_comunicacao = %s, online = true
                WHERE id = %s
            """, (datetime.now(), dispositivo_id))
            
            conn.commit()
            
            # Preparar resposta
            resposta = {
                'status': 'sucesso',
                'mensagem': f'{leituras_processadas} leitura(s) processada(s) com sucesso',
                'datalogger': dispositivo_nome,
                'leituras_processadas': leituras_processadas,
                'leituras_com_erro': len(leituras_com_erro)
            }
            
            if leituras_com_erro:
                resposta['erros_detalhados'] = leituras_com_erro
            
            return jsonify(resposta), 200
            
    except Exception as e:
        print(f"❌ Erro ao processar leituras do datalogger: {e}")
        if conn:
            conn.rollback()
        
        return jsonify({
            'status': 'erro',
            'mensagem': f'Erro interno do servidor: {str(e)}'
        }), 500
    finally:
        if conn:
            conn.close()


def verificar_limites_temperatura(cursor, localizacao_id, sensor_id, valor, sensor_nome, timestamp):
    """
    Verifica se a temperatura está dentro dos limites e gera alertas se necessário
    """
    try:
        # Buscar limites para esta localização e tipo de sensor
        cursor.execute("""
            SELECT lt.maximo, lt.minimo, s.posicao
            FROM limites_temperatura lt
            JOIN sensores s ON s.id = %s
            WHERE lt.localizacao_id = %s AND lt.tipo_sensor = s.posicao
        """, (sensor_id, localizacao_id))
        
        limite = cursor.fetchone()
        
        if not limite:
            return
        
        maximo, minimo, posicao = limite
        
        # Verificar se está fora dos limites
        if valor > maximo or valor < minimo:
            tipo_alerta = "TEMPERATURA_ALTA" if valor > maximo else "TEMPERATURA_BAIXA"
            severidade = "ALTA" if abs(valor - (maximo if valor > maximo else minimo)) > 5 else "MEDIA"
            
            mensagem = (
                f"Temperatura {posicao}: {valor:.1f}°C "
                f"{'acima' if valor > maximo else 'abaixo'} do limite "
                f"({maximo if valor > maximo else minimo}°C)"
            )
            
            # Inserir alerta
            cursor.execute("""
                INSERT INTO alertas (localizacao_id, tipo, severidade, mensagem, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, (localizacao_id, tipo_alerta, severidade, mensagem, timestamp))
            
    except Exception as e:
        print(f"❌ Erro ao verificar limites de temperatura: {e}")


@app.route('/api/datalogger/status', methods=['POST'])
def atualizar_status_datalogger():
    """
    Rota para atualizar status do datalogger (heartbeat)
    Formato esperado:
    {
        "mac_address": "AA:BB:CC:DD:EE:01",
        "status": "online",
        "versao_firmware": "1.2.3",
        "sensores_ativos": 3
    }
    """
    try:
        if not request.is_json:
            return jsonify({'status': 'erro', 'mensagem': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        mac_address = data.get('mac_address', '').strip().upper()
        status = data.get('status', 'online')
        versao_firmware = data.get('versao_firmware', '')
        sensores_ativos = data.get('sensores_ativos')
        
        if not mac_address:
            return jsonify({'status': 'erro', 'mensagem': 'mac_address é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'status': 'erro', 'mensagem': 'Erro de conexão com o banco'}), 500
        
        with conn.cursor() as cursor:
            # Verificar se dispositivo existe
            cursor.execute("""
                SELECT id FROM dispositivos 
                WHERE mac_address = %s AND tipo = 'datalogger'
            """, (mac_address,))
            
            dispositivo = cursor.fetchone()
            
            if not dispositivo:
                return jsonify({'status': 'erro', 'mensagem': 'Datalogger não encontrado'}), 404
            
            dispositivo_id = dispositivo[0]
            
            # Atualizar status
            cursor.execute("""
                UPDATE dispositivos 
                SET online = %s, ultima_comunicacao = %s, versao_firmware = %s
                WHERE id = %s
            """, (status == 'online', datetime.now(), versao_firmware, dispositivo_id))
            
            # Atualizar contagem de sensores se fornecida
            if sensores_ativos is not None:
                cursor.execute("""
                    UPDATE dataloggers 
                    SET quantidade_sensores = %s
                    WHERE dispositivo_id = %s
                """, (sensores_ativos, dispositivo_id))
            
            conn.commit()
            
            return jsonify({
                'status': 'sucesso',
                'mensagem': 'Status atualizado com sucesso'
            }), 200
            
    except Exception as e:
        print(f"❌ Erro ao atualizar status do datalogger: {e}")
        if conn:
            conn.rollback()
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/datalogger/config', methods=['GET'])
def obter_config_datalogger():
    """
    Rota para o datalogger obter sua configuração
    Parâmetros: mac_address
    """
    try:
        mac_address = request.args.get('mac_address', '').strip().upper()
        
        if not mac_address:
            return jsonify({'status': 'erro', 'mensagem': 'mac_address é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'status': 'erro', 'mensagem': 'Erro de conexão com o banco'}), 500
        
        with conn.cursor() as cursor:
            # Buscar configuração do datalogger
            cursor.execute("""
                SELECT dl.intervalo_leitura, d.nome
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.mac_address = %s AND d.tipo = 'datalogger'
            """, (mac_address,))
            
            datalogger = cursor.fetchone()
            
            if not datalogger:
                return jsonify({'status': 'erro', 'mensagem': 'Datalogger não encontrado'}), 404
            
            intervalo_leitura, nome = datalogger
            
            # Buscar sensores ativos
            cursor.execute("""
                SELECT endereco, nome, tipo, unidade, posicao
                FROM sensores 
                WHERE datalogger_id = (
                    SELECT dl.id FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    WHERE d.mac_address = %s
                ) AND ativo = true
            """, (mac_address,))
            
            sensores = cursor.fetchall()
            
            sensores_config = []
            for sensor in sensores:
                sensores_config.append({
                    'endereco': sensor[0],
                    'nome': sensor[1],
                    'tipo': sensor[2],
                    'unidade': sensor[3],
                    'posicao': sensor[4]
                })
            
            return jsonify({
                'status': 'sucesso',
                'datalogger': nome,
                'config': {
                    'intervalo_leitura': intervalo_leitura,
                    'sensores': sensores_config
                }
            }), 200
            
    except Exception as e:
        print(f"❌ Erro ao obter configuração do datalogger: {e}")
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500
    finally:
        if conn:
            conn.close()

# ====================
# API PARA CADASTRO AUTOMÁTICO DE EQUIPAMENTOS E ENVIO DE DADOS
# ====================

@app.route('/api/equipamento/dados', methods=['POST'])
def receber_dados_equipamento():
    """
    Rota para receber dados completos do equipamento e cadastrar automaticamente se necessário
    Formato esperado do JSON:
    {
        "identificacao": {
            "mac_address": "AA:BB:CC:DD:EE:16",
            "tipo": "datalogger",
            "nome": "ESP32 Estufa 01",
            "modelo": "ESP32 DevKit",
            "versao_firmware": "1.0.0",
            "sensores": [
                {
                    "nome": "Sensor Água",
                    "tipo": "temperatura",
                    "posicao": "agua",
                    "endereco": "DS18B20_agua",
                    "unidade": "°C"
                },
                {
                    "nome": "Sensor Estufa",
                    "tipo": "temperatura",
                    "posicao": "estufa",
                    "endereco": "DS18B20_estufa",
                    "unidade": "°C"
                }
            ]
        },
        "localizacao": {
            "nome": "Estufa Principal",
            "tipo": "estufa",
            "descricao": "Estufa de produção principal"
        },
        "dados": [
            {
                "sensor_endereco": "DS18B20_agua",
                "valor": 25.5,
                "timestamp": "2024-09-20 10:30:00"
            },
            {
                "sensor_endereco": "DS18B20_estufa",
                "valor": 28.3,
                "timestamp": "2024-09-20 10:30:00"
            }
        ]
    }
    """
    try:
        # Verificar se é uma requisição JSON
        if not request.is_json:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Content-Type deve ser application/json'
            }), 400
        
        data = request.get_json()
        
        # Validar campos obrigatórios
        if not data or 'identificacao' not in data:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Campo "identificacao" é obrigatório'
            }), 400
        
        identificacao = data['identificacao']
        localizacao_info = data.get('localizacao')
        dados = data.get('dados', [])
        
        # Validar identificação do equipamento
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
            # Verificar se o equipamento já existe
            cursor.execute("""
                SELECT d.id, d.tipo, d.nome, d.localizacao_id, 
                       dl.id as datalogger_id, d.online
                FROM dispositivos d
                LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id AND d.tipo = 'datalogger'
                WHERE d.mac_address = %s
            """, (mac_address,))
            
            equipamento_existente = cursor.fetchone()
            
            if equipamento_existente:
                # Equipamento existe, verificar se é do tipo correto
                dispositivo_id, tipo_existente, nome_existente, localizacao_id, datalogger_id, online = equipamento_existente
                
                if tipo_existente != tipo:
                    return jsonify({
                        'status': 'erro',
                        'mensagem': f'Equipamento já existe com tipo diferente: {tipo_existente}'
                    }), 400
                
                print(f"✅ Equipamento existente encontrado: {nome_existente} (ID: {dispositivo_id})")
                
                # Atualizar status online e última comunicação
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = true, ultima_comunicacao = %s,
                        versao_firmware = COALESCE(%s, versao_firmware)
                    WHERE id = %s
                """, (datetime.now(), identificacao.get('versao_firmware'), dispositivo_id))
                
            else:
                # Equipamento não existe, criar automaticamente
                print(f"🔧 Criando novo equipamento com MAC: {mac_address}")
                
                # 1. Criar ou usar localização existente
                localizacao_id = None
                
                if localizacao_info:
                    # Verificar se localização já existe
                    nome_localizacao = localizacao_info.get('nome', f'Localização {mac_address}')
                    cursor.execute("""
                        SELECT id FROM localizacoes WHERE nome = %s
                    """, (nome_localizacao,))
                    
                    localizacao = cursor.fetchone()
                    
                    if localizacao:
                        localizacao_id = localizacao[0]
                        print(f"📍 Usando localização existente (ID: {localizacao_id})")
                    else:
                        # Criar nova localização
                        tipo_localizacao = localizacao_info.get('tipo', 'estufa')
                        descricao_localizacao = localizacao_info.get('descricao', '')
                        
                        cursor.execute("""
                            INSERT INTO localizacoes (nome, tipo, descricao)
                            VALUES (%s, %s, %s)
                            RETURNING id
                        """, (nome_localizacao, tipo_localizacao, descricao_localizacao))
                        
                        localizacao_id = cursor.fetchone()[0]
                        
                        # Associar localização ao usuário admin por padrão
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
                
                # Se não forneceram localização, usar a primeira disponível
                if not localizacao_id:
                    cursor.execute("SELECT id FROM localizacoes LIMIT 1")
                    localizacao_id = cursor.fetchone()[0] if cursor.rowcount > 0 else None
                
                # 2. Criar dispositivo
                nome_equipamento = identificacao.get('nome', f'Equipamento {mac_address}')
                modelo = identificacao.get('modelo', '')
                versao_firmware = identificacao.get('versao_firmware', '')
                
                cursor.execute("""
                    INSERT INTO dispositivos (
                        localizacao_id, nome, descricao, mac_address,
                        tipo, modelo, versao_firmware, online, ultima_comunicacao
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    localizacao_id,
                    nome_equipamento,
                    f'Equipamento cadastrado automaticamente via API - MAC: {mac_address}',
                    mac_address,
                    tipo,
                    modelo,
                    versao_firmware,
                    True,
                    datetime.now()
                ))
                
                dispositivo_id = cursor.fetchone()[0]
                print(f"✅ Dispositivo criado (ID: {dispositivo_id})")
                
                # 3. Criar datalogger se for do tipo correto
                if tipo == 'datalogger':
                    sensores_info = identificacao.get('sensores', [])
                    quantidade_sensores = len(sensores_info) if sensores_info else 3
                    
                    cursor.execute("""
                        INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                        VALUES (%s, %s, %s)
                        RETURNING id
                    """, (dispositivo_id, quantidade_sensores, 60))  # 60 segundos por padrão
                    
                    datalogger_id = cursor.fetchone()[0]
                    
                    # 4. Criar sensores automaticamente
                    if sensores_info:
                        for sensor_info in sensores_info:
                            nome_sensor = sensor_info.get('nome', f'Sensor {sensor_info.get("posicao", "desconhecido")}')
                            tipo_sensor = sensor_info.get('tipo', 'temperatura')
                            posicao = sensor_info.get('posicao', '')
                            endereco = sensor_info.get('endereco', f'DS18B20_{datalogger_id}_{posicao}')
                            unidade = sensor_info.get('unidade', '°C' if tipo_sensor == 'temperatura' else '')
                            
                            cursor.execute("""
                                INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (endereco) DO UPDATE SET
                                    nome = EXCLUDED.nome,
                                    tipo = EXCLUDED.tipo,
                                    unidade = EXCLUDED.unidade,
                                    posicao = EXCLUDED.posicao,
                                    ativo = true
                            """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco, True))
                        
                        print(f"✅ {len(sensores_info)} sensores criados/atualizados")
                    else:
                        # Criar sensores padrão se não fornecidos
                        sensores_padrao = [
                            ('Sensor Água', 'temperatura', '°C', 'agua'),
                            ('Sensor Estufa', 'temperatura', '°C', 'estufa'),
                            ('Sensor Externa', 'temperatura', '°C', 'externa')
                        ]
                        
                        for nome_sensor, tipo_sensor, unidade, posicao in sensores_padrao:
                            endereco = f'DS18B20_{datalogger_id}_{posicao}'
                            cursor.execute("""
                                INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco, True))
                        
                        print(f"✅ 3 sensores padrão criados")
                
                print(f"🎉 Equipamento cadastrado automaticamente com sucesso!")
            
            # 5. Processar dados recebidos
            leituras_processadas = 0
            leituras_com_erro = []
            
            if dados:
                for dado in dados:
                    try:
                        sensor_endereco = dado.get('sensor_endereco', '').strip()
                        valor = dado.get('valor')
                        timestamp_str = dado.get('timestamp')
                        
                        if not sensor_endereco or valor is None:
                            leituras_com_erro.append({
                                'sensor_endereco': sensor_endereco,
                                'erro': 'Campos sensor_endereco e valor são obrigatórios'
                            })
                            continue
                        
                        # Buscar sensor pelo endereço
                        cursor.execute("""
                            SELECT id, nome, tipo, unidade, datalogger_id, ativo
                            FROM sensores 
                            WHERE endereco = %s
                        """, (sensor_endereco,))
                        
                        sensor = cursor.fetchone()
                        
                        if not sensor:
                            # Tentar criar sensor automaticamente se não encontrado
                            if tipo == 'datalogger' and datalogger_id:
                                # Extrair informações do endereço
                                sensor_nome = f'Sensor Auto {sensor_endereco[-10:]}'
                                sensor_tipo = 'temperatura'  # Padrão
                                sensor_unidade = '°C'
                                sensor_posicao = sensor_endereco.split('_')[-1] if '_' in sensor_endereco else 'desconhecido'
                                
                                cursor.execute("""
                                    INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                                    RETURNING id
                                """, (datalogger_id, sensor_nome, sensor_tipo, sensor_unidade, 
                                      sensor_posicao, sensor_endereco, True))
                                
                                sensor_id = cursor.fetchone()[0]
                                print(f"🔧 Sensor criado automaticamente: {sensor_endereco} (ID: {sensor_id})")
                            else:
                                leituras_com_erro.append({
                                    'sensor_endereco': sensor_endereco,
                                    'erro': 'Sensor não encontrado e não foi possível criar automaticamente'
                                })
                                continue
                        else:
                            sensor_id, sensor_nome, sensor_tipo, sensor_unidade, sensor_datalogger_id, sensor_ativo = sensor
                            
                            if not sensor_ativo:
                                leituras_com_erro.append({
                                    'sensor_endereco': sensor_endereco,
                                    'erro': 'Sensor inativo'
                                })
                                continue
                        
                        # Converter timestamp
                        if timestamp_str:
                            try:
                                # Tentar diferentes formatos de data
                                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                                    try:
                                        timestamp = datetime.strptime(timestamp_str, fmt)
                                        break
                                    except ValueError:
                                        continue
                                else:
                                    timestamp = datetime.now()
                            except ValueError:
                                timestamp = datetime.now()
                        else:
                            timestamp = datetime.now()
                        
                        # Inserir leitura
                        cursor.execute("""
                            INSERT INTO leituras_sensores (sensor_id, valor, timestamp)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (sensor_id, timestamp) DO UPDATE SET
                                valor = EXCLUDED.valor
                        """, (sensor_id, float(valor), timestamp))
                        
                        leituras_processadas += 1
                        
                        # Verificar limites de temperatura se for sensor de temperatura
                        if sensor_tipo == 'temperatura' and localizacao_id:
                            verificar_limites_temperatura_api(
                                cursor, 
                                localizacao_id, 
                                sensor_id, 
                                float(valor), 
                                sensor_nome,
                                timestamp
                            )
                        
                    except Exception as e:
                        leituras_com_erro.append({
                            'sensor_endereco': dado.get('sensor_endereco', 'desconhecido'),
                            'erro': str(e)
                        })
                        continue
            
            conn.commit()
            
            # Preparar resposta
            resposta = {
                'status': 'sucesso',
                'mensagem': f'Equipamento processado com sucesso',
                'equipamento_id': dispositivo_id,
                'datalogger_id': datalogger_id if tipo == 'datalogger' else None,
                'localizacao_id': localizacao_id,
                'leituras_processadas': leituras_processadas,
                'leituras_com_erro': len(leituras_com_erro)
            }
            
            if leituras_com_erro:
                resposta['erros_detalhados'] = leituras_com_erro
            
            return jsonify(resposta), 200
            
    except Exception as e:
        print(f"❌ Erro ao processar dados do equipamento: {e}")
        import traceback
        traceback.print_exc()
        
        if conn:
            conn.rollback()
        
        return jsonify({
            'status': 'erro',
            'mensagem': f'Erro interno do servidor: {str(e)}'
        }), 500
    finally:
        if conn:
            conn.close()


def validar_mac_address(mac):
    """Valida o formato do MAC address"""
    import re
    pattern = r'^([0-9A-Fa-f]{2}[:]){5}([0-9A-Fa-f]{2})$'
    return re.match(pattern, mac) is not None


def verificar_limites_temperatura_api(cursor, localizacao_id, sensor_id, valor, sensor_nome, timestamp):
    """
    Verifica se a temperatura está dentro dos limites e gera alertas se necessário
    Versão para a API de cadastro automático
    """
    try:
        # Primeiro, obter a posição do sensor
        cursor.execute("SELECT posicao FROM sensores WHERE id = %s", (sensor_id,))
        resultado = cursor.fetchone()
        
        if not resultado:
            return
        
        posicao = resultado[0]
        
        # Buscar limites para esta localização e posição
        cursor.execute("""
            SELECT maximo, minimo 
            FROM limites_temperatura 
            WHERE localizacao_id = %s AND tipo_sensor = %s
        """, (localizacao_id, posicao))
        
        limite = cursor.fetchone()
        
        if not limite:
            # Criar limites padrão se não existirem
            if posicao == 'agua':
                maximo, minimo = 30.0, 20.0
            elif posicao == 'estufa':
                maximo, minimo = 35.0, 25.0
            elif posicao == 'externa':
                maximo, minimo = 40.0, 15.0
            else:
                maximo, minimo = 28.0, 22.0
            
            cursor.execute("""
                INSERT INTO limites_temperatura (localizacao_id, tipo_sensor, maximo, minimo)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (localizacao_id, tipo_sensor) DO NOTHING
            """, (localizacao_id, posicao, maximo, minimo))
        else:
            maximo, minimo = limite
        
        # Verificar se está fora dos limites
        if valor > maximo or valor < minimo:
            tipo_alerta = "TEMPERATURA_ALTA" if valor > maximo else "TEMPERATURA_BAIXA"
            severidade = "ALTA" if abs(valor - (maximo if valor > maximo else minimo)) > 5 else "MEDIA"
            
            mensagem = (
                f"Temperatura {posicao} ({sensor_nome}): {valor:.1f}°C "
                f"{'acima' if valor > maximo else 'abaixo'} do limite "
                f"({maximo if valor > maximo else minimo}°C)"
            )
            
            # Inserir alerta
            cursor.execute("""
                INSERT INTO alertas (localizacao_id, tipo, severidade, mensagem, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, (localizacao_id, tipo_alerta, severidade, mensagem, timestamp))
            
    except Exception as e:
        print(f"⚠️ Erro ao verificar limites de temperatura na API: {e}")


@app.route('/api/equipamento/simples', methods=['POST'])
def receber_dados_simples():
    """Rota para receber dados simplificados do ESP32 datalogger"""
    print("\n" + "="*60)
    print("📥 DADOS RECEBIDOS DO ESP32 DATALOGGER")
    print("="*60)
    
    # Log da requisição
    print(f"Remote Addr: {request.remote_addr}")
    print(f"Content-Type: {request.content_type}")
    print(f"User-Agent: {request.user_agent}")
    
    try:
        # Forçar leitura do JSON mesmo sem header correto
        if request.content_type and 'application/json' in request.content_type:
            data = request.get_json()
        else:
            # Tentar parsear como JSON mesmo sem header
            try:
                raw_data = request.get_data(as_text=True)
                print(f"Dados brutos: {raw_data[:200]}...")
                import json
                data = json.loads(raw_data)
                print("✅ JSON parseado com sucesso")
            except json.JSONDecodeError as je:
                print(f"❌ Erro ao parsear JSON: {je}")
                return jsonify({
                    'status': 'erro',
                    'mensagem': 'Formato JSON inválido'
                }), 400
        
        print(f"Dados recebidos: {data}")
        
        # Validar campos obrigatórios
        if 'mac' not in data:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Campo "mac" é obrigatório'
            }), 400
        
        mac_address = data['mac'].strip().upper()
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        # Processar sensores
        sensores_data = data.get('sensores', {})
        
        print(f"📊 Processando dados para MAC: {mac_address}")
        print(f"📈 Sensores recebidos: {list(sensores_data.keys())}")
        
        conn = db.get_connection()
        if not conn:
            print("❌ Erro: Não foi possível conectar ao banco de dados")
            return jsonify({
                'status': 'erro',
                'mensagem': 'Erro de conexão com o banco de dados'
            }), 500
        
        try:
            with conn.cursor() as cursor:
                # 1. Verificar se o dispositivo existe
                cursor.execute("""
                    SELECT d.id, d.tipo, d.nome, d.localizacao_id, 
                           dl.id as datalogger_id, d.online
                    FROM dispositivos d
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id AND d.tipo = 'datalogger'
                    WHERE d.mac_address = %s
                """, (mac_address,))
                
                dispositivo = cursor.fetchone()
                
                if not dispositivo:
                    print(f"⚠️ Dispositivo não encontrado: {mac_address}")
                    return jsonify({
                        'status': 'erro',
                        'mensagem': f'Equipamento com MAC {mac_address} não encontrado. Por favor, cadastre-o primeiro.'
                    }), 404
                
                dispositivo_id, tipo, nome, localizacao_id, datalogger_id, online = dispositivo
                
                print(f"✅ Dispositivo encontrado: {nome} (ID: {dispositivo_id})")
                print(f"   Tipo: {tipo}, Datalogger ID: {datalogger_id}")
                
                if tipo != 'datalogger':
                    return jsonify({
                        'status': 'erro',
                        'mensagem': f'O equipamento {mac_address} não é um datalogger (tipo: {tipo})'
                    }), 400
                
                # 2. Atualizar status do dispositivo
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = true, ultima_comunicacao = %s
                    WHERE id = %s
                """, (datetime.now(), dispositivo_id))
                
                print(f"✅ Status do dispositivo atualizado")
                
                # 3. Processar leituras dos sensores
                leituras_processadas = 0
                erros = []
                
                # Mapeamento de posições para endereços
                posicoes_para_endereco = {
                    'agua': f'DS18B20_{datalogger_id}_agua',
                    'estufa': f'DS18B20_{datalogger_id}_estufa',
                    'externa': f'DS18B20_{datalogger_id}_externa'
                }
                
                for posicao, valor in sensores_data.items():
                    try:
                        # Validar valor
                        if valor is None:
                            erros.append(f"Valor nulo para {posicao}")
                            continue
                        
                        valor_float = float(valor)
                        
                        # Obter endereço do sensor baseado na posição
                        endereco = posicoes_para_endereco.get(posicao)
                        if not endereco:
                            # Tentar endereço padrão
                            endereco = f'DS18B20_{datalogger_id}_{posicao}'
                        
                        print(f"📡 Processando sensor {posicao}: {valor_float}°C (endereço: {endereco})")
                        
                        # Buscar sensor pelo endereço
                        cursor.execute("""
                            SELECT id, nome, tipo, unidade, ativo
                            FROM sensores 
                            WHERE endereco = %s AND datalogger_id = %s
                        """, (endereco, datalogger_id))
                        
                        sensor = cursor.fetchone()
                        
                        if not sensor:
                            print(f"⚠️ Sensor não encontrado: {endereco}")
                            
                            # Tentar criar sensor automaticamente
                            nome_sensor = f"Sensor {posicao.capitalize()}"
                            tipo_sensor = 'temperatura'
                            unidade = '°C'
                            
                            cursor.execute("""
                                INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                RETURNING id
                            """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco, True))
                            
                            sensor_id = cursor.fetchone()[0]
                            print(f"✅ Sensor criado automaticamente: {nome_sensor} (ID: {sensor_id})")
                        else:
                            sensor_id, sensor_nome, sensor_tipo, unidade, ativo = sensor
                            
                            if not ativo:
                                erros.append(f"Sensor {posicao} está inativo")
                                continue
                            
                            print(f"✅ Sensor encontrado: {sensor_nome} (ID: {sensor_id})")
                        
                        # Converter timestamp
                        try:
                            if isinstance(timestamp, str):
                                if 'T' in timestamp:
                                    timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                else:
                                    # Tentar diferentes formatos
                                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                                        try:
                                            timestamp_dt = datetime.strptime(timestamp, fmt)
                                            break
                                        except ValueError:
                                            continue
                                    else:
                                        timestamp_dt = datetime.now()
                            else:
                                timestamp_dt = datetime.now()
                        except Exception as e:
                            print(f"⚠️ Erro ao converter timestamp: {e}")
                            timestamp_dt = datetime.now()
                        
                        # Inserir leitura
                        cursor.execute("""
                            INSERT INTO leituras_sensores (sensor_id, valor, timestamp)
                            VALUES (%s, %s, %s)
                        """, (sensor_id, valor_float, timestamp_dt))
                        
                        leituras_processadas += 1
                        
                        # Verificar limites de temperatura
                        if localizacao_id and posicao in ['agua', 'estufa', 'externa']:
                            verificar_limites_temperatura_api(
                                cursor, 
                                localizacao_id, 
                                sensor_id, 
                                valor_float, 
                                f"Sensor {posicao}", 
                                timestamp_dt
                            )
                        
                    except Exception as e:
                        print(f"❌ Erro ao processar sensor {posicao}: {e}")
                        erros.append(f"{posicao}: {str(e)}")
                        continue
                
                # 4. Atualizar informações do datalogger
                sensores_recebidos = len([k for k in sensores_data.keys() if sensores_data[k] is not None])
                if sensores_recebidos > 0:
                    cursor.execute("""
                        UPDATE dataloggers 
                        SET quantidade_sensores = %s
                        WHERE id = %s
                    """, (sensores_recebidos, datalogger_id))
                
                # 5. Commitar todas as mudanças
                conn.commit()
                
                print(f"\n✅ RESULTADO DO PROCESSAMENTO:")
                print(f"   Leituras processadas: {leituras_processadas}/{len(sensores_data)}")
                print(f"   Erros: {len(erros)}")
                
                if erros:
                    print(f"   Detalhes dos erros: {erros}")
                
                # 6. Preparar resposta
                resposta = {
                    'status': 'sucesso',
                    'mensagem': f'{leituras_processadas} leitura(s) processada(s) com sucesso',
                    'equipamento': nome,
                    'mac': mac_address,
                    'leituras_processadas': leituras_processadas,
                    'sensores_recebidos': len(sensores_data),
                    'timestamp': datetime.now().isoformat()
                }
                
                if erros:
                    resposta['erros'] = erros
                    resposta['status'] = 'parcial'
                    resposta['mensagem'] = f'{leituras_processadas} leitura(s) processada(s), {len(erros)} erro(s)'
                
                return jsonify(resposta), 200
                
        except Exception as e:
            print(f"❌ Erro no processamento: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return jsonify({
                'status': 'erro',
                'mensagem': f'Erro no processamento: {str(e)}'
            }), 500
        finally:
            if conn:
                conn.close()
                
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'erro',
            'mensagem': f'Erro ao processar requisição: {str(e)}'
        }), 500
# ====================
# MIDDLEWARE - Verificar autenticação
# ====================

# ====================
# MIDDLEWARE - Verificar autenticação
# ====================


@app.route('/api/ping', methods=['GET', 'POST'])
def api_ping():
    """Rota simples de teste - sempre retorna JSON"""
    print(f"\n📡 /api/ping chamado - Método: {request.method}")
    
    if request.method == 'GET':
        return jsonify({
            'status': 'ok',
            'message': 'pong',
            'timestamp': datetime.now().isoformat()
        })
    
    elif request.method == 'POST':
        if request.is_json:
            data = request.get_json()
            return jsonify({
                'status': 'ok',
                'message': 'POST recebido',
                'data': data,
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Content-Type deve ser application/json'
            }), 400

@app.route('/api/equipamento/autocadastro', methods=['POST'])
def autocadastro_equipamento():
    """Rota para autocadastro completo do ESP32 (datalogger OU alimentador)"""
    print("\n" + "="*60)
    print("🤖 AUTOCADASTRO DO ESP32")
    print("="*60)
    
    try:
        # Forçar leitura do JSON
        if request.content_type and 'application/json' in request.content_type:
            data = request.get_json()
        else:
            try:
                raw_data = request.get_data(as_text=True)
                import json
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                return jsonify({
                    'status': 'erro',
                    'mensagem': 'Formato JSON inválido'
                }), 400
        
        print(f"Dados recebidos: {data}")
        
        # Validar campos obrigatórios
        campos_obrigatorios = ['identificacao']
        for campo in campos_obrigatorios:
            if campo not in data:
                return jsonify({
                    'status': 'erro',
                    'mensagem': f'Campo "{campo}" é obrigatório'
                }), 400
        
        identificacao = data['identificacao']
        
        # Validar identificação
        if 'mac' not in identificacao:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Campo "mac" é obrigatório na identificação'
            }), 400
        
        mac_address = identificacao['mac'].strip().upper()
        nome = identificacao.get('nome', f'ESP32 {mac_address[-6:]}')
        tipo = identificacao.get('tipo', 'datalogger')
        modelo = identificacao.get('modelo', 'ESP32 DevKit')
        versao_firmware = identificacao.get('versao_firmware', '1.0.0')
        
        # Informações da localização (opcional - pode criar automaticamente)
        localizacao_info = identificacao.get('localizacao', {})
        localizacao_nome = localizacao_info.get('nome', f'Local-{mac_address[-4:]}')
        localizacao_tipo = localizacao_info.get('tipo', 'estufa')
        localizacao_desc = localizacao_info.get('descricao', f'Localização automática para {mac_address}')
        
        print(f"📋 IDENTIFICAÇÃO DO EQUIPAMENTO:")
        print(f"   MAC: {mac_address}")
        print(f"   Nome: {nome}")
        print(f"   Tipo: {tipo}")
        print(f"   Modelo: {modelo}")
        print(f"   Localização: {localizacao_nome} ({localizacao_tipo})")
        
        conn = db.get_connection()
        if not conn:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Erro de conexão com o banco de dados'
            }), 500
        
        try:
            with conn.cursor() as cursor:
                # 1. Verificar se o dispositivo já existe
                cursor.execute("""
                    SELECT d.id, d.nome, d.localizacao_id, 
                           dl.id as datalogger_id,
                           a.id as alimentador_id
                    FROM dispositivos d
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id AND d.tipo = 'datalogger'
                    LEFT JOIN alimentadores a ON d.id = a.dispositivo_id AND d.tipo = 'alimentador'
                    WHERE d.mac_address = %s
                """, (mac_address,))
                
                dispositivo_existente = cursor.fetchone()
                
                if dispositivo_existente:
                    # Equipamento já existe, usar os dados existentes
                    dispositivo_id, nome_existente, localizacao_id, datalogger_id, alimentador_id = dispositivo_existente
                    print(f"✅ Equipamento já cadastrado: {nome_existente} (ID: {dispositivo_id})")
                    
                    # Atualizar informações do dispositivo
                    cursor.execute("""
                        UPDATE dispositivos 
                        SET nome = COALESCE(%s, nome),
                            modelo = COALESCE(%s, modelo),
                            versao_firmware = COALESCE(%s, versao_firmware),
                            online = true,
                            ultima_comunicacao = %s
                        WHERE id = %s
                    """, (nome, modelo, versao_firmware, datetime.now(), dispositivo_id))
                    
                else:
                    # 2. Criar nova localização (ou usar existente)
                    localizacao_id = None
                    
                    # Verificar se localização já existe pelo nome
                    cursor.execute("""
                        SELECT id FROM localizacoes WHERE nome = %s
                    """, (localizacao_nome,))
                    
                    localizacao = cursor.fetchone()
                    
                    if localizacao:
                        localizacao_id = localizacao[0]
                        print(f"📍 Localização existente: {localizacao_nome} (ID: {localizacao_id})")
                    else:
                        # Criar nova localização
                        cursor.execute("""
                            INSERT INTO localizacoes (nome, tipo, descricao)
                            VALUES (%s, %s, %s)
                            RETURNING id
                        """, (localizacao_nome, localizacao_tipo, localizacao_desc))
                        
                        localizacao_id = cursor.fetchone()[0]
                        
                        # Associar ao primeiro usuário admin encontrado
                        cursor.execute("""
                            SELECT id FROM usuarios WHERE tipo = 'admin' AND ativo = true LIMIT 1
                        """)
                        
                        admin = cursor.fetchone()
                        if admin:
                            admin_id = admin[0]
                            cursor.execute("""
                                INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                                VALUES (%s, %s)
                                ON CONFLICT (usuario_id, localizacao_id) DO NOTHING
                            """, (admin_id, localizacao_id))
                        
                        print(f"📍 Nova localização criada: {localizacao_nome} (ID: {localizacao_id})")
                    
                    # 3. Criar novo dispositivo
                    cursor.execute("""
                        INSERT INTO dispositivos (
                            localizacao_id, nome, descricao, mac_address,
                            tipo, modelo, versao_firmware, online, ultima_comunicacao
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        localizacao_id,
                        nome,
                        f'Equipamento autocadastrado via API - MAC: {mac_address}',
                        mac_address,
                        tipo,
                        modelo,
                        versao_firmware,
                        True,
                        datetime.now()
                    ))
                    
                    dispositivo_id = cursor.fetchone()[0]
                    print(f"✅ Novo dispositivo criado: {nome} (ID: {dispositivo_id})")
                    
                    # ============================================
                    # 4. LÓGICA ESPECÍFICA PARA DATALOGGER
                    # ============================================
                    if tipo == 'datalogger':
                        cursor.execute("""
                            INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                            VALUES (%s, %s, %s)
                            RETURNING id
                        """, (dispositivo_id, 3, 60))
                        
                        datalogger_id = cursor.fetchone()[0]
                        print(f"✅ Datalogger criado: ID {datalogger_id}")
                        
                        # Criar sensores padrão
                        sensores_padrao = [
                            ('Sensor Água', 'temperatura', '°C', 'agua', f'DS18B20_{datalogger_id}_agua'),
                            ('Sensor Estufa', 'temperatura', '°C', 'estufa', f'DS18B20_{datalogger_id}_estufa'),
                            ('Sensor Externa', 'temperatura', '°C', 'externa', f'DS18B20_{datalogger_id}_externa')
                        ]
                        
                        for nome_sensor, tipo_sensor, unidade, posicao, endereco in sensores_padrao:
                            cursor.execute("""
                                INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (endereco) DO UPDATE SET
                                    nome = EXCLUDED.nome,
                                    ativo = true
                            """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco, True))
                        
                        print(f"✅ 3 sensores padrão criados/atualizados")
                        
                        # Processar dados dos sensores se enviados
                        if 'dados_sensores' in data:
                            processar_dados_sensores(cursor, datalogger_id, localizacao_id, data['dados_sensores'])
                    
                    # ============================================
                    # 5. LÓGICA ESPECÍFICA PARA ALIMENTADOR
                    # ============================================
                    elif tipo == 'alimentador':
                        # Extrair dados de configuração (se fornecidos)
                        configuracao = data.get('configuracao', {})
                        dados_operacao = data.get('dados', {})
                        
                        # 5.1 Criar alimentador
                        capacidade_racao = configuracao.get('capacidade_racao', 5000.00)
                        vazao_media = configuracao.get('vazao_media', 10.00)
                        nivel_racao_atual = dados_operacao.get('nivel_racao', capacidade_racao)
                        motor_ligado = dados_operacao.get('motor_ligado', False)
                        
                        cursor.execute("""
                            INSERT INTO alimentadores (
                                dispositivo_id, capacidade_racao, vazao_media, 
                                nivel_racao_atual, motor_ligado
                            ) VALUES (%s, %s, %s, %s, %s)
                            RETURNING id
                        """, (dispositivo_id, capacidade_racao, vazao_media, nivel_racao_atual, motor_ligado))
                        
                        alimentador_id = cursor.fetchone()[0]
                        print(f"✅ Alimentador criado: ID {alimentador_id}")
                        
                        # 5.2 Criar configuração do alimentador
                        ativa = configuracao.get('ativa', False)
                        horario_inicio = configuracao.get('horario_inicio', '08:00:00')
                        horario_fim = configuracao.get('horario_fim', '18:00:00')
                        intervalo_alimentacao = configuracao.get('intervalo_alimentacao', 3600)
                        quantidade_por_alimentacao = configuracao.get('quantidade_por_alimentacao', 15.00)
                        dias_semana = configuracao.get('dias_semana', '1,2,3,4,5,6,7')
                        
                        cursor.execute("""
                            INSERT INTO config_alimentadores (
                                alimentador_id, ativa, horario_inicio, horario_fim,
                                intervalo_alimentacao, quantidade_por_alimentacao, dias_semana
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (alimentador_id) DO UPDATE SET
                                ativa = EXCLUDED.ativa,
                                horario_inicio = EXCLUDED.horario_inicio,
                                horario_fim = EXCLUDED.horario_fim,
                                intervalo_alimentacao = EXCLUDED.intervalo_alimentacao,
                                quantidade_por_alimentacao = EXCLUDED.quantidade_por_alimentacao,
                                dias_semana = EXCLUDED.dias_semana,
                                updated_at = CURRENT_TIMESTAMP
                        """, (alimentador_id, ativa, horario_inicio, horario_fim, 
                              intervalo_alimentacao, quantidade_por_alimentacao, dias_semana))
                        
                        print(f"✅ Configuração do alimentador criada")
                        
                        # 5.3 Criar calibração do alimentador
                        constante_a = configuracao.get('constante_a', 0.105)
                        constante_b = configuracao.get('constante_b', 0.0)
                        tempo_acionamento = configuracao.get('tempo_acionamento', 1050)
                        
                        cursor.execute("""
                            INSERT INTO calibracao_alimentadores (
                                alimentador_id, constante_a, constante_b, 
                                tempo_acionamento, calibrado_em
                            ) VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (alimentador_id) DO UPDATE SET
                                constante_a = EXCLUDED.constante_a,
                                constante_b = EXCLUDED.constante_b,
                                tempo_acionamento = EXCLUDED.tempo_acionamento,
                                updated_at = CURRENT_TIMESTAMP
                        """, (alimentador_id, constante_a, constante_b, tempo_acionamento, datetime.now()))
                        
                        print(f"✅ Calibração do alimentador criada")
                        
                        # 5.4 Associar a um datalogger da mesma localização (se existir)
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
                            print(f"⚠️ Nenhum datalogger encontrado na localização {localizacao_nome} para associar")
                        
                        # 5.5 Registrar histórico de alimentação se houver dados
                        if 'historico' in data:
                            for evento in data['historico']:
                                quantidade = evento.get('quantidade_racao', 0)
                                tempo = evento.get('tempo_acionamento', 0)
                                timestamp_alimentacao = evento.get('timestamp', datetime.now().isoformat())
                                modo = evento.get('modo', 'automatico')
                                
                                try:
                                    if isinstance(timestamp_alimentacao, str):
                                        timestamp_dt = datetime.fromisoformat(timestamp_alimentacao.replace('Z', '+00:00'))
                                    else:
                                        timestamp_dt = datetime.now()
                                    
                                    cursor.execute("""
                                        INSERT INTO historico_alimentacao (
                                            alimentador_id, quantidade_racao, tempo_acionamento, 
                                            timestamp, modo
                                        ) VALUES (%s, %s, %s, %s, %s)
                                    """, (alimentador_id, quantidade, tempo, timestamp_dt, modo))
                                except Exception as e:
                                    print(f"⚠️ Erro ao registrar histórico: {e}")
                            
                            if len(data['historico']) > 0:
                                print(f"✅ {len(data['historico'])} eventos de histórico registrados")
                        
                        # 5.6 Verificar nível de ração e gerar alerta se necessário
                        nivel_percentual = (nivel_racao_atual / capacidade_racao) * 100 if capacidade_racao > 0 else 0
                        
                        if nivel_percentual < 10:
                            cursor.execute("""
                                INSERT INTO alertas (
                                    dispositivo_id, localizacao_id, tipo, severidade, 
                                    mensagem, timestamp
                                ) VALUES (%s, %s, %s, %s, %s, %s)
                            """, (
                                dispositivo_id, localizacao_id, 'racao', 'alto',
                                f'Nível de ração CRÍTICO: {nivel_racao_atual:.0f}g ({nivel_percentual:.0f}% da capacidade)',
                                datetime.now()
                            ))
                            print(f"⚠️ Alerta gerado: Nível de ração crítico ({nivel_percentual:.0f}%)")
                        elif nivel_percentual < 20:
                            cursor.execute("""
                                INSERT INTO alertas (
                                    dispositivo_id, localizacao_id, tipo, severidade, 
                                    mensagem, timestamp
                                ) VALUES (%s, %s, %s, %s, %s, %s)
                            """, (
                                dispositivo_id, localizacao_id, 'racao', 'medio',
                                f'Nível de ração BAIXO: {nivel_racao_atual:.0f}g ({nivel_percentual:.0f}% da capacidade)',
                                datetime.now()
                            ))
                            print(f"⚠️ Alerta gerado: Nível de ração baixo ({nivel_percentual:.0f}%)")
                        
                        # 5.7 Criar limites padrão para temperatura (se não existirem)
                        sensores_posicoes = ['agua', 'estufa', 'externa']
                        for posicao in sensores_posicoes:
                            cursor.execute("""
                                SELECT 1 FROM limites_temperatura 
                                WHERE localizacao_id = %s AND tipo_sensor = %s
                            """, (localizacao_id, posicao))
                            
                            if not cursor.fetchone():
                                if posicao == 'agua':
                                    maximo, minimo = 30.0, 20.0
                                elif posicao == 'estufa':
                                    maximo, minimo = 35.0, 25.0
                                elif posicao == 'externa':
                                    maximo, minimo = 40.0, 15.0
                                else:
                                    maximo, minimo = 28.0, 22.0
                                
                                cursor.execute("""
                                    INSERT INTO limites_temperatura (localizacao_id, tipo_sensor, maximo, minimo)
                                    VALUES (%s, %s, %s, %s)
                                    ON CONFLICT (localizacao_id, tipo_sensor) DO NOTHING
                                """, (localizacao_id, posicao, maximo, minimo))
                
                # 6. Commitar todas as mudanças
                conn.commit()
                
                # 7. Preparar resposta baseada no tipo
                if tipo == 'datalogger':
                    resposta = {
                        'status': 'sucesso',
                        'mensagem': 'Datalogger autocadastrado com sucesso!',
                        'equipamento': {
                            'id': dispositivo_id,
                            'nome': nome,
                            'mac': mac_address,
                            'tipo': tipo,
                            'localizacao_id': localizacao_id,
                            'localizacao_nome': localizacao_nome
                        },
                        'datalogger_id': datalogger_id if tipo == 'datalogger' else None,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # Adicionar estatísticas de leituras se processadas
                    if 'dados_sensores' in data:
                        resposta['leituras_processadas'] = len(data['dados_sensores'])
                    
                elif tipo == 'alimentador':
                    resposta = {
                        'status': 'sucesso',
                        'mensagem': 'Alimentador autocadastrado com sucesso!',
                        'equipamento': {
                            'id': dispositivo_id,
                            'nome': nome,
                            'mac': mac_address,
                            'tipo': tipo,
                            'localizacao_id': localizacao_id,
                            'localizacao_nome': localizacao_nome
                        },
                        'alimentador_id': alimentador_id,
                        'configuracoes': {
                            'ativa': ativa if 'ativa' in locals() else False,
                            'intervalo_alimentacao': intervalo_alimentacao if 'intervalo_alimentacao' in locals() else 3600,
                            'quantidade_por_alimentacao': quantidade_por_alimentacao if 'quantidade_por_alimentacao' in locals() else 15.00
                        },
                        'nivel_racao': nivel_racao_atual if 'nivel_racao_atual' in locals() else 0,
                        'capacidade': capacidade_racao if 'capacidade_racao' in locals() else 0,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # Adicionar aviso se nível baixo
                    if 'nivel_percentual' in locals() and nivel_percentual < 20:
                        resposta['alerta'] = f'Nível de ração baixo: {nivel_percentual:.0f}%'
                else:
                    resposta = {
                        'status': 'sucesso',
                        'mensagem': f'Equipamento tipo "{tipo}" cadastrado com sucesso!',
                        'equipamento': {
                            'id': dispositivo_id,
                            'nome': nome,
                            'mac': mac_address,
                            'tipo': tipo,
                            'localizacao_id': localizacao_id,
                            'localizacao_nome': localizacao_nome
                        },
                        'timestamp': datetime.now().isoformat()
                    }
                
                print(f"\n✅ AUTOCADASTRO CONCLUÍDO COM SUCESSO!")
                return jsonify(resposta), 200
                
        except Exception as e:
            print(f"❌ Erro no autocadastro: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
            return jsonify({
                'status': 'erro',
                'mensagem': f'Erro no autocadastro: {str(e)}'
            }), 500
        finally:
            if conn:
                conn.close()
                
    except Exception as e:
        print(f"❌ Erro geral no autocadastro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'erro',
            'mensagem': f'Erro ao processar requisição: {str(e)}'
        }), 500


def processar_dados_sensores(cursor, datalogger_id, localizacao_id, dados_sensores):
    """Função auxiliar para processar dados dos sensores"""
    for sensor_data in dados_sensores:
        try:
            posicao = sensor_data.get('posicao', '').lower()
            valor = sensor_data.get('valor')
            timestamp = sensor_data.get('timestamp', datetime.now().isoformat())
            
            if not posicao or valor is None:
                continue
            
            valor_float = float(valor)
            
            # Buscar sensor
            cursor.execute("""
                SELECT id, nome, tipo, unidade, ativo
                FROM sensores 
                WHERE datalogger_id = %s AND posicao = %s
            """, (datalogger_id, posicao))
            
            sensor = cursor.fetchone()
            
            if not sensor:
                # Criar sensor automaticamente
                nome_sensor = f"Sensor {posicao.capitalize()}"
                tipo_sensor = 'temperatura'
                unidade = '°C'
                endereco = f'DS18B20_{datalogger_id}_{posicao}'
                
                cursor.execute("""
                    INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco, True))
                
                sensor_id = cursor.fetchone()[0]
                print(f"  ✅ Sensor {posicao} criado (ID: {sensor_id})")
            else:
                sensor_id = sensor[0]
                if not sensor[4]:  # ativo = false
                    cursor.execute("UPDATE sensores SET ativo = true WHERE id = %s", (sensor_id,))
                    print(f"  ✅ Sensor {posicao} reativado")
            
            # Converter timestamp
            try:
                if isinstance(timestamp, str):
                    if 'T' in timestamp:
                        timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    else:
                        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                            try:
                                timestamp_dt = datetime.strptime(timestamp, fmt)
                                break
                            except ValueError:
                                continue
                        else:
                            timestamp_dt = datetime.now()
                else:
                    timestamp_dt = datetime.now()
            except Exception:
                timestamp_dt = datetime.now()
            
            # Inserir leitura
            cursor.execute("""
                INSERT INTO leituras_sensores (sensor_id, valor, timestamp)
                VALUES (%s, %s, %s)
            """, (sensor_id, valor_float, timestamp_dt))
            
            # Verificar limites de temperatura
            if localizacao_id and posicao in ['agua', 'estufa', 'externa']:
                verificar_limites_temperatura_simples(
                    cursor, localizacao_id, posicao, valor_float, 
                    f"Sensor {posicao}", timestamp_dt
                )
            
        except Exception as e:
            print(f"  ❌ Erro no sensor {sensor_data.get('posicao', 'unknown')}: {e}")
            continue

def verificar_limites_temperatura_simples(cursor, localizacao_id, sensor_posicao, valor, sensor_nome, timestamp):
    """
    Versão simplificada para verificar limites de temperatura
    """
    try:
        # Buscar limites para esta localização e posição
        cursor.execute("""
            SELECT maximo, minimo 
            FROM limites_temperatura 
            WHERE localizacao_id = %s AND tipo_sensor = %s
        """, (localizacao_id, sensor_posicao))
        
        limite = cursor.fetchone()
        
        if limite:
            maximo, minimo = limite
            
            # Verificar se está fora dos limites
            if valor > maximo or valor < minimo:
                tipo_alerta = "TEMPERATURA_ALTA" if valor > maximo else "TEMPERATURA_BAIXA"
                severidade = "ALTA" if abs(valor - (maximo if valor > maximo else minimo)) > 5 else "MEDIA"
                
                mensagem = (
                    f"Temperatura {sensor_posicao} ({sensor_nome}): {valor:.1f}°C "
                    f"{'acima' if valor > maximo else 'abaixo'} do limite "
                    f"({maximo if valor > maximo else minimo}°C)"
                )
                
                # Inserir alerta
                cursor.execute("""
                    INSERT INTO alertas (localizacao_id, tipo, severidade, mensagem, timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                """, (localizacao_id, tipo_alerta, severidade, mensagem, timestamp))
                print(f"⚠️ Alerta gerado: {mensagem}")
                
    except Exception as e:
        print(f"⚠️ Erro ao verificar limites: {e}")

# Adicione no app.py

# Adicione após as importações e antes das rotas

from functools import wraps

# Decorator para verificar permissões
def require_permission(permission_level='usuario'):
    """
    Decorator para verificar permissões do usuário
    
    Args:
        permission_level: 'usuario' (padrão) ou 'admin'
    
    Usage:
        @require_permission()  # Qualquer usuário logado
        @require_permission('admin')  # Apenas admin
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Verificar se usuário está logado
            if 'usuario_id' not in session:
                if request.is_json:
                    return jsonify({'error': 'Não autenticado'}), 401
                flash('Por favor, faça login para acessar esta página.', 'warning')
                return redirect(url_for('login'))
            
            # Verificar nível de permissão
            if permission_level == 'admin' and session.get('usuario_tipo') != 'admin':
                if request.is_json:
                    return jsonify({'error': 'Acesso negado. Apenas administradores.'}), 403
                flash('Acesso negado. Apenas administradores podem acessar esta página.', 'danger')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Versão simples sem argumentos (para compatibilidade com código existente)
def login_required(f):
    """Decorator simples que apenas verifica se usuário está logado"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Não autenticado'}), 401
            flash('Por favor, faça login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/equipamento/comando', methods=['GET'])
def obter_comando_equipamento():
    """Retorna comandos pendentes para o equipamento"""
    if 'usuario_id' not in session:
        return jsonify({'error': 'Não autenticado'}), 401
    
    mac_address = request.args.get('mac_address', '').strip().upper()
    
    conn = db.get_connection()
    if not conn:
        return jsonify({'error': 'Erro de conexão'}), 500
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Buscar comandos pendentes para este equipamento
            cursor.execute("""
                SELECT comando, parametros, criado_em
                FROM comandos_pendentes
                WHERE mac_address = %s AND executado = false
                ORDER BY criado_em ASC
                LIMIT 1
            """, (mac_address,))
            
            comando = cursor.fetchone()
            
            if comando:
                # Marcar como executado
                cursor.execute("""
                    UPDATE comandos_pendentes 
                    SET executado = true, executado_em = NOW()
                    WHERE mac_address = %s AND comando = %s
                """, (mac_address, comando['comando']))
                
                conn.commit()
                
                return jsonify({
                    'comando': comando['comando'],
                    'peso': comando['parametros'].get('peso', 0) if comando['parametros'] else 0,
                    'estado': comando['parametros'].get('estado', False) if comando['parametros'] else False
                })
            
            return jsonify({'comando': 'nenhum'})
            
    except Exception as e:
        app.logger.error(f"Erro ao buscar comando: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/equipamento/enviar-comando', methods=['POST'])
@require_permission()
def enviar_comando_equipamento():
    """Envia um comando para um equipamento específico"""
    data = request.get_json()
    
    mac_address = data.get('mac_address', '').strip().upper()
    comando = data.get('comando')
    parametros = data.get('parametros', {})
    
    if not mac_address or not comando:
        return jsonify({'error': 'mac_address e comando são obrigatórios'}), 400
    
    conn = db.get_connection()
    if not conn:
        return jsonify({'error': 'Erro de conexão'}), 500
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                VALUES (%s, %s, %s, %s)
            """, (mac_address, comando, json.dumps(parametros), session['usuario_id']))
            
            conn.commit()
            
            # Registrar log
            db.registrar_log(
                session['usuario_id'],
                'ENVIAR_COMANDO',
                f'Comando {comando} enviado para {mac_address}',
                request.remote_addr,
                request.user_agent.string
            )
            
            return jsonify({'success': True, 'mensagem': 'Comando enviado com sucesso'})
            
    except Exception as e:
        app.logger.error(f"Erro ao enviar comando: {e}")
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

# ============================================
# API PARA DATALOGGER (APENAS LEITURA)
# ============================================

# ============================================
# ROTAS DA API PARA DATALOGGER - CORRIGIDAS
# ============================================

@app.route('/api/datalogger/autocadastro', methods=['POST'])
def autocadastro_datalogger():
    """
    Autocadastro de datalogger ESP32
    """
    print("\n" + "="*60)
    print("🌡️ AUTOCADASTRO DATALOGGER")
    print("="*60)
    
    try:
        # Verificar se é JSON
        if not request.is_json:
            print("❌ Content-Type não é JSON")
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        print(f"📥 Dados recebidos: {data}")
        
        # Validar campos
        if 'identificacao' not in data:
            print("❌ Campo 'identificacao' não encontrado")
            return jsonify({'error': 'Campo identificacao é obrigatório'}), 400
        
        identificacao = data['identificacao']
        
        if 'mac' not in identificacao:
            print("❌ Campo 'mac' não encontrado")
            return jsonify({'error': 'Campo mac é obrigatório'}), 400
        
        mac_address = identificacao['mac'].strip().upper()
        print(f"🔑 MAC Address: {mac_address}")
        
        conn = db.get_connection()
        if not conn:
            print("❌ Erro de conexão com banco")
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            # Verificar se já existe
            cursor.execute("""
                SELECT d.id, d.nome, d.localizacao_id 
                FROM dispositivos d
                WHERE d.mac_address = %s AND d.tipo = 'datalogger'
            """, (mac_address,))
            
            existente = cursor.fetchone()
            
            if existente:
                print(f"✅ Datalogger já existe: ID {existente[0]}")
                
                # Atualizar online
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = true, ultima_comunicacao = %s
                    WHERE id = %s
                """, (datetime.now(), existente[0]))
                conn.commit()
                
                return jsonify({
                    'status': 'sucesso',
                    'mensagem': 'Datalogger já cadastrado',
                    'datalogger_id': existente[0]
                }), 200
            
            # Criar localização padrão
            localizacao_nome = identificacao.get('localizacao', {}).get('nome', 'Localização Padrão')
            localizacao_tipo = identificacao.get('localizacao', {}).get('tipo', 'estufa')
            
            cursor.execute("""
                INSERT INTO localizacoes (nome, tipo, descricao)
                VALUES (%s, %s, %s)
                ON CONFLICT (nome) DO UPDATE SET nome = EXCLUDED.nome
                RETURNING id
            """, (localizacao_nome, localizacao_tipo, f'Localização para {mac_address}'))
            
            localizacao_id = cursor.fetchone()[0]
            print(f"📍 Localização ID: {localizacao_id}")
            
            # Criar dispositivo
            nome_equipamento = identificacao.get('nome', f'Datalogger {mac_address[-8:]}')
            modelo = identificacao.get('modelo', 'ESP32')
            versao = identificacao.get('versao_firmware', '1.0.0')
            
            cursor.execute("""
                INSERT INTO dispositivos (
                    localizacao_id, nome, descricao, mac_address,
                    tipo, modelo, versao_firmware, online, ultima_comunicacao
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                localizacao_id,
                nome_equipamento,
                f'Datalogger autocadastrado - MAC: {mac_address}',
                mac_address,
                'datalogger',
                modelo,
                versao,
                True,
                datetime.now()
            ))
            
            dispositivo_id = cursor.fetchone()[0]
            print(f"✅ Dispositivo criado: ID {dispositivo_id}")
            
            # Criar datalogger
            cursor.execute("""
                INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (dispositivo_id, 3, 60))
            
            datalogger_id = cursor.fetchone()[0]
            print(f"✅ Datalogger criado: ID {datalogger_id}")
            
            # Criar sensores
            sensores_info = identificacao.get('sensores', [])
            
            if not sensores_info:
                # Sensores padrão
                sensores_padrao = [
                    ('Sensor Água', 'temperatura', '°C', 'agua', 'DS18B20_agua'),
                    ('Sensor Estufa', 'temperatura', '°C', 'estufa', 'DS18B20_estufa'),
                    ('Sensor Externa', 'temperatura', '°C', 'externa', 'DS18B20_externa')
                ]
                
                for nome_sensor, tipo_sensor, unidade, posicao, endereco in sensores_padrao:
                    cursor.execute("""
                        INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco, True))
            else:
                for sensor in sensores_info:
                    cursor.execute("""
                        INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        datalogger_id,
                        sensor.get('nome', 'Sensor'),
                        sensor.get('tipo', 'temperatura'),
                        sensor.get('unidade', '°C'),
                        sensor.get('posicao', 'desconhecido'),
                        sensor.get('endereco', f'DS18B20_{datalogger_id}'),
                        True
                    ))
            
            print(f"✅ {len(sensores_info) if sensores_info else 3} sensores criados")
            
            # Criar limites padrão
            limites_padrao = [
                ('agua', 30.0, 20.0),
                ('estufa', 35.0, 25.0),
                ('externa', 40.0, 15.0)
            ]
            
            for tipo_sensor, maximo, minimo in limites_padrao:
                cursor.execute("""
                    INSERT INTO limites_temperatura (localizacao_id, tipo_sensor, maximo, minimo)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (localizacao_id, tipo_sensor) DO NOTHING
                """, (localizacao_id, tipo_sensor, maximo, minimo))
            
            conn.commit()
            
            print("🎉 Datalogger cadastrado com sucesso!")
            
            return jsonify({
                'status': 'sucesso',
                'mensagem': 'Datalogger cadastrado com sucesso',
                'datalogger_id': dispositivo_id
            }), 201
            
    except Exception as e:
        print(f"❌ Erro no autocadastro: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()




@app.route('/api/datalogger/config', methods=['GET'])
def get_config_datalogger():
    """Retorna configurações do datalogger"""
    mac_address = request.args.get('mac_address', '').strip().upper()
    
    if not mac_address:
        return jsonify({'error': 'mac_address é obrigatório'}), 400
    
    conn = db.get_connection()
    if not conn:
        return jsonify({'error': 'Erro de conexão'}), 500
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT d.id, d.localizacao_id, dl.intervalo_leitura
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.mac_address = %s AND d.tipo = 'datalogger'
            """, (mac_address,))
            
            resultado = cursor.fetchone()
            
            if not resultado:
                return jsonify({'error': 'Datalogger não encontrado'}), 404
            
            dispositivo_id, localizacao_id, intervalo = resultado
            
            # Buscar limites
            cursor.execute("""
                SELECT tipo_sensor, maximo, minimo
                FROM limites_temperatura
                WHERE localizacao_id = %s
            """, (localizacao_id,))
            
            limites = cursor.fetchall()
            
            limites_dict = {}
            for limite in limites:
                limites_dict[limite[0]] = {
                    'max': float(limite[1]),
                    'min': float(limite[2])
                }
            
            return jsonify({
                'status': 'sucesso',
                'config': {
                    'intervalo_leitura': intervalo,
                    'limites': limites_dict
                }
            }), 200
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def criar_localizacao(cursor, localizacao_info):
    """Cria ou obtém localização"""
    nome = localizacao_info.get('nome', 'Localização Padrão')
    
    cursor.execute("SELECT id FROM localizacoes WHERE nome = %s", (nome,))
    existente = cursor.fetchone()
    
    if existente:
        return existente['id']
    
    cursor.execute("""
        INSERT INTO localizacoes (nome, tipo, descricao)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (
        nome,
        localizacao_info.get('tipo', 'estufa'),
        localizacao_info.get('descricao', '')
    ))
    
    return cursor.fetchone()['id']

def criar_limites_temperatura(cursor, localizacao_id):
    """Cria limites padrão de temperatura"""
    limites_padrao = [
        ('agua', 30.0, 20.0),
        ('estufa', 35.0, 25.0),
        ('externa', 40.0, 15.0),
        ('solo', 30.0, 18.0),
        ('ar', 28.0, 22.0)
    ]
    
    for tipo, maximo, minimo in limites_padrao:
        cursor.execute("""
            INSERT INTO limites_temperatura (localizacao_id, tipo_sensor, maximo, minimo)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (localizacao_id, tipo_sensor) DO NOTHING
        """, (localizacao_id, tipo, maximo, minimo))

def buscar_config_datalogger(cursor, dispositivo_id):
    """Busca configurações completas do datalogger"""
    config = {
        'intervalo_leitura': 60,
        'limites': {},
        'ventilador': {
            'manual': False,
            'estado': False
        }
    }
    
    # Buscar limites
    cursor.execute("""
        SELECT lt.tipo_sensor, lt.maximo, lt.minimo
        FROM limites_temperatura lt
        JOIN dispositivos d ON d.localizacao_id = lt.localizacao_id
        WHERE d.id = %s
    """, (dispositivo_id,))
    
    for limite in cursor.fetchall():
        config['limites'][limite['tipo_sensor']] = {
            'max': float(limite['maximo']),
            'min': float(limite['minimo'])
        }
    
    return config

def processar_leitura_sensor(cursor, datalogger_id, dado):
    """Processa uma leitura de sensor"""
    sensor_endereco = dado.get('sensor_endereco', '')
    valor = dado.get('valor')
    timestamp_str = dado.get('timestamp')
    
    if not sensor_endereco or valor is None:
        return
    
    cursor.execute("""
        SELECT id FROM sensores 
        WHERE endereco = %s AND datalogger_id = %s
    """, (sensor_endereco, datalogger_id))
    
    sensor = cursor.fetchone()
    if sensor:
        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')) if timestamp_str else datetime.now()
        cursor.execute("""
            INSERT INTO leituras_sensores (sensor_id, valor, timestamp)
            VALUES (%s, %s, %s)
        """, (sensor['id'], float(valor), timestamp))









# ============================================
# ROTAS DA API PARA ALIMENTADOR
# ============================================

@app.route('/api/equipamento/status', methods=['POST'])
def atualizar_status_equipamento():
    """
    Recebe status do equipamento (heartbeat).
    O campo 'online' vindo do ESP32 é ignorado.
    """

    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400

        data = request.get_json()
        mac_address = data.get('mac', '').strip().upper()

        if not mac_address:
            return jsonify({'error': 'MAC address é obrigatório'}), 400

        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500

        try:
            with conn.cursor() as cursor:

                # =========================
                # 1) Buscar dispositivo
                # =========================
                cursor.execute("""
                    SELECT d.id, a.id as alimentador_id, a.capacidade_racao, d.online
                    FROM dispositivos d
                    JOIN alimentadores a ON d.id = a.dispositivo_id
                    WHERE d.mac_address = %s AND d.tipo = 'alimentador'
                """, (mac_address,))

                resultado = cursor.fetchone()

                if not resultado:
                    return jsonify({'error': 'Alimentador não encontrado'}), 404

                dispositivo_id, alimentador_id, capacidade, estava_online = resultado

                agora = datetime.now()

                # =========================
                # 2) Atualizar heartbeat
                # =========================
                cursor.execute("""
                    UPDATE dispositivos
                    SET online = TRUE,
                        ultima_comunicacao = %s
                    WHERE id = %s
                """, (agora, dispositivo_id))

                # =========================
                # 3) Atualizar dados operacionais
                # =========================
                nivel_racao = data.get('nivel_racao')
                motor_ligado = data.get('motor_ligado')

                if nivel_racao is not None:
                    cursor.execute("""
                        UPDATE alimentadores
                        SET nivel_racao_atual = %s,
                            motor_ligado = %s
                        WHERE id = %s
                    """, (nivel_racao, motor_ligado or False, alimentador_id))

                    # =========================
                    # 4) Verificar nível de ração
                    # =========================
                    percentual = (nivel_racao / capacidade) * 100 if capacidade > 0 else 0

                    # Verificar último alerta similar (evitar spam)
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
                                f'Nível de ração CRÍTICO: {nivel_racao:.0f}g ({percentual:.0f}%)',
                                agora
                            ))

                        elif percentual < 20:
                            cursor.execute("""
                                INSERT INTO alertas 
                                (dispositivo_id, tipo, severidade, mensagem, timestamp)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (
                                dispositivo_id, 'racao', 'medio',
                                f'Nível de ração BAIXO: {nivel_racao:.0f}g ({percentual:.0f}%)',
                                agora
                            ))

                # =========================
                # 5) Histórico (opcional mas recomendado)
                # =========================
                cursor.execute("""
                    INSERT INTO historico_status 
                    (dispositivo_id, nivel_racao, motor_ligado, timestamp)
                    VALUES (%s, %s, %s, %s)
                """, (
                    dispositivo_id,
                    nivel_racao,
                    motor_ligado or False,
                    agora
                ))

                conn.commit()

                return jsonify({
                    'status': 'sucesso',
                    'mensagem': 'Status atualizado com sucesso',
                    'timestamp': agora.isoformat()
                }), 200

        except Exception as e:
            conn.rollback()
            print(f"❌ Erro interno: {e}")
            return jsonify({'error': str(e)}), 500

        finally:
            conn.close()

    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/equipamento/config', methods=['GET'])
def obter_config_equipamento():
    """
    Retorna configurações atuais do equipamento
    Parâmetros: mac_address
    """
    try:
        mac_address = request.args.get('mac_address', '').strip().upper()
        
        if not mac_address:
            return jsonify({'error': 'mac_address é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Buscar dispositivo e alimentador
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
                
                # Buscar configuração
                cursor.execute("""
                    SELECT ativa, horario_inicio, horario_fim, 
                           intervalo_alimentacao, quantidade_por_alimentacao, dias_semana
                    FROM config_alimentadores
                    WHERE alimentador_id = %s
                """, (dispositivo['alimentador_id'],))
                
                config = cursor.fetchone()
                
                # Buscar calibração
                cursor.execute("""
                    SELECT constante_a, constante_b, tempo_acionamento
                    FROM calibracao_alimentadores
                    WHERE alimentador_id = %s
                """, (dispositivo['alimentador_id'],))
                
                calibracao = cursor.fetchone()
                
                # Buscar comandos pendentes
                cursor.execute("""
                    SELECT comando, parametros, id
                    FROM comandos_pendentes
                    WHERE mac_address = %s AND executado = false
                    ORDER BY criado_em ASC
                """, (mac_address,))
                
                comandos_pendentes = cursor.fetchall()
                
                # Preparar resposta
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
                        'tempo_acionamento': calibracao['tempo_acionamento']
                    }
                
                if comandos_pendentes:
                    resposta['comandos_pendentes'] = []
                    for cmd in comandos_pendentes:
                        resposta['comandos_pendentes'].append({
                            'id': cmd['id'],
                            'comando': cmd['comando'],
                            'parametros': cmd['parametros']
                        })
                
                return jsonify(resposta), 200
                
        except Exception as e:
            print(f"❌ Erro ao buscar configuração: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/equipamento/comando', methods=['POST'])
def enviar_comando_alimentador():
    """
    Envia comando para o alimentador
    Formato esperado:
    {
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "comando": "alimentar",
        "parametros": {
            "peso": 50.0,
            "tempo": 5.0
        }
    }
    
    Comandos suportados:
    - alimentar: Aciona o motor (parâmetros: peso OU tempo)
    - calibrar: Inicia calibração (parâmetros: tempo1, tempo2)
    - parar: Para o motor imediatamente
    - configurar: Atualiza configurações
    - reset: Reinicia o equipamento
    """
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        mac_address = data.get('mac_address', '').strip().upper()
        comando = data.get('comando', '').lower()
        parametros = data.get('parametros', {})
        
        if not mac_address or not comando:
            return jsonify({'error': 'mac_address e comando são obrigatórios'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Verificar se o dispositivo existe
                cursor.execute("""
                    SELECT d.id, a.id as alimentador_id
                    FROM dispositivos d
                    JOIN alimentadores a ON d.id = a.dispositivo_id
                    WHERE d.mac_address = %s AND d.tipo = 'alimentador'
                """, (mac_address,))
                
                dispositivo = cursor.fetchone()
                
                if not dispositivo:
                    return jsonify({'error': 'Alimentador não encontrado'}), 404
                
                # Validar comando
                comandos_validos = ['alimentar', 'calibrar', 'parar', 'configurar', 'reset']
                if comando not in comandos_validos:
                    return jsonify({'error': f'Comando inválido. Use: {", ".join(comandos_validos)}'}), 400
                
                # Processar cada tipo de comando
                if comando == 'alimentar':
                    # Verificar parâmetros
                    peso = parametros.get('peso', 0)
                    tempo = parametros.get('tempo', 0)
                    
                    if peso <= 0 and tempo <= 0:
                        return jsonify({'error': 'Informe peso (g) ou tempo (s) para alimentar'}), 400
                    
                    # Buscar constantes de calibração
                    cursor.execute("""
                        SELECT constante_a, constante_b
                        FROM calibracao_alimentadores
                        WHERE alimentador_id = %s
                    """, (dispositivo['alimentador_id'],))
                    
                    calibracao = cursor.fetchone()
                    
                    if calibracao:
                        constante_a = float(calibracao['constante_a'])
                        constante_b = float(calibracao['constante_b'])
                        
                        if peso > 0:
                            tempo_calculado = (peso * constante_a) + constante_b
                        else:
                            tempo_calculado = tempo
                            peso_calculado = (tempo - constante_b) / constante_a if constante_a != 0 else 0
                    else:
                        tempo_calculado = tempo if tempo > 0 else 5.0
                    
                    # Criar comando pendente
                    cursor.execute("""
                        INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (
                        mac_address,
                        'alimentar',
                        json.dumps({'tempo': tempo_calculado, 'peso': peso}),
                        session.get('usuario_id')
                    ))
                    
                    comando_id = cursor.fetchone()['id']
                    
                    mensagem = f'Comando de alimentação enviado: {tempo_calculado:.2f}s'
                    if peso > 0:
                        mensagem += f' ({peso}g)'
                    
                elif comando == 'calibrar':
                    tempo1 = parametros.get('tempo1', 0)
                    tempo2 = parametros.get('tempo2', 0)
                    
                    if tempo1 <= 0 or tempo2 <= 0:
                        return jsonify({'error': 'Informe tempo1 e tempo2 para calibração'}), 400
                    
                    cursor.execute("""
                        INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (
                        mac_address,
                        'calibrar',
                        json.dumps({'tempo1': tempo1, 'tempo2': tempo2, 'etapa': 1}),
                        session.get('usuario_id')
                    ))
                    
                    comando_id = cursor.fetchone()['id']
                    mensagem = f'Comando de calibração enviado (tempo1={tempo1}s, tempo2={tempo2}s)'
                    
                elif comando == 'parar':
                    cursor.execute("""
                        INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (
                        mac_address,
                        'parar',
                        '{}',
                        session.get('usuario_id')
                    ))
                    
                    comando_id = cursor.fetchone()['id']
                    mensagem = 'Comando de parada enviado'
                    
                elif comando == 'configurar':
                    # Atualizar configurações diretamente no banco
                    config = parametros.get('configuracao', {})
                    
                    if config:
                        update_fields = []
                        values = []
                        
                        if 'ativa' in config:
                            update_fields.append("ativa = %s")
                            values.append(config['ativa'])
                        if 'horario_inicio' in config:
                            update_fields.append("horario_inicio = %s")
                            values.append(config['horario_inicio'])
                        if 'horario_fim' in config:
                            update_fields.append("horario_fim = %s")
                            values.append(config['horario_fim'])
                        if 'intervalo_alimentacao' in config:
                            update_fields.append("intervalo_alimentacao = %s")
                            values.append(config['intervalo_alimentacao'])
                        if 'quantidade_por_alimentacao' in config:
                            update_fields.append("quantidade_por_alimentacao = %s")
                            values.append(config['quantidade_por_alimentacao'])
                        if 'dias_semana' in config:
                            update_fields.append("dias_semana = %s")
                            values.append(config['dias_semana'])
                        
                        if update_fields:
                            values.append(dispositivo['alimentador_id'])
                            query = f"""
                                UPDATE config_alimentadores 
                                SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                                WHERE alimentador_id = %s
                            """
                            cursor.execute(query, values)
                    
                    # Calibração
                    calib = parametros.get('calibracao', {})
                    if calib:
                        update_fields = []
                        values = []
                        
                        if 'constante_a' in calib:
                            update_fields.append("constante_a = %s")
                            values.append(calib['constante_a'])
                        if 'constante_b' in calib:
                            update_fields.append("constante_b = %s")
                            values.append(calib['constante_b'])
                        if 'tempo_acionamento' in calib:
                            update_fields.append("tempo_acionamento = %s")
                            values.append(calib['tempo_acionamento'])
                        
                        if update_fields:
                            values.append(dispositivo['alimentador_id'])
                            query = f"""
                                UPDATE calibracao_alimentadores 
                                SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                                WHERE alimentador_id = %s
                            """
                            cursor.execute(query, values)
                    
                    # Enviar comando para o ESP32 atualizar
                    cursor.execute("""
                        INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (
                        mac_address,
                        'configurar',
                        json.dumps({'recarregar': True}),
                        session.get('usuario_id')
                    ))
                    
                    conn.commit()
                    mensagem = 'Configurações atualizadas com sucesso'
                    
                elif comando == 'reset':
                    cursor.execute("""
                        INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                        VALUES (%s, %s, %s, %s)
                        RETURNING id
                    """, (
                        mac_address,
                        'reset',
                        '{}',
                        session.get('usuario_id')
                    ))
                    
                    comando_id = cursor.fetchone()['id']
                    mensagem = 'Comando de reset enviado'
                
                conn.commit()
                
                # Registrar log
                if 'usuario_id' in session:
                    db.registrar_log(
                        session['usuario_id'],
                        'ENVIAR_COMANDO',
                        f'Comando {comando} enviado para {mac_address}',
                        request.remote_addr,
                        request.user_agent.string
                    )
                
                return jsonify({
                    'status': 'sucesso',
                    'mensagem': mensagem,
                    'comando_id': comando_id if 'comando_id' in locals() else None,
                    'timestamp': datetime.now().isoformat()
                }), 200
                
        except Exception as e:
            print(f"❌ Erro ao enviar comando: {e}")
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/equipamento/comandos', methods=['GET'])
def obter_comandos_pendentes():
    """
    Retorna comandos pendentes para o equipamento
    Parâmetros: mac_address
    """
    try:
        mac_address = request.args.get('mac_address', '').strip().upper()
        
        if not mac_address:
            return jsonify({'error': 'mac_address é obrigatório'}), 400
        
        print(f"🔍 Buscando comandos para MAC: {mac_address}")
        
        conn = db.get_connection()
        if not conn:
            print("❌ Erro de conexão com o banco")
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        try:
            with conn.cursor() as cursor:
                # Primeiro, verificar se a tabela existe
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'comandos_pendentes'
                    )
                """)
                tabela_existe = cursor.fetchone()[0]
                
                if not tabela_existe:
                    print("⚠️ Tabela comandos_pendentes não existe")
                    return jsonify({
                        'status': 'sucesso',
                        'comandos': [],
                        'quantidade': 0,
                        'mensagem': 'Tabela de comandos não disponível'
                    }), 200
                
                # Buscar comandos pendentes
                cursor.execute("""
                    SELECT id, comando, parametros, criado_em
                    FROM comandos_pendentes
                    WHERE mac_address = %s AND executado = false
                    ORDER BY criado_em ASC
                    LIMIT 10
                """, (mac_address,))
                
                comandos_raw = cursor.fetchall()
                
                # Marcar como executados
                for cmd in comandos_raw:
                    cursor.execute("""
                        UPDATE comandos_pendentes 
                        SET executado = true, executado_em = NOW()
                        WHERE id = %s
                    """, (cmd[0],))
                
                conn.commit()
                
                # Formatar resposta
                comandos_lista = []
                for cmd in comandos_raw:
                    # Parse dos parâmetros JSON
                    parametros = {}
                    if cmd[2]:
                        try:
                            import json
                            if isinstance(cmd[2], str):
                                parametros = json.loads(cmd[2])
                            else:
                                parametros = cmd[2]
                        except:
                            parametros = {}
                    
                    comandos_lista.append({
                        'id': cmd[0],
                        'comando': cmd[1],
                        'parametros': parametros,
                        'criado_em': cmd[3].isoformat() if cmd[3] else None
                    })
                
                print(f"✅ {len(comandos_lista)} comando(s) encontrado(s)")
                
                return jsonify({
                    'status': 'sucesso',
                    'comandos': comandos_lista,
                    'quantidade': len(comandos_lista),
                    'timestamp': datetime.now().isoformat()
                }), 200
                
        except Exception as e:
            print(f"❌ Erro ao buscar comandos: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/equipamento/historico', methods=['GET'])
def obter_historico_alimentador():
    """
    Retorna histórico de alimentações do equipamento
    Parâmetros: mac_address, dias (opcional, padrão 7)
    """
    try:
        mac_address = request.args.get('mac_address', '').strip().upper()
        dias = int(request.args.get('dias', 7))
        
        if not mac_address:
            return jsonify({'error': 'mac_address é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Buscar alimentador
                cursor.execute("""
                    SELECT a.id
                    FROM dispositivos d
                    JOIN alimentadores a ON d.id = a.dispositivo_id
                    WHERE d.mac_address = %s AND d.tipo = 'alimentador'
                """, (mac_address,))
                
                alimentador = cursor.fetchone()
                
                if not alimentador:
                    return jsonify({'error': 'Alimentador não encontrado'}), 404
                
                # Buscar histórico dos últimos N dias
                cursor.execute("""
                    SELECT id, quantidade_racao, tempo_acionamento, 
                           timestamp, modo, created_at
                    FROM historico_alimentacao
                    WHERE alimentador_id = %s
                      AND timestamp >= CURRENT_DATE - INTERVAL '%s days'
                    ORDER BY timestamp DESC
                    LIMIT 1000
                """, (alimentador['id'], dias))
                
                historico = cursor.fetchall()
                
                # Calcular estatísticas
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_eventos,
                        SUM(quantidade_racao) as total_racao,
                        AVG(quantidade_racao) as media_por_alimentacao,
                        MIN(timestamp) as primeira,
                        MAX(timestamp) as ultima
                    FROM historico_alimentacao
                    WHERE alimentador_id = %s
                      AND timestamp >= CURRENT_DATE - INTERVAL '%s days'
                """, (alimentador['id'], dias))
                
                estatisticas = cursor.fetchone()
                
                # Formatar histórico
                historico_lista = []
                for item in historico:
                    historico_lista.append({
                        'id': item['id'],
                        'quantidade_racao': float(item['quantidade_racao']),
                        'tempo_acionamento': item['tempo_acionamento'],
                        'timestamp': item['timestamp'].isoformat() if item['timestamp'] else None,
                        'modo': item['modo']
                    })
                
                return jsonify({
                    'status': 'sucesso',
                    'historico': historico_lista,
                    'estatisticas': {
                        'total_eventos': estatisticas['total_eventos'] if estatisticas else 0,
                        'total_racao': float(estatisticas['total_racao']) if estatisticas and estatisticas['total_racao'] else 0,
                        'media_por_alimentacao': float(estatisticas['media_por_alimentacao']) if estatisticas and estatisticas['media_por_alimentacao'] else 0,
                        'periodo_inicio': estatisticas['primeira'].isoformat() if estatisticas and estatisticas['primeira'] else None,
                        'periodo_fim': estatisticas['ultima'].isoformat() if estatisticas and estatisticas['ultima'] else None
                    },
                    'dias': dias,
                    'timestamp': datetime.now().isoformat()
                }), 200
                
        except Exception as e:
            print(f"❌ Erro ao buscar histórico: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/equipamento/calibracao', methods=['POST'])
def registrar_calibracao():
    """
    Registra os resultados da calibração enviados pelo ESP32
    Formato esperado:
    {
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "constante_a": 0.105,
        "constante_b": 0.0,
        "tempo_acionamento": 1050,
        "peso1": 100,
        "peso2": 200,
        "tempo1": 10.5,
        "tempo2": 21.0
    }
    """
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        mac_address = data.get('mac_address', '').strip().upper()
        
        if not mac_address:
            return jsonify({'error': 'MAC address é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        try:
            with conn.cursor() as cursor:
                # Buscar alimentador
                cursor.execute("""
                    SELECT a.id
                    FROM dispositivos d
                    JOIN alimentadores a ON d.id = a.dispositivo_id
                    WHERE d.mac_address = %s AND d.tipo = 'alimentador'
                """, (mac_address,))
                
                resultado = cursor.fetchone()
                
                if not resultado:
                    return jsonify({'error': 'Alimentador não encontrado'}), 404
                
                alimentador_id = resultado[0]
                
                # Atualizar calibração
                constante_a = data.get('constante_a')
                constante_b = data.get('constante_b')
                tempo_acionamento = data.get('tempo_acionamento')
                
                update_fields = []
                values = []
                
                if constante_a is not None:
                    update_fields.append("constante_a = %s")
                    values.append(constante_a)
                if constante_b is not None:
                    update_fields.append("constante_b = %s")
                    values.append(constante_b)
                if tempo_acionamento is not None:
                    update_fields.append("tempo_acionamento = %s")
                    values.append(tempo_acionamento)
                
                if update_fields:
                    update_fields.append("calibrado_em = %s")
                    values.append(datetime.now())
                    values.append(alimentador_id)
                    
                    query = f"""
                        UPDATE calibracao_alimentadores 
                        SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                        WHERE alimentador_id = %s
                    """
                    cursor.execute(query, values)
                
                # Registrar histórico da calibração
                cursor.execute("""
                    INSERT INTO logs_sistema (acao, descricao, created_at)
                    VALUES (%s, %s, %s)
                """, (
                    'CALIBRACAO',
                    f'Calibração realizada para MAC {mac_address}: A={constante_a}, B={constante_b}',
                    datetime.now()
                ))
                
                conn.commit()
                
                return jsonify({
                    'status': 'sucesso',
                    'mensagem': 'Calibração registrada com sucesso',
                    'timestamp': datetime.now().isoformat()
                }), 200
                
        except Exception as e:
            print(f"❌ Erro ao registrar calibração: {e}")
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return jsonify({'error': str(e)}), 500






# ============================================
# SISTEMA DE HEARTBEAT E DETECÇÃO DE OFFLINE
# ============================================

@app.route('/api/equipamento/heartbeat', methods=['POST'])
def heartbeat_equipamento():
    """
    Recebe heartbeat do equipamento para manter status online
    """
    print("\n💓 HEARTBEAT RECEBIDO")
    
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        mac_address = data.get('mac', '').strip().upper()
        
        if not mac_address:
            # Tentar pegar de outra chave
            mac_address = data.get('mac_address', '').strip().upper()
        
        if not mac_address:
            return jsonify({'error': 'MAC address é obrigatório'}), 400
        
        print(f"   MAC: {mac_address}")
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            # Verificar se o dispositivo existe
            cursor.execute("""
                SELECT id, tipo FROM dispositivos 
                WHERE mac_address = %s
            """, (mac_address,))
            
            dispositivo = cursor.fetchone()
            
            if not dispositivo:
                print(f"   ❌ Equipamento não encontrado: {mac_address}")
                return jsonify({'error': 'Equipamento não encontrado'}), 404
            
            dispositivo_id, tipo = dispositivo
            agora = datetime.now()
            
            print(f"   ✅ Equipamento encontrado: ID {dispositivo_id}, Tipo: {tipo}")
            
            # Atualizar online e última comunicação
            cursor.execute("""
                UPDATE dispositivos 
                SET online = true, ultima_comunicacao = %s
                WHERE id = %s
            """, (agora, dispositivo_id))
            
            conn.commit()
            
            print(f"   ✅ Status atualizado: online=true, ultima_comunicacao={agora}")
            
            return jsonify({
                'status': 'sucesso',
                'mensagem': 'Heartbeat registrado',
                'timestamp': agora.isoformat()
            }), 200
            
    except Exception as e:
        print(f"❌ Erro no heartbeat: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/equipamento/status/<int:equipamento_id>', methods=['GET'])
@login_required
def obter_status_equipamento_id(equipamento_id):
    """Retorna o status atual de um equipamento"""
    try:
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT d.id, d.nome, d.tipo, d.online, d.ultima_comunicacao,
                       EXTRACT(EPOCH FROM (NOW() - d.ultima_comunicacao)) as segundos_desde_ultima
                FROM dispositivos d
                WHERE d.id = %s
            """, (equipamento_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'error': 'Equipamento não encontrado'}), 404
            
            segundos_offline = row[5] if row[5] else None
            
            # Se passou mais de 2 minutos sem comunicação, considerar offline
            if segundos_offline and segundos_offline > 120:
                # Atualizar para offline
                cursor.execute("""
                    UPDATE dispositivos SET online = false WHERE id = %s
                """, (equipamento_id,))
                conn.commit()
                online = False
            else:
                online = row[3]
            
            return jsonify({
                'status': 'sucesso',
                'equipamento': {
                    'id': row[0],
                    'nome': row[1],
                    'tipo': row[2],
                    'online': online,
                    'ultima_comunicacao': row[4].isoformat() if row[4] else None,
                    'segundos_offline': int(segundos_offline) if segundos_offline else 0
                }
            }), 200
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

@app.route('/api/equipamento/verificar-offline', methods=['GET'])
def verificar_equipamentos_offline():
    """
    Verifica equipamentos que não enviaram heartbeat nos últimos X segundos
    (Pode ser chamado por um scheduler ou cron job)
    """
    try:
        # Tempo limite para considerar offline (padrão: 2 minutos)
        timeout_minutos = int(request.args.get('timeout', 2))
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        try:
            with conn.cursor() as cursor:
                # Buscar equipamentos que deveriam estar online mas não respondem
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = false
                    WHERE online = true 
                      AND ultima_comunicacao < NOW() - INTERVAL '%s minutes'
                    RETURNING id, mac_address, nome
                """, (timeout_minutos,))
                
                equipamentos_offline = cursor.fetchall()
                
                conn.commit()
                
                # Gerar alertas para equipamentos que ficaram offline
                alertas_gerados = []
                for eq in equipamentos_offline:
                    eq_id, mac, nome = eq
                    
                    # Verificar se já existe alerta recente para este equipamento
                    cursor.execute("""
                        SELECT id FROM alertas 
                        WHERE dispositivo_id = %s 
                          AND tipo = 'comunicacao'
                          AND resolvido = false
                          AND timestamp > NOW() - INTERVAL '1 hour'
                    """, (eq_id,))
                    
                    alerta_existente = cursor.fetchone()
                    
                    if not alerta_existente:
                        # Criar alerta de comunicação
                        cursor.execute("""
                            INSERT INTO alertas (dispositivo_id, tipo, severidade, mensagem, timestamp)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            eq_id, 'comunicacao', 'alto',
                            f'Equipamento {nome} ({mac}) está OFFLINE. Última comunicação há mais de {timeout_minutos} minutos.',
                            datetime.now()
                        ))
                        alertas_gerados.append(mac)
                
                conn.commit()
                
                return jsonify({
                    'status': 'sucesso',
                    'equipamentos_offline': len(equipamentos_offline),
                    'alertas_gerados': alertas_gerados,
                    'timestamp': datetime.now().isoformat()
                }), 200
                
        except Exception as e:
            print(f"❌ Erro ao verificar offline: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            conn.close()
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        return jsonify({'error': str(e)}), 500


# Função para ser chamada periodicamente (usando APScheduler)
# Instale: pip install apscheduler

from apscheduler.schedulers.background import BackgroundScheduler
def verificar_equipamentos_offline_auto():
    """Versão automática que verifica equipamentos offline"""
    try:
        timeout_minutos = 2  # 2 minutos sem heartbeat = offline
        
        conn = db.get_connection()
        if not conn:
            return
        
        try:
            with conn.cursor() as cursor:
                # Buscar equipamentos que deveriam estar online mas não respondem
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = false
                    WHERE online = true 
                      AND ultima_comunicacao < NOW() - INTERVAL '%s minutes'
                    RETURNING id, mac_address, nome, tipo
                """, (timeout_minutos,))
                
                equipamentos_offline = cursor.fetchall()
                
                if equipamentos_offline:
                    print(f"🔴 {len(equipamentos_offline)} equipamento(s) ficaram offline:")
                    for eq in equipamentos_offline:
                        print(f"   - {eq[2]} ({eq[3]}) - MAC: {eq[1]}")
                    
                    conn.commit()
                
        except Exception as e:
            print(f"❌ Erro no verificador automático: {e}")
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Erro geral no verificador: {e}")

# Iniciar verificador em background (adicione no final do arquivo, antes do if __name__)
def iniciar_verificador_offline():
    """Inicia o scheduler para verificar equipamentos offline"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=verificar_equipamentos_offline_auto, trigger="interval", seconds=60)
        scheduler.start()
        print("✅ Verificador de equipamentos offline iniciado (a cada 60 segundos)")
    except ImportError:
        print("⚠️ APScheduler não instalado. Instale com: pip install apscheduler")
    except Exception as e:
        print(f"⚠️ Erro ao iniciar verificador: {e}")

# Adicione esta rota para consultar status de um equipamento específico
@app.route('/api/equipamento/status/<mac_address>', methods=['GET'])
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
                
                # Calcular status
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

# ============================================
# ROTAS DE CONFIGURAÇÕES
# ============================================

@app.route('/configuracoes')
@app.route('/configuracoes/')
@login_required
def configuracoes():
    """Página principal de configurações - lista equipamentos"""
    try:
        conn = db.get_connection()
        if not conn:
            flash('Erro de conexão com o banco de dados', 'danger')
            return render_template('configuracoes.html', alimentadores=[], dataloggers=[])
        
        with conn.cursor() as cursor:
            # ============================================
            # DEBUG: Verificar quantos dataloggers existem
            # ============================================
            cursor.execute("SELECT COUNT(*) FROM dispositivos WHERE tipo = 'datalogger'")
            count_dataloggers = cursor.fetchone()[0]
            print(f"🔍 Total de dataloggers na tabela dispositivos: {count_dataloggers}")
            
            # ============================================
            # 1. BUSCAR ALIMENTADORES
            # ============================================
            if session['usuario_tipo'] == 'admin':
                cursor.execute("""
                    SELECT 
                        d.id, d.nome, d.mac_address, d.online, d.ultima_comunicacao,
                        l.nome as localizacao_nome,
                        a.capacidade_racao, a.nivel_racao_atual,
                        ca.ativa, ca.porcoes_por_dia
                    FROM dispositivos d
                    JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN config_alimentadores ca ON a.id = ca.alimentador_id
                    WHERE d.tipo = 'alimentador'
                    ORDER BY d.nome
                """)
            else:
                cursor.execute("""
                    SELECT 
                        d.id, d.nome, d.mac_address, d.online, d.ultima_comunicacao,
                        l.nome as localizacao_nome,
                        a.capacidade_racao, a.nivel_racao_atual,
                        ca.ativa, ca.porcoes_por_dia
                    FROM dispositivos d
                    JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN config_alimentadores ca ON a.id = ca.alimentador_id
                    WHERE d.tipo = 'alimentador' AND ul.usuario_id = %s
                    ORDER BY d.nome
                """, (session['usuario_id'],))
            
            alimentadores_raw = cursor.fetchall()
            
            # Converter para lista de dicionários
            alimentadores = []
            colunas_alimentadores = ['id', 'nome', 'mac_address', 'online', 'ultima_comunicacao',
                                     'localizacao_nome', 'capacidade_racao', 'nivel_racao_atual',
                                     'ativa', 'porcoes_por_dia']
            
            for row in alimentadores_raw:
                alm = dict(zip(colunas_alimentadores, row))
                if alm['capacidade_racao']:
                    alm['capacidade_racao'] = float(alm['capacidade_racao'])
                if alm['nivel_racao_atual']:
                    alm['nivel_racao_atual'] = float(alm['nivel_racao_atual'])
                alimentadores.append(alm)
            
            print(f"✅ Alimentadores encontrados: {len(alimentadores)}")
            
            # ============================================
            # 2. BUSCAR DATALOGGERS - VERSÃO CORRIGIDA
            # ============================================
            # Primeiro, buscar todos os dispositivos do tipo datalogger
            if session['usuario_tipo'] == 'admin':
                cursor.execute("""
                    SELECT 
                        d.id, d.nome, d.mac_address, d.online, d.ultima_comunicacao,
                        d.descricao, d.modelo,
                        l.id as localizacao_id, l.nome as localizacao_nome,
                        dl.intervalo_leitura, dl.quantidade_sensores
                    FROM dispositivos d
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    WHERE d.tipo = 'datalogger'
                    ORDER BY d.nome
                """)
            else:
                cursor.execute("""
                    SELECT 
                        d.id, d.nome, d.mac_address, d.online, d.ultima_comunicacao,
                        d.descricao, d.modelo,
                        l.id as localizacao_id, l.nome as localizacao_nome,
                        dl.intervalo_leitura, dl.quantidade_sensores
                    FROM dispositivos d
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    WHERE d.tipo = 'datalogger' AND ul.usuario_id = %s
                    ORDER BY d.nome
                """, (session['usuario_id'],))
            
            dataloggers_raw = cursor.fetchall()
            print(f"🔍 Dataloggers raw encontrados: {len(dataloggers_raw)}")
            
            # Converter para lista de dicionários
            colunas_dataloggers = ['id', 'nome', 'mac_address', 'online', 'ultima_comunicacao',
                                   'descricao', 'modelo', 'localizacao_id', 'localizacao_nome',
                                   'intervalo_leitura', 'quantidade_sensores']
            
            dataloggers = []
            for row in dataloggers_raw:
                dg = dict(zip(colunas_dataloggers, row))
                print(f"  - Processando datalogger: {dg.get('nome')} (ID: {dg.get('id')})")
                
                # Buscar últimos valores dos sensores
                if dg.get('id'):
                    cursor.execute("""
                        SELECT s.posicao, ls.valor, ls.timestamp
                        FROM leituras_sensores ls
                        JOIN sensores s ON ls.sensor_id = s.id
                        JOIN dataloggers dl ON s.datalogger_id = dl.id
                        WHERE dl.dispositivo_id = %s
                        ORDER BY ls.timestamp DESC
                        LIMIT 3
                    """, (dg['id'],))
                    
                    sensores_raw = cursor.fetchall()
                    sensores = []
                    dg['ultima_leitura'] = None
                    
                    for s in sensores_raw:
                        sensores.append({
                            'posicao': s[0],
                            'ultima_leitura': float(s[1]) if s[1] else None
                        })
                        if not dg['ultima_leitura'] and s[2]:
                            if hasattr(s[2], 'strftime'):
                                dg['ultima_leitura'] = s[2].strftime('%d/%m/%Y %H:%M:%S')
                            else:
                                dg['ultima_leitura'] = str(s[2])
                    
                    dg['sensores'] = sensores
                    
                    # Contar total de leituras
                    cursor.execute("""
                        SELECT COUNT(*) as total
                        FROM leituras_sensores ls
                        JOIN sensores s ON ls.sensor_id = s.id
                        JOIN dataloggers dl ON s.datalogger_id = dl.id
                        WHERE dl.dispositivo_id = %s
                    """, (dg['id'],))
                    
                    total_row = cursor.fetchone()
                    dg['total_leituras'] = total_row[0] if total_row else 0
                else:
                    dg['sensores'] = []
                    dg['total_leituras'] = 0
                
                dataloggers.append(dg)
            
            print(f"✅ Dataloggers processados: {len(dataloggers)}")
        
        conn.close()
        
        return render_template('configuracoes.html', 
                             alimentadores=alimentadores,
                             dataloggers=dataloggers,
                             usuario=session)
                             
    except Exception as e:
        print(f"❌ Erro na rota configuracoes: {e}")
        import traceback
        traceback.print_exc()
        flash(f'Erro ao carregar configurações: {str(e)}', 'danger')
        return render_template('configuracoes.html', alimentadores=[], dataloggers=[])


@app.route('/configuracoes/alimentador/<int:equipamento_id>')
@login_required
def configuracoes_alimentador(equipamento_id):
    """Página de configurações específica do alimentador"""
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('configuracoes'))
    
    try:
        with conn.cursor() as cursor:
            # Verificar permissão
            if session['usuario_tipo'] != 'admin':
                cursor.execute("""
                    SELECT 1 FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s
                """, (equipamento_id, session['usuario_id']))
                
                if not cursor.fetchone():
                    flash('Acesso negado a este equipamento', 'danger')
                    return redirect(url_for('configuracoes'))
            
            # Buscar dados completos do alimentador
            cursor.execute("""
                SELECT 
                    d.id, d.nome, d.mac_address, d.modelo, d.online,
                    l.id, l.nome,
                    a.id, a.capacidade_racao, a.vazao_media, a.nivel_racao_atual,
                    ca.id, ca.ativa, ca.horario_inicio, ca.horario_fim,
                    ca.porcoes_por_dia, ca.quantidade_total_diaria,
                    ca.intervalo_alimentacao, ca.quantidade_por_alimentacao, ca.dias_semana,
                    cal.id, cal.constante_a, cal.constante_b, cal.tempo_acionamento
                FROM dispositivos d
                JOIN localizacoes l ON d.localizacao_id = l.id
                JOIN alimentadores a ON d.id = a.dispositivo_id
                LEFT JOIN config_alimentadores ca ON a.id = ca.alimentador_id
                LEFT JOIN calibracao_alimentadores cal ON a.id = cal.alimentador_id
                WHERE d.id = %s AND d.tipo = 'alimentador'
            """, (equipamento_id,))
            
            resultado = cursor.fetchone()
            
            if not resultado:
                flash('Alimentador não encontrado', 'danger')
                return redirect(url_for('configuracoes'))
            
            # Converter para dicionário
            alimentador = {
                'id': resultado[0],
                'nome': resultado[1],
                'mac_address': resultado[2],
                'modelo': resultado[3],
                'online': resultado[4],
                'localizacao_id': resultado[5],
                'localizacao_nome': resultado[6],
                'alimentador_id': resultado[7],
                'capacidade_racao': float(resultado[8]) if resultado[8] else 0,
                'vazao_media': float(resultado[9]) if resultado[9] else 0,
                'nivel_racao_atual': float(resultado[10]) if resultado[10] else 0,
                'config_id': resultado[11],
                'ativa': resultado[12] if resultado[12] is not None else False,
                'horario_inicio': resultado[13].strftime('%H:%M') if resultado[13] else '08:00',
                'horario_fim': resultado[14].strftime('%H:%M') if resultado[14] else '18:00',
                'porcoes_por_dia': resultado[15] if resultado[15] is not None else 10,
                'quantidade_total_diaria': float(resultado[16]) if resultado[16] else 150.0,
                'intervalo_alimentacao': resultado[17] if resultado[17] else 3600,
                'quantidade_por_alimentacao': float(resultado[18]) if resultado[18] else 15.0,
                'dias_semana': resultado[19] if resultado[19] else '1,2,3,4,5,6,7',
                'calibracao_id': resultado[20],
                'constante_a': float(resultado[21]) if resultado[21] else 0.105,
                'constante_b': float(resultado[22]) if resultado[22] else 0.0,
                'tempo_acionamento': resultado[23] if resultado[23] else 1050
            }
            
            # Buscar histórico de calibração
            cursor.execute("""
                SELECT constante_a, constante_b, calibrado_em
                FROM calibracao_alimentadores
                WHERE alimentador_id = %s
                ORDER BY calibrado_em DESC
                LIMIT 5
            """, (alimentador['alimentador_id'],))
            
            historico_calibracao = []
            for row in cursor.fetchall():
                historico_calibracao.append({
                    'constante_a': float(row[0]) if row[0] else 0,
                    'constante_b': float(row[1]) if row[1] else 0,
                    'calibrado_em': row[2]
                })
            
            # Buscar últimas alimentações
            cursor.execute("""
                SELECT quantidade_racao, tempo_acionamento, timestamp, modo
                FROM historico_alimentacao
                WHERE alimentador_id = %s
                ORDER BY timestamp DESC
                LIMIT 10
            """, (alimentador['alimentador_id'],))
            
            ultimas_alimentacoes = []
            for row in cursor.fetchall():
                ultimas_alimentacoes.append({
                    'quantidade_racao': float(row[0]) if row[0] else 0,
                    'tempo_acionamento': float(row[1]) if row[1] else 0,
                    'timestamp': row[2],
                    'modo': row[3] if row[3] else 'automatico'
                })
            
    except Exception as e:
        print(f"❌ Erro ao buscar configurações: {e}")
        import traceback
        traceback.print_exc()
        flash('Erro ao carregar configurações', 'danger')
        return redirect(url_for('configuracoes'))
    finally:
        conn.close()
    
    return render_template('configuracoes_alimentador.html',
                         alimentador=alimentador,
                         historico_calibracao=historico_calibracao,
                         ultimas_alimentacoes=ultimas_alimentacoes,
                         usuario=session)


@app.route('/api/configuracoes/alimentador/<int:alimentador_id>', methods=['PUT'])
@login_required
def atualizar_config_alimentador(alimentador_id):
    """API para atualizar configurações do alimentador"""
    try:
        data = request.get_json()
        print(f"📥 Recebendo configurações para alimentador {alimentador_id}:")
        print(f"   {data}")
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            # Verificar permissão
            if session['usuario_tipo'] != 'admin':
                cursor.execute("""
                    SELECT 1 FROM alimentadores a
                    JOIN dispositivos d ON a.dispositivo_id = d.id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE a.id = %s AND ul.usuario_id = %s
                """, (alimentador_id, session['usuario_id']))
                
                if not cursor.fetchone():
                    return jsonify({'error': 'Acesso negado'}), 403
            
            # ============================================
            # 1. ATUALIZAR CONFIGURAÇÃO DO ALIMENTADOR
            # ============================================
            if 'configuracao' in data:
                config = data['configuracao']
                
                # Campos que o usuário informa
                ativa = config.get('ativa')
                horario_inicio = config.get('horario_inicio')
                horario_fim = config.get('horario_fim')
                porcoes_por_dia = config.get('porcoes_por_dia')
                quantidade_total_diaria = config.get('quantidade_total_diaria')
                dias_semana = config.get('dias_semana')
                
                # CORREÇÃO: Remover os segundos se existirem
                if horario_inicio and len(horario_inicio) > 5:
                    horario_inicio = horario_inicio[:5]  # Pega apenas "HH:MM"
                if horario_fim and len(horario_fim) > 5:
                    horario_fim = horario_fim[:5]        # Pega apenas "HH:MM"
                
                print(f"   Horários processados: inicio={horario_inicio}, fim={horario_fim}")
                
                # Calcular automaticamente os campos derivados
                quantidade_por_alimentacao = None
                intervalo_alimentacao = None
                
                if porcoes_por_dia and quantidade_total_diaria and porcoes_por_dia > 0:
                    quantidade_por_alimentacao = quantidade_total_diaria / porcoes_por_dia
                    
                    if horario_inicio and horario_fim:
                        from datetime import datetime
                        try:
                            inicio = datetime.strptime(horario_inicio, '%H:%M')
                            fim = datetime.strptime(horario_fim, '%H:%M')
                            minutos_total = (fim - inicio).seconds // 60
                            if minutos_total < 0:
                                minutos_total += 24 * 60
                            
                            if porcoes_por_dia > 1:
                                intervalo_minutos = minutos_total // (porcoes_por_dia - 1)
                            else:
                                intervalo_minutos = minutos_total
                            
                            intervalo_alimentacao = intervalo_minutos * 60
                            print(f"   Cálculo: minutos_total={minutos_total}, intervalo_minutos={intervalo_minutos}")
                        except Exception as e:
                            print(f"   Erro no cálculo do intervalo: {e}")
                            intervalo_alimentacao = 3600
                
                # Inserir ou atualizar configuração
                cursor.execute("""
                    INSERT INTO config_alimentadores (
                        alimentador_id, ativa, horario_inicio, horario_fim,
                        porcoes_por_dia, quantidade_total_diaria,
                        intervalo_alimentacao, quantidade_por_alimentacao, dias_semana,
                        updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (alimentador_id) DO UPDATE SET
                        ativa = EXCLUDED.ativa,
                        horario_inicio = EXCLUDED.horario_inicio,
                        horario_fim = EXCLUDED.horario_fim,
                        porcoes_por_dia = EXCLUDED.porcoes_por_dia,
                        quantidade_total_diaria = EXCLUDED.quantidade_total_diaria,
                        intervalo_alimentacao = EXCLUDED.intervalo_alimentacao,
                        quantidade_por_alimentacao = EXCLUDED.quantidade_por_alimentacao,
                        dias_semana = EXCLUDED.dias_semana,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    alimentador_id,
                    ativa,
                    horario_inicio,
                    horario_fim,
                    porcoes_por_dia,
                    quantidade_total_diaria,
                    intervalo_alimentacao,
                    quantidade_por_alimentacao,
                    dias_semana
                ))
                
                print(f"   ✅ Configuração salva: {porcoes_por_dia} porções/dia, {quantidade_total_diaria}g total")
            
            # ============================================
            # 2. ATUALIZAR CALIBRAÇÃO
            # ============================================
            if 'calibracao' in data:
                cal = data['calibracao']
                cursor.execute("""
                    INSERT INTO calibracao_alimentadores (
                        alimentador_id, constante_a, constante_b, tempo_acionamento, calibrado_em, updated_at
                    ) VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (alimentador_id) DO UPDATE SET
                        constante_a = EXCLUDED.constante_a,
                        constante_b = EXCLUDED.constante_b,
                        tempo_acionamento = EXCLUDED.tempo_acionamento,
                        calibrado_em = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    alimentador_id,
                    cal.get('constante_a'),
                    cal.get('constante_b'),
                    cal.get('tempo_acionamento')
                ))
                print("   ✅ Calibração salva")
            
            # ============================================
            # 3. ATUALIZAR ALIMENTADOR (dados físicos)
            # ============================================
            if 'alimentador' in data:
                alm = data['alimentador']
                cursor.execute("""
                    UPDATE alimentadores 
                    SET capacidade_racao = COALESCE(%s, capacidade_racao),
                        vazao_media = COALESCE(%s, vazao_media),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (
                    alm.get('capacidade_racao'),
                    alm.get('vazao_media'),
                    alimentador_id
                ))
                print("   ✅ Dados físicos salvos")
            
            conn.commit()
            
            # Enviar comando para o ESP32 recarregar configurações
            cursor.execute("""
                SELECT d.mac_address FROM dispositivos d
                JOIN alimentadores a ON d.id = a.dispositivo_id
                WHERE a.id = %s
            """, (alimentador_id,))
            
            mac_result = cursor.fetchone()
            if mac_result:
                mac_address = mac_result[0]
                cursor.execute("""
                    INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                    VALUES (%s, %s, %s, %s)
                """, (mac_address, 'configurar', '{"recarregar": true}', session['usuario_id']))
                print(f"   ✅ Comando enviado para ESP32: {mac_address}")
                conn.commit()
            
            return jsonify({
                'status': 'sucesso', 
                'mensagem': 'Configurações atualizadas com sucesso'
            }), 200
            
    except Exception as e:
        print(f"❌ Erro ao atualizar configurações: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/configuracoes/alimentador/<int:alimentador_id>/acionar', methods=['POST'])
@login_required
def acionar_alimentador(alimentador_id):
    """Aciona o alimentador manualmente"""
    try:
        data = request.get_json()
        peso = data.get('peso', 0)
        tempo = data.get('tempo', 0)
        
        if peso <= 0 and tempo <= 0:
            return jsonify({'error': 'Informe peso (g) ou tempo (s)'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            # Verificar permissão
            if session['usuario_tipo'] != 'admin':
                cursor.execute("""
                    SELECT 1 FROM alimentadores a
                    JOIN dispositivos d ON a.dispositivo_id = d.id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE a.id = %s AND ul.usuario_id = %s
                """, (alimentador_id, session['usuario_id']))
                
                if not cursor.fetchone():
                    return jsonify({'error': 'Acesso negado'}), 403
            
            # Buscar MAC e constantes
            cursor.execute("""
                SELECT d.mac_address, cal.constante_a, cal.constante_b
                FROM dispositivos d
                JOIN alimentadores a ON d.id = a.dispositivo_id
                JOIN calibracao_alimentadores cal ON a.id = cal.alimentador_id
                WHERE a.id = %s
            """, (alimentador_id,))
            
            resultado = cursor.fetchone()
            if not resultado:
                return jsonify({'error': 'Alimentador não encontrado'}), 404
            
            mac_address, constante_a, constante_b = resultado
            
            # Calcular tempo
            if peso > 0:
                tempo_calculado = (peso * constante_a) + constante_b
            else:
                tempo_calculado = tempo
            
            # Criar comando pendente
            cursor.execute("""
                INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                VALUES (%s, %s, %s, %s)
            """, (mac_address, 'alimentar', f'{{"tempo": {tempo_calculado}, "peso": {peso}}}', session['usuario_id']))
            
            conn.commit()
            
            return jsonify({
                'status': 'sucesso', 
                'mensagem': f'Comando enviado: {tempo_calculado:.2f} segundos',
                'tempo': tempo_calculado
            }), 200
            
    except Exception as e:
        print(f"❌ Erro ao acionar alimentador: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

# ============================================
# ROTAS ATUALIZADAS PARA DATALOGGER ESP32
# ============================================

@app.route('/api/datalogger/autocadastro', methods=['POST'])
def autocadastro_datalogger_esp32():
    """
    Autocadastro de datalogger ESP32
    Formato esperado:
    {
        "identificacao": {
            "mac": "AA:BB:CC:DD:EE:FF",
            "nome": "Datalogger ABC123",
            "tipo": "datalogger",
            "modelo": "ESP32",
            "versao_firmware": "1.0.0",
            "localizacao": {
                "nome": "Estufa Principal",
                "tipo": "estufa"
            },
            "sensores": [
                {"nome": "Sensor Água", "tipo": "temperatura", "posicao": "agua", "unidade": "°C", "endereco": "DS18B20_agua"},
                {"nome": "Sensor Estufa", "tipo": "temperatura", "posicao": "estufa", "unidade": "°C", "endereco": "DS18B20_estufa"},
                {"nome": "Sensor Externa", "tipo": "temperatura", "posicao": "externa", "unidade": "°C", "endereco": "DS18B20_externa"}
            ]
        }
    }
    """
    print("\n" + "="*60)
    print("🌡️ AUTOCADASTRO DATALOGGER ESP32")
    print("="*60)
    
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        
        if 'identificacao' not in data:
            return jsonify({'error': 'Campo "identificacao" é obrigatório'}), 400
        
        identificacao = data['identificacao']
        mac_address = identificacao.get('mac', '').strip().upper()
        
        if not mac_address:
            return jsonify({'error': 'MAC address é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Verificar se datalogger já existe
            cursor.execute("""
                SELECT d.id, d.nome, dl.id as datalogger_id
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.mac_address = %s AND d.tipo = 'datalogger'
            """, (mac_address,))
            
            existente = cursor.fetchone()
            
            if existente:
                print(f"✅ Datalogger já existe: {existente['nome']}")
                # Atualizar online status
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = true, ultima_comunicacao = %s
                    WHERE id = %s
                """, (datetime.now(), existente['id']))
                conn.commit()
                
                # Buscar configurações
                config = buscar_config_datalogger_simples(cursor, existente['id'])
                
                return jsonify({
                    'status': 'sucesso',
                    'mensagem': 'Datalogger já cadastrado',
                    'datalogger_id': existente['id'],
                    'config': config
                }), 200
            
            # Criar novo datalogger
            print(f"🆕 Criando novo datalogger: {mac_address}")
            
            # Criar localização
            localizacao_info = identificacao.get('localizacao', {})
            localizacao_nome = localizacao_info.get('nome', f'Local-{mac_address[-8:]}')
            localizacao_tipo = localizacao_info.get('tipo', 'estufa')
            
            # Verificar se localização já existe
            cursor.execute("SELECT id FROM localizacoes WHERE nome = %s", (localizacao_nome,))
            localizacao = cursor.fetchone()
            
            if localizacao:
                localizacao_id = localizacao['id']
            else:
                cursor.execute("""
                    INSERT INTO localizacoes (nome, tipo, descricao)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (localizacao_nome, localizacao_tipo, f'Localização automática para {mac_address}'))
                localizacao_id = cursor.fetchone()['id']
                
                # Associar ao admin
                cursor.execute("SELECT id FROM usuarios WHERE tipo = 'admin' LIMIT 1")
                admin = cursor.fetchone()
                if admin:
                    cursor.execute("""
                        INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING
                    """, (admin['id'], localizacao_id))
            
            # Criar dispositivo
            nome_equipamento = identificacao.get('nome', f'Datalogger {mac_address[-8:]}')
            cursor.execute("""
                INSERT INTO dispositivos (
                    localizacao_id, nome, descricao, mac_address,
                    tipo, modelo, versao_firmware, online, ultima_comunicacao
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                localizacao_id,
                nome_equipamento,
                f'Datalogger autocadastrado - MAC: {mac_address}',
                mac_address,
                'datalogger',
                identificacao.get('modelo', 'ESP32'),
                identificacao.get('versao_firmware', '1.0.0'),
                True,
                datetime.now()
            ))
            
            dispositivo_id = cursor.fetchone()['id']
            
            # Criar datalogger
            cursor.execute("""
                INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (dispositivo_id, 3, 60))
            
            datalogger_id = cursor.fetchone()['id']
            
            # Criar sensores
            sensores_info = identificacao.get('sensores', [])
            if not sensores_info:
                # Sensores padrão
                sensores_info = [
                    {'nome': 'Sensor Água', 'tipo': 'temperatura', 'posicao': 'agua', 'unidade': '°C', 'endereco': 'DS18B20_agua'},
                    {'nome': 'Sensor Estufa', 'tipo': 'temperatura', 'posicao': 'estufa', 'unidade': '°C', 'endereco': 'DS18B20_estufa'},
                    {'nome': 'Sensor Externa', 'tipo': 'temperatura', 'posicao': 'externa', 'unidade': '°C', 'endereco': 'DS18B20_externa'}
                ]
            
            for sensor in sensores_info:
                cursor.execute("""
                    INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    datalogger_id,
                    sensor['nome'],
                    sensor.get('tipo', 'temperatura'),
                    sensor.get('unidade', '°C'),
                    sensor['posicao'],
                    sensor.get('endereco', f"DS18B20_{datalogger_id}_{sensor['posicao']}"),
                    True
                ))
            
            # Criar limites padrão
            criar_limites_padrao(cursor, localizacao_id)
            
            conn.commit()
            
            print(f"✅ Datalogger criado! ID: {dispositivo_id}")
            
            # Buscar configurações
            config = buscar_config_datalogger_simples(cursor, dispositivo_id)
            
            return jsonify({
                'status': 'sucesso',
                'mensagem': 'Datalogger cadastrado com sucesso',
                'datalogger_id': dispositivo_id,
                'config': config
            }), 201
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/datalogger/dados', methods=['POST'])
def receber_dados_datalogger_esp32():
    """
    Recebe dados de temperatura do datalogger ESP32
    Formato esperado:
    {
        "mac": "AA:BB:CC:DD:EE:FF",
        "timestamp": "2024-01-15 10:30:00",
        "sensores": {
            "agua": 25.5,
            "estufa": 28.3,
            "externa": 22.1
        }
    }
    """
    print("\n" + "="*60)
    print("📊 RECEBENDO DADOS DO DATALOGGER ESP32")
    print("="*60)
    
    try:
        # Verificar se é JSON
        if not request.is_json:
            print("❌ Content-Type não é JSON")
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        print(f"📥 Dados recebidos: {data}")
        
        # Validar MAC address
        mac_address = data.get('mac', '') or data.get('mac_address', '')
        mac_address = mac_address.strip().upper()
        
        if not mac_address:
            print("❌ MAC address não fornecido")
            return jsonify({'error': 'MAC address é obrigatório'}), 400
        
        print(f"🔑 MAC Address: {mac_address}")
        
        # Conectar ao banco
        conn = db.get_connection()
        if not conn:
            print("❌ Erro de conexão com o banco")
            return jsonify({'error': 'Erro de conexão com o banco de dados'}), 500
        
        try:
            with conn.cursor() as cursor:
                # 1. Buscar o datalogger pelo MAC
                cursor.execute("""
                    SELECT d.id, d.localizacao_id, dl.id as datalogger_id, d.nome
                    FROM dispositivos d
                    JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    WHERE d.mac_address = %s AND d.tipo = 'datalogger'
                """, (mac_address,))
                
                datalogger = cursor.fetchone()
                
                if not datalogger:
                    print(f"❌ Datalogger não encontrado: {mac_address}")
                    return jsonify({
                        'error': f'Datalogger com MAC {mac_address} não encontrado',
                        'sugestao': 'Cadastre o equipamento primeiro usando /api/equipamento/autocadastro'
                    }), 404
                
                # Usar índices numéricos
                dispositivo_id = datalogger[0]
                localizacao_id = datalogger[1]
                datalogger_id = datalogger[2]
                nome_datalogger = datalogger[3]
                
                print(f"✅ Datalogger encontrado: {nome_datalogger} (ID: {dispositivo_id})")
                
                # 2. Atualizar última comunicação
                agora = datetime.now()
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = true, ultima_comunicacao = %s
                    WHERE id = %s
                """, (agora, dispositivo_id))
                
                print(f"✅ Status atualizado: online=true")
                
                # 3. Processar timestamp
                timestamp_str = data.get('timestamp', agora.isoformat())
                try:
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                        try:
                            timestamp = datetime.strptime(timestamp_str, fmt)
                            break
                        except ValueError:
                            continue
                    else:
                        timestamp = agora
                except Exception:
                    timestamp = agora
                
                # 4. Processar leituras dos sensores
                sensores_data = data.get('sensores', {})
                leituras_processadas = 0
                erros = []
                
                print(f"📈 Sensores recebidos: {list(sensores_data.keys())}")
                
                for posicao, valor in sensores_data.items():
                    if valor is None:
                        erros.append(f"Valor nulo para {posicao}")
                        continue
                    
                    try:
                        valor_float = float(valor)
                        
                        # Buscar sensor pela posição
                        cursor.execute("""
                            SELECT id, nome
                            FROM sensores 
                            WHERE datalogger_id = %s AND posicao = %s AND ativo = true
                        """, (datalogger_id, posicao))
                        
                        sensor = cursor.fetchone()
                        
                        if sensor:
                            sensor_id = sensor[0]
                            sensor_nome = sensor[1]
                            
                            # Inserir leitura
                            cursor.execute("""
                                INSERT INTO leituras_sensores (sensor_id, valor, timestamp)
                                VALUES (%s, %s, %s)
                            """, (sensor_id, valor_float, timestamp))
                            leituras_processadas += 1
                            print(f"  ✅ {posicao}: {valor_float}°C registrado")
                            
                            # Verificar limites de temperatura
                            if localizacao_id and posicao in ['agua', 'estufa', 'externa']:
                                try:
                                    cursor.execute("""
                                        SELECT maximo, minimo 
                                        FROM limites_temperatura 
                                        WHERE localizacao_id = %s AND tipo_sensor = %s
                                    """, (localizacao_id, posicao))
                                    
                                    limite = cursor.fetchone()
                                    
                                    if limite:
                                        maximo, minimo = limite
                                        if valor_float > maximo or valor_float < minimo:
                                            tipo_alerta = "TEMPERATURA_ALTA" if valor_float > maximo else "TEMPERATURA_BAIXA"
                                            mensagem = f"Temperatura {posicao}: {valor_float:.1f}°C fora do limite ({minimo:.0f}-{maximo:.0f}°C)"
                                            
                                            cursor.execute("""
                                                INSERT INTO alertas (localizacao_id, tipo, severidade, mensagem, timestamp)
                                                VALUES (%s, %s, %s, %s, %s)
                                            """, (localizacao_id, tipo_alerta, 'MEDIA', mensagem, timestamp))
                                            print(f"  ⚠️ Alerta: {mensagem}")
                                except Exception as e:
                                    print(f"  ⚠️ Erro ao verificar limites: {e}")
                        else:
                            print(f"  ⚠️ Sensor não encontrado para posição: {posicao}")
                            erros.append(f"Sensor não encontrado: {posicao}")
                            
                    except Exception as e:
                        print(f"  ❌ Erro ao processar {posicao}: {e}")
                        erros.append(f"{posicao}: {str(e)}")
                        continue
                
                # 5. Atualizar quantidade de sensores do datalogger
                if sensores_data:
                    cursor.execute("""
                        UPDATE dataloggers 
                        SET quantidade_sensores = %s
                        WHERE id = %s
                    """, (len(sensores_data), datalogger_id))
                
                conn.commit()
                
                print(f"\n✅ RESULTADO: {leituras_processadas}/{len(sensores_data)} leituras processadas")
                
                # 6. Preparar resposta
                resposta = {
                    'status': 'sucesso',
                    'mensagem': f'{leituras_processadas} leitura(s) processada(s)',
                    'datalogger_id': dispositivo_id,
                    'datalogger_nome': nome_datalogger,
                    'leituras_processadas': leituras_processadas,
                    'timestamp': datetime.now().isoformat()
                }
                
                if erros:
                    resposta['erros'] = erros
                    resposta['status'] = 'parcial' if leituras_processadas > 0 else 'erro'
                
                return jsonify(resposta), 200
                
        except Exception as e:
            print(f"❌ Erro no processamento: {e}")
            import traceback
            traceback.print_exc()
            if conn:
                conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            if conn:
                conn.close()
            
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/datalogger/autocadastro', methods=['POST'])
def autocadastro_emergencia():
    """Rota de emergência para autocadastro - sempre funciona"""
    print("\n" + "="*60)
    print("🚨 AUTOCADASTRO DE EMERGÊNCIA")
    print("="*60)
    
    try:
        if not request.is_json:
            return jsonify({'error': 'Content-Type deve ser application/json'}), 400
        
        data = request.get_json()
        print(f"📥 Dados recebidos: {data}")
        
        identificacao = data.get('identificacao', {})
        mac_address = identificacao.get('mac', '').strip().upper()
        
        if not mac_address:
            return jsonify({'error': 'MAC address é obrigatório'}), 400
        
        nome = identificacao.get('nome', f'Datalogger {mac_address[-8:]}')
        modelo = identificacao.get('modelo', 'ESP32')
        versao = identificacao.get('versao_firmware', '1.0.0')
        
        # Informações da localização
        localizacao_info = identificacao.get('localizacao', {})
        localizacao_nome = localizacao_info.get('nome', f'Local-{mac_address[-8:]}')
        localizacao_tipo = localizacao_info.get('tipo', 'estufa')
        
        # Informações dos sensores
        sensores_info = identificacao.get('sensores', [])
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão com o banco'}), 500
        
        with conn.cursor() as cursor:
            # 1. Verificar se já existe
            cursor.execute("""
                SELECT d.id, dl.id as datalogger_id
                FROM dispositivos d
                LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.mac_address = %s AND d.tipo = 'datalogger'
            """, (mac_address,))
            
            existente = cursor.fetchone()
            
            if existente:
                dispositivo_id = existente[0]
                print(f"✅ Datalogger já existe: ID {dispositivo_id}")
                
                # Atualizar online
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = true, ultima_comunicacao = %s
                    WHERE id = %s
                """, (datetime.now(), dispositivo_id))
                conn.commit()
                
                return jsonify({
                    'status': 'sucesso',
                    'mensagem': 'Datalogger já cadastrado',
                    'datalogger_id': dispositivo_id
                }), 200
            
            # 2. Criar localização
            cursor.execute("""
                SELECT id FROM localizacoes WHERE nome = %s
            """, (localizacao_nome,))
            
            localizacao = cursor.fetchone()
            
            if localizacao:
                localizacao_id = localizacao[0]
            else:
                cursor.execute("""
                    INSERT INTO localizacoes (nome, tipo, descricao)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (localizacao_nome, localizacao_tipo, f'Localização para {mac_address}'))
                localizacao_id = cursor.fetchone()[0]
            
            # 3. Criar dispositivo
            cursor.execute("""
                INSERT INTO dispositivos (
                    localizacao_id, nome, descricao, mac_address,
                    tipo, modelo, versao_firmware, online, ultima_comunicacao
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                localizacao_id,
                nome,
                f'Datalogger autocadastrado - MAC: {mac_address}',
                mac_address,
                'datalogger',
                modelo,
                versao,
                True,
                datetime.now()
            ))
            
            dispositivo_id = cursor.fetchone()[0]
            
            # 4. Criar datalogger
            cursor.execute("""
                INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (dispositivo_id, len(sensores_info) if sensores_info else 3, 60))
            
            datalogger_id = cursor.fetchone()[0]
            
            # 5. Criar sensores
            if not sensores_info:
                # Sensores padrão
                sensores_padrao = [
                    ('Sensor Água', 'temperatura', '°C', 'agua', f'DS18B20_{datalogger_id}_agua'),
                    ('Sensor Estufa', 'temperatura', '°C', 'estufa', f'DS18B20_{datalogger_id}_estufa'),
                    ('Sensor Externa', 'temperatura', '°C', 'externa', f'DS18B20_{datalogger_id}_externa')
                ]
                for nome_sensor, tipo_sensor, unidade, posicao, endereco in sensores_padrao:
                    cursor.execute("""
                        INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco, True))
            else:
                for sensor in sensores_info:
                    cursor.execute("""
                        INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        datalogger_id,
                        sensor.get('nome', 'Sensor'),
                        sensor.get('tipo', 'temperatura'),
                        sensor.get('unidade', '°C'),
                        sensor.get('posicao', 'desconhecido'),
                        sensor.get('endereco', f'DS18B20_{datalogger_id}'),
                        True
                    ))
            
            # 6. Criar limites padrão
            limites_padrao = [('agua', 30.0, 20.0), ('estufa', 35.0, 25.0), ('externa', 40.0, 15.0)]
            for tipo_sensor, maximo, minimo in limites_padrao:
                cursor.execute("""
                    INSERT INTO limites_temperatura (localizacao_id, tipo_sensor, maximo, minimo)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (localizacao_id, tipo_sensor) DO NOTHING
                """, (localizacao_id, tipo_sensor, maximo, minimo))
            
            conn.commit()
            
            print(f"✅ Datalogger criado com sucesso! ID: {dispositivo_id}")
            
            return jsonify({
                'status': 'sucesso',
                'mensagem': 'Datalogger cadastrado com sucesso!',
                'datalogger_id': dispositivo_id
            }), 201
            
    except Exception as e:
        print(f"❌ Erro no autocadastro: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/datalogger/config', methods=['GET'])
def get_config_datalogger_esp32():
    """
    Retorna configurações do datalogger para o ESP32
    Parâmetros: mac_address
    """
    mac_address = request.args.get('mac_address', '').strip().upper()
    
    if not mac_address:
        return jsonify({'error': 'mac_address é obrigatório'}), 400
    
    conn = db.get_connection()
    if not conn:
        return jsonify({'error': 'Erro de conexão'}), 500
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT d.id, d.localizacao_id, dl.intervalo_leitura
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
        print(f"❌ Erro: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# ============================================
# FUNÇÕES AUXILIARES
# ============================================

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
    
    # Buscar limites
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
# ============================================
# ROTAS DA API PARA DATALOGGER - CONFIGURAÇÕES
# ============================================

@app.route('/api/configuracoes/datalogger/<int:datalogger_id>', methods=['PUT'])
@login_required
def atualizar_config_datalogger(datalogger_id):
    """API para atualizar configurações do datalogger"""
    try:
        data = request.get_json()
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            # Verificar permissão
            if session['usuario_tipo'] != 'admin':
                cursor.execute("""
                    SELECT 1 FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s
                """, (datalogger_id, session['usuario_id']))
                
                if not cursor.fetchone():
                    return jsonify({'error': 'Acesso negado'}), 403
            
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
                limites = data['limites']
                for posicao, valores in limites.items():
                    cursor.execute("""
                        INSERT INTO limites_temperatura (localizacao_id, tipo_sensor, maximo, minimo)
                        SELECT localizacao_id, %s, %s, %s
                        FROM dispositivos WHERE id = %s
                        ON CONFLICT (localizacao_id, tipo_sensor) DO UPDATE SET
                            maximo = EXCLUDED.maximo,
                            minimo = EXCLUDED.minimo,
                            updated_at = CURRENT_TIMESTAMP
                    """, (posicao, valores['max'], valores['min'], datalogger_id))
            
            conn.commit()
            
            # Enviar comando para o ESP32 recarregar configurações
            cursor.execute("""
                SELECT mac_address FROM dispositivos WHERE id = %s
            """, (datalogger_id,))
            
            mac_result = cursor.fetchone()
            if mac_result:
                mac_address = mac_result[0]
                cursor.execute("""
                    INSERT INTO comandos_pendentes (mac_address, comando, parametros, criado_por)
                    VALUES (%s, %s, %s, %s)
                """, (mac_address, 'configurar', '{"recarregar": true}', session['usuario_id']))
                conn.commit()
            
            return jsonify({'status': 'sucesso', 'mensagem': 'Configurações atualizadas'}), 200
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/configuracoes/datalogger/<int:datalogger_id>', methods=['PUT'])
@login_required
def atualizar_config_datalogger_api(datalogger_id):
    """API para atualizar configurações do datalogger"""
    try:
        data = request.get_json()
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            # Verificar permissão
            if session['usuario_tipo'] != 'admin':
                cursor.execute("""
                    SELECT 1 FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s
                """, (datalogger_id, session['usuario_id']))
                
                if not cursor.fetchone():
                    return jsonify({'error': 'Acesso negado'}), 403
            
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
                # Buscar localizacao_id
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
            
            return jsonify({'status': 'sucesso', 'mensagem': 'Configurações atualizadas'}), 200
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/datalogger/dados/historico/<int:datalogger_id>', methods=['GET'])
@login_required
def obter_historico_datalogger(datalogger_id):
    """Retorna histórico de dados do datalogger"""
    try:
        horas = int(request.args.get('horas', 24))
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Verificar permissão
            if session['usuario_tipo'] != 'admin':
                cursor.execute("""
                    SELECT 1 FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s
                """, (datalogger_id, session['usuario_id']))
                
                if not cursor.fetchone():
                    return jsonify({'error': 'Acesso negado'}), 403
            
            # Buscar dados
            cursor.execute("""
                SELECT 
                    ls.timestamp,
                    MAX(CASE WHEN s.posicao = 'agua' THEN ls.valor END) as agua,
                    MAX(CASE WHEN s.posicao = 'estufa' THEN ls.valor END) as estufa,
                    MAX(CASE WHEN s.posicao = 'externa' THEN ls.valor END) as externa
                FROM leituras_sensores ls
                JOIN sensores s ON ls.sensor_id = s.id
                JOIN dataloggers dl ON s.datalogger_id = dl.id
                WHERE dl.dispositivo_id = %s
                    AND ls.timestamp >= NOW() - INTERVAL '%s hours'
                GROUP BY DATE_TRUNC('hour', ls.timestamp), ls.timestamp
                ORDER BY ls.timestamp DESC
                LIMIT 1000
            """, (datalogger_id, horas))
            
            dados = cursor.fetchall()
            
            # Estatísticas
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_leituras,
                    MAX(ls.timestamp) as ultima_leitura
                FROM leituras_sensores ls
                JOIN sensores s ON ls.sensor_id = s.id
                JOIN dataloggers dl ON s.datalogger_id = dl.id
                WHERE dl.dispositivo_id = %s
            """, (datalogger_id,))
            
            estatisticas = cursor.fetchone()
            
            return jsonify({
                'status': 'sucesso',
                'dados': dados,
                'estatisticas': estatisticas
            }), 200
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/api/datalogger/dados/exportar/<int:datalogger_id>', methods=['GET'])
@login_required
def exportar_dados_datalogger(datalogger_id):
    """Exporta dados do datalogger para CSV"""
    try:
        horas = int(request.args.get('horas', 24))
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'error': 'Erro de conexão'}), 500
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Buscar dados
            cursor.execute("""
                SELECT 
                    ls.timestamp,
                    MAX(CASE WHEN s.posicao = 'agua' THEN ls.valor END) as agua,
                    MAX(CASE WHEN s.posicao = 'estufa' THEN ls.valor END) as estufa,
                    MAX(CASE WHEN s.posicao = 'externa' THEN ls.valor END) as externa
                FROM leituras_sensores ls
                JOIN sensores s ON ls.sensor_id = s.id
                JOIN dataloggers dl ON s.datalogger_id = dl.id
                WHERE dl.dispositivo_id = %s
                    AND ls.timestamp >= NOW() - INTERVAL '%s hours'
                GROUP BY ls.timestamp
                ORDER BY ls.timestamp ASC
            """, (datalogger_id, horas))
            
            dados = cursor.fetchall()
            
            # Criar CSV
            import io
            output = io.StringIO()
            output.write("timestamp,agua,estufa,externa\n")
            
            for row in dados:
                output.write(f"{row['timestamp']},{row['agua']},{row['estufa']},{row['externa']}\n")
            
            # Enviar resposta
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = f'attachment; filename=datalogger_{datalogger_id}_dados.csv'
            return response
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@app.route('/configuracoes/datalogger/<int:equipamento_id>')
@login_required
def configuracoes_datalogger(equipamento_id):
    """Página de configurações específica do datalogger"""
    conn = db.get_connection()
    if not conn:
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('configuracoes'))
    
    try:
        with conn.cursor() as cursor:  # SEM cursor_factory
            # Verificar permissão
            if session['usuario_tipo'] != 'admin':
                cursor.execute("""
                    SELECT 1 FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s
                """, (equipamento_id, session['usuario_id']))
                
                if not cursor.fetchone():
                    flash('Acesso negado a este equipamento', 'danger')
                    return redirect(url_for('configuracoes'))
            
            # Buscar dados do datalogger
            cursor.execute("""
                SELECT 
                    d.id, d.nome, d.mac_address, d.modelo, d.descricao, d.online,
                    d.ultima_comunicacao, d.localizacao_id,
                    l.nome as localizacao_nome, l.tipo as localizacao_tipo,
                    dl.intervalo_leitura, dl.quantidade_sensores
                FROM dispositivos d
                JOIN localizacoes l ON d.localizacao_id = l.id
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.id = %s AND d.tipo = 'datalogger'
            """, (equipamento_id,))
            
            datalogger_row = cursor.fetchone()
            
            if not datalogger_row:
                flash('Datalogger não encontrado', 'danger')
                return redirect(url_for('configuracoes'))
            
            # Converter para dicionário
            colunas_datalogger = ['id', 'nome', 'mac_address', 'modelo', 'descricao', 'online',
                                  'ultima_comunicacao', 'localizacao_id', 'localizacao_nome', 
                                  'localizacao_tipo', 'intervalo_leitura', 'quantidade_sensores']
            datalogger = dict(zip(colunas_datalogger, datalogger_row))
            
            # Buscar sensores
            cursor.execute("""
                SELECT id, nome, tipo, unidade, posicao, endereco, ativo
                FROM sensores
                WHERE datalogger_id = (
                    SELECT id FROM dataloggers WHERE dispositivo_id = %s
                )
                ORDER BY posicao
            """, (equipamento_id,))
            
            sensores_raw = cursor.fetchall()
            colunas_sensores = ['id', 'nome', 'tipo', 'unidade', 'posicao', 'endereco', 'ativo']
            sensores = [dict(zip(colunas_sensores, s)) for s in sensores_raw]
            
            # Buscar limites de temperatura
            cursor.execute("""
                SELECT tipo_sensor, maximo, minimo
                FROM limites_temperatura
                WHERE localizacao_id = %s
            """, (datalogger['localizacao_id'],))
            
            limites_raw = cursor.fetchall()
            limites = {}
            for limite in limites_raw:
                limites[limite[0]] = {
                    'max': float(limite[1]) if limite[1] else 0,
                    'min': float(limite[2]) if limite[2] else 0
                }
            
            # Buscar localizações disponíveis
            if session['usuario_tipo'] == 'admin':
                cursor.execute("SELECT id, nome, tipo FROM localizacoes ORDER BY nome")
            else:
                cursor.execute("""
                    SELECT l.id, l.nome, l.tipo
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                    ORDER BY l.nome
                """, (session['usuario_id'],))
            
            localizacoes_raw = cursor.fetchall()
            colunas_loc = ['id', 'nome', 'tipo']
            localizacoes = [dict(zip(colunas_loc, loc)) for loc in localizacoes_raw]
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        flash('Erro ao carregar configurações', 'danger')
        return redirect(url_for('configuracoes'))
    finally:
        conn.close()
    
    return render_template('configuracoes_datalogger.html',
                         datalogger=datalogger,
                         sensores=sensores,
                         limites=limites,
                         localizacoes=localizacoes,
                         usuario=session)






































if __name__ == '__main__':
    # Iniciar verificador de offline em background
    iniciar_verificador_offline()
    
    # Rodar a API
    app.run(debug=True, host='0.0.0.0', port=5000)