from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from auth import login_required
from database import Database
from utils import processar_dados_grafico, calcular_estatisticas
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor

routes_bp = Blueprint("routes", __name__)
db = Database()

@routes_bp.route("/dashboard")
@login_required
def dashboard():
    """Dashboard principal após login"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return render_template("dashboard.html", 
                             usuario=session,
                             localizacoes=[],
                             stats={})
    
    try:
        with conn.cursor() as cursor:
            usuario_id = session["usuario_id"]
            usuario_tipo = session["usuario_tipo"]
            
            stats = {}
            ultimos_equipamentos = []

            if usuario_tipo == "admin":
                cursor.execute("SELECT COUNT(*) FROM localizacoes")
                stats["total_localizacoes"] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM dispositivos")
                stats["total_equipamentos"] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM dispositivos WHERE online = true")
                stats["equipamentos_online"] = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM usuarios WHERE ativo = true")
                stats["total_usuarios"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM alimentadores a 
                    JOIN dispositivos d ON a.dispositivo_id = d.id
                """)
                stats["total_alimentadores"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM dataloggers dl 
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                """)
                stats["total_dataloggers"] = cursor.fetchone()[0]
                
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
                cursor.execute("""
                    SELECT COUNT(DISTINCT l.id) 
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                """, (usuario_id,))
                stats["total_localizacoes"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT d.id)
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                """, (usuario_id,))
                stats["total_equipamentos"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(DISTINCT d.id)
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s AND d.online = true
                """, (usuario_id,))
                stats["equipamentos_online"] = cursor.fetchone()[0]
                
                stats["total_usuarios"] = 1 # Apenas o próprio para usuários normais
                
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM alimentadores a
                    JOIN dispositivos d ON a.dispositivo_id = d.id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                """, (usuario_id,))
                stats["total_alimentadores"] = cursor.fetchone()[0]
                
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                """, (usuario_id,))
                stats["total_dataloggers"] = cursor.fetchone()[0]
                
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

            return render_template("dashboard.html", 
                                 usuario=session,
                                 stats=stats,
                                 ultimos_equipamentos=ultimos_equipamentos)

    except Exception as e:
        print(f"❌ Erro ao carregar dashboard: {e}")
        flash(f"Erro ao carregar dashboard: {str(e)}", "danger")
        return render_template("dashboard.html", 
                             usuario=session,
                             localizacoes=[],
                             stats={})
    finally:
        if conn:
            conn.close()

@routes_bp.route("/equipamentos")
@login_required
def equipamentos():
    """Página principal de equipamentos"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return render_template("equipamentos.html", dispositivos=[])
    
    try:
        with conn.cursor() as cursor:
            if session["usuario_tipo"] == "admin":
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
                """, (session["usuario_id"],))
            
            dispositivos_raw = cursor.fetchall()
            
            dispositivos = []
            for d in dispositivos_raw:
                dispositivo_dict = dict(d)
                if dispositivo_dict["ultima_comunicacao"]:
                    dispositivo_dict["ultima_comunicacao_formatada"] = dispositivo_dict["ultima_comunicacao"].strftime("%d/%m/%Y %H:%M:%S")
                else:
                    dispositivo_dict["ultima_comunicacao_formatada"] = "N/A"
                dispositivos.append(dispositivo_dict)

            return render_template("equipamentos.html", dispositivos=dispositivos)

    except Exception as e:
        print(f"❌ Erro ao buscar equipamentos: {e}")
        flash(f"Erro ao carregar equipamentos: {str(e)}", "danger")
        return render_template("equipamentos.html", dispositivos=[])
    finally:
        if conn:
            conn.close()

@routes_bp.route("/cadastrar_equipamento")
@login_required
def cadastrar_equipamento():
    """Página de cadastro de novo equipamento"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return render_template("cadastrar_equipamento.html", localizacoes=[])
    
    try:
        with conn.cursor() as cursor:
            if session["usuario_tipo"] == "admin":
                cursor.execute("SELECT id, nome, descricao, tipo FROM localizacoes ORDER BY nome")
            else:
                cursor.execute("""
                    SELECT l.id, l.nome, l.descricao, l.tipo 
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                    ORDER BY l.nome
                """, (session["usuario_id"],))
            
            localizacoes = cursor.fetchall()
            localizacoes_dict = [
                {
                    "id": loc[0],
                    "nome": loc[1],
                    "descricao": loc[2],
                    "tipo": loc[3]
                }
                for loc in localizacoes
            ]
            
    except Exception as e:
        print(f"❌ Erro ao buscar localizações: {e}")
        localizacoes_dict = []
    finally:
        conn.close()
    
    return render_template("cadastrar_equipamento.html", localizacoes=localizacoes_dict)

@routes_bp.route("/equipamentos/salvar", methods=["POST"])
@login_required
def salvar_equipamento():
    """Salva um novo equipamento"""
    try:
        nome = request.form["nome"]
        descricao = request.form.get("descricao", "")
        mac_address = request.form["mac_address"]
        ip_address = request.form.get("ip_address", "")
        tipo = request.form["tipo"]
        modelo = request.form.get("modelo", "")
        localizacao_id = request.form["localizacao_id"]
        
        if not localizacao_id:
            flash("A localização é obrigatória.", "danger")
            return redirect(url_for("routes.cadastrar_equipamento"))
        
        conn = db.get_connection()
        if not conn:
            flash("Erro de conexão com o banco de dados", "danger")
            return redirect(url_for("routes.cadastrar_equipamento"))
        
        with conn.cursor() as cursor:
            if session["usuario_tipo"] != "admin":
                cursor.execute("""
                    SELECT 1 FROM usuario_localizacao 
                    WHERE usuario_id = %s AND localizacao_id = %s
                """, (session["usuario_id"], localizacao_id))
                
                if not cursor.fetchone():
                    flash("Você não tem acesso a esta localização.", "danger")
                    return redirect(url_for("routes.cadastrar_equipamento"))
            
            cursor.execute("SELECT id FROM dispositivos WHERE mac_address = %s", (mac_address,))
            if cursor.fetchone():
                flash("MAC Address já está em uso. Por favor, use um endereço único.", "danger")
                return redirect(url_for("routes.cadastrar_equipamento"))
            
            cursor.execute("""
                INSERT INTO dispositivos (localizacao_id, nome, descricao, mac_address, ip_address, tipo, modelo)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (localizacao_id, nome, descricao, mac_address, ip_address, tipo, modelo))
            
            dispositivo_id = cursor.fetchone()[0]
            
            if tipo == "alimentador":
                cursor.execute("""
                    INSERT INTO alimentadores (dispositivo_id, capacidade_racao, vazao_media)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (dispositivo_id, 0, 0))
                
                alimentador_id = cursor.fetchone()[0]
                
                cursor.execute("""
                    INSERT INTO config_alimentadores (alimentador_id, ativa)
                    VALUES (%s, false)
                """, (alimentador_id,))
                
                cursor.execute("""
                    INSERT INTO calibracao_alimentadores (alimentador_id)
                    VALUES (%s)
                """, (alimentador_id,))
                
                flash("Alimentador cadastrado com sucesso!", "success")
                
            elif tipo == "datalogger":
                cursor.execute("""
                    INSERT INTO dataloggers (dispositivo_id, quantidade_sensores, intervalo_leitura)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (dispositivo_id, 3, 60))
                
                datalogger_id = cursor.fetchone()[0]
                
                sensores_base = [
                    ("Sensor Água", "temperatura", "°C", "agua"),
                    ("Sensor Estufa", "temperatura", "°C", "estufa"),
                    ("Sensor Externa", "temperatura", "°C", "externa")
                ]
                
                for nome_sensor, tipo_sensor, unidade, posicao in sensores_base:
                    endereco = f"DS18B20_{datalogger_id}_{posicao}"
                    cursor.execute("""
                        INSERT INTO sensores (datalogger_id, nome, tipo, unidade, posicao, endereco)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (datalogger_id, nome_sensor, tipo_sensor, unidade, posicao, endereco))
                
                flash("Datalogger cadastrado com sucesso! 3 sensores de temperatura criados automaticamente.", "success")
            
            conn.commit()
            
    except Exception as e:
        print(f"❌ Erro ao salvar equipamento: {e}")
        flash(f"Erro ao cadastrar equipamento: {str(e)}", "danger")
        return redirect(url_for("routes.cadastrar_equipamento"))
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.equipamentos"))

@routes_bp.route("/equipamentos/<int:dispositivo_id>")
@login_required
def ver_equipamento(dispositivo_id):
    """Visualizar detalhes de um equipamento"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return redirect(url_for("routes.equipamentos"))
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if session["usuario_tipo"] == "admin":
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
                """, (dispositivo_id, session["usuario_id"],))
            
            dispositivo = cursor.fetchone()
            
            if not dispositivo:
                flash("Equipamento não encontrado ou você não tem permissão para visualizá-lo.", "danger")
                return redirect(url_for("routes.equipamentos"))
            
            # Buscar dados específicos se for alimentador
            alimentador_info = None
            if dispositivo["tipo_especifico"] == "alimentador":
                cursor.execute("""
                    SELECT a.*, ca.ativa, ca.horario_inicio, ca.horario_fim, ca.intervalo_alimentacao, ca.quantidade_por_alimentacao, ca.dias_semana,
                           cal.constante_a, cal.constante_b, cal.tempo_acionamento
                    FROM alimentadores a
                    LEFT JOIN config_alimentadores ca ON a.id = ca.alimentador_id
                    LEFT JOIN calibracao_alimentadores cal ON a.id = cal.alimentador_id
                    WHERE a.dispositivo_id = %s
                """, (dispositivo_id,))
                alimentador_info = cursor.fetchone()

                # Buscar histórico de alimentação
                cursor.execute("""
                    SELECT quantidade_racao, tempo_acionamento, timestamp, modo
                    FROM historico_alimentacao
                    WHERE alimentador_id = %s
                    ORDER BY timestamp DESC
                    LIMIT 10
                """, (dispositivo["alimentador_id"],))
                historico_alimentacao = cursor.fetchall()
                dispositivo["historico_alimentacao"] = historico_alimentacao

            # Buscar dados específicos se for datalogger
            datalogger_info = None
            sensores = []
            if dispositivo["tipo_especifico"] == "datalogger":
                cursor.execute("""
                    SELECT dl.* FROM dataloggers dl WHERE dl.dispositivo_id = %s
                """, (dispositivo_id,))
                datalogger_info = cursor.fetchone()

                cursor.execute("""
                    SELECT id, nome, tipo, unidade, posicao, endereco, ativo
                    FROM sensores
                    WHERE datalogger_id = %s
                    ORDER BY posicao
                """, (datalogger_info["id"],))
                sensores = cursor.fetchall()
                dispositivo["sensores"] = sensores

                # Buscar limites de temperatura para a localização do datalogger
                cursor.execute("""
                    SELECT tipo_sensor, maximo, minimo
                    FROM limites_temperatura
                    WHERE localizacao_id = %s
                """, (dispositivo["localizacao_id"],))
                limites_temperatura = cursor.fetchall()
                dispositivo["limites_temperatura"] = {l["tipo_sensor"]: {"max": l["maximo"], "min": l["minimo"]} for l in limites_temperatura}

            # Buscar comandos pendentes
            cursor.execute("""
                SELECT id, comando, parametros, criado_em, executado, executado_em
                FROM comandos_pendentes
                WHERE mac_address = %s
                ORDER BY criado_em DESC
                LIMIT 5
            """, (dispositivo["mac_address"],))
            comandos_pendentes = cursor.fetchall()
            dispositivo["comandos_pendentes"] = comandos_pendentes

            return render_template("ver_equipamento.html", 
                                 dispositivo=dispositivo,
                                 alimentador_info=alimentador_info,
                                 datalogger_info=datalogger_info)

    except Exception as e:
        print(f"❌ Erro ao visualizar equipamento: {e}")
        flash(f"Erro ao carregar detalhes do equipamento: {str(e)}", "danger")
        return redirect(url_for("routes.equipamentos"))
    finally:
        if conn:
            conn.close()

@routes_bp.route("/equipamentos/<int:dispositivo_id>/editar")
@login_required
def editar_equipamento(dispositivo_id):
    """Página de edição de equipamento"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return redirect(url_for("routes.equipamentos"))
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if session["usuario_tipo"] == "admin":
                cursor.execute("""
                    SELECT d.*, l.nome as localizacao_nome,
                           CASE 
                               WHEN a.id IS NOT NULL THEN 'alimentador'
                               WHEN dl.id IS NOT NULL THEN 'datalogger'
                               ELSE 'dispositivo'
                           END as tipo_especifico
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    WHERE d.id = %s
                """, (dispositivo_id,))
            else:
                cursor.execute("""
                    SELECT d.*, l.nome as localizacao_nome,
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
                    WHERE d.id = %s AND ul.usuario_id = %s
                """, (dispositivo_id, session["usuario_id"],))
            
            dispositivo = cursor.fetchone()
            
            if not dispositivo:
                flash("Equipamento não encontrado ou você não tem permissão para editá-lo.", "danger")
                return redirect(url_for("routes.equipamentos"))
            
            if session["usuario_tipo"] == "admin":
                cursor.execute("SELECT id, nome, descricao, tipo FROM localizacoes ORDER BY nome")
            else:
                cursor.execute("""
                    SELECT l.id, l.nome, l.descricao, l.tipo 
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                    ORDER BY l.nome
                """, (session["usuario_id"],))
            
            localizacoes = cursor.fetchall()

            return render_template("editar_equipamento.html", 
                                 dispositivo=dispositivo,
                                 localizacoes=localizacoes)

    except Exception as e:
        print(f"❌ Erro ao carregar equipamento para edição: {e}")
        flash(f"Erro ao carregar equipamento para edição: {str(e)}", "danger")
        return redirect(url_for("routes.equipamentos"))
    finally:
        if conn:
            conn.close()

@routes_bp.route("/equipamentos/<int:dispositivo_id>/atualizar", methods=["POST"])
@login_required
def atualizar_equipamento(dispositivo_id):
    """Atualiza um equipamento existente"""
    try:
        nome = request.form["nome"]
        descricao = request.form.get("descricao", "")
        mac_address = request.form["mac_address"]
        ip_address = request.form.get("ip_address", "")
        tipo = request.form["tipo"]
        modelo = request.form.get("modelo", "")
        localizacao_id = request.form["localizacao_id"]

        if not localizacao_id:
            flash("A localização é obrigatória.", "danger")
            return redirect(url_for("routes.editar_equipamento", dispositivo_id=dispositivo_id))

        conn = db.get_connection()
        if not conn:
            flash("Erro de conexão com o banco de dados", "danger")
            return redirect(url_for("routes.editar_equipamento", dispositivo_id=dispositivo_id))

        with conn.cursor() as cursor:
            # Verificar permissão
            if session["usuario_tipo"] != "admin":
                cursor.execute("""
                    SELECT 1 FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s
                """, (dispositivo_id, session["usuario_id"],))
                if not cursor.fetchone():
                    flash("Você não tem permissão para editar este equipamento.", "danger")
                    return redirect(url_for("routes.equipamentos"))

            # Verificar MAC Address duplicado (excluindo o próprio equipamento)
            cursor.execute("SELECT id FROM dispositivos WHERE mac_address = %s AND id != %s", (mac_address, dispositivo_id))
            if cursor.fetchone():
                flash("MAC Address já está em uso por outro equipamento. Por favor, use um endereço único.", "danger")
                return redirect(url_for("routes.editar_equipamento", dispositivo_id=dispositivo_id))

            cursor.execute("""
                UPDATE dispositivos
                SET nome = %s, descricao = %s, mac_address = %s, ip_address = %s, tipo = %s, modelo = %s, localizacao_id = %s
                WHERE id = %s
            """, (nome, descricao, mac_address, ip_address, tipo, modelo, localizacao_id, dispositivo_id))

            conn.commit()
            flash("Equipamento atualizado com sucesso!", "success")

    except Exception as e:
        print(f"❌ Erro ao atualizar equipamento: {e}")
        flash(f"Erro ao atualizar equipamento: {str(e)}", "danger")
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.ver_equipamento", dispositivo_id=dispositivo_id))

@routes_bp.route("/equipamentos/<int:dispositivo_id>/excluir", methods=["POST"])
@login_required
def excluir_equipamento(dispositivo_id):
    """Exclui um equipamento"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para excluir equipamentos.", "danger")
        return redirect(url_for("routes.equipamentos"))

    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return redirect(url_for("routes.equipamentos"))

    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM dispositivos WHERE id = %s", (dispositivo_id,))
            conn.commit()
            flash("Equipamento excluído com sucesso!", "success")
    except Exception as e:
        print(f"❌ Erro ao excluir equipamento: {e}")
        flash(f"Erro ao excluir equipamento: {str(e)}", "danger")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.equipamentos"))

@routes_bp.route("/localizacoes")
@login_required
def localizacoes():
    """Página de gerenciamento de localizações"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return render_template("localizacoes.html", localizacoes=[])
    
    try:
        with conn.cursor() as cursor:
            if session["usuario_tipo"] == "admin":
                cursor.execute("SELECT id, nome, descricao, tipo FROM localizacoes ORDER BY nome")
            else:
                cursor.execute("""
                    SELECT l.id, l.nome, l.descricao, l.tipo 
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                    ORDER BY l.nome
                """, (session["usuario_id"],))
            
            localizacoes = cursor.fetchall()
            
            localizacoes_dict = [
                {
                    "id": loc[0],
                    "nome": loc[1],
                    "descricao": loc[2],
                    "tipo": loc[3]
                }
                for loc in localizacoes
            ]

            return render_template("localizacoes.html", localizacoes=localizacoes_dict)

    except Exception as e:
        print(f"❌ Erro ao buscar localizações: {e}")
        flash(f"Erro ao carregar localizações: {str(e)}", "danger")
        return render_template("localizacoes.html", localizacoes=[])
    finally:
        if conn:
            conn.close()

@routes_bp.route("/localizacoes/cadastrar")
@login_required
def cadastrar_localizacao():
    """Página de cadastro de nova localização"""
    return render_template("cadastrar_localizacao.html")

@routes_bp.route("/localizacoes/salvar", methods=["POST"])
@login_required
def salvar_localizacao():
    """Salva uma nova localização"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para cadastrar localizações.", "danger")
        return redirect(url_for("routes.localizacoes"))

    try:
        nome = request.form["nome"]
        descricao = request.form.get("descricao", "")
        tipo = request.form.get("tipo", "")

        if not nome:
            flash("O nome da localização é obrigatório.", "danger")
            return redirect(url_for("routes.cadastrar_localizacao"))

        conn = db.get_connection()
        if not conn:
            flash("Erro de conexão com o banco de dados", "danger")
            return redirect(url_for("routes.cadastrar_localizacao"))

        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM localizacoes WHERE nome = %s", (nome,))
            if cursor.fetchone():
                flash("Já existe uma localização com este nome. Por favor, use um nome único.", "danger")
                return redirect(url_for("routes.cadastrar_localizacao"))

            cursor.execute("""
                INSERT INTO localizacoes (nome, descricao, tipo)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (nome, descricao, tipo))
            localizacao_id = cursor.fetchone()[0]

            # Associar ao usuário admin por padrão
            cursor.execute("SELECT id FROM usuarios WHERE tipo = 'admin' LIMIT 1")
            admin_id = cursor.fetchone()[0] if cursor.rowcount > 0 else None
            if admin_id:
                cursor.execute("""
                    INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                    VALUES (%s, %s)
                """, (admin_id, localizacao_id))

            conn.commit()
            flash("Localização cadastrada com sucesso!", "success")

    except Exception as e:
        print(f"❌ Erro ao salvar localização: {e}")
        flash(f"Erro ao cadastrar localização: {str(e)}", "danger")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.localizacoes"))

@routes_bp.route("/localizacoes/<int:localizacao_id>/editar")
@login_required
def editar_localizacao(localizacao_id):
    """Página de edição de localização"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return redirect(url_for("routes.localizacoes"))
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if session["usuario_tipo"] == "admin":
                cursor.execute("SELECT id, nome, descricao, tipo FROM localizacoes WHERE id = %s", (localizacao_id,))
            else:
                cursor.execute("""
                    SELECT l.id, l.nome, l.descricao, l.tipo 
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE l.id = %s AND ul.usuario_id = %s
                """, (localizacao_id, session["usuario_id"],))
            
            localizacao = cursor.fetchone()
            
            if not localizacao:
                flash("Localização não encontrada ou você não tem permissão para editá-la.", "danger")
                return redirect(url_for("routes.localizacoes"))

            return render_template("editar_localizacao.html", localizacao=localizacao)

    except Exception as e:
        print(f"❌ Erro ao carregar localização para edição: {e}")
        flash(f"Erro ao carregar localização para edição: {str(e)}", "danger")
        return redirect(url_for("routes.localizacoes"))
    finally:
        if conn:
            conn.close()

@routes_bp.route("/localizacoes/<int:localizacao_id>/atualizar", methods=["POST"])
@login_required
def atualizar_localizacao(localizacao_id):
    """Atualiza uma localização existente"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para atualizar localizações.", "danger")
        return redirect(url_for("routes.localizacoes"))

    try:
        nome = request.form["nome"]
        descricao = request.form.get("descricao", "")
        tipo = request.form.get("tipo", "")

        if not nome:
            flash("O nome da localização é obrigatório.", "danger")
            return redirect(url_for("routes.editar_localizacao", localizacao_id=localizacao_id))

        conn = db.get_connection()
        if not conn:
            flash("Erro de conexão com o banco de dados", "danger")
            return redirect(url_for("routes.editar_localizacao", localizacao_id=localizacao_id))

        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM localizacoes WHERE nome = %s AND id != %s", (nome, localizacao_id))
            if cursor.fetchone():
                flash("Já existe uma localização com este nome. Por favor, use um nome único.", "danger")
                return redirect(url_for("routes.editar_localizacao", localizacao_id=localizacao_id))

            cursor.execute("""
                UPDATE localizacoes
                SET nome = %s, descricao = %s, tipo = %s
                WHERE id = %s
            """, (nome, descricao, tipo, localizacao_id))
            conn.commit()
            flash("Localização atualizada com sucesso!", "success")

    except Exception as e:
        print(f"❌ Erro ao atualizar localização: {e}")
        flash(f"Erro ao atualizar localização: {str(e)}", "danger")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.localizacoes"))

@routes_bp.route("/localizacoes/<int:localizacao_id>/excluir", methods=["POST"])
@login_required
def excluir_localizacao(localizacao_id):
    """Exclui uma localização"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para excluir localizações.", "danger")
        return redirect(url_for("routes.localizacoes"))

    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return redirect(url_for("routes.localizacoes"))

    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM localizacoes WHERE id = %s", (localizacao_id,))
            conn.commit()
            flash("Localização excluída com sucesso!", "success")
    except Exception as e:
        print(f"❌ Erro ao excluir localização: {e}")
        flash(f"Erro ao excluir localização: {str(e)}", "danger")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.localizacoes"))

@routes_bp.route("/usuarios")
@login_required
def usuarios():
    """Página de gerenciamento de usuários"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para gerenciar usuários.", "danger")
        return redirect(url_for("routes.dashboard"))

    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return render_template("usuarios.html", usuarios=[])
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, nome, email, tipo, ativo FROM usuarios ORDER BY nome")
            usuarios_raw = cursor.fetchall()
            
            usuarios_dict = [
                {
                    "id": u[0],
                    "nome": u[1],
                    "email": u[2],
                    "tipo": u[3],
                    "ativo": u[4]
                }
                for u in usuarios_raw
            ]

            return render_template("usuarios.html", usuarios=usuarios_dict)

    except Exception as e:
        print(f"❌ Erro ao buscar usuários: {e}")
        flash(f"Erro ao carregar usuários: {str(e)}", "danger")
        return render_template("usuarios.html", usuarios=[])
    finally:
        if conn:
            conn.close()

@routes_bp.route("/usuarios/cadastrar")
@login_required
def cadastrar_usuario():
    """Página de cadastro de novo usuário"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para cadastrar usuários.", "danger")
        return redirect(url_for("routes.dashboard"))

    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return render_template("cadastrar_usuario.html", localizacoes=[])
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, nome FROM localizacoes ORDER BY nome")
            localizacoes = cursor.fetchall()
            localizacoes_dict = [
                {
                    "id": loc[0],
                    "nome": loc[1]
                }
                for loc in localizacoes
            ]
            return render_template("cadastrar_usuario.html", localizacoes=localizacoes_dict)
    except Exception as e:
        print(f"❌ Erro ao buscar localizações para cadastro de usuário: {e}")
        flash(f"Erro ao carregar localizações: {str(e)}", "danger")
        return render_template("cadastrar_usuario.html", localizacoes=[])
    finally:
        if conn:
            conn.close()

@routes_bp.route("/usuarios/salvar", methods=["POST"])
@login_required
def salvar_usuario():
    """Salva um novo usuário"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para cadastrar usuários.", "danger")
        return redirect(url_for("routes.usuarios"))

    try:
        nome = request.form["nome"]
        email = request.form["email"]
        senha = request.form["senha"]
        tipo = request.form["tipo"]
        localizacoes_selecionadas = request.form.getlist("localizacoes")

        if not nome or not email or not senha or not tipo:
            flash("Por favor, preencha todos os campos obrigatórios.", "danger")
            return redirect(url_for("routes.cadastrar_usuario"))

        conn = db.get_connection()
        if not conn:
            flash("Erro de conexão com o banco de dados", "danger")
            return redirect(url_for("routes.cadastrar_usuario"))

        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            if cursor.fetchone():
                flash("Já existe um usuário com este email. Por favor, use um email único.", "danger")
                return redirect(url_for("routes.cadastrar_usuario"))

            # A função hash_password agora está em utils.py
            from utils import hash_password
            senha_hash, salt = hash_password(senha)

            cursor.execute("""
                INSERT INTO usuarios (nome, email, senha_hash, salt, tipo, ativo)
                VALUES (%s, %s, %s, %s, %s, true)
                RETURNING id
            """, (nome, email, senha_hash, salt, tipo))
            usuario_id = cursor.fetchone()[0]

            for loc_id in localizacoes_selecionadas:
                cursor.execute("""
                    INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                    VALUES (%s, %s)
                """, (usuario_id, loc_id))

            conn.commit()
            flash("Usuário cadastrado com sucesso!", "success")

    except Exception as e:
        print(f"❌ Erro ao salvar usuário: {e}")
        flash(f"Erro ao cadastrar usuário: {str(e)}", "danger")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.usuarios"))

@routes_bp.route("/usuarios/<int:usuario_id>/editar")
@login_required
def editar_usuario(usuario_id):
    """Página de edição de usuário"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para editar usuários.", "danger")
        return redirect(url_for("routes.dashboard"))

    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return redirect(url_for("routes.usuarios"))
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id, nome, email, tipo, ativo FROM usuarios WHERE id = %s", (usuario_id,))
            usuario = cursor.fetchone()
            
            if not usuario:
                flash("Usuário não encontrado.", "danger")
                return redirect(url_for("routes.usuarios"))

            cursor.execute("SELECT id, nome FROM localizacoes ORDER BY nome")
            todas_localizacoes = cursor.fetchall()

            cursor.execute("SELECT localizacao_id FROM usuario_localizacao WHERE usuario_id = %s", (usuario_id,))
            localizacoes_do_usuario_raw = cursor.fetchall()
            localizacoes_do_usuario = [loc["localizacao_id"] for loc in localizacoes_do_usuario_raw]

            return render_template("editar_usuario.html", 
                                 usuario=usuario,
                                 todas_localizacoes=todas_localizacoes,
                                 localizacoes_do_usuario=localizacoes_do_usuario)

    except Exception as e:
        print(f"❌ Erro ao carregar usuário para edição: {e}")
        flash(f"Erro ao carregar usuário para edição: {str(e)}", "danger")
        return redirect(url_for("routes.usuarios"))
    finally:
        if conn:
            conn.close()

@routes_bp.route("/usuarios/<int:usuario_id>/atualizar", methods=["POST"])
@login_required
def atualizar_usuario(usuario_id):
    """Atualiza um usuário existente"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para atualizar usuários.", "danger")
        return redirect(url_for("routes.dashboard"))

    try:
        nome = request.form["nome"]
        email = request.form["email"]
        tipo = request.form["tipo"]
        ativo = "ativo" in request.form
        senha = request.form.get("senha") # Senha é opcional na atualização
        localizacoes_selecionadas = request.form.getlist("localizacoes")

        if not nome or not email or not tipo:
            flash("Por favor, preencha todos os campos obrigatórios (Nome, Email, Tipo).", "danger")
            return redirect(url_for("routes.editar_usuario", usuario_id=usuario_id))

        conn = db.get_connection()
        if not conn:
            flash("Erro de conexão com o banco de dados", "danger")
            return redirect(url_for("routes.editar_usuario", usuario_id=usuario_id))

        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s AND id != %s", (email, usuario_id))
            if cursor.fetchone():
                flash("Já existe outro usuário com este email. Por favor, use um email único.", "danger")
                return redirect(url_for("routes.editar_usuario", usuario_id=usuario_id))

            update_query = "UPDATE usuarios SET nome = %s, email = %s, tipo = %s, ativo = %s WHERE id = %s"
            update_params = [nome, email, tipo, ativo, usuario_id]

            if senha:
                from utils import hash_password
                senha_hash, salt = hash_password(senha)
                update_query = "UPDATE usuarios SET nome = %s, email = %s, senha_hash = %s, salt = %s, tipo = %s, ativo = %s WHERE id = %s"
                update_params = [nome, email, senha_hash, salt, tipo, ativo, usuario_id]
            
            cursor.execute(update_query, tuple(update_params))

            # Atualizar associações de localização
            cursor.execute("DELETE FROM usuario_localizacao WHERE usuario_id = %s", (usuario_id,))
            for loc_id in localizacoes_selecionadas:
                cursor.execute("""
                    INSERT INTO usuario_localizacao (usuario_id, localizacao_id)
                    VALUES (%s, %s)
                """, (usuario_id, loc_id))

            conn.commit()
            flash("Usuário atualizado com sucesso!", "success")

    except Exception as e:
        print(f"❌ Erro ao atualizar usuário: {e}")
        flash(f"Erro ao atualizar usuário: {str(e)}", "danger")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.usuarios"))

@routes_bp.route("/usuarios/<int:usuario_id>/excluir", methods=["POST"])
@login_required
def excluir_usuario(usuario_id):
    """Exclui um usuário"""
    if session["usuario_tipo"] != "admin":
        flash("Você não tem permissão para excluir usuários.", "danger")
        return redirect(url_for("routes.usuarios"))

    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return redirect(url_for("routes.usuarios"))

    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM usuarios WHERE id = %s", (usuario_id,))
            conn.commit()
            flash("Usuário excluído com sucesso!", "success")
    except Exception as e:
        print(f"❌ Erro ao excluir usuário: {e}")
        flash(f"Erro ao excluir usuário: {str(e)}", "danger")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.usuarios"))

@routes_bp.route("/relatorios")
@login_required
def relatorios():
    """Página de relatórios"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return render_template("relatorios.html", dataloggers=[], dados={})
    
    try:
        with conn.cursor() as cursor:
            if session["usuario_tipo"] == "admin":
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
                cursor.execute("""
                    SELECT d.id, d.nome, l.nome as localizacao_nome, dl.quantidade_sensores,
                           d.mac_address, d.online
                    FROM dispositivos d
                    JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.tipo = 'datalogger' AND ul.usuario_id = %s
                    ORDER BY d.nome
                """, (session["usuario_id"],))
            
            dataloggers_raw = cursor.fetchall()
            
            dataloggers_dict = []
            colunas = ["id", "nome", "localizacao_nome", "quantidade_sensores", "mac_address", "online"]
            
            for datalogger in dataloggers_raw:
                datalogger_dict = dict(zip(colunas, datalogger))
                
                cursor.execute("""
                    SELECT MIN(ls.timestamp), MAX(ls.timestamp), COUNT(ls.id)
                    FROM leituras_sensores ls
                    JOIN sensores s ON ls.sensor_id = s.id
                    WHERE s.datalogger_id = (
                        SELECT dl.id FROM dataloggers dl
                        JOIN dispositivos d ON dl.dispositivo_id = d.id
                        WHERE d.id = %s
                    )
                """, (datalogger_dict["id"],))
                
                periodo = cursor.fetchone()
                
                if periodo and periodo[0] and periodo[1]:
                    try:
                        if hasattr(periodo[0], "strftime"):
                            inicio = periodo[0].strftime("%d/%m/%Y %H:%M")
                            fim = periodo[1].strftime("%d/%m/%Y %H:%M")
                        else:
                            inicio_dt = datetime.strptime(str(periodo[0]), "%Y-%m-%d %H:%M:%S")
                            fim_dt = datetime.strptime(str(periodo[1]), "%Y-%m-%d %H:%M:%S")
                            inicio = inicio_dt.strftime("%d/%m/%Y %H:%M")
                            fim = fim_dt.strftime("%d/%m/%Y %H:%M")
                            
                        datalogger_dict["periodo_inicio"] = inicio
                        datalogger_dict["periodo_fim"] = fim
                        datalogger_dict["total_leituras"] = periodo[2] or 0
                    except Exception as e:
                        print(f"⚠️ Erro ao formatar datas: {e}")
                        datalogger_dict["periodo_inicio"] = str(periodo[0])[:16]
                        datalogger_dict["periodo_fim"] = str(periodo[1])[:16]
                        datalogger_dict["total_leituras"] = periodo[2] or 0
                else:
                    datalogger_dict["periodo_inicio"] = None
                    datalogger_dict["periodo_fim"] = None
                    datalogger_dict["total_leituras"] = 0
                
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
                """, (datalogger_dict["id"],))
                
                sensores = cursor.fetchall()
                datalogger_dict["sensores"] = [
                    {
                        "nome": s[0],
                        "posicao": s[1],
                        "tipo": s[2],
                        "ativo": s[3],
                        "leituras": s[4]
                    } for s in sensores
                ]
                
                dataloggers_dict.append(datalogger_dict)
            
            return render_template("relatorios.html", 
                                 dataloggers=dataloggers_dict, 
                                 dados={})

    except Exception as e:
        print(f"❌ Erro ao buscar dataloggers para relatório: {e}")
        flash(f"Erro ao carregar relatórios: {str(e)}", "danger")
        return render_template("relatorios.html", dataloggers=[], dados={})
    finally:
        if conn:
            conn.close()

@routes_bp.route("/relatorios/dados", methods=["POST"])
@login_required
def obter_dados_relatorio():
    """Obtém dados para o relatório baseado nos filtros (via AJAX) """
    try:
        datalogger_id = request.form.get("datalogger_id")
        data_inicio_str = request.form.get("data_inicio")
        data_fim_str = request.form.get("data_fim")
        
        if not datalogger_id:
            return jsonify({"error": "Selecione um datalogger"}), 400
        
        conn = db.get_connection()
        if not conn:
            return jsonify({"error": "Erro de conexão com o banco"}), 500
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if session["usuario_tipo"] != "admin":
                cursor.execute("""
                    SELECT 1 
                    FROM dispositivos d
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.id = %s AND ul.usuario_id = %s AND d.tipo = 'datalogger'
                """, (datalogger_id, session["usuario_id"],))
                
                if not cursor.fetchone():
                    return jsonify({"error": "Acesso negado a este datalogger"}), 403
            
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
            
            if not periodo_disponivel or not periodo_disponivel["min"] or periodo_disponivel["count"] == 0:
                return jsonify({
                    "error": "Nenhum dado disponível para este datalogger no período selecionado",
                    "dados": {},
                    "estatisticas": {},
                    "periodo_disponivel": None
                })
            
            min_data_db, max_data_db, total_leituras_db = periodo_disponivel["min"], periodo_disponivel["max"], periodo_disponivel["count"]

            data_inicio = datetime.strptime(data_inicio_str, "%Y-%m-%dT%H:%M") if data_inicio_str else min_data_db
            data_fim = datetime.strptime(data_fim_str, "%Y-%m-%dT%H:%M") if data_fim_str else max_data_db

            # Ajustar data_fim para incluir o dia inteiro se for apenas data
            if not data_fim_str or len(data_fim_str) == 10: # Se for apenas YYYY-MM-DD
                data_fim = data_fim.replace(hour=23, minute=59, second=59)

            # Garantir que o período solicitado esteja dentro do disponível
            data_inicio = max(data_inicio, min_data_db)
            data_fim = min(data_fim, max_data_db)

            cursor.execute("""
                SELECT s.id as sensor_id, s.nome as sensor_nome, s.posicao, s.unidade, ls.valor, ls.timestamp
                FROM leituras_sensores ls
                JOIN sensores s ON ls.sensor_id = s.id
                WHERE s.datalogger_id = (
                    SELECT dl.id FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    WHERE d.id = %s
                )
                AND ls.timestamp BETWEEN %s AND %s
                ORDER BY ls.timestamp
            """, (datalogger_id, data_inicio, data_fim))
            
            dados_leituras = cursor.fetchall()
            
            dados_grafico = processar_dados_grafico(dados_leituras)
            estatisticas = calcular_estatisticas(dados_leituras)
            
            return jsonify({
                "status": "sucesso",
                "dados": dados_grafico,
                "estatisticas": estatisticas,
                "periodo_disponivel": {
                    "min": min_data_db.isoformat(),
                    "max": max_data_db.isoformat(),
                    "total_leituras": total_leituras_db
                }
            }), 200

    except Exception as e:
        print(f"❌ Erro ao obter dados do relatório: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@routes_bp.route("/configuracoes")
@login_required
def configuracoes():
    """Página principal de configurações - lista equipamentos"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return render_template("configuracoes.html", alimentadores=[], dataloggers=[])
    
    try:
        with conn.cursor() as cursor:
            # 1. BUSCAR ALIMENTADORES
            if session["usuario_tipo"] == "admin":
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
                """, (session["usuario_id"],))
            
            alimentadores_raw = cursor.fetchall()
            
            alimentadores = []
            colunas_alimentadores = ["id", "nome", "mac_address", "online", "ultima_comunicacao",
                                     "localizacao_nome", "capacidade_racao", "nivel_racao_atual",
                                     "ativa", "porcoes_por_dia"]
            
            for row in alimentadores_raw:
                alm = dict(zip(colunas_alimentadores, row))
                if alm["capacidade_racao"]:
                    alm["capacidade_racao"] = float(alm["capacidade_racao"])
                if alm["nivel_racao_atual"]:
                    alm["nivel_racao_atual"] = float(alm["nivel_racao_atual"])
                alimentadores.append(alm)
            
            # 2. BUSCAR DATALOGGERS
            if session["usuario_tipo"] == "admin":
                cursor.execute("""
                    SELECT 
                        d.id, d.nome, d.mac_address, d.online, d.ultima_comunicacao,
                        l.nome as localizacao_nome,
                        dl.intervalo_leitura
                    FROM dispositivos d
                    JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    WHERE d.tipo = 'datalogger'
                    ORDER BY d.nome
                """)
            else:
                cursor.execute("""
                    SELECT 
                        d.id, d.nome, d.mac_address, d.online, d.ultima_comunicacao,
                        l.nome as localizacao_nome,
                        dl.intervalo_leitura
                    FROM dispositivos d
                    JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE d.tipo = 'datalogger' AND ul.usuario_id = %s
                    ORDER BY d.nome
                """, (session["usuario_id"],))
            
            dataloggers_raw = cursor.fetchall()
            
            dataloggers = []
            colunas_dataloggers = ["id", "nome", "mac_address", "online", "ultima_comunicacao",
                                   "localizacao_nome", "intervalo_leitura"]
            
            for row in dataloggers_raw:
                dtl = dict(zip(colunas_dataloggers, row))
                dataloggers.append(dtl)

            return render_template("configuracoes.html", 
                                 alimentadores=alimentadores, 
                                 dataloggers=dataloggers)

    except Exception as e:
        print(f"❌ Erro ao carregar configurações: {e}")
        flash(f"Erro ao carregar configurações: {str(e)}", "danger")
        return render_template("configuracoes.html", alimentadores=[], dataloggers=[])
    finally:
        if conn:
            conn.close()

@routes_bp.route("/configuracoes/alimentador/<int:alimentador_id>")
@login_required
def configurar_alimentador(alimentador_id):
    """Página de configuração de um alimentador específico"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return redirect(url_for("routes.configuracoes"))
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if session["usuario_tipo"] == "admin":
                cursor.execute("""
                    SELECT d.id, d.nome, d.mac_address, d.localizacao_id, l.nome as localizacao_nome,
                           a.id as alimentador_id, a.capacidade_racao, a.vazao_media,
                           ca.ativa, ca.horario_inicio, ca.horario_fim, ca.intervalo_alimentacao, ca.quantidade_por_alimentacao, ca.dias_semana,
                           cal.constante_a, cal.constante_b, cal.tempo_acionamento
                    FROM dispositivos d
                    JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    LEFT JOIN config_alimentadores ca ON a.id = ca.alimentador_id
                    LEFT JOIN calibracao_alimentadores cal ON a.id = cal.alimentador_id
                    WHERE a.id = %s
                """, (alimentador_id,))
            else:
                cursor.execute("""
                    SELECT d.id, d.nome, d.mac_address, d.localizacao_id, l.nome as localizacao_nome,
                           a.id as alimentador_id, a.capacidade_racao, a.vazao_media,
                           ca.ativa, ca.horario_inicio, ca.horario_fim, ca.intervalo_alimentacao, ca.quantidade_por_alimentacao, ca.dias_semana,
                           cal.constante_a, cal.constante_b, cal.tempo_acionamento
                    FROM dispositivos d
                    JOIN alimentadores a ON d.id = a.dispositivo_id
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    LEFT JOIN config_alimentadores ca ON a.id = ca.alimentador_id
                    LEFT JOIN calibracao_alimentadores cal ON a.id = cal.alimentador_id
                    WHERE a.id = %s AND ul.usuario_id = %s
                """, (alimentador_id, session["usuario_id"],))
            
            alimentador = cursor.fetchone()
            
            if not alimentador:
                flash("Alimentador não encontrado ou você não tem permissão para configurá-lo.", "danger")
                return redirect(url_for("routes.configuracoes"))

            # Formatar horários para exibição no formulário
            if alimentador["horario_inicio"]:
                alimentador["horario_inicio"] = str(alimentador["horario_inicio"])
            if alimentador["horario_fim"]:
                alimentador["horario_fim"] = str(alimentador["horario_fim"])

            # Buscar todas as localizações para o dropdown de mudança de localização
            if session["usuario_tipo"] == "admin":
                cursor.execute("SELECT id, nome FROM localizacoes ORDER BY nome")
            else:
                cursor.execute("""
                    SELECT l.id, l.nome 
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                    ORDER BY l.nome
                """, (session["usuario_id"],))
            todas_localizacoes = cursor.fetchall()

            return render_template("configurar_alimentador.html", 
                                 alimentador=alimentador,
                                 todas_localizacoes=todas_localizacoes)

    except Exception as e:
        print(f"❌ Erro ao carregar configuração do alimentador: {e}")
        flash(f"Erro ao carregar configuração do alimentador: {str(e)}", "danger")
        return redirect(url_for("routes.configuracoes"))
    finally:
        if conn:
            conn.close()

@routes_bp.route("/configuracoes/alimentador/<int:alimentador_id>/salvar", methods=["POST"])
@login_required
def salvar_config_alimentador(alimentador_id):
    """Salva as configurações de um alimentador"""
    try:
        # Dados do dispositivo
        nome_dispositivo = request.form["nome_dispositivo"]
        modelo_dispositivo = request.form.get("modelo_dispositivo", "")
        descricao_dispositivo = request.form.get("descricao_dispositivo", "")
        localizacao_id = request.form["localizacao_id"]

        # Dados do alimentador
        capacidade_racao = float(request.form["capacidade_racao"])
        vazao_media = float(request.form["vazao_media"])

        # Dados de configuração
        ativa = "ativa" in request.form
        horario_inicio_str = request.form.get("horario_inicio")
        horario_fim_str = request.form.get("horario_fim")
        intervalo_alimentacao = int(request.form.get("intervalo_alimentacao", 0))
        quantidade_por_alimentacao = float(request.form.get("quantidade_por_alimentacao", 0))
        dias_semana = request.form.getlist("dias_semana")

        # Dados de calibração
        constante_a = float(request.form.get("constante_a", 0))
        constante_b = float(request.form.get("constante_b", 0))
        tempo_acionamento = float(request.form.get("tempo_acionamento", 0))

        conn = db.get_connection()
        if not conn:
            flash("Erro de conexão com o banco de dados", "danger")
            return redirect(url_for("routes.configurar_alimentador", alimentador_id=alimentador_id))

        with conn.cursor() as cursor:
            # Verificar permissão
            if session["usuario_tipo"] != "admin":
                cursor.execute("""
                    SELECT 1 FROM alimentadores a
                    JOIN dispositivos d ON a.dispositivo_id = d.id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE a.id = %s AND ul.usuario_id = %s
                """, (alimentador_id, session["usuario_id"],))
                if not cursor.fetchone():
                    flash("Você não tem permissão para configurar este alimentador.", "danger")
                    return redirect(url_for("routes.configuracoes"))

            # 1. Atualizar dispositivo
            cursor.execute("""
                UPDATE dispositivos
                SET nome = %s, modelo = %s, descricao = %s, localizacao_id = %s
                WHERE id = (SELECT dispositivo_id FROM alimentadores WHERE id = %s)
            """, (nome_dispositivo, modelo_dispositivo, descricao_dispositivo, localizacao_id, alimentador_id))

            # 2. Atualizar alimentador
            cursor.execute("""
                UPDATE alimentadores
                SET capacidade_racao = %s, vazao_media = %s
                WHERE id = %s
            """, (capacidade_racao, vazao_media, alimentador_id))

            # 3. Atualizar configuração do alimentador
            horario_inicio = datetime.strptime(horario_inicio_str, "%H:%M").time() if horario_inicio_str else None
            horario_fim = datetime.strptime(horario_fim_str, "%H:%M").time() if horario_fim_str else None
            dias_semana_str = ",".join(dias_semana)

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
            """, (alimentador_id, ativa, horario_inicio, horario_fim, 
                  intervalo_alimentacao, quantidade_por_alimentacao, dias_semana_str))

            # 4. Atualizar calibração do alimentador
            cursor.execute("""
                INSERT INTO calibracao_alimentadores (alimentador_id, constante_a, constante_b, tempo_acionamento)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (alimentador_id) DO UPDATE SET
                    constante_a = EXCLUDED.constante_a,
                    constante_b = EXCLUDED.constante_b,
                    tempo_acionamento = EXCLUDED.tempo_acionamento,
                    updated_at = CURRENT_TIMESTAMP
            """, (alimentador_id, constante_a, constante_b, tempo_acionamento))

            conn.commit()
            flash("Configurações do alimentador salvas com sucesso!", "success")

    except Exception as e:
        print(f"❌ Erro ao salvar configuração do alimentador: {e}")
        flash(f"Erro ao salvar configuração do alimentador: {str(e)}", "danger")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.configurar_alimentador", alimentador_id=alimentador_id))

@routes_bp.route("/configuracoes/datalogger/<int:datalogger_id>")
@login_required
def configurar_datalogger(datalogger_id):
    """Página de configuração de um datalogger específico"""
    conn = db.get_connection()
    if not conn:
        flash("Erro de conexão com o banco de dados", "danger")
        return redirect(url_for("routes.configuracoes"))
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if session["usuario_tipo"] == "admin":
                cursor.execute("""
                    SELECT d.id, d.nome, d.mac_address, d.localizacao_id, l.nome as localizacao_nome,
                           dl.id as datalogger_id, dl.intervalo_leitura
                    FROM dispositivos d
                    JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    WHERE dl.id = %s
                """, (datalogger_id,))
            else:
                cursor.execute("""
                    SELECT d.id, d.nome, d.mac_address, d.localizacao_id, l.nome as localizacao_nome,
                           dl.id as datalogger_id, dl.intervalo_leitura
                    FROM dispositivos d
                    JOIN dataloggers dl ON d.id = dl.dispositivo_id
                    LEFT JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE dl.id = %s AND ul.usuario_id = %s
                """, (datalogger_id, session["usuario_id"],))
            
            datalogger = cursor.fetchone()
            
            if not datalogger:
                flash("Datalogger não encontrado ou você não tem permissão para configurá-lo.", "danger")
                return redirect(url_for("routes.configuracoes"))

            # Buscar sensores do datalogger
            cursor.execute("""
                SELECT id, nome, tipo, unidade, posicao, endereco, ativo
                FROM sensores
                WHERE datalogger_id = %s
                ORDER BY posicao
            """, (datalogger["datalogger_id"],))
            sensores = cursor.fetchall()
            datalogger["sensores"] = sensores

            # Buscar limites de temperatura para a localização do datalogger
            cursor.execute("""
                SELECT tipo_sensor, maximo, minimo
                FROM limites_temperatura
                WHERE localizacao_id = %s
            """, (datalogger["localizacao_id"],))
            limites_temperatura = cursor.fetchall()
            datalogger["limites_temperatura"] = {l["tipo_sensor"]: {"max": l["maximo"], "min": l["minimo"]} for l in limites_temperatura}

            # Buscar todas as localizações para o dropdown de mudança de localização
            if session["usuario_tipo"] == "admin":
                cursor.execute("SELECT id, nome FROM localizacoes ORDER BY nome")
            else:
                cursor.execute("""
                    SELECT l.id, l.nome 
                    FROM localizacoes l
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE ul.usuario_id = %s
                    ORDER BY l.nome
                """, (session["usuario_id"],))
            todas_localizacoes = cursor.fetchall()

            return render_template("configurar_datalogger.html", 
                                 datalogger=datalogger,
                                 todas_localizacoes=todas_localizacoes)

    except Exception as e:
        print(f"❌ Erro ao carregar configuração do datalogger: {e}")
        flash(f"Erro ao carregar configuração do datalogger: {str(e)}", "danger")
        return redirect(url_for("routes.configuracoes"))
    finally:
        if conn:
            conn.close()

@routes_bp.route("/configuracoes/datalogger/<int:datalogger_id>/salvar", methods=["POST"])
@login_required
def salvar_config_datalogger(datalogger_id):
    """Salva as configurações de um datalogger"""
    try:
        # Dados do dispositivo
        nome_dispositivo = request.form["nome_dispositivo"]
        modelo_dispositivo = request.form.get("modelo_dispositivo", "")
        descricao_dispositivo = request.form.get("descricao_dispositivo", "")
        localizacao_id = request.form["localizacao_id"]

        # Dados do datalogger
        intervalo_leitura = int(request.form.get("intervalo_leitura", 60))

        # Dados dos sensores (para atualização de nome/posicao/ativo)
        sensores_data = {}
        for key, value in request.form.items():
            if key.startswith("sensor_nome_"):
                sensor_id = key.replace("sensor_nome_", "")
                sensores_data[sensor_id] = {"nome": value}
            elif key.startswith("sensor_posicao_"):
                sensor_id = key.replace("sensor_posicao_", "")
                if sensor_id not in sensores_data: sensores_data[sensor_id] = {}
                sensores_data[sensor_id]["posicao"] = value
            elif key.startswith("sensor_ativo_"):
                sensor_id = key.replace("sensor_ativo_", "")
                if sensor_id not in sensores_data: sensores_data[sensor_id] = {}
                sensores_data[sensor_id]["ativo"] = True

        # Limites de temperatura
        limites_data = {}
        for key, value in request.form.items():
            if key.startswith("limite_max_"):
                tipo_sensor = key.replace("limite_max_", "")
                if tipo_sensor not in limites_data: limites_data[tipo_sensor] = {}
                limites_data[tipo_sensor]["max"] = float(value)
            elif key.startswith("limite_min_"):
                tipo_sensor = key.replace("limite_min_", "")
                if tipo_sensor not in limites_data: limites_data[tipo_sensor] = {}
                limites_data[tipo_sensor]["min"] = float(value)

        conn = db.get_connection()
        if not conn:
            flash("Erro de conexão com o banco de dados", "danger")
            return redirect(url_for("routes.configurar_datalogger", datalogger_id=datalogger_id))

        with conn.cursor() as cursor:
            # Verificar permissão
            if session["usuario_tipo"] != "admin":
                cursor.execute("""
                    SELECT 1 FROM dataloggers dl
                    JOIN dispositivos d ON dl.dispositivo_id = d.id
                    JOIN localizacoes l ON d.localizacao_id = l.id
                    JOIN usuario_localizacao ul ON l.id = ul.localizacao_id
                    WHERE dl.id = %s AND ul.usuario_id = %s
                """, (datalogger_id, session["usuario_id"],))
                if not cursor.fetchone():
                    flash("Você não tem permissão para configurar este datalogger.", "danger")
                    return redirect(url_for("routes.configuracoes"))

            # 1. Atualizar dispositivo
            cursor.execute("""
                UPDATE dispositivos
                SET nome = %s, modelo = %s, descricao = %s, localizacao_id = %s
                WHERE id = (SELECT dispositivo_id FROM dataloggers WHERE id = %s)
            """, (nome_dispositivo, modelo_dispositivo, descricao_dispositivo, localizacao_id, datalogger_id))

            # 2. Atualizar datalogger
            cursor.execute("""
                UPDATE dataloggers
                SET intervalo_leitura = %s
                WHERE id = %s
            """, (intervalo_leitura, datalogger_id))

            # 3. Atualizar sensores
            for sensor_id, data in sensores_data.items():
                ativo = data.get("ativo", False)
                cursor.execute("""
                    UPDATE sensores
                    SET nome = %s, posicao = %s, ativo = %s
                    WHERE id = %s AND datalogger_id = %s
                """, (data["nome"], data["posicao"], ativo, sensor_id, datalogger_id))
            
            # 4. Atualizar limites de temperatura
            for tipo_sensor, valores in limites_data.items():
                cursor.execute("""
                    INSERT INTO limites_temperatura (localizacao_id, tipo_sensor, maximo, minimo)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (localizacao_id, tipo_sensor) DO UPDATE SET
                        maximo = EXCLUDED.maximo,
                        minimo = EXCLUDED.minimo,
                        updated_at = CURRENT_TIMESTAMP
                """, (localizacao_id, tipo_sensor, valores["max"], valores["min"])) # localizacao_id vem do dispositivo

            conn.commit()
            flash("Configurações do datalogger salvas com sucesso!", "success")

    except Exception as e:
        print(f"❌ Erro ao salvar configuração do datalogger: {e}")
        flash(f"Erro ao salvar configuração do datalogger: {str(e)}", "danger")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
    
    return redirect(url_for("routes.configurar_datalogger", datalogger_id=datalogger_id))

# ============================================
# Verificador de equipamentos offline em background
# ============================================

def verificar_equipamentos_offline_auto():
    """Verifica equipamentos que estão offline e atualiza o status no banco de dados"""
    print("⚙️ Executando verificador de equipamentos offline...")
    conn = None
    try:
        conn = db.get_connection()
        if not conn:
            print("❌ Erro: Não foi possível conectar ao banco de dados para verificar equipamentos offline.")
            return
        
        with conn.cursor() as cursor:
            # Define um limite de tempo para considerar um equipamento offline (ex: 5 minutos)
            offline_threshold = datetime.now() - timedelta(minutes=5)
            
            cursor.execute("""
                SELECT id, mac_address, nome, tipo
                FROM dispositivos
                WHERE online = true AND ultima_comunicacao < %s
            """, (offline_threshold,))
            
            equipamentos_offline = cursor.fetchall()
            
            if equipamentos_offline:
                for eq_id, mac, nome, tipo in equipamentos_offline:
                    cursor.execute("UPDATE dispositivos SET online = false WHERE id = %s", (eq_id,))
                    print(f"🔴 Equipamento {nome} ({tipo}, MAC: {mac}) marcado como offline.")
                conn.commit()
                print(f"✅ {len(equipamentos_offline)} equipamento(s) marcado(s) como offline.")
            else:
                print("✅ Nenhum equipamento novo offline encontrado.")
                
    except Exception as e:
        print(f"❌ Erro no verificador automático de offline: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def iniciar_verificador_offline():
    """Inicia o scheduler para verificar equipamentos offline"""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        # Verifica a cada 60 segundos
        scheduler.add_job(func=verificar_equipamentos_offline_auto, trigger="interval", seconds=60)
        scheduler.start()
        print("✅ Verificador de equipamentos offline iniciado (a cada 60 segundos)")
    except ImportError:
        print("⚠️ APScheduler não instalado. Instale com: pip install apscheduler")
    except Exception as e:
        print(f"⚠️ Erro ao iniciar verificador: {e}")
