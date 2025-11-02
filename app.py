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
    
    # Bloquear se estiver aguardando qualidade (exceto para qualidade)
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
            # Salvar processo finalizado
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
                    'canal': request.form.get('sensor_canal') if tem_sensor else None,
                    'temp_min': int(request.form.get('temp_min')) if request.form.get('temp_min') else None,
                    'temp_max': int(request.form.get('temp_max')) if request.form.get('temp_max') else None,
                    'alerta_ativo': request.form.get('alerta_ativo') == 'on'
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
                    'canal': request.form.get('sensor_canal') if tem_sensor else None,
                    'temp_min': int(request.form.get('temp_min')) if request.form.get('temp_min') else None,
                    'temp_max': int(request.form.get('temp_max')) if request.form.get('temp_max') else None,
                    'alerta_ativo': request.form.get('alerta_ativo') == 'on'
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
    
    return render_template('ti_equipamentos.html', equipamentos=equipamentos, icones_disponiveis=icones_disponiveis)

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
            # Finaliza higienização e envia para qualidade
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
        
        # Encontrar processo
        processo = next((p for p in processos_finalizados if p['id'] == processo_id), None)
        
        if processo:
            processo['status_qualidade'] = resultado
            processo['data_analise'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            processo['analisado_por'] = session['nome_usuario']
            
            # Liberar equipamento
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
    return render_template('relatorios.html', relatorios=relatorios_personalizados, equipamentos=equipamentos)

@app.route('/gerar_relatorio', methods=['POST'])
@login_required
def gerar_relatorio():
    id_relatorio = request.form.get('id_relatorio')
    formato = request.form.get('formato')
    
    # Buscar relatório
    relatorio = relatorios_personalizados.get(id_relatorio)
    if not relatorio:
        flash('Relatório não encontrado!', 'danger')
        return redirect(url_for('relatorios'))
    
    # Aplicar filtros
    dados = processos_finalizados.copy()
    
    # Filtro de data
    data_inicio = request.form.get('filtro_data_inicio')
    data_fim = request.form.get('filtro_data_fim')
    
    if data_inicio:
        dados = [d for d in dados if d.get('data_finalizacao', '')[:10] >= data_inicio]
    if data_fim:
        dados = [d for d in dados if d.get('data_finalizacao', '')[:10] <= data_fim]
    
    # Filtro de equipamento
    equip_id = request.form.get('filtro_equipamento_id')
    if equip_id:
        dados = [d for d in dados if d.get('equipamento_id') == int(equip_id)]
    
    if not dados:
        flash('Nenhum dado disponível para gerar relatório!', 'warning')
        return redirect(url_for('relatorios'))
    
    # Preparar dados para exportação
    dados_exportacao = []
    for processo in dados:
        linha = {}
        if 'equipamento' in relatorio['campos']:
            linha['Equipamento'] = processo.get('equipamento', '')
        if 'produto' in relatorio['campos']:
            linha['Produto'] = processo.get('produto', '')
        if 'ordem_producao' in relatorio['campos']:
            linha['Ordem de Produção'] = processo.get('ordem_producao', '')
        if 'responsavel' in relatorio['campos']:
            linha['Responsável'] = processo.get('responsavel', '')
        if 'data_finalizacao' in relatorio['campos']:
            linha['Data Finalização'] = processo.get('data_finalizacao', '')
        if 'status_qualidade' in relatorio['campos']:
            linha['Status Qualidade'] = processo.get('status_qualidade', '').upper()
        dados_exportacao.append(linha)
    
    # Gerar Excel
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
    
    # Gerar PDF
    elif formato == 'pdf':
        output = BytesIO()
        doc = SimpleDocTemplate(output, pagesize=A4)
        elements = []
        
        # Estilos
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#4A90E2'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        # Título
        elements.append(Paragraph(relatorio['nome'], title_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Informações do relatório
        info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=9, textColor=colors.grey)
        elements.append(Paragraph(f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", info_style))
        elements.append(Paragraph(f"Usuário: {session.get('nome_usuario', 'N/A')}", info_style))
        elements.append(Spacer(1, 0.3*inch))
        
        # Tabela de dados
        if dados_exportacao:
            # Cabeçalhos
            headers = list(dados_exportacao[0].keys())
            table_data = [headers]
            
            # Dados
            for row in dados_exportacao:
                table_data.append([str(row.get(h, '')) for h in headers])
            
            # Criar tabela
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
            
            # Criar permissões
            permissoes = {}
            for key in request.form.keys():
                if key.startswith('perm_'):
                    perm_name = key.replace('perm_', '')
                    permissoes[perm_name] = True
            
            usuarios[username] = {
                'senha': request.form.get('senha'),
                'nome': request.form.get('nome'),
                'email': request.form.get('email'),
                'tipo': request.form.get('tipo'),
                'ativo': True,
                'grupo': None,
                'permissoes': permissoes
            }
            flash(f'Usuário {username} criado com sucesso!', 'success')
        
        elif acao == 'editar':
            username = request.form.get('username')
            if username not in usuarios:
                flash('Usuário não encontrado!', 'danger')
                return redirect(url_for('gerenciar_usuarios'))
            
            # Atualizar dados
            usuarios[username]['nome'] = request.form.get('nome')
            usuarios[username]['email'] = request.form.get('email')
            usuarios[username]['tipo'] = request.form.get('tipo')
            
            # Atualizar senha apenas se fornecida
            senha = request.form.get('senha')
            if senha:
                usuarios[username]['senha'] = senha
            
            # Atualizar permissões
            permissoes = {}
            for key in request.form.keys():
                if key.startswith('perm_'):
                    perm_name = key.replace('perm_', '')
                    permissoes[perm_name] = True
            usuarios[username]['permissoes'] = permissoes
            
            flash(f'Usuário {username} atualizado!', 'success')
        
        elif acao == 'ativar_desativar':
            username = request.form.get('username')
            if username in usuarios:
                usuarios[username]['ativo'] = not usuarios[username]['ativo']
                status = 'ativado' if usuarios[username]['ativo'] else 'desativado'
                flash(f'Usuário {username} {status}!', 'success')
        
        elif acao == 'alterar_senha':
            username = request.form.get('username')
            nova_senha = request.form.get('nova_senha')
            if username in usuarios and nova_senha:
                usuarios[username]['senha'] = nova_senha
                flash(f'Senha de {username} alterada com sucesso!', 'success')
            else:
                flash('Erro ao alterar senha!', 'danger')
        
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
            
            # Criar permissões
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
                
                # Atualizar permissões
                permissoes = {}
                for key in request.form.keys():
                    if key.startswith('perm_'):
                        perm_name = key.replace('perm_', '')
                        permissoes[perm_name] = True
                
                # Se o nome mudou, criar novo e remover antigo
                if nome_antigo != nome_novo:
                    grupos_usuarios[nome_novo] = {
                        'id': grupo['id'],
                        'nome': nome_novo,
                        'descricao': request.form.get('descricao', ''),
                        'cor': request.form.get('cor', '#4A90E2'),
                        'permissoes': permissoes
                    }
                    del grupos_usuarios[nome_antigo]
                else:
                    grupos_usuarios[nome_antigo]['descricao'] = request.form.get('descricao', '')
                    grupos_usuarios[nome_antigo]['cor'] = request.form.get('cor', '#4A90E2')
                    grupos_usuarios[nome_antigo]['permissoes'] = permissoes
                
                flash(f'Grupo atualizado!', 'success')
        
        elif acao == 'excluir':
            nome = request.form.get('nome_grupo')
            if nome in grupos_usuarios:
                del grupos_usuarios[nome]
                flash(f'Grupo {nome} excluído!', 'success')
        
        return redirect(url_for('gerenciar_grupos'))
    
    return render_template('grupos.html', grupos=grupos_usuarios)

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
            
            # Pegar campos selecionados
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
    
    return render_template('config_relatorios.html', relatorios=relatorios_personalizados)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)