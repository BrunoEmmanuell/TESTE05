# backend/ml/train_feedback_model.py
import pandas as pd
import joblib
import logging
from pathlib import Path
import json
from sklearn.model_selection import train_test_split, GridSearchCV # ADICIONADO GridSearchCV
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from sklearn.preprocessing import LabelEncoder

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Constantes ---
script_dir = Path(__file__).resolve().parent
INPUT_CSV_FILE = script_dir / "prepared_training_data.csv"
MODEL_OUTPUT_FILE = script_dir / "feedback_predictor_model.joblib"
TRAINED_COLUMNS_OUTPUT_FILE = script_dir / "trained_model_columns.json"

# Mapeamento inverso para o relatório de classificação
FEEDBACK_MAP_ORIGINAL = {"Excelente": 4, "Bom": 3, "Médio": 2, "Ruim": 1}
FEEDBACK_MAP_INVERSO = {v: k for k, v in FEEDBACK_MAP_ORIGINAL.items()}


# --- Função Principal de Treinamento ---
def train_model():
    """Carrega dados, treina com XGBoost e GridSearchCV, avalia e salva o modelo."""
    logger.info("Iniciando treinamento do modelo de previsão de feedback com XGBoost e GridSearchCV...")

    # 1. Carregar Dados Preparados
    try:
        logger.info(f"Carregando dados de '{INPUT_CSV_FILE}'...")
        df = pd.read_csv(INPUT_CSV_FILE)
        logger.info(f"Dados carregados: {df.shape[0]} linhas, {df.shape[1]} colunas.")
        if df.empty:
            logger.error("O arquivo de dados preparados está vazio. Execute data_preparation.py primeiro.")
            return
    except FileNotFoundError:
        logger.error(f"Erro: Arquivo de dados preparados '{INPUT_CSV_FILE}' não encontrado.")
        logger.error("Execute o script 'data_preparation.py' primeiro.")
        return
    except Exception as e:
        logger.exception(f"Erro ao carregar o arquivo CSV: {e}")
        return

    # 2. Separar Features (X) e Target (y)
    try:
        target_column = 'feedback_score'
        if target_column not in df.columns:
            logger.error(f"Coluna target '{target_column}' não encontrada no dataset.")
            logger.error(f"Colunas disponíveis: {df.columns.tolist()}")
            return

        X = df.drop(columns=[target_column])
        y_original_labels = df[target_column]
        logger.info(f"Features (X) shape: {X.shape}")
        logger.info(f"Target (y) shape: {y_original_labels.shape}")

        if X.isnull().sum().sum() > 0:
             logger.warning(f"Detectados NaNs nas features (X) antes do split. Verifique data_preparation.py.")
             # X = X.fillna(X.median()) # Considere tratar em data_preparation.py
             # logger.warning("NaNs preenchidos com mediana como fallback.")

    except KeyError as e:
        logger.error(f"Erro ao separar features/target: Coluna não encontrada - {e}")
        return
    except Exception as e:
        logger.exception(f"Erro inesperado ao preparar X e y: {e}")
        return

    # Codificar os rótulos (target y) para que comecem de 0
    le = LabelEncoder()
    y_encoded = le.fit_transform(y_original_labels)
    target_names_for_report = [f"{FEEDBACK_MAP_INVERSO.get(label, str(label))} (score {label})" for label in le.classes_]

    # 3. Dividir em Treino e Teste
    try:
        X_train, X_test, y_train_encoded, y_test_encoded = train_test_split(
            X, y_encoded,
            test_size=0.2,
            random_state=42,
            stratify=y_encoded
        )
        logger.info(f"Dados divididos: Treino={X_train.shape[0]}, Teste={X_test.shape[0]}")
    except ValueError as ve:
        logger.warning(f"Erro ao tentar estratificar (ValueError: {ve}). Tentando dividir sem estratificação...")
        try:
            X_train, X_test, y_train_encoded, y_test_encoded = train_test_split(X, y_encoded, test_size=0.2, random_state=42)
            logger.info(f"Dados divididos (sem stratify): Treino={X_train.shape[0]}, Teste={X_test.shape[0]}")
        except Exception as e_nostrat:
            logger.exception(f"Erro fatal ao dividir os dados mesmo sem estratificação: {e_nostrat}")
            return
    except Exception as e:
         logger.exception(f"Erro ao dividir os dados em treino/teste: {e}")
         return

    # 4. Definir o Modelo Base e a Grade de Hiperparâmetros para GridSearchCV
    logger.info("Configurando GridSearchCV para XGBClassifier...")
    xgb_base_model = XGBClassifier(
        objective='multi:softmax',
        num_class=len(le.classes_),
        random_state=42,
        use_label_encoder=False, # Já fizemos o encoding manualmente
        eval_metric='mlogloss'
    )

    # Grade de parâmetros para testar - comece com uma grade menor para testes rápidos
    # Depois, você pode expandir esta grade
    param_grid = {
        'n_estimators': [100, 200],             # Número de árvores
        'learning_rate': [0.05, 0.1],           # Taxa de aprendizado
        'max_depth': [3, 5],                    # Profundidade máxima da árvore
        'subsample': [0.8, 1.0],                # Fração de amostras usadas para cada árvore
        'colsample_bytree': [0.8, 1.0]          # Fração de features usadas para cada árvore
    }
    # Para uma busca mais completa (pode demorar mais):
    # param_grid = {
    #     'n_estimators': [50, 100, 200, 300],
    #     'learning_rate': [0.01, 0.05, 0.1, 0.2],
    #     'max_depth': [3, 5, 7, 9],
    #     'subsample': [0.6, 0.7, 0.8, 0.9, 1.0],
    #     'colsample_bytree': [0.6, 0.7, 0.8, 0.9, 1.0],
    #     'gamma': [0, 0.1, 0.2], # Parâmetro de regularização
    #     'min_child_weight': [1, 5, 10] # Parâmetro de regularização
    # }


    # Configurar GridSearchCV
    # cv=3 significa validação cruzada de 3 folds. Aumente para 5 para mais robustez (mais tempo).
    # scoring='accuracy' é comum. Se suas classes forem desbalanceadas, considere 'f1_weighted'.
    grid_search = GridSearchCV(
        estimator=xgb_base_model,
        param_grid=param_grid,
        scoring='accuracy', # Ou 'f1_weighted' se as classes forem desbalanceadas
        cv=3,               # Número de folds da validação cruzada
        n_jobs=-1,          # Usar todos os processadores disponíveis
        verbose=2           # Mostra mais informações durante a execução
    )

    # 5. Treinar o Modelo usando GridSearchCV
    try:
        logger.info("Iniciando busca de hiperparâmetros com GridSearchCV...")
        grid_search.fit(X_train, y_train_encoded)
        logger.info("Busca de hiperparâmetros com GridSearchCV concluída.")
        logger.info(f"Melhores Parâmetros encontrados: {grid_search.best_params_}")
        logger.info(f"Melhor Score (Validação Cruzada): {grid_search.best_score_:.4f}")

        # O melhor modelo treinado está em grid_search.best_estimator_
        model = grid_search.best_estimator_
    except Exception as e:
        logger.exception(f"Erro durante o GridSearchCV: {e}")
        # Como fallback, você poderia treinar um modelo com parâmetros padrão se o GridSearch falhar
        # logger.info("GridSearchCV falhou. Treinando XGBoost com parâmetros padrão como fallback...")
        # model = xgb_base_model
        # model.fit(X_train, y_train_encoded)
        return


    # 6. Avaliar o Melhor Modelo Encontrado
    logger.info("Avaliando o melhor modelo no conjunto de teste...")
    try:
        y_pred_encoded = model.predict(X_test)
        y_pred_original = le.inverse_transform(y_pred_encoded)
        y_test_original = le.inverse_transform(y_test_encoded)

        accuracy = accuracy_score(y_test_original, y_pred_original)
        report = classification_report(y_test_original, y_pred_original, target_names=target_names_for_report)
        conf_matrix = confusion_matrix(y_test_original, y_pred_original, labels=le.classes_)

        logger.info(f"Acurácia no Teste (com melhor modelo): {accuracy:.4f}")
        logger.info(f"Relatório de Classificação (com melhor modelo):\n{report}")
        logger.info(f"Matriz de Confusão (Rótulos Originais: {le.classes_}):\n{conf_matrix}")

    except Exception as e:
        logger.exception(f"Erro durante a avaliação do melhor modelo: {e}")


    # 7. Salvar o Melhor Modelo Treinado e as Colunas
    try:
        logger.info(f"Salvando o melhor modelo treinado em '{MODEL_OUTPUT_FILE}'...")
        joblib.dump(model, MODEL_OUTPUT_FILE)
        logger.info("Melhor modelo salvo com sucesso!")

        with open(TRAINED_COLUMNS_OUTPUT_FILE, 'w') as f:
            json.dump(X_train.columns.tolist(), f)
        logger.info(f"Colunas do modelo salvas em '{TRAINED_COLUMNS_OUTPUT_FILE}'")

    except Exception as e:
        logger.exception(f"Erro ao salvar o melhor modelo treinado ou as colunas: {e}")

if __name__ == "__main__":
    train_model()