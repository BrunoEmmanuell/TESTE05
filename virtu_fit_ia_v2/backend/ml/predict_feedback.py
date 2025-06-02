# backend/ml/predict_feedback.py
import joblib
import pandas as pd
import logging
from pathlib import Path
import sys

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Ajuste de Path para importar data_preparation (se necessário para features) ---
script_dir = Path(__file__).resolve().parent # /backend/ml
backend_dir = script_dir.parent # /backend
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
    logger.debug(f"Adicionado '{backend_dir}' ao sys.path")

try:
    # Importa funções/constantes de data_preparation se precisar delas
    # para processar os dados de entrada da mesma forma que no treino
    from ml.data_preparation import extract_workout_features, normalize_text, FEEDBACK_MAP
    logger.info("Funções/Constantes importadas de data_preparation.")
except ImportError as e:
    logger.error(f"Erro ao importar de ml.data_preparation: {e}")
    logger.error("Certifique-se que os scripts estão na mesma pasta 'ml'.")
    # Defina fallbacks se necessário, mas a importação é ideal
    def extract_workout_features(json_str): logger.error("Fallback extract_workout_features!"); return {}
    def normalize_text(text): logger.error("Fallback normalize_text!"); return text if text else ""
    FEEDBACK_MAP = {"Excelente": 4, "Bom": 3, "Médio": 2, "Ruim": 1}


# --- Constantes ---
MODEL_FILE = script_dir / "feedback_predictor_model.joblib"
# Mapeamento inverso para converter predição numérica em texto
SCORE_TO_FEEDBACK_MAP = {v: k for k, v in FEEDBACK_MAP.items()}

# --- Carregar o Modelo (uma vez quando o módulo é importado) ---
try:
    model = joblib.load(MODEL_FILE)
    logger.info(f"Modelo de previsão de feedback carregado de '{MODEL_FILE}'.")
except FileNotFoundError:
    logger.error(f"Erro CRÍTICO: Modelo '{MODEL_FILE}' não encontrado.")
    logger.error("Execute o script 'train_feedback_model.py' primeiro.")
    model = None # Define como None para evitar erros posteriores
except Exception as e:
    logger.exception(f"Erro ao carregar o modelo '{MODEL_FILE}': {e}")
    model = None

# --- Função de Predição ---
def predict_plan_feedback(aluno_info: dict, plano_gerado: dict) -> str | None:
    """
    Prevê o feedback para um plano gerado, dado o aluno e o plano.
    Retorna o feedback previsto como string ('Excelente', 'Bom', etc.) ou None se erro.
    """
    if model is None:
        logger.error("Modelo não está carregado. Impossível fazer a predição.")
        return None
    if not isinstance(aluno_info, dict) or not isinstance(plano_gerado, dict):
         logger.error("Entrada inválida para predição (aluno_info ou plano_gerado não são dicts).")
         return None

    logger.info("Iniciando predição de feedback...")

    try:
        # 1. Criar um DataFrame de uma linha com as features do aluno e do plano
        #    Esta parte precisa **replicar EXATAMENTE** a engenharia de features
        #    feita em data_preparation.py para os dados de entrada!

        # a) Features do Aluno
        features = {
            'aluno_idade': aluno_info.get('idade'),
            'aluno_nivel': normalize_text(aluno_info.get('nivel', '')),
            'aluno_sexo': normalize_text(aluno_info.get('sexo', '')),
            'aluno_foco': normalize_text(aluno_info.get('foco_treino', '')),
            'aluno_lesoes': normalize_text(aluno_info.get('historico_lesoes', '')),
            # Adicione medidas se foram usadas no treino (IMC, etc.)
            # 'imc': calcular_imc(aluno_info.get('medidas', {})),
        }
        logger.debug(f"Features iniciais do aluno: {features}")


        # b) Features do Plano (usando a mesma função de extração)
        #    Assume que plano_gerado é o dict completo retornado pela IA
        try:
            # Precisa do JSON como string para a função de exemplo
            plano_json_str = json.dumps(plano_gerado)
        except Exception:
             plano_json_str = "{}" # Fallback

        workout_features = extract_workout_features(plano_json_str)
        features.update(workout_features) # Adiciona features do treino ao dict
        logger.debug(f"Features combinadas (aluno + treino): {features}")

        # c) Converter para DataFrame e aplicar One-Hot Encoding (igual ao treino)
        input_df = pd.DataFrame([features])

        # Aplicar normalização de texto nas colunas categóricas ANTES do get_dummies
        categorical_cols_predict = ['aluno_nivel', 'aluno_sexo', 'aluno_foco', 'aluno_lesoes'] # Adicione 'dia_key' se prever por dia
        for col in categorical_cols_predict:
             if col in input_df.columns:
                  input_df[col] = input_df[col].fillna('Nenhuma').astype(str).apply(normalize_text)

        # Aplicar get_dummies - IMPORTANTE: usar as mesmas colunas e prefixos do treino!
        # Para garantir consistência, o ideal é salvar as colunas do treino (X_train.columns)
        # e reindexar o input_df para ter exatamente as mesmas colunas, preenchendo com 0 as faltantes.
        # Exemplo simplificado (PODE DAR ERRO se categorias novas aparecerem):
        try:
             # Carrega colunas usadas no treino (você precisa salvar isso no script de treino)
             trained_columns_file = script_dir / "trained_model_columns.json"
             with open(trained_columns_file, 'r') as f:
                  trained_columns = json.load(f)

             input_df_encoded = pd.get_dummies(input_df, columns=categorical_cols_predict, prefix=categorical_cols_predict, dummy_na=False)

             # Reindexar para garantir as mesmas colunas do treino
             input_df_reindexed = input_df_encoded.reindex(columns=trained_columns, fill_value=0)
             logger.debug(f"Features prontas para predição (shape {input_df_reindexed.shape}):\n{input_df_reindexed.iloc[0].to_dict()}")

        except FileNotFoundError:
             logger.error(f"Arquivo de colunas do treino '{trained_columns_file}' não encontrado. Salve X_train.columns no script de treino.")
             return None
        except Exception as e_encode:
             logger.exception(f"Erro durante encoding/reindexing para predição: {e_encode}")
             return None


        # d) Tratar NaNs numéricos (igual ao treino)
        numeric_cols_predict = input_df_reindexed.select_dtypes(include=['number']).columns
        if input_df_reindexed[numeric_cols_predict].isnull().sum().sum() > 0:
            logger.warning("Detectados NaNs nas features numéricas para predição. Usando mediana como fallback (verifique a preparação).")
            # Idealmente, você teria salvo os valores de imputação do treino (medianas/médias)
            # Aqui, usamos a mediana do próprio input (pode não ser ideal)
            input_df_reindexed = input_df_reindexed.fillna(input_df_reindexed.median())


        # 2. Fazer a Predição
        prediction_numeric = model.predict(input_df_reindexed)
        predicted_score = prediction_numeric[0] # Pega o primeiro (e único) resultado
        logger.info(f"Predição numérica do modelo: {predicted_score}")

        # 3. Converter para Texto
        predicted_label = SCORE_TO_FEEDBACK_MAP.get(predicted_score, "Desconhecido")
        logger.info(f"Feedback previsto: {predicted_label}")

        return predicted_label

    except Exception as e:
        logger.exception(f"Erro inesperado durante a predição de feedback: {e}")
        return None

# --- Bloco de Teste (Exemplo) ---
if __name__ == '__main__':
    logger.info("Executando teste da função de predição...")

    # Crie dados de exemplo para testar (substitua com dados reais se possível)
    # Use a mesma estrutura esperada pelas suas features
    sample_aluno_info = {
        "id": 999, "nivel": "Intermediario", "sexo": "Masculino", "idade": 30,
        "foco_treino": "hipertrofia", "historico_lesoes": "", "medidas": {"peso_kg": 80, "altura_cm": 180}
    }
    # Pegue um JSON de treino real gerado anteriormente para teste
    sample_plano_gerado = {
        "plano_info": {"template_id": "intermediario_m_abcd_v2"},
        "dias_treino": {
            "A": {"nome_dia": "Peito, Tríceps", "exercicios": [
                {"tipo_item": "exercicio_normal", "exercicio": {"chave_original": "supino_reto_barra", "nome": "Supino Reto com Barra", "series": 3, "repeticoes": "8-12", "descanso": "60s", "grupo": "Peito", "tipo": "Composto"}},
                {"tipo_item": "exercicio_normal", "exercicio": {"chave_original": "supino_inclinado_halteres", "nome": "Supino Inclinado Halter", "series": 3, "repeticoes": "10-15", "descanso": "60s", "grupo": "Peito", "tipo": "Composto"}},
                {"tipo_item": "exercicio_normal", "exercicio": {"chave_original": "triceps_testa_barra", "nome": "Tríceps Testa", "series": 3, "repeticoes": "8-12", "descanso": "60s", "grupo": "Triceps", "tipo": "Isolado"}}
            ]},
            # ... outros dias ...
        },
         "observacoes_gerais": []
    }

    # --- IMPORTANTE: Salve as colunas durante o treino! ---
    # Execute este trecho no `train_feedback_model.py` após definir `X_train`:
    #
    # import json
    # columns_path = script_dir / "trained_model_columns.json"
    # with open(columns_path, 'w') as f:
    #     json.dump(X_train.columns.tolist(), f)
    # logger.info(f"Colunas do modelo salvas em {columns_path}")
    # --- Fim do trecho para salvar colunas ---


    # Só executa a predição se o modelo foi carregado
    if model:
        predicted_feedback = predict_plan_feedback(sample_aluno_info, sample_plano_gerado)

        if predicted_feedback:
            print(f"\nFeedback previsto para o plano de exemplo: {predicted_feedback}")
        else:
            print("\nNão foi possível gerar a predição para o plano de exemplo.")
    else:
        print("\nModelo não carregado, predição não realizada.")