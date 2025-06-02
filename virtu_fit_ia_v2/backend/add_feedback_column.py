# add_feedback_column.py
import sqlite3
import logging
from pathlib import Path
import sys

# --- Configuração básica de logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - MIGRATION - %(message)s')

# --- Encontrar e importar a função de conexão do database.py ---
try:
    # Tenta importar assumindo que este script está na pasta raiz do projeto
    # e database.py está em backend/
    project_root = Path(__file__).resolve().parent
    backend_dir = project_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from database import get_db_connection, DATABASE_FILE
    logging.info(f"Função get_db_connection importada de 'backend.database'. Usando DB: {DATABASE_FILE}")

except ImportError:
    logging.error("Não foi possível importar 'get_db_connection' de backend.database.")
    logging.error("Certifique-se de que este script está na pasta raiz do projeto e database.py está em backend/")
    # Fallback: Se não conseguir importar, define o nome do arquivo aqui
    DATABASE_FILE = "virtufit_data.db"
    def get_db_connection(): # Redefine uma função básica de conexão como fallback
        conn = None
        try:
            conn = sqlite3.connect(DATABASE_FILE, timeout=5.0)
            conn.execute("PRAGMA foreign_keys = ON;")
            logging.info("Usando conexão de fallback.")
            return conn
        except sqlite3.Error as e:
            logging.error(f"Erro na conexão de fallback: {e}")
            raise

def add_feedback_column():
    """Adiciona a coluna 'feedback_instrutor' à tabela 'treinos_gerados'."""
    conn = None
    try:
        logging.info(f"Conectando ao banco de dados '{DATABASE_FILE}'...")
        conn = get_db_connection()
        cursor = conn.cursor()

        logging.info("Verificando se a coluna 'feedback_instrutor' já existe...")
        cursor.execute("PRAGMA table_info(treinos_gerados);")
        columns = [column[1] for column in cursor.fetchall()]

        if 'feedback_instrutor' in columns:
            logging.warning("A coluna 'feedback_instrutor' já existe na tabela 'treinos_gerados'. Nenhuma alteração necessária.")
        else:
            logging.info("Coluna não encontrada. Adicionando 'feedback_instrutor' TEXT à tabela 'treinos_gerados'...")
            # Adiciona a coluna
            cursor.execute("ALTER TABLE treinos_gerados ADD COLUMN feedback_instrutor TEXT;")
            conn.commit()
            logging.info("Coluna 'feedback_instrutor' adicionada com sucesso!")

    except sqlite3.Error as e:
        logging.error(f"Erro durante a alteração da tabela 'treinos_gerados': {e}")
        if conn:
            conn.rollback() # Desfaz em caso de erro
    except Exception as e:
        logging.error(f"Erro inesperado: {e}")
    finally:
        if conn:
            conn.close()
            logging.info("Conexão com o banco de dados fechada.")

if __name__ == "__main__":
    print("--- Iniciando script para adicionar coluna de feedback ---")
    add_feedback_column()
    print("--- Script finalizado ---")