from flask import Flask, render_template, request, redirect, url_for, session, g
from urllib.parse import quote_plus
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# configurar a aplicação
app = Flask(__name__)
app.config['SECRET_KEY'] = '30042007'

# CONFIGURAÇÃO DO BANCO DE DADOS
DB_USER = 'postgres'
DB_PASSWORD = '30042007'
DB_HOST = 'localhost'
DB_NAME = 'py_estoque_3a'
DB_PORT = '5432'
# URL-encode A SENHA PARA GARANTIR QUE CARACTERES ESPECIAIS SEJAM TRATADOS CORRETAMENTE
ENCODED_DB_PASSWORD = quote_plus(DB_PASSWORD)

app.config['DATABASE_URL'] = f"postgreql://{DB_USER}:{ENCODED_DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
# função para conexão com banco de dados


def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME
        )
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.cursor()
    cur.execute(query, args)
    #db.commit()
    rv = cur.fetchall()
    cur.close
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    db = get_db()
    cur = db.cursor()
    cur.execute(query, args)
    db.commit()
    # Retornar o ID do último registro inserido, útil para o Serial
    if cur.description:
        last_id = cur.fetchall()[0]
    else:
        last_id = None
    cur.close()
    return last_id


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('autenticacao'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def home():
    if 'usuario_id' in session:
        return redirect(url_for('cadastro_produto'))
    return redirect(url_for('autenticacao'))


@app.route('/autenticacao', methods=['GET', 'POST'])
def autenticacao():
    if request.method == 'POST':
        email = request.form['email']
        senha = request.form['senha']
        usuario = query_db(
            'SELECT * FROM usuarios WHERE email = %s, ' (email,), one=True)
        if usuario and check_password_hash(usuario['senha'], senha):
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = usuario['nome']
            return redirect(url_for('cadastro_produto'))
        else:
            return render_template('autenticacao.html', erro='E-mail ou senha inválidos.')
    return render_template('autenticacao.html')


@app.route('/cadastrar_usuario', methods=['GET', 'POST'])
def cadastro_usuario():
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']

        usuario_existente = query_db(
            'SELECT id FROM usuarios WHERE email = %s, ' (email,), one=True)

        if usuario_existente:
            return render_template('autenticacao.html', erro='E-mail já cadastrado. ')

        senha_hash = generate_password_hash(senha, methods='pbkdf2:sha256')
        execute_db('INSERT INTO usuarios (nome, email, senha) VALUES (%s, %s ,%s)',(nome, email, senha_hash))
        return redirect(url_for(autenticacao))
    return render_template('cadastro_usuario.html')


@app.route('/logout')
def logout():
    session.pop('usuario_id', None)
    session.pop('usuario_nome', None)
    return redirect(url_for(autenticacao))


@app.route('/cadastro_protudo', methods=['GET', 'POST'])
@login_required
def cadastro_produto():
    if request.method == 'POST':
        nome = request.form['nome']
        descricao = request.form['descricao']
        quantidade = int(request.form['quantitade'])
        preco = float(request.form['preco'])
        quantidade_minima = int(request.form['quantitade_minima'])

        produto = query_db(
            'SELECT * FROM produtos WHERE nome = %s', (nome,), one=True)

        if produto:
            execute_db('UPDATE produtos SET quantidade = quantidade + %s, quantidade_minima = %s WHERE id = %s',(quantidade, quantidade_minima, produto['id']))
            produto_id = produto['id']
        else:
            result = execute_db(
                'INSERT INTO produtos (nome, descricao, quantidade_minima) VALUES (%s, %s, %s, %s, %s) RETURNING id, (nome, descricao, quantidade, preco, quantidade_minima)')
            produto_id = result

        execute_db('INSERT INTO movimentacao_estoque (produto_id, tipo_movimentacao, quantidade, usuario_id) VALUES (%s, %s, %s, %s)',(produto_id, 'entrada', quantidade, session['usuario_id']))

        return redirect(url_for('cadastro_produto'))

    # ordernar os produtos com base na quantidade mínima
    produtos = query_db(
        'SELECT * FROM produtos ORDER BY quantidade - quantidade_minima')
    return render_template('cadastro_produto.html', produtos=produtos, usuario=session.get('usuario_nome'))


@app.route('/saida_produto/<int:produto_id>', methods=['POST'])
@login_required
def saida_produto(produto_id):
    produto = query_db('SELECT * FROM produton WHERE id = %s',(produto_id,), one=True)
    if not produto:
        return "Produto não encontrado", 404

    quantidade_saida = int(request.form['quantidade_saida'])

    if quantidade_saida > 0 and produto['quantidade'] >= quantidade_saida:
        execute_db('UPDATE produtos SET quantidade = quantidade - %s WHERE id = %s', (quantidade_saida, produto_id))
        execute_db('INSERT INTO movimentacao_estoque (produto_id,  tipo_movimentacao, quantidade, usuario_id) VALUES (%s, %s, %s, %s)', (produto_id, 'saida', quantidade_saida, session['usuario_id']))

    return redirect(url_for('cadastro_produto'))

@app.route('/estoque')
@login_required
def estoque():
    movimentacoes = query_db('SELECT * FORM movimentacao_estoque AS m JOIN usuario AS u ON m.usuario_id = u.id ORDER BY m.data_movimentacao DESC')
    return render_template('estoque.html', movimentacoes=movimentacoes, usuario=session.get('usuario_nome'))

if __name__ == '__main__':
    app.run(debug=True)
