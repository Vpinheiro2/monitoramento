from flask import Flask, render_template, redirect, url_for, flash, session, request, jsonify
from functools import wraps
from datetime import datetime
import json
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui_mude_em_producao'

# ===== FUNÇÕES AUXILIARES =====

def get_cor_status(status):
    cores = {
        'livre': 'success',
        'ocupada': 'danger',
        'manutencao': 'warning',
        'higienizacao': 'info',
        'offline': 'secondary'
    }
    return cores.get(status, 'secondary')

def get_equipamento_por_id(equip_id):
    return next((e for e in equipamentos if e['id'] == equip_id), None)

# ===== DADOS MOCKADOS =====

usuarios = {
    'operador': {'senha': '123', 'tipo': 'operador', 'nome': 'João Operador', 'email': 'operador@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'operador': True, 'relatorios': False}},
    'ti': {'senha': '123', 'tipo': 'ti', 'nome': 'Maria TI', 'email': 'ti@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'operador': True, 'ti': True, 'relatorios': True}},
    'manutencao': {'senha': '123', 'tipo': 'manutencao', 'nome': 'Carlos Manutenção', 'email': 'manutencao@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'manutencao': True, 'relatorios': True}},
    'higienizacao': {'senha': '123', 'tipo': 'higienizacao', 'nome': 'Ana Higienização', 'email': 'higienizacao@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'higienizacao': True, 'relatorios': True}},
    'qualidade': {'senha': '123', 'tipo': 'qualidade', 'nome': 'Pedro Qualidade', 'email': 'qualidade@empresa.com', 'ativo': True, 'grupo': None, 'permissoes': {'dashboard': True, 'qualidade': True, 'relatorios': True}}
}

equipamentos = [
    {'id': 1, 'nome': 'Estufa 01', 'tipo': 'estufa', 'status': 'livre', 'icone': '🌡️', 'processo': None, 'manutencao': None, 'higienizacao': None, 'sensor': {'ativo': True, 'ip': '192.168.1.254', 'porta': '80', 'canal': '1', 'temp_min': 20, 'temp_max': 80, 'alerta_ativo': True}, 'descricao': 'Estufa principal', 'localizacao': 'Galpão A', 'ativo': True, 'campos_personalizados': []},
    {'id': 2, 'nome': 'Estufa 02', 'tipo': 'estufa', 'status': 'ocupada', 'icone': '🌡️', 'processo': {'produto': 'Tomates', 'ordem_producao': 'OP-001', 'duracao': '08:00', 'carregado_as': '14:30', 'responsavel': 'João', 'data_inicio': '2024-10-30'}, 'manutencao': None, 'higienizacao': None, 'sensor': {'ativo': True, 'ip': '192.168.1.254', 'porta': '80', 'canal': '2', 'temp_min': 20, 'temp_max': 80, 'alerta_ativo': True}, 'descricao': 'Estufa secundária', 'localizacao': 'Galpão A', 'ativo': True, 'campos_personalizados': []},
    {'id': 3, 'nome': 'Autoclave 01', 'tipo': 'autoclave', 'status': 'livre', 'icone': '⚗️', 'processo': None, 'manutencao': None, 'higienizacao': None, 'sensor': {'ativo': False, 'ip': None, 'porta': None, 'canal': None}, 'descricao': 'Autoclave', 'localizacao': 'Lab', 'ativo': True, 'campos_personalizados': []}
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

relatorios_personalizados = {
    'producao_diaria': {'id': 1, 'nome': 'Produção Diária', 'descricao': 'Relatório de produção', 'tipo': 'processos', 'campos': [], 'filtros': [], 'formatos': ['excel', 'pdf'], 'ativo': True}
}

processos_finalizados = []
historico_processos = []

# Context processor
@app.context_processor
def inject_globals():
    return {'usuarios': usuarios, 'grupos_usuarios': grupos_usuarios, 'relatorios_personalizados': relatorios_personalizados, 'get_cor_status': get_cor_status}

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
            equipamento['processo'] = None
            equipamento['status'] = 'livre'
            flash('Processo finalizado!', 'success')
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
                         relatorios_personalizados=relatorios_personalizados)

@app.route('/ti/equipamentos', methods=['GET', 'POST'])
@login_required
@tipo_usuario_required('ti')
def ti_equipamentos():
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'adicionar':
            novo_id = max([e['id'] for e in equipamentos]) + 1 if equipamentos else 1
            tem_sensor = request.form.get('tem_sensor') == 'on'
            
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
                'sensor': {
                    'ativo': tem_sensor,
                    'ip': request.form.get('sensor_ip') if tem_sensor else None,
                    'porta': request.form.get('sensor_porta') if tem_sensor else None,
                    'canal': request.form.get('sensor_canal') if tem_sensor else None
                }
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
                
                tem_sensor = request.form.get('tem_sensor') == 'on'
                equip['sensor'] = {
                    'ativo': tem_sensor,
                    'ip': request.form.get('sensor_ip') if tem_sensor else None,
                    'porta': request.form.get('sensor_porta') if tem_sensor else None,
                    'canal': request.form.get('sensor_canal') if tem_sensor else None
                }
                flash('Equipamento atualizado!', 'success')
            return redirect(url_for('ti_equipamentos'))
        
        elif acao == 'excluir':
            equip_id = int(request.form.get('equip_id'))
            equip = get_equipamento_por_id(equip_id)
            if equip and equip['status'] == 'livre':
                equipamentos.remove(equip)
                flash('Equipamento excluído!', 'success')
            else:
                flash('Não é possível excluir!', 'danger')
            return redirect(url_for('ti_equipamentos'))
    
    return render_template('ti_equipamentos.html', equipamentos=equipamentos, icones_disponiveis=icones_disponiveis)

@app.route('/manutencao')
@login_required
def manutencao():
    return render_template('manutencao.html', equipamentos=equipamentos)

@app.route('/higienizacao')
@login_required
def higienizacao():
    return render_template('higienizacao.html', equipamentos=equipamentos)

@app.route('/qualidade')
@login_required
def qualidade():
    return render_template('qualidade.html', processos=processos_finalizados)

@app.route('/relatorios')
@login_required
def relatorios():
    return render_template('relatorios.html', relatorios=relatorios_personalizados, equipamentos=equipamentos)

@app.route('/gerenciar_usuarios')
@login_required
@tipo_usuario_required('ti')
def gerenciar_usuarios():
    return render_template('usuarios.html', usuarios=usuarios, grupos=grupos_usuarios)

@app.route('/gerenciar_grupos')
@login_required
@tipo_usuario_required('ti')
def gerenciar_grupos():
    flash('Página de grupos em desenvolvimento', 'info')
    return redirect(url_for('ti'))

@app.route('/gerenciar_relatorios')
@login_required
@tipo_usuario_required('ti')
def gerenciar_relatorios():
    flash('Página de configuração de relatórios em desenvolvimento', 'info')
    return redirect(url_for('ti'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)