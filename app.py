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
    """Verifica autenticação para rotas protegidas"""
    
    print(f"\n🔍 DEBUG MIDDLEWARE:")
    print(f"  Path: {request.path}")
    print(f"  Method: {request.method}")
    print(f"  Endpoint: {request.endpoint}")
    print(f"  Content-Type: {request.content_type}")
    
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

@app.before_request
def check_authentication():
    """Verifica autenticação para rotas protegidas"""
    
    # DEBUG: Mostrar todas as requisições
    print(f"\n🔍 BEFORE_REQUEST: {request.method} {request.path}")
    
    # LISTA COMPLETA de rotas que NÃO precisam de autenticação
    public_paths = [
        '/login',
        '/logout', 
        '/health',
        '/api/',  # Todas as rotas API
        '/static/'  # Arquivos estáticos
    ]
    
    # Verificar se a rota atual começa com algum dos paths públicos
    for public_path in public_paths:
        if request.path.startswith(public_path):
            print(f"✅ Rota pública: {request.path} - ACESSO PERMITIDO")
            return  # Permite acesso SEM verificar autenticação
    
    # Se chegou aqui, precisa de autenticação
    if 'usuario_id' not in session:
        print(f"❌ Não autenticado: {request.path} - REDIRECIONANDO")
        flash('Por favor, faça login para acessar esta página.', 'warning')
        return redirect(url_for('login'))
    
    print(f"✅ Usuário autenticado: {request.path}")

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
    """Rota para autocadastro completo do ESP32 datalogger"""
    print("\n" + "="*60)
    print("🤖 AUTOCADASTRO DO ESP32 DATALOGGER")
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
        campos_obrigatorios = ['identificacao', 'dados_sensores']
        for campo in campos_obrigatorios:
            if campo not in data:
                return jsonify({
                    'status': 'erro',
                    'mensagem': f'Campo "{campo}" é obrigatório'
                }), 400
        
        identificacao = data['identificacao']
        dados_sensores = data['dados_sensores']
        
        # Validar identificação
        if 'mac' not in identificacao:
            return jsonify({
                'status': 'erro',
                'mensagem': 'Campo "mac" é obrigatório na identificação'
            }), 400
        
        mac_address = identificacao['mac'].strip().upper()
        nome = identificacao.get('nome', f'ESP32 Datalogger {mac_address[-6:]}')
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
                    SELECT d.id, d.nome, d.localizacao_id, dl.id as datalogger_id
                    FROM dispositivos d
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id AND d.tipo = 'datalogger'
                    WHERE d.mac_address = %s
                """, (mac_address,))
                
                dispositivo_existente = cursor.fetchone()
                
                if dispositivo_existente:
                    # Equipamento já existe, usar os dados existentes
                    dispositivo_id, nome_existente, localizacao_id, datalogger_id = dispositivo_existente
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
                    
                    # 4. Criar datalogger
                    if tipo == 'datalogger':
                        cursor.execute("""
                            INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                            VALUES (%s, %s, %s)
                            RETURNING id
                        """, (dispositivo_id, 3, 60))  # 3 sensores, 60s intervalo
                        
                        datalogger_id = cursor.fetchone()[0]
                        print(f"✅ Datalogger criado: ID {datalogger_id}")
                        
                        # 5. Criar sensores padrão baseado nas posições esperadas
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
                
                # 6. Processar dados dos sensores
                print(f"\n📊 PROCESSANDO DADOS DOS SENSORES:")
                
                leituras_processadas = 0
                erros = []
                
                # Processar cada sensor
                for sensor_data in dados_sensores:
                    try:
                        # Validar dados do sensor
                        posicao = sensor_data.get('posicao', '').lower()
                        valor = sensor_data.get('valor')
                        timestamp = sensor_data.get('timestamp', datetime.now().isoformat())
                        
                        if not posicao:
                            erros.append("Posição do sensor não informada")
                            continue
                        
                        if valor is None:
                            erros.append(f"Valor não informado para sensor {posicao}")
                            continue
                        
                        valor_float = float(valor)
                        
                        print(f"📡 Sensor {posicao}: {valor_float}°C")
                        
                        # Determinar endereço do sensor
                        endereco = f'DS18B20_{datalogger_id}_{posicao}'
                        
                        # Buscar ou criar sensor
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
                            
                            cursor.execute("""
                                INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                                RETURNING id
                            """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco, True))
                            
                            sensor_id = cursor.fetchone()[0]
                            print(f"  ✅ Sensor {posicao} criado (ID: {sensor_id})")
                        else:
                            sensor_id, sensor_nome, sensor_tipo, unidade, ativo = sensor
                            
                            if not ativo:
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
                        
                        leituras_processadas += 1
                        
                        # Verificar limites de temperatura
                        if localizacao_id and posicao in ['agua', 'estufa', 'externa']:
                            verificar_limites_temperatura_simples(
                                cursor, 
                                localizacao_id, 
                                posicao, 
                                valor_float, 
                                f"Sensor {posicao}", 
                                timestamp_dt
                            )
                        
                    except Exception as e:
                        print(f"  ❌ Erro no sensor {posicao}: {e}")
                        erros.append(f"{posicao}: {str(e)}")
                        continue
                
                # 7. Atualizar quantidade de sensores ativos
                cursor.execute("""
                    UPDATE dataloggers 
                    SET quantidade_sensores = (
                        SELECT COUNT(*) FROM sensores 
                        WHERE datalogger_id = %s AND ativo = true
                    )
                    WHERE id = %s
                """, (datalogger_id, datalogger_id))
                
                # 8. Criar limites de temperatura padrão se não existirem
                sensores_posicoes = ['agua', 'estufa', 'externa']
                for posicao in sensores_posicoes:
                    cursor.execute("""
                        SELECT 1 FROM limites_temperatura 
                        WHERE localizacao_id = %s AND tipo_sensor = %s
                    """, (localizacao_id, posicao))
                    
                    if not cursor.fetchone():
                        # Definir limites padrão baseado na posição
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
                
                # 9. Commitar todas as mudanças
                conn.commit()
                
                print(f"\n✅ AUTOCADASTRO CONCLUÍDO COM SUCESSO!")
                print(f"   Leituras processadas: {leituras_processadas}/{len(dados_sensores)}")
                print(f"   Erros: {len(erros)}")
                
                # 10. Preparar resposta
                resposta = {
                    'status': 'sucesso',
                    'mensagem': 'Autocadastro realizado com sucesso!',
                    'equipamento': {
                        'id': dispositivo_id,
                        'nome': nome,
                        'mac': mac_address,
                        'localizacao_id': localizacao_id,
                        'localizacao_nome': localizacao_nome
                    },
                    'datalogger_id': datalogger_id,
                    'leituras_processadas': leituras_processadas,
                    'sensores_cadastrados': leituras_processadas,
                    'timestamp': datetime.now().isoformat()
                }
                
                if erros:
                    resposta['erros'] = erros
                    resposta['status'] = 'parcial'
                    resposta['mensagem'] = f'Autocadastro realizado com {len(erros)} erro(s)'
                
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


# ====================
# API ESPECÍFICA PARA ESP32 DATALOGGER
# ====================

@app.route('/api/esp32/dados', methods=['POST'])
def receber_dados_esp32():
    """
    Rota específica para receber dados do ESP32
    Formato esperado:
    {
        "mac": "AA:BB:CC:DD:EE:FF",
        "timestamp": "2024-01-15 10:30:00",
        "temperaturas": {
            "agua": 25.5,
            "estufa": 28.3,
            "externa": 22.1
        }
    }
    """
    print("\n" + "="*50)
    print("📥 RECEBENDO DADOS DO ESP32")
    print("="*50)
    
    try:
        # Verificar se é JSON
        if not request.is_json:
            return jsonify({'erro': 'Content-Type deve ser application/json'}), 400
        
        dados = request.get_json()
        print(f"Dados recebidos: {dados}")
        
        # Validar campos obrigatórios
        if 'mac' not in dados:
            return jsonify({'erro': 'Campo "mac" é obrigatório'}), 400
        
        mac_address = dados['mac'].strip().upper()
        timestamp_str = dados.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        temperaturas = dados.get('temperaturas', {})
        
        if not temperaturas:
            return jsonify({'erro': 'Nenhuma temperatura fornecida'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'erro': 'Erro de conexão com o banco'}), 500
        
        with conn.cursor() as cursor:
            # 1. Verificar se o dispositivo existe
            cursor.execute("""
                SELECT d.id, d.nome, dl.id as datalogger_id, d.localizacao_id
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.mac_address = %s AND d.tipo = 'datalogger'
            """, (mac_address,))
            
            dispositivo = cursor.fetchone()
            
            if not dispositivo:
                # Criar dispositivo automaticamente
                print(f"⚠️ Dispositivo não encontrado. Criando automaticamente...")
                
                # Criar localização padrão
                cursor.execute("""
                    INSERT INTO localizacoes (nome, tipo, descricao)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (f"Local_{mac_address[-6:]}", "estufa", "Localização automática"))
                
                localizacao_id = cursor.fetchone()[0]
                
                # Criar dispositivo
                cursor.execute("""
                    INSERT INTO dispositivos (localizacao_id, nome, mac_address, tipo, online, ultima_comunicacao)
                    VALUES (%s, %s, %s, %s, true, %s)
                    RETURNING id
                """, (localizacao_id, f"ESP32_{mac_address[-6:]}", mac_address, 'datalogger', datetime.now()))
                
                dispositivo_id = cursor.fetchone()[0]
                
                # Criar datalogger
                cursor.execute("""
                    INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (dispositivo_id, 3, 60))
                
                datalogger_id = cursor.fetchone()[0]
                
                # Criar sensores
                sensores = [
                    ('Sensor Água', 'agua', 'DS18B20_agua'),
                    ('Sensor Estufa', 'estufa', 'DS18B20_estufa'),
                    ('Sensor Externa', 'externa', 'DS18B20_externa')
                ]
                
                for nome, posicao, endereco in sensores:
                    cursor.execute("""
                        INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco, ativo)
                        VALUES (%s, %s, 'temperatura', '°C', %s, %s, true)
                    """, (datalogger_id, nome, posicao, endereco))
                
                conn.commit()
                print(f"✅ Dispositivo criado: ID {dispositivo_id}")
                
            else:
                dispositivo_id, nome, datalogger_id, localizacao_id = dispositivo
                print(f"✅ Dispositivo encontrado: {nome} (ID: {dispositivo_id})")
                
                # Atualizar última comunicação
                cursor.execute("""
                    UPDATE dispositivos 
                    SET online = true, ultima_comunicacao = %s
                    WHERE id = %s
                """, (datetime.now(), dispositivo_id))
            
            # 2. Processar cada temperatura
            leituras_processadas = 0
            timestamp = None
            
            # Converter timestamp
            try:
                if isinstance(timestamp_str, str):
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                else:
                    timestamp = datetime.now()
            except:
                timestamp = datetime.now()
            
            # Mapeamento das posições
            mapeamento = {
                'agua': 'agua',
                'estufa': 'estufa', 
                'externa': 'externa'
            }
            
            for posicao_key, valor in temperaturas.items():
                posicao = mapeamento.get(posicao_key.lower(), posicao_key.lower())
                
                # Buscar sensor pela posição
                cursor.execute("""
                    SELECT id, nome FROM sensores 
                    WHERE datalogger_id = %s AND posicao = %s AND ativo = true
                """, (datalogger_id, posicao))
                
                sensor = cursor.fetchone()
                
                if sensor:
                    sensor_id, sensor_nome = sensor
                    
                    # Inserir leitura
                    cursor.execute("""
                        INSERT INTO leituras_sensores (sensor_id, valor, timestamp)
                        VALUES (%s, %s, %s)
                    """, (sensor_id, float(valor), timestamp))
                    
                    leituras_processadas += 1
                    print(f"  ✅ {sensor_nome}: {valor}°C")
                    
                    # Verificar limites (opcional)
                    verificar_limites_temperatura_simples(
                        cursor, localizacao_id, posicao, float(valor), sensor_nome, timestamp
                    )
                else:
                    print(f"  ⚠️ Sensor não encontrado para posição: {posicao}")
            
            conn.commit()
            
            return jsonify({
                'status': 'sucesso',
                'mensagem': f'{leituras_processadas} leitura(s) processada(s)',
                'dispositivo_id': dispositivo_id,
                'leituras': leituras_processadas
            }), 200
            
    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        return jsonify({'erro': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/esp32/status', methods=['POST'])
def atualizar_status_esp32():
    """Recebe status do ESP32"""
    try:
        if not request.is_json:
            return jsonify({'erro': 'JSON esperado'}), 400
        
        dados = request.get_json()
        mac_address = dados.get('mac', '').strip().upper()
        
        if not mac_address:
            return jsonify({'erro': 'MAC é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'erro': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE dispositivos 
                SET online = true, ultima_comunicacao = %s
                WHERE mac_address = %s AND tipo = 'datalogger'
            """, (datetime.now(), mac_address))
            
            conn.commit()
            
            return jsonify({
                'status': 'ok',
                'mensagem': 'Status atualizado'
            }), 200
            
    except Exception as e:
        return jsonify({'erro': str(e)}), 500
    finally:
        if conn:
            conn.close()


@app.route('/api/esp32/config', methods=['GET'])
def obter_config_esp32():
    """ESP32 obtém sua configuração"""
    try:
        mac_address = request.args.get('mac', '').strip().upper()
        
        if not mac_address:
            return jsonify({'erro': 'MAC é obrigatório'}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({'erro': 'Erro de conexão'}), 500
        
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT d.nome, dl.intervalo_leitura
                FROM dispositivos d
                JOIN dataloggers dl ON d.id = dl.dispositivo_id
                WHERE d.mac_address = %s AND d.tipo = 'datalogger'
            """, (mac_address,))
            
            config = cursor.fetchone()
            
            if not config:
                return jsonify({'erro': 'Dispositivo não encontrado'}), 404
            
            nome, intervalo = config
            
            return jsonify({
                'status': 'ok',
                'nome': nome,
                'intervalo_segundos': intervalo,
                'versao_api': '1.0'
            }), 200
            
    except Exception as e:
        return jsonify({'erro': str(e)}), 500
    finally:
        if conn:
            conn.close()
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)