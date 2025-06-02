# backend/ml/data_preparation.py
import psycopg2
import pandas as pd
import json
import sys
import logging
from pathlib import Path
import unicodedata # Para normalizar texto, se necessário

# --- Configuração de Logging ---
# Usará a configuração definida em main.py se executado como parte da app,
# ou uma configuração básica se executado diretamente.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Ajuste de Path para importar 'database' ---
# Adiciona o diretório pai ('backend') ao sys.path para encontrar 'database.py'
script_dir = Path(__file__).resolve().parent # /backend/ml
backend_dir = script_dir.parent # /backend
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
    logger.debug(f"Adicionado '{backend_dir}' ao sys.path")

try:
    from database import get_db_connection # Importa a função de conexão PG
    logger.info("Função 'get_db_connection' importada com sucesso.")
except ImportError as e:
    logger.critical(f"Erro ao importar 'get_db_connection' de database.py: {e}")
    logger.critical("Certifique-se que database.py está na pasta 'backend'.")
    sys.exit(1) # Sai se não puder importar a conexão

# --- Constantes ---
# Mapeia feedback textual para numérico (ajuste conforme sua preferência)
FEEDBACK_MAP = {"Excelente": 4, "Bom": 3, "Médio": 2, "Ruim": 1}
OUTPUT_CSV_FILE = script_dir / "prepared_training_data.csv" # Salva na mesma pasta ml

# --- Funções Auxiliares (Exemplo: Normalização) ---
def normalize_text(text: str) -> str:
    if not isinstance(text, str): return ""
    try:
        nfkd = unicodedata.normalize('NFD', text)
        sem_acentos = "".join([c for c in nfkd if not unicodedata.combining(c)])
        return sem_acentos.lower().strip()
    except Exception:
        return ""

# --- Função para Extrair Features do Treino JSON ---
def extract_workout_features(plano: dict | None): # Recebe diretamente um dict (ou None)
    """
    Extrai características relevantes do dicionário do treino.
    """
    # Define a estrutura padrão de retorno
    features = {
        'num_total_exercicios': 0,
        'num_dias': 0,
        'avg_ex_por_dia': 0,
        'prop_compostos': 0.0,
        'num_tec_biset': 0,
        'num_tec_piramide': 0,
        # Adicione outras features que julgar importantes
    }

    # Verifica se a entrada é um dicionário válido
    if not isinstance(plano, dict):
        logger.warning(f"Entrada inválida para extract_workout_features: esperado dict, recebido {type(plano)}")
        return features # Retorna features zeradas

    try:
        # NÃO PRECISA MAIS de json.loads() aqui! 'plano' já é um dicionário.
        dias_treino = plano.get("dias_treino", {})
        features['num_dias'] = len(dias_treino)
        if not dias_treino:
            return features # Retorna features zeradas se não houver dias

        total_exercicios_plano = 0
        num_compostos = 0
        num_isolados = 0

        for dia_key, dia_info in dias_treino.items():
            exercicios_dia = dia_info.get("exercicios", [])
            if not isinstance(exercicios_dia, list): continue # Pula se 'exercicios' não for lista

            # Ajuste a lógica de contagem se necessário (ex: biset conta como 1 ou 2?)
            # Aqui, contamos cada item na lista de exercícios do dia
            total_exercicios_plano += len(exercicios_dia)

            for item in exercicios_dia:
                 if not isinstance(item, dict): continue # Pula se item não for dict

                 # Contar técnicas
                 if item.get("tipo_item") == "tecnica":
                     nome_tecnica = item.get("nome_tecnica")
                     if nome_tecnica == "biset":
                         features['num_tec_biset'] += 1
                     elif nome_tecnica == "piramide":
                          features['num_tec_piramide'] += 1
                     # Contar outras técnicas...

                 # Tentar identificar tipo (Composto/Isolado)
                 ex_info = item.get("exercicio") or item.get("exercicio_1")
                 if ex_info and isinstance(ex_info, dict):
                     # Idealmente, buscar o tipo do exercicio_db se não estiver no json
                     # Exemplo simplificado:
                     tipo_ex_no_plano = ex_info.get("tipo", "").lower()
                     if tipo_ex_no_plano == "composto":
                          num_compostos += 1
                     elif tipo_ex_no_plano == "isolado":
                          num_isolados += 1
                     # Se 'tipo' não está no json do plano, você precisaria carregar
                     # o exercicios.json e buscar pelo 'chave_original', se disponível.

        features['num_total_exercicios'] = total_exercicios_plano
        if features['num_dias'] > 0:
            features['avg_ex_por_dia'] = round(total_exercicios_plano / features['num_dias'], 2)

        total_tipos_identificados = num_compostos + num_isolados
        if total_tipos_identificados > 0:
             features['prop_compostos'] = round(num_compostos / total_tipos_identificados, 2)
        else:
             features['prop_compostos'] = 0.0 # Evita divisão por zero e define um padrão

    except (TypeError, KeyError, AttributeError) as e:
        # O erro de slicing no log não deve mais acontecer aqui
        logger.warning(f"Erro ao processar dicionário do plano: {e} - Plano (parcial): {str(plano)[:200]}...")
        return {k: 0 for k in features} # Retorna um dict com zeros em caso de erro

    return features

# --- Função Principal de Preparação ---
def prepare_data():
    """Busca dados, combina, extrai features e salva o dataset."""
    logger.info("Iniciando preparação de dados para ML...")
    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            raise ConnectionError("Não foi possível conectar ao banco de dados.")

        # 1. Buscar Treinos Gerados com Feedback (Exemplo: Feedback por Dia)
        #    Ajuste a query para buscar feedback_grupos se preferir, ou ambos.
        #    Esta query precisa ser ajustada para unir as tabelas corretamente.
        sql_query = """
        SELECT
            tg.id as treino_id,
            tg.aluno_id,
            tg.treino_json,
            fd.dia_key,        -- Se usando feedback por dia
            fd.feedback,       -- O feedback ('Excelente', 'Bom', etc.)
            a.nivel as aluno_nivel,
            a.sexo as aluno_sexo,
            a.idade as aluno_idade,
            a.foco_treino as aluno_foco,
            a.historico_lesoes as aluno_lesoes
            -- Adicione JOIN com 'medidas' se quiser usar medidas como features
            -- Ex: JOIN (SELECT DISTINCT ON (aluno_id) * FROM medidas ORDER BY aluno_id, data_medicao DESC) as m ON a.id = m.aluno_id
        FROM treinos_gerados tg
        JOIN feedback_dias fd ON tg.id = fd.treino_gerado_id -- JOIN com feedback
        JOIN alunos a ON tg.aluno_id = a.id                -- JOIN com alunos
        WHERE fd.feedback IS NOT NULL -- Garante que temos um feedback
        ORDER BY tg.data_geracao DESC; -- Ou outra ordenação relevante
        """
        logger.info("Executando query para buscar dados de treino e feedback...")
        df = pd.read_sql_query(sql_query, conn)
        logger.info(f"Dados brutos carregados: {df.shape[0]} registros.")

        if df.empty:
            logger.warning("Nenhum dado com feedback encontrado. Verifique as tabelas 'treinos_gerados' e 'feedback_dias'.")
            return

        # 2. Processar e Extrair Features
        logger.info("Processando dados e extraindo features...")

        # Aplicar extração de features do JSON
        workout_features_df = df['treino_json'].apply(lambda x: pd.Series(extract_workout_features(x)))
        logger.debug(f"Features extraídas do treino:\n{workout_features_df.head()}")

        # Combinar features do treino com o dataframe principal
        df = pd.concat([df.drop(columns=['treino_json']), workout_features_df], axis=1)

        # Mapear feedback para numérico (Target Variable)
        df['feedback_score'] = df['feedback'].map(FEEDBACK_MAP)
        df = df.dropna(subset=['feedback_score']) # Remove linhas onde o feedback não pode ser mapeado
        df['feedback_score'] = df['feedback_score'].astype(int)
        logger.debug(f"Feedback mapeado para score:\n{df[['feedback', 'feedback_score']].head()}")

        # Converter Features Categóricas do Aluno (Exemplo com One-Hot Encoding)
        categorical_cols = ['aluno_nivel', 'aluno_sexo', 'aluno_foco', 'aluno_lesoes', 'dia_key'] # Adicione outras se necessário
        # Normalizar texto antes do encoding pode ser útil
        for col in categorical_cols:
            if col in df.columns:
                 # Tratar NaNs antes de normalizar
                 df[col] = df[col].fillna('Nenhuma').astype(str).apply(normalize_text)


        df = pd.get_dummies(df, columns=categorical_cols, prefix=categorical_cols, dummy_na=False) # dummy_na=False para não criar coluna para NaN
        logger.debug(f"Colunas após One-Hot Encoding: {df.columns.tolist()}")

        # Remover colunas não necessárias para o modelo
        cols_to_drop = ['treino_id', 'aluno_id', 'feedback'] # Mantenha 'feedback_score'
        df = df.drop(columns=cols_to_drop, errors='ignore')

        # Tratar NaNs em colunas numéricas (ex: imputar com mediana ou média)
        numeric_cols = df.select_dtypes(include=['number']).columns
        for col in numeric_cols:
            if df[col].isnull().any():
                median_val = df[col].median()
                df[col] = df[col].fillna(median_val)
                logger.info(f"Valores nulos na coluna numérica '{col}' preenchidos com mediana ({median_val}).")


        # Verificar se ainda existem NaNs
        if df.isnull().sum().sum() > 0:
            logger.warning(f"Ainda existem NaNs no dataset após tratamento:\n{df.isnull().sum()}")
            # Considere estratégias mais robustas se necessário
            # df = df.dropna() # Opção drástica: remover linhas com NaN

        # 3. Salvar Dataset Processado
        logger.info(f"Salvando dataset preparado em '{OUTPUT_CSV_FILE}'...")
        df.to_csv(OUTPUT_CSV_FILE, index=False)
        logger.info(f"Dataset salvo com sucesso! Shape final: {df.shape}")
        logger.info(f"Colunas finais: {df.columns.tolist()}")
        logger.info(f"Distribuição do Feedback Score:\n{df['feedback_score'].value_counts()}")


    except (psycopg2.Error, ConnectionError) as db_err:
        logger.exception(f"Erro de banco de dados: {db_err}")
    except FileNotFoundError as fnf_err:
        logger.exception(f"Erro de arquivo não encontrado: {fnf_err}")
    except Exception as e:
        logger.exception(f"Erro inesperado durante a preparação dos dados: {e}")
    finally:
        if conn:
            conn.close()
            logger.debug("Conexão com o banco de dados fechada.")

if __name__ == "__main__":
    # Executa a preparação dos dados quando o script é rodado diretamente
    prepare_data()