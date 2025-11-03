from flask import Flask, render_template, redirect, url_for, flash, session, request, jsonify, send_file
from functools import wraps
from datetime import datetime
import json
from io import BytesIO
import pandas as pd
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui_mude_em_producao'

# ===== FUNÇÕES AUXILIARES =====

def get_cor_status(status):
    cores = {
        'livre': 'success',
        'ocupada': 'danger',
        'manutencao': 'warning',
        'higienizacao': 'info',
        'offline': 'secondary',
        'aguardando_qualidade': 'warning'
    }
    return cores.get(status, 'secondary')

def get_equipamento_por_id(equip_id):
    return next((e for e in equipamentos if e['id'] == equip_id), None)

def get_sensor_por_id(sensor_id):
    return next((s for s in sensores if s['id'] == sensor_id), None)

# ===== DADOS MOCKADOS =====

usuarios = {
    'operador': {'senha': '123', 'tipo': 'operador', 'nome': 'João Operador', 'email': 'operador@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'operador': True, 'relatorios': False}},
    'ti': {'senha': '123', 'tipo': 'ti', 'nome': 'Maria TI', 'email': 'ti@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'operador': True, 'ti': True, 'relatorios': True}},
    'manutencao': {'senha': '123', 'tipo': 'manutencao', 'nome': 'Carlos Manutenção', 'email': 'manutencao@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'manutencao': True, 'relatorios': True}},
    'higienizacao': {'senha': '123', 'tipo': 'higienizacao', 'nome': 'Ana Higienização', 'email': 'higienizacao@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'higienizacao': True, 'relatorios': True}},
    'qualidade': {'senha': '123', 'tipo': 'qualidade', 'nome': 'Pedro Qualidade', 'email': 'qualidade@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'qualidade': True, 'relatorios': True}}
}

sensores = [
    {
        'id': 1,
        'nome': 'Sensor-1',
        'tipo_comunicacao': 'rede',
        'config': {
            'ip': '192.168.1.254',
            'porta': '80',
            'canal': '1'
        },
        'temp_min': 20,
        'temp_max': 80,
        'alerta_ativo': True,
        'status_teste': None,
        'ativo': True
    },
    {
        'id': 2,
        'nome': 'Sensor-2',
        'tipo_comunicacao': 'rede',
        'config': {
            'ip': '192.168.1.254',
            'porta': '80',
            'canal': '2'
        },
        'temp_min': 20,
        'temp_max': 80,
        'alerta_ativo': True,
        'status_teste': None,
        'ativo': True
    }
]

equipamentos = [
    {'id': 1, 'nome': 'Estufa 01', 'tipo': 'estufa', 'status': 'livre', 'icone': '🌡️', 'processo': None, 'manutencao': None, 'higienizacao': None, 'sensor_id': 1, 'descricao': 'Estufa principal', 'localizacao': 'Galpão A', 'ativo': True, 'campos_personalizados': []},
    {'id': 2, 'nome': 'Estufa 02', 'tipo': 'estufa', 'status': 'ocupada', 'icone': '🌡️', 'processo': {'produto': 'Tomates', 'ordem_producao': 'OP-001', 'duracao': '08:00', 'carregado_as': '14:30', 'responsavel': 'João', 'data_inicio': '2024-10-30'}, 'manutencao': None, 'higienizacao': None, 'sensor_id': 2, 'descricao': 'Estufa secundária', 'localizacao': 'Galpão A', 'ativo': True, 'campos_personalizados': []},
    {'id': 3, 'nome': 'Autoclave 01', 'tipo': 'autoclave', 'status': 'livre', 'icone': '⚗️', 'processo': None, 'manutencao': None, 'higienizacao': None, 'sensor_id': None, 'descricao': 'Autoclave', 'localizacao': 'Lab', 'ativo': True, 'campos_personalizados': []}
]

icones_disponiveis = {
    'estufa': ['🌡️', '🔥', '♨️'],
    'autoclave': ['⚗️', '🧪', '🔬'],
    'reator': ['🏭', '⚙️'],
    'outro': ['📦', '🔧']
}

grupos_usuarios = {
    'Operadores': {'id': 1, 'nome': 'Operadores', 'descricao': 'Operadores de produção', 'cor': '#4A90E2', 'permissoes': {'dashboard': True, 'operador': True}},
    'TI': {'id': 2, 'nome': 'TI', 'descricao': 'TI - Acesso total', 'cor': '#ef4444', 'permissoes': {'dashboard': True, 'operador': True, 'ti': True}}
}

# Layouts para relatórios
layouts_relatorios = {
    'layout_padrao_excel': {
        'id': 'layout_padrao_excel',
        'nome': 'Layout Padrão Excel',
        'tipo': 'excel',
        'config': {
            'cabecalho': {
                'titulo': 'RELATÓRIO DE PRODUÇÃO',
                'subtitulo': 'Sistema de Monitoramento',
                'cor_fundo': '#4A90E2',
                'cor_texto': '#FFFFFF'
            },
            'tabela': {
                'cor_cabecalho': '#4A90E2',
                'cor_linhas_alternadas': True
            }
        }
    },
    'layout_padrao_pdf': {
        'id': 'layout_padrao_pdf',
        'nome': 'Layout Padrão PDF',
        'tipo': 'pdf',
        'config': {
            'cabecalho': {
                'titulo': 'RELATÓRIO DE PRODUÇÃO',
                'subtitulo': 'Sistema de Monitoramento',
                'logo': None
            },
            'rodape': {
                'texto': 'Gerado automaticamente pelo Sistema de Monitoramento',
                'numeracao': True
            }
        }
    }
}

relatorios_personalizados = {
    'producao_diaria': {
        'id': 'producao_diaria',
        'nome': 'Produção Diária',
        'descricao': 'Relatório de produção',
        'tipo': 'processos',
        'campos': ['equipamento', 'produto', 'ordem_producao', 'responsavel', 'data_finalizacao', 'status_qualidade'],
        'filtros': [
            {'nome': 'data_inicio', 'label': 'Data Início', 'tipo': 'date'},
            {'nome': 'data_fim', 'label': 'Data Fim', 'tipo': 'date'},
            {'nome': 'equipamento_id', 'label': 'Equipamento', 'tipo': 'select'}
        ],
        'formatos': ['excel', 'pdf'],
        'layout_excel': 'layout_padrao_excel',
        'layout_pdf': 'layout_padrao_pdf',
        'ativo': True
    }
}

processos_finalizados = []
historico_processos = []

# Context processor
@app.context_processor
def inject_globals():
    return {
        'usuarios': usuarios,
        'grupos_usuarios': grupos_usuarios,
        'relatorios_personalizados': relatorios_personalizados,
        'layouts_relatorios': layouts_relatorios,
        'sensores': sensores,
        'get_cor_status': get_cor_status
    }

# ===== DECORADORES =====

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            flash('Por favor, faça login.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def tipo_usuario_required(*tipos_permitidos):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'usuario' not in session:
                flash('Por favor, faça login.', 'warning')
                return redirect(url_for('login'))
            if session.get('tipo_usuario') == 'ti':
                return f(*args, **kwargs)
            if session.get('tipo_usuario') not in tipos_permitidos:
                flash('Sem permissão.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ===== ROTAS =====

@app.route('/')
def index():
    if 'usuario' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        senha = request.form.get('senha')
        
        if usuario in usuarios and usuarios[usuario]['senha'] == senha:
            if not usuarios[usuario]['ativo']:
                flash('Usuário inativo! Contate o administrador.', 'danger')
                return render_template('login.html')
            
            session['usuario'] = usuario
            session['tipo_usuario'] = usuarios[usuario]['tipo']
            session['nome_usuario'] = usuarios[usuario]['nome']
            flash(f'Bem-vindo, {usuarios[usuario]["nome"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuário ou senha incorretos!', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', equipamentos=equipamentos)

@app.route('/operador')
@login_required
def operador():
    return render_template('operador.html', equipamentos=equipamentos)

@app.route('/gerenciar/<int:equip_id>', methods=['GET', 'POST'])
@login_required
def gerenciar(equip_id):
    equipamento = get_equipamento_por_id(equip_id)
    if not equipamento:
        flash('Equipamento não encontrado!', 'danger')
        return redirect(url_for('operador'))
    
    if equipamento['status'] == 'aguardando_qualidade' and session.get('tipo_usuario') not in ['qualidade', 'ti']:
        flash('Este equipamento está aguardando validação da qualidade!', 'warning')
        return redirect(url_for('operador'))
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        if acao == 'iniciar':
            equipamento['processo'] = {
                'produto': request.form.get('produto'),
                'ordem_producao': request.form.get('ordem_producao'),
                'duracao': request.form.get('duracao'),
                'carregado_as': request.form.get('carregado_as'),
                'responsavel': request.form.get('responsavel'),
                'data_inicio': datetime.now().strftime('%Y-%m-%d')
            }
            equipamento['status'] = 'ocupada'
            flash('Processo iniciado!', 'success')
        elif acao == 'finalizar':
            processo_finalizado = {
                'id': len(processos_finalizados) + 1,
                'equipamento': equipamento['nome'],
                'equipamento_id': equip_id,
                'produto': equipamento['processo']['produto'],
                'ordem_producao': equipamento['processo']['ordem_producao'],
                'responsavel': equipamento['processo']['responsavel'],
                'data_finalizacao': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'status_qualidade': 'pendente'
            }
            processos_finalizados.append(processo_finalizado)
            
            equipamento['processo'] = None
            equipamento['status'] = 'aguardando_qualidade'
            flash('Processo finalizado! Aguardando validação da qualidade.', 'info')
        return redirect(url_for('operador'))
    
    return render_template('gerenciar.html', equipamento=equipamento)

@app.route('/ti')
@login_required
@tipo_usuario_required('ti')
def ti():
    return render_template('ti.html',
                         equipamentos=equipamentos,
                         usuarios=usuarios,
                         grupos_usuarios=grupos_usuarios,
                         relatorios_personalizados=relatorios_personalizados,
                         sensores=sensores)

@app.route('/ti/equipamentos', methods=['GET', 'POST'])
@login_required
@tipo_usuario_required('ti')
def ti_equipamentos():
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'adicionar':
            novo_id = max([e['id'] for e in equipamentos]) + 1 if equipamentos else 1
            sensor_id = request.form.get('sensor_id')
            
            novo = {
                'id': novo_id,
                'nome': request.form.get('nome'),
                'tipo': request.form.get('tipo'),
                'status': 'livre',
                'icone': request.form.get('icone', '📦'),
                'descricao': request.form.get('descricao', ''),
                'localizacao': request.form.get('localizacao', ''),
                'processo': None,
                'manutencao': None,
                'higienizacao': None,
                'ativo': True,
                'campos_personalizados': [],
                'sensor_id': int(sensor_id) if sensor_id and sensor_id != '' else None
            }
            equipamentos.append(novo)
            flash(f'Equipamento {novo["nome"]} criado!', 'success')
            return redirect(url_for('ti_equipamentos'))
        
        elif acao == 'editar':
            equip_id = int(request.form.get('equip_id'))
            equip = get_equipamento_por_id(equip_id)
            if equip:
                equip['nome'] = request.form.get('nome')
                equip['tipo'] = request.form.get('tipo')
                equip['icone'] = request.form.get('icone')
                equip['descricao'] = request.form.get('descricao', '')
                equip['localizacao'] = request.form.get('localizacao', '')
                
                sensor_id = request.form.get('sensor_id')
                equip['sensor_id'] = int(sensor_id) if sensor_id and sensor_id != '' else None
                
                flash('Equipamento atualizado!', 'success')
            return redirect(url_for('ti_equipamentos'))
        
        elif acao == 'excluir':
            equip_id = int(request.form.get('equip_id'))
            equip = get_equipamento_por_id(equip_id)
            if equip and equip['status'] == 'livre':
                equipamentos.remove(equip)
                flash('Equipamento excluído!', 'success')
            else:
                flash('Não é possível excluir! O equipamento está em uso.', 'danger')
            return redirect(url_for('ti_equipamentos'))
        
        elif acao == 'ativar_desativar':
            equip_id = int(request.form.get('equip_id'))
            equip = get_equipamento_por_id(equip_id)
            if equip:
                equip['ativo'] = not equip.get('ativo', True)
                status = 'ativado' if equip['ativo'] else 'desativado'
                flash(f'Equipamento {status}!', 'success')
            return redirect(url_for('ti_equipamentos'))
    
    return render_template('ti_equipamentos.html', equipamentos=equipamentos, icones_disponiveis=icones_disponiveis, sensores=sensores)

@app.route('/ti/sensores', methods=['GET', 'POST'])
@login_required
@tipo_usuario_required('ti')
def ti_sensores():
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'adicionar':
            novo_id = max([s['id'] for s in sensores]) + 1 if sensores else 1
            tipo_com = request.form.get('tipo_comunicacao')
            
            config = {}
            if tipo_com == 'rede':
                config = {
                    'ip': request.form.get('ip'),
                    'porta': request.form.get('porta'),
                    'canal': request.form.get('canal')
                }
            elif tipo_com == 'usb_com':
                config = {
                    'porta_com': request.form.get('porta_com'),
                    'baud_rate': request.form.get('baud_rate')
                }
            elif tipo_com == 'i2c':
                config = {
                    'endereco': request.form.get('endereco'),
                    'barramento': request.form.get('barramento')
                }
            elif tipo_com == 'serial':
                config = {
                    'porta': request.form.get('porta_serial'),
                    'baud_rate': request.form.get('baud_rate_serial')
                }
            elif tipo_com == 'rs232':
                config = {
                    'porta': request.form.get('porta_rs232'),
                    'baud_rate': request.form.get('baud_rate_rs232'),
                    'data_bits': request.form.get('data_bits'),
                    'stop_bits': request.form.get('stop_bits'),
                    'parity': request.form.get('parity')
                }
            elif tipo_com == 'modbus':
                config = {
                    'endereco_escravo': request.form.get('endereco_escravo'),
                    'porta': request.form.get('porta_modbus'),
                    'baud_rate': request.form.get('baud_rate_modbus')
                }
            
            novo_sensor = {
                'id': novo_id,
                'nome': request.form.get('nome'),
                'tipo_comunicacao': tipo_com,
                'config': config,
                'temp_min': int(request.form.get('temp_min')) if request.form.get('temp_min') else None,
                'temp_max': int(request.form.get('temp_max')) if request.form.get('temp_max') else None,
                'alerta_ativo': request.form.get('alerta_ativo') == 'on',
                'status_teste': None,
                'ativo': True
            }
            sensores.append(novo_sensor)
            flash(f'Sensor {novo_sensor["nome"]} criado com sucesso!', 'success')
            return redirect(url_for('ti_sensores'))
        
        elif acao == 'editar':
            sensor_id = int(request.form.get('sensor_id'))
            sensor = get_sensor_por_id(sensor_id)
            if sensor:
                sensor['nome'] = request.form.get('nome')
                tipo_com = request.form.get('tipo_comunicacao')
                sensor['tipo_comunicacao'] = tipo_com
                
                config = {}
                if tipo_com == 'rede':
                    config = {
                        'ip': request.form.get('ip'),
                        'porta': request.form.get('porta'),
                        'canal': request.form.get('canal')
                    }
                elif tipo_com == 'usb_com':
                    config = {
                        'porta_com': request.form.get('porta_com'),
                        'baud_rate': request.form.get('baud_rate')
                    }
                elif tipo_com == 'i2c':
                    config = {
                        'endereco': request.form.get('endereco'),
                        'barramento': request.form.get('barramento')
                    }
                elif tipo_com == 'serial':
                    config = {
                        'porta': request.form.get('porta_serial'),
                        'baud_rate': request.form.get('baud_rate_serial')
                    }
                elif tipo_com == 'rs232':
                    config = {
                        'porta': request.form.get('porta_rs232'),
                        'baud_rate': request.form.get('baud_rate_rs232'),
                        'data_bits': request.form.get('data_bits'),
                        'stop_bits': request.form.get('stop_bits'),
                        'parity': request.form.get('parity')
                    }
                elif tipo_com == 'modbus':
                    config = {
                        'endereco_escravo': request.form.get('endereco_escravo'),
                        'porta': request.form.get('porta_modbus'),
                        'baud_rate': request.form.get('baud_rate_modbus')
                    }
                
                sensor['config'] = config
                sensor['temp_min'] = int(request.form.get('temp_min')) if request.form.get('temp_min') else None
                sensor['temp_max'] = int(request.form.get('temp_max')) if request.form.get('temp_max') else None
                sensor['alerta_ativo'] = request.form.get('alerta_ativo') == 'on'
                
                flash('Sensor atualizado!', 'success')
            return redirect(url_for('ti_sensores'))
        
        elif acao == 'excluir':
            sensor_id = int(request.form.get('sensor_id'))
            sensor = get_sensor_por_id(sensor_id)
            if sensor:
                # Verificar se algum equipamento usa este sensor
                em_uso = any(e.get('sensor_id') == sensor_id for e in equipamentos)
                if em_uso:
                    flash('Não é possível excluir! Este sensor está sendo usado por um equipamento.', 'danger')
                else:
                    sensores.remove(sensor)
                    flash('Sensor excluído!', 'success')
            return redirect(url_for('ti_sensores'))
        
        elif acao == 'ativar_desativar':
            sensor_id = int(request.form.get('sensor_id'))
            sensor = get_sensor_por_id(sensor_id)
            if sensor:
                sensor['ativo'] = not sensor.get('ativo', True)
                status = 'ativado' if sensor['ativo'] else 'desativado'
                flash(f'Sensor {status}!', 'success')
            return redirect(url_for('ti_sensores'))
    
    return render_template('ti_sensores.html', sensores=sensores)

@app.route('/ti/sensores/testar/<int:sensor_id>', methods=['POST'])
@login_required
@tipo_usuario_required('ti')
def testar_sensor(sensor_id):
    sensor = get_sensor_por_id(sensor_id)
    if not sensor:
        return jsonify({'sucesso': False, 'mensagem': 'Sensor não encontrado'}), 404
    
    # Simulação de teste de comunicação
    import random
    sucesso = random.choice([True, True, True, False])  # 75% de chance de sucesso
    
    if sucesso:
        sensor['status_teste'] = {
            'status': 'sucesso',
            'mensagem': 'Comunicação estabelecida com sucesso!',
            'temperatura_lida': round(random.uniform(20, 30), 2),
            'data_teste': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        return jsonify({
            'sucesso': True,
            'mensagem': 'Sensor testado com sucesso!',
            'temperatura': sensor['status_teste']['temperatura_lida']
        })
    else:
        sensor['status_teste'] = {
            'status': 'erro',
            'mensagem': 'Falha na comunicação. Verifique as configurações.',
            'data_teste': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        return jsonify({
            'sucesso': False,
            'mensagem': 'Falha na comunicação. Verifique as configurações.'
        }), 400

@app.route('/manutencao', methods=['GET', 'POST'])
@login_required
def manutencao():
    if request.method == 'POST':
        acao = request.form.get('acao')
        equip_id = int(request.form.get('equip_id'))
        equip = get_equipamento_por_id(equip_id)
        
        if not equip:
            flash('Equipamento não encontrado!', 'danger')
            return redirect(url_for('manutencao'))
        
        if acao == 'iniciar':
            equip['manutencao'] = {
                'motivo': request.form.get('motivo'),
                'previsao': request.form.get('previsao'),
                'responsavel': session['nome_usuario'],
                'data_inicio': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            equip['status'] = 'manutencao'
            flash(f'Manutenção iniciada em {equip["nome"]}!', 'success')
        
        elif acao == 'finalizar':
            equip['manutencao'] = None
            equip['status'] = 'livre'
            flash(f'Manutenção finalizada em {equip["nome"]}!', 'success')
        
        return redirect(url_for('manutencao'))
    
    return render_template('manutencao.html', equipamentos=equipamentos)

@app.route('/higienizacao', methods=['GET', 'POST'])
@login_required
def higienizacao():
    if request.method == 'POST':
        acao = request.form.get('acao')
        equip_id = int(request.form.get('equip_id'))
        equip = get_equipamento_por_id(equip_id)
        
        if not equip:
            flash('Equipamento não encontrado!', 'danger')
            return redirect(url_for('higienizacao'))
        
        if acao == 'iniciar':
            equip['higienizacao'] = {
                'previsao': request.form.get('previsao'),
                'responsavel': session['nome_usuario'],
                'data_inicio': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            equip['status'] = 'higienizacao'
            flash(f'Higienização iniciada em {equip["nome"]}!', 'success')
        
        elif acao == 'finalizar':
            processo_finalizado = {
                'id': len(processos_finalizados) + 1,
                'equipamento': equip['nome'],
                'equipamento_id': equip_id,
                'produto': 'Higienização',
                'ordem_producao': f'HIG-{equip_id}-{datetime.now().strftime("%Y%m%d")}',
                'responsavel': session['nome_usuario'],
                'data_finalizacao': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'status_qualidade': 'pendente'
            }
            processos_finalizados.append(processo_finalizado)
            
            equip['higienizacao'] = None
            equip['status'] = 'aguardando_qualidade'
            flash(f'Higienização finalizada! {equip["nome"]} aguarda validação da qualidade.', 'info')
        
        return redirect(url_for('higienizacao'))
    
    return render_template('higienizacao.html', equipamentos=equipamentos)

@app.route('/qualidade', methods=['GET', 'POST'])
@login_required
def qualidade():
    if request.method == 'POST':
        processo_id = int(request.form.get('processo_id'))
        resultado = request.form.get('resultado')
        
        processo = next((p for p in processos_finalizados if p['id'] == processo_id), None)
        
        if processo:
            processo['status_qualidade'] = resultado
            processo['data_analise'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            processo['analisado_por'] = session['nome_usuario']
            
            equip = get_equipamento_por_id(processo['equipamento_id'])
            if equip:
                if resultado == 'aprovado':
                    equip['status'] = 'livre'
                    flash(f'Processo aprovado! {equip["nome"]} liberado para uso.', 'success')
                else:
                    equip['status'] = 'livre'
                    flash(f'Processo rejeitado! {equip["nome"]} liberado para novo processo.', 'warning')
        
        return redirect(url_for('qualidade'))
    
    return render_template('qualidade.html', processos=processos_finalizados)

@app.route('/relatorios')
@login_required
def relatorios():
    return render_template('relatorios.html', relatorios=relatorios_personalizados, equipamentos=equipamentos, layouts=layouts_relatorios)

@app.route('/gerar_relatorio', methods=['POST'])
@login_required
def gerar_relatorio():
    id_relatorio = request.form.get('id_relatorio')
    formato = request.form.get('formato')
    
    relatorio = relatorios_personalizados.get(id_relatorio)
    if not relatorio:
        flash('Relatório não encontrado!', 'danger')
        return redirect(url_for('relatorios'))
    
    dados = processos_finalizados.copy()
    
    data_inicio = request.form.get('filtro_data_inicio')
    data_fim = request.form.get('filtro_data_fim')
    
    if data_inicio:
        dados = [d for d in dados if d.get('data_finalizacao', '')[:10] >= data_inicio]
    if data_fim:
        dados = [d for d in dados if d.get('data_finalizacao', '')[:10] <= data_fim]
    
    equip_id = request.form.get('filtro_equipamento_id')
    if equip_id:
        dados = [d for d in dados if d.get('equipamento_id') == int(equip_id)]
    
    if not dados:
        flash('Nenhum dado disponível para gerar relatório!', 'warning')
        return redirect(url_for('relatorios'))
    
    dados_exportacao = []
    for processo in dados:
        linha = {}
        for campo in relatorio['campos']:
            if campo == 'equipamento':
                linha['Equipamento'] = processo.get('equipamento', '')
            elif campo == 'produto':
                linha['Produto'] = processo.get('produto', '')
            elif campo == 'ordem_producao':
                linha['Ordem de Produção'] = processo.get('ordem_producao', '')
            elif campo == 'responsavel':
                linha['Responsável'] = processo.get('responsavel', '')
            elif campo == 'data_finalizacao':
                linha['Data Finalização'] = processo.get('data_finalizacao', '')
            elif campo == 'status_qualidade':
                linha['Status Qualidade'] = processo.get('status_qualidade', '').upper()
        dados_exportacao.append(linha)
    
    if formato == 'excel':
        df = pd.DataFrame(dados_exportacao)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Relatório')
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{relatorio["nome"]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    
    elif formato == 'pdf':
        output = BytesIO()
        doc = SimpleDocTemplate(output, pagesize=A4)
        elements = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#4A90E2'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        elements.append(Paragraph(relatorio['nome'], title_style))
        elements.append(Spacer(1, 0.3*inch))
        
        info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
        elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", info_style))
        elements.append(Paragraph(f"Usuário: {session.get('nome_usuario', 'N/A')}", info_style))
        elements.append(Spacer(1, 0.3*inch))
        
        if dados_exportacao:
            headers = list(dados_exportacao[0].keys())
            table_data = [headers]
            
            for row in dados_exportacao:
                table_data.append([str(row.get(h, '')) for h in headers])
            
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A90E2')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
            ]))
            
            elements.append(table)
        
        doc.build(elements)
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{relatorio["nome"]}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    
    flash('Formato de relatório não suportado!', 'warning')
    return redirect(url_for('relatorios'))

@app.route('/gerenciar_usuarios', methods=['GET', 'POST'])
@login_required
@tipo_usuario_required('ti')
def gerenciar_usuarios():
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'adicionar':
            username = request.form.get('username')
            if username in usuarios:
                flash('Usuário já existe!', 'danger')
                return redirect(url_for('gerenciar_usuarios'))
            
            permissoes = {}
            for key in request.form.keys():
                if key.startswith('perm_'):
                    perm_name = key.replace('perm_', '')
                    permissoes[perm_name] = True
            
            grupo_nome = request.form.get('grupo')
            if grupo_nome and grupo_nome in grupos_usuarios:
                grupo_perms = grupos_usuarios[grupo_nome]['permissoes']
                permissoes.update(grupo_perms)
            
            usuarios[username] = {
                'senha': request.form.get('senha'),
                'nome': request.form.get('nome'),
                'email': request.form.get('email'),
                'tipo': request.form.get('tipo'),
                'ativo': True,
                'grupo': grupo_nome if grupo_nome else None,
                'permissoes': permissoes
            }
            flash(f'Usuário {username} criado com sucesso!', 'success')
        
        elif acao == 'editar':
            username = request.form.get('username')
            if username not in usuarios:
                flash('Usuário não encontrado!', 'danger')
                return redirect(url_for('gerenciar_usuarios'))
            
            usuarios[username]['nome'] = request.form.get('nome')
            usuarios[username]['email'] = request.form.get('email')
            usuarios[username]['tipo'] = request.form.get('tipo')
            
            senha = request.form.get('senha')
            if senha:
                usuarios[username]['senha'] = senha
            
            permissoes = {}
            for key in request.form.keys():
                if key.startswith('perm_'):
                    perm_name = key.replace('perm_', '')
                    permissoes[perm_name] = True
            
            grupo_nome = request.form.get('grupo')
            if grupo_nome and grupo_nome in grupos_usuarios:
                grupo_perms = grupos_usuarios[grupo_nome]['permissoes']
                permissoes.update(grupo_perms)
            
            usuarios[username]['grupo'] = grupo_nome if grupo_nome else None
            usuarios[username]['permissoes'] = permissoes
            
            flash(f'Usuário {username} atualizado!', 'success')
        
        elif acao == 'ativar_desativar':
            username = request.form.get('username')
            if username in usuarios:
                usuarios[username]['ativo'] = not usuarios[username]['ativo']
                status = 'ativado' if usuarios[username]['ativo'] else 'desativado'
                flash(f'Usuário {username} {status}!', 'success')
        
        elif acao == 'resetar_senha':
            username = request.form.get('username')
            if username in usuarios:
                usuarios[username]['senha'] = '123'
                flash(f'Senha de {username} resetada para "123"!', 'success')
        
        return redirect(url_for('gerenciar_usuarios'))
    
    return render_template('usuarios.html', usuarios=usuarios, grupos=grupos_usuarios, relatorios_personalizados=relatorios_personalizados)

@app.route('/gerenciar_grupos', methods=['GET', 'POST'])
@login_required
@tipo_usuario_required('ti')
def gerenciar_grupos():
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'adicionar':
            nome = request.form.get('nome')
            if nome in grupos_usuarios:
                flash('Grupo já existe!', 'danger')
                return redirect(url_for('gerenciar_grupos'))
            
            permissoes = {}
            for key in request.form.keys():
                if key.startswith('perm_'):
                    perm_name = key.replace('perm_', '')
                    permissoes[perm_name] = True
            
            grupos_usuarios[nome] = {
                'id': len(grupos_usuarios) + 1,
                'nome': nome,
                'descricao': request.form.get('descricao', ''),
                'cor': request.form.get('cor', '#4A90E2'),
                'permissoes': permissoes
            }
            flash(f'Grupo {nome} criado!', 'success')
        
        elif acao == 'editar':
            nome_antigo = request.form.get('nome_antigo')
            nome_novo = request.form.get('nome')
            
            if nome_antigo in grupos_usuarios:
                grupo = grupos_usuarios[nome_antigo]
                
                permissoes = {}
                for key in request.form.keys():
                    if key.startswith('perm_'):
                        perm_name = key.replace('perm_', '')
                        permissoes[perm_name] = True
                
                if nome_antigo != nome_novo:
                    grupos_usuarios[nome_novo] = {
                        'id': grupo['id'],
                        'nome': nome_novo,
                        'descricao': request.form.get('descricao', ''),
                        'cor': request.form.get('cor', '#4A90E2'),
                        'permissoes': permissoes
                    }
                    del grupos_usuarios[nome_antigo]
                    
                    # Atualizar usuários que usam este grupo
                    for user in usuarios.values():
                        if user.get('grupo') == nome_antigo:
                            user['grupo'] = nome_novo
                else:
                    grupos_usuarios[nome_antigo]['descricao'] = request.form.get('descricao', '')
                    grupos_usuarios[nome_antigo]['cor'] = request.form.get('cor', '#4A90E2')
                    grupos_usuarios[nome_antigo]['permissoes'] = permissoes
                
                flash(f'Grupo atualizado!', 'success')
        
        elif acao == 'excluir':
            nome = request.form.get('nome_grupo')
            if nome in grupos_usuarios:
                del grupos_usuarios[nome]
                # Remover grupo dos usuários
                for user in usuarios.values():
                    if user.get('grupo') == nome:
                        user['grupo'] = None
                flash(f'Grupo {nome} excluído!', 'success')
        
        return redirect(url_for('gerenciar_grupos'))
    
    return render_template('grupos.html', grupos=grupos_usuarios, relatorios=relatorios_personalizados)

@app.route('/gerenciar_relatorios', methods=['GET', 'POST'])
@login_required
@tipo_usuario_required('ti')
def gerenciar_relatorios():
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'adicionar':
            id_rel = request.form.get('id_relatorio')
            if id_rel in relatorios_personalizados:
                flash('ID de relatório já existe!', 'danger')
                return redirect(url_for('gerenciar_relatorios'))
            
            campos = request.form.getlist('campos')
            
            relatorios_personalizados[id_rel] = {
                'id': id_rel,
                'nome': request.form.get('nome'),
                'descricao': request.form.get('descricao', ''),
                'tipo': request.form.get('tipo'),
                'campos': campos,
                'filtros': [
                    {'nome': 'data_inicio', 'label': 'Data Início', 'tipo': 'date'},
                    {'nome': 'data_fim', 'label': 'Data Fim', 'tipo': 'date'},
                    {'nome': 'equipamento_id', 'label': 'Equipamento', 'tipo': 'select'}
                ],
                'formatos': request.form.getlist('formatos'),
                'layout_excel': request.form.get('layout_excel'),
                'layout_pdf': request.form.get('layout_pdf'),
                'ativo': True
            }
            flash(f'Relatório {request.form.get("nome")} criado!', 'success')
        
        elif acao == 'editar':
            id_rel = request.form.get('id_relatorio')
            if id_rel in relatorios_personalizados:
                campos = request.form.getlist('campos')
                
                relatorios_personalizados[id_rel]['nome'] = request.form.get('nome')
                relatorios_personalizados[id_rel]['descricao'] = request.form.get('descricao', '')
                relatorios_personalizados[id_rel]['tipo'] = request.form.get('tipo')
                relatorios_personalizados[id_rel]['campos'] = campos
                relatorios_personalizados[id_rel]['formatos'] = request.form.getlist('formatos')
                relatorios_personalizados[id_rel]['layout_excel'] = request.form.get('layout_excel')
                relatorios_personalizados[id_rel]['layout_pdf'] = request.form.get('layout_pdf')
                flash('Relatório atualizado!', 'success')
        
        elif acao == 'ativar_desativar':
            id_rel = request.form.get('id_relatorio')
            if id_rel in relatorios_personalizados:
                relatorios_personalizados[id_rel]['ativo'] = not relatorios_personalizados[id_rel].get('ativo', True)
                status = 'ativado' if relatorios_personalizados[id_rel]['ativo'] else 'desativado'
                flash(f'Relatório {status}!', 'success')
        
        elif acao == 'excluir':
            id_rel = request.form.get('id_relatorio')
            if id_rel in relatorios_personalizados:
                del relatorios_personalizados[id_rel]
                flash('Relatório excluído!', 'success')
        
        return redirect(url_for('gerenciar_relatorios'))
    
    return render_template('config_relatorios.html', relatorios=relatorios_personalizados, layouts=layouts_relatorios)

@app.route('/gerenciar_layouts', methods=['GET', 'POST'])
@login_required
@tipo_usuario_required('ti')
def gerenciar_layouts():
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'adicionar':
            id_layout = request.form.get('id_layout')
            if id_layout in layouts_relatorios:
                flash('ID de layout já existe!', 'danger')
                return redirect(url_for('gerenciar_layouts'))
            
            tipo = request.form.get('tipo')
            config = {}
            
            if tipo == 'excel':
                config = {
                    'cabecalho': {
                        'titulo': request.form.get('titulo'),
                        'subtitulo': request.form.get('subtitulo'),
                        'cor_fundo': request.form.get('cor_fundo'),
                        'cor_texto': request.form.get('cor_texto')
                    },
                    'tabela': {
                        'cor_cabecalho': request.form.get('cor_cabecalho'),
                        'cor_linhas_alternadas': request.form.get('cor_linhas_alternadas') == 'on'
                    }
                }
            elif tipo == 'pdf':
                config = {
                    'cabecalho': {
                        'titulo': request.form.get('titulo'),
                        'subtitulo': request.form.get('subtitulo'),
                        'logo': None
                    },
                    'rodape': {
                        'texto': request.form.get('rodape_texto'),
                        'numeracao': request.form.get('rodape_numeracao') == 'on'
                    }
                }
            
            layouts_relatorios[id_layout] = {
                'id': id_layout,
                'nome': request.form.get('nome'),
                'tipo': tipo,
                'config': config
            }
            flash(f'Layout {request.form.get("nome")} criado!', 'success')
        
        elif acao == 'editar':
            id_layout = request.form.get('id_layout')
            if id_layout in layouts_relatorios:
                tipo = request.form.get('tipo')
                config = {}
                
                if tipo == 'excel':
                    config = {
                        'cabecalho': {
                            'titulo': request.form.get('titulo'),
                            'subtitulo': request.form.get('subtitulo'),
                            'cor_fundo': request.form.get('cor_fundo'),
                            'cor_texto': request.form.get('cor_texto')
                        },
                        'tabela': {
                            'cor_cabecalho': request.form.get('cor_cabecalho'),
                            'cor_linhas_alternadas': request.form.get('cor_linhas_alternadas') == 'on'
                        }
                    }
                elif tipo == 'pdf':
                    config = {
                        'cabecalho': {
                            'titulo': request.form.get('titulo'),
                            'subtitulo': request.form.get('subtitulo'),
                            'logo': None
                        },
                        'rodape': {
                            'texto': request.form.get('rodape_texto'),
                            'numeracao': request.form.get('rodape_numeracao') == 'on'
                        }
                    }
                
                layouts_relatorios[id_layout]['nome'] = request.form.get('nome')
                layouts_relatorios[id_layout]['tipo'] = tipo
                layouts_relatorios[id_layout]['config'] = config
                flash('Layout atualizado!', 'success')
        
        elif acao == 'excluir':
            id_layout = request.form.get('id_layout')
            if id_layout in layouts_relatorios:
                # Verificar se algum relatório usa este layout
                em_uso = any(
                    r.get('layout_excel') == id_layout or r.get('layout_pdf') == id_layout
                    for r in relatorios_personalizados.values()
                )
                if em_uso:
                    flash('Não é possível excluir! Este layout está sendo usado por um relatório.', 'danger')
                else:
                    del layouts_relatorios[id_layout]
                    flash('Layout excluído!', 'success')
        
        return redirect(url_for('gerenciar_layouts'))
    
    return render_template('layouts.html', layouts=layouts_relatorios)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)