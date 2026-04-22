import os
import sys
import traceback as _tb
from io import BytesIO

# Adiciona o diretório atual ao path para evitar erros de importação no uWSGI
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_PATH = os.path.join(_APP_DIR, 'init_error.log')

try:
    from flask import Flask, jsonify, request, render_template, session, redirect, url_for, send_file
    from functools import wraps
    from dotenv import load_dotenv
    from werkzeug.exceptions import RequestEntityTooLarge
    load_dotenv()
    from src.core.routes.imoveis import imoveis_bp, Session
    from src.core.schema_sync import sync_schema
    try:
        sync_schema()
    except Exception as sync_err:
        with open(_LOG_PATH, 'a') as f:
            f.write(f"AVISO sync_schema: {sync_err}\n")
            f.write(_tb.format_exc())
except Exception as e:
    try:
        with open(_LOG_PATH, 'a') as f:
            f.write(f"ERRO DE INICIALIZAÇÃO: {str(e)}\n")
            f.write(_tb.format_exc())
    except Exception:
        pass
    raise e

app = Flask(__name__)
# app.debug = True
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gandu_secret_key_123')

_DEFAULT_UPLOAD_ROOT = os.path.join(_APP_DIR, 'storage', 'uploads')
_MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', '15'))
_DEFAULT_REQUEST_SIZE_MB = max(_MAX_UPLOAD_SIZE_MB, 50)
_MAX_REQUEST_SIZE_MB = int(os.environ.get('MAX_REQUEST_SIZE_MB', str(_DEFAULT_REQUEST_SIZE_MB)))
if _MAX_REQUEST_SIZE_MB < _MAX_UPLOAD_SIZE_MB:
    _MAX_REQUEST_SIZE_MB = _MAX_UPLOAD_SIZE_MB

app.config['UPLOAD_ROOT'] = os.environ.get('UPLOAD_ROOT', _DEFAULT_UPLOAD_ROOT)
app.config['UPLOAD_FOLDER'] = app.config['UPLOAD_ROOT']
app.config['MAX_UPLOAD_SIZE_MB'] = _MAX_UPLOAD_SIZE_MB
app.config['MAX_UPLOAD_SIZE_BYTES'] = _MAX_UPLOAD_SIZE_MB * 1024 * 1024
app.config['MAX_REQUEST_SIZE_MB'] = _MAX_REQUEST_SIZE_MB
app.config['MAX_REQUEST_SIZE_BYTES'] = _MAX_REQUEST_SIZE_MB * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = app.config['MAX_REQUEST_SIZE_BYTES']

os.makedirs(app.config['UPLOAD_ROOT'], exist_ok=True)

# Decorator de Proteção de Rotas
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

app.register_blueprint(imoveis_bp)


@app.errorhandler(RequestEntityTooLarge)
def handle_large_upload(_error):
    max_mb = app.config.get('MAX_UPLOAD_SIZE_MB', 15)
    request_mb = app.config.get('MAX_REQUEST_SIZE_MB', max_mb)
    if request_mb > max_mb:
        message = f"Requisição excede o limite técnico de {request_mb} MB. Limite por arquivo: {max_mb} MB."
    else:
        message = f"Arquivo excede o limite configurado de {max_mb} MB."

    if request.path.startswith('/api/'):
        return jsonify({"error": message}), 413

    return render_template('login.html', error=message), 413

@app.route('/admin/sync-schema')
def admin_sync_schema():
    try:
        from src.core.schema_sync import sync_schema
        sync_schema()
        return jsonify({"status": "ok", "message": "Schema sincronizado"})
    except Exception as e:
        import traceback
        return jsonify({"status": "error", "error": str(e), "trace": traceback.format_exc()}), 500

@app.route('/')
@login_required
def index():
    return render_template('dashboard.html')

@app.route('/imoveis')
@login_required
def imoveis():
    return render_template('dashboard.html')

@app.route('/triagem')
@login_required
def triagem():
    return render_template('triagem.html')

@app.route('/imovel/<int:id>')
@login_required
def detalhe(id):
    return render_template('detalhe.html', id=id)


@app.route('/imovel/<int:id>/pdf-executivo')
@login_required
def detalhe_pdf_executivo(id):
    try:
        # Import tardio para que dependências opcionais do PDF não derrubem a aplicação inteira.
        from src.core.services.executive_pdf_service import ExecutivePdfService
    except ModuleNotFoundError as err:
        missing_name = (err.name or "").split(".")[0]
        if missing_name in {"PIL", "reportlab"}:
            dependency_name = "Pillow" if missing_name == "PIL" else "reportlab"
            return jsonify({
                "error": (
                    f"Dependência ausente para geração do PDF Executivo: {dependency_name}. "
                    "Atualize o ambiente com `pip install -r requirements.txt`."
                )
            }), 503
        raise

    company_id = int(session.get('company_id') or request.args.get('company_id', 1))
    layout = (request.args.get('layout') or 'desktop').strip().lower()
    if layout not in {'desktop', 'mobile'}:
        layout = 'desktop'

    db_session = Session()
    try:
        filename, pdf_bytes, _, _ = ExecutivePdfService.generate_for_imovel(
            db_session,
            imovel_id=id,
            company_id=company_id,
            root_path=app.root_path,
            upload_root=app.config['UPLOAD_ROOT'],
            output_root=os.path.join(app.root_path, 'output', 'pdf'),
            layout=layout,
        )
    except ValueError as err:
        return jsonify({"error": str(err)}), 404
    except Exception as err:
        return jsonify({"error": f"Falha ao gerar PDF Executivo: {err}"}), 500
    finally:
        db_session.close()

    return send_file(
        BytesIO(pdf_bytes),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=filename,
        max_age=0,
    )

@app.route('/calendario')
@login_required
def calendario():
    return render_template('calendario.html')

@app.route('/leiloes-semana')
@login_required
def leiloes_semana():
    return render_template('leiloes_semana.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Simulação de autenticação rápida para o MVP
        if email == "admin@ganduinvest.com.br" and password == "gandu123":
            session['user_id'] = 1
            session['user_name'] = "Admin Gandu"
            session['company_id'] = 1
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Credenciais inválidas. Tente novamente.")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
