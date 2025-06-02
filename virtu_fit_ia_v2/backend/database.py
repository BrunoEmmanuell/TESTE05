# backend/database.py
# Versão MODIFICADA - Define DictCursor na conexão e Logging Aprimorado + Tabela feedback_dias

from dotenv import load_dotenv
load_dotenv() # Carrega variáveis do .env
import psycopg2
import psycopg2.extras # Para retornar dicionários
import logging
import os
import sys # Importar sys para StreamHandler, se usado

# Logger para este módulo - Obtido da configuração centralizada em main.py
db_logger = logging.getLogger(__name__)

# --- Configurações de Conexão PostgreSQL (Use Variáveis de Ambiente!) ---
# As variáveis são carregadas por load_dotenv() no início do arquivo
DB_NAME = os.environ.get('PG_DB_NAME', 'virtufit_db')
DB_USER = os.environ.get('PG_DB_USER', 'virtufit_user')
DB_PASSWORD = os.environ.get('PG_DB_PASSWORD', 'novaSenha123')
DB_HOST = os.environ.get('PG_DB_HOST', 'localhost')
DB_PORT = os.environ.get('PG_DB_PORT', '5432')

def get_db_connection():
    """Cria e retorna uma conexão com o banco de dados PostgreSQL,
       configurada para retornar dicionários."""
    conn = None
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            cursor_factory=psycopg2.extras.DictCursor # <--- Cursor como Dicionário
        )
        db_logger.debug(f"Conexão com PostgreSQL DB '{DB_NAME}' estabelecida (Cursor: DictCursor).")
        return conn
    except psycopg2.Error as e:
        db_logger.error(f"Erro ao conectar ao banco de dados PostgreSQL {DB_NAME}: {e}")
        raise
    except Exception as e:
        db_logger.exception(f"Erro inesperado em get_db_connection: {e}")
        raise


def init_db():
    """Inicializa o banco de dados criando as tabelas PostgreSQL se não existirem,
       incluindo a nova tabela para feedback por dia."""
    db_logger.info(f"Inicializando DB PostgreSQL: Verificando/Criando tabelas em '{DB_NAME}'...")
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Tabela Instrutores
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS instrutores (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            email TEXT UNIQUE,
            hashed_password TEXT NOT NULL,
            data_registro TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        """)
        db_logger.info("Tabela 'instrutores' verificada/criada.")

        # Tabela Alunos
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS alunos (
            id SERIAL PRIMARY KEY,
            instrutor_id INTEGER NOT NULL REFERENCES instrutores(id) ON DELETE CASCADE,
            nome TEXT NOT NULL,
            sexo TEXT CHECK(sexo IN ('Masculino', 'Feminino')),
            idade INTEGER,
            nivel TEXT CHECK(nivel IN ('Iniciante', 'Intermediário', 'Avançado')),
            objetivos TEXT,
            historico_lesoes TEXT,
            foco_treino TEXT,
            data_cadastro TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_aluno_instrutor ON alunos (instrutor_id);")
        db_logger.info("Tabela 'alunos' verificada/criada.")

        # Tabela Medidas
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS medidas (
            id SERIAL PRIMARY KEY,
            aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            data_medicao TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            altura_cm REAL, peso_kg REAL, circ_ombros_cm REAL, circ_peito_cm REAL, circ_cintura_cm REAL, circ_quadril_cm REAL,
            circ_biceps_d_relaxado_cm REAL, circ_biceps_e_relaxado_cm REAL, circ_biceps_d_contraido_cm REAL, circ_biceps_e_contraido_cm REAL,
            circ_antebraco_d_cm REAL, circ_antebraco_e_cm REAL, circ_coxa_d_cm REAL, circ_coxa_e_cm REAL, circ_panturrilha_d_cm REAL, circ_panturrilha_e_cm REAL,
            dc_triceps_mm REAL, dc_subescapular_mm REAL, dc_peitoral_axilar_mm REAL, dc_suprailiaca_mm REAL, dc_abdominal_mm REAL, dc_coxa_mm REAL, dc_panturrilha_mm REAL
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_medidas_aluno ON medidas (aluno_id);")
        db_logger.info("Tabela 'medidas' verificada/criada.")

        # Tabela Treinos Gerados
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS treinos_gerados (
            id SERIAL PRIMARY KEY,
            aluno_id INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
            data_geracao TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            treino_json JSONB NOT NULL,
            feedback_instrutor TEXT NULL -- Mantido por enquanto
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_treinos_aluno ON treinos_gerados (aluno_id);")
        db_logger.info("Tabela 'treinos_gerados' verificada/criada.")

        # Tabela Feedback por Grupo (Existente)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback_grupos (
            id SERIAL PRIMARY KEY,
            treino_gerado_id INTEGER NOT NULL REFERENCES treinos_gerados(id) ON DELETE CASCADE,
            grupo_muscular TEXT NOT NULL,
            feedback TEXT NOT NULL CHECK(feedback IN ('Excelente', 'Bom', 'Médio', 'Ruim')),
            comentario TEXT NULL,
            data_feedback TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (treino_gerado_id, grupo_muscular)
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_grupo_treino ON feedback_grupos (treino_gerado_id);")
        db_logger.info("Tabela 'feedback_grupos' verificada/criada.")

        # --- NOVA Tabela Feedback por Dia ---
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback_dias (
            id SERIAL PRIMARY KEY,
            treino_gerado_id INTEGER NOT NULL REFERENCES treinos_gerados(id) ON DELETE CASCADE,
            dia_key TEXT NOT NULL, -- Ex: 'A', 'B', 'C'
            feedback TEXT NOT NULL CHECK(feedback IN ('Excelente', 'Bom', 'Médio', 'Ruim')),
            -- comentario TEXT NULL, -- Descomente se quiser adicionar comentários por dia
            data_feedback TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (treino_gerado_id, dia_key) -- Garante um feedback por dia por treino
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_dia_treino ON feedback_dias (treino_gerado_id);")
        db_logger.info("Tabela 'feedback_dias' verificada/criada.") # Log para a nova tabela
        # --- Fim Nova Tabela ---

        conn.commit()
        db_logger.info("Inicialização do DB PostgreSQL concluída com sucesso.")

    except psycopg2.Error as e:
        db_logger.error(f"Erro durante inicialização do DB PostgreSQL: {e}")
        if conn: conn.rollback()
    except Exception as e:
         db_logger.exception(f"Erro inesperado durante init_db: {e}")
         if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        db_logger.debug("Conexão DB fechada (init_db).")


# Bloco de teste para execução direta (sem alterações)
if __name__ == "__main__":
    print("Tentando inicializar o banco de dados PostgreSQL...")
    try:
        conn_teste = get_db_connection()
        print(f"Conexão com {DB_NAME} bem-sucedida! (Cursor factory: {type(conn_teste.cursor).__name__})")
        conn_teste.close()
        init_db()
        print("Função init_db() executada.")
    except Exception as main_e:
        db_logger.exception(f"Erro ao executar o teste de inicialização: {main_e}")
        print(f"Erro ao executar o teste de inicialização: {main_e}")
        print("Verifique as configurações de conexão (DB_NAME, USER, PASSWORD, HOST, PORT) e se o servidor PostgreSQL está acessível.")