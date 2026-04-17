import os
import sys

# Adiciona o diretório atual ao path para evitar erros de importação no uWSGI
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from flask import Flask, jsonify, request, render_template, session, redirect, url_for
    from functools import wraps
    from dotenv import load_dotenv
    load_dotenv()
    from src.core.routes.imoveis import imoveis_bp
except Exception as e:
    with open('init_error.log', 'a') as f:
        import traceback
        f.write(f"ERRO DE INICIALIZAÇÃO: {str(e)}\n")
        f.write(traceback.format_exc())
    raise e

app = Flask(__name__)
# app.debug = True
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'gandu_secret_key_123')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Decorator de Proteção de Rotas
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

app.register_blueprint(imoveis_bp)

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
