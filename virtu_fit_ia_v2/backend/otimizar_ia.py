# otimizar_ia.py (Versão com Avaliação de Feedback POR GRUPO - Adaptado para PostgreSQL)
# Logging Aprimorado (Usa logger nomeado e configuração centralizada)

import optuna
import json
import random
import logging
from pathlib import Path
from datetime import datetime
import sys
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
load_dotenv() # Carrega variáveis do .env


# --- Configuração de Logging (Apenas obtem os loggers, a configuração é centralizada em main.py) ---
# Logger para este módulo
opt_logger = logging.getLogger(__name__)
# Loggers de outros módulos que este arquivo utiliza
# Se você usou __name__ em gerador_treino_ia, o nome será backend.ia.gerador_treino_ia
ia_logger = logging.getLogger('backend.ia.gerador_treino_ia')
selection_logger = logging.getLogger('SelectionDebug') # Nome do logger de seleção (verificar nome em gerador_treino_ia.py)


# --- Ajuste de Path e Importações (Mantido) ---
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
backend_dir_for_import = Path(__file__).resolve().parent
if str(backend_dir_for_import) not in sys.path:
     sys.path.insert(0, str(backend_dir_for_import))

try:
    # Certifique-se de que a importação está correta
    from backend.ia.gerador_treino_ia import gerar_plano_semanal_ia, SPLIT_TEMPLATES, exercicios_db, normalize_text, GRUPOS_MUSCULARES
    opt_logger.info("Importação de 'gerador_treino_ia' bem-sucedida.")
except ImportError:
    # Este fallback pode ser útil, mas o ideal é corrigir os caminhos no sistema
    try:
        from ia.gerador_treino_ia import gerar_plano_semanal_ia, SPLIT_TEMPLATES, exercicios_db, normalize_text, GRUPOS_MUSCULARES
        opt_logger.info("Importação de 'gerador_treino_ia' (fallback) bem-sucedida.")
    except ImportError as e_fatal:
         opt_logger.critical(f"ERRO FATAL de Importação de gerador_treino_ia: {e_fatal}")
         # Considere levantar o erro ou sair se o gerador for essencial
         exit()


# Importa conexão com DB PostgreSQL
try:
    # Tenta importar do backend (agora database.py conecta ao PG)
    from backend.database import get_db_connection, DB_NAME, DB_HOST # Importa função e talvez configs
    opt_logger.info(f"Importação de 'database' (PostgreSQL) bem-sucedida. Usando DB: {DB_NAME} em {DB_HOST}")
except ImportError:
     opt_logger.error("Falha ao importar de database.py (PostgreSQL). Verifique o path.")
     # Defina um fallback se necessário (mas o ideal é corrigir o import)
     def get_db_connection():
         opt_logger.error("Função get_db_connection não importada, otimização não funcionará corretamente com DB.")
         raise ImportError("get_db_connection não pôde ser importada.")


# --- Alunos de Exemplo para Teste (Mantido) ---
alunos_teste_otimizacao = [
    {"id": "Opt_Fem_Int", "nivel": "Intermediario", "sexo": "Feminino", "foco_treino": "gluteo", "historico_lesoes": "", "medidas": {}},
    {"id": "Opt_Masc_Adv", "nivel": "Avancado", "sexo": "Masculino", "foco_treino": "hipertrofia", "historico_lesoes": "joelho", "medidas": {}},
    # Adicionar mais alunos de teste para maior robustez da otimização
    # {"id": "Opt_Masc_Int", "nivel": "Intermediario", "sexo": "Masculino", "foco_treino": "resistencia", "historico_lesoes": "", "medidas": {}},
    # {"id": "Opt_Fem_Adv", "nivel": "Avancado", "sexo": "Feminino", "foco_treino": "peito", "historico_lesoes": "ombro", "medidas": {}},
]
if not alunos_teste_otimizacao:
     opt_logger.warning("Nenhum aluno de teste definido para otimização.")


# --- Função de Avaliação de Qualidade (Adaptada para Feedback POR GRUPO e PostgreSQL) ---
def avaliar_qualidade_plano(plano_gerado: dict, aluno_info: dict) -> float:
    """
    Avalia um plano gerado, retornando uma pontuação de qualidade.
    Verifica Aderência ao Foco Primário, Volume e CONSIDERA FEEDBACK POR GRUPO (do DB PostgreSQL).
    """
    score_total = 0.0
    PENALIDADE_FOCO_ERRADO_ISOLADO = -100.0; PENALIDADE_FOCO_ERRADO_COMPOSTO = -20.0
    PENALIDADE_VOLUME_EXCEDIDO = -25.0; PENALIDADE_VOLUME_INSUFICIENTE = -15.0 # Penalidades diferentes
    BONUS_FOCO_CERTO = 10.0; BONUS_VOLUME_CERTO = 8.0
    PESO_FOCO = 3.0; PESO_VOLUME = 2.0
    PESO_FEEDBACK_GRUPO = 5.0 # Aumenta o peso do feedback granular
    FEEDBACK_SCORES = {"Excelente": 4, "Bom": 3, "Médio": 2, "Ruim": 1}
    FEEDBACK_SCORE_MULTIPLIER = 1.0 # Multiplicador para ajustar a escala do score de feedback

    conn = None
    cursor = None
    try:
        plano_info = plano_gerado.get("plano_info", {})
        dias_treino = plano_gerado.get("dias_treino", {})
        num_dias_treino = len(dias_treino)
        if num_dias_treino == 0:
            opt_logger.warning("Plano gerado sem dias de treino para avaliação.")
            return -1000.0
        template_id = plano_info.get("template_id")
        aluno_id = aluno_info.get('id') # Obter o ID do aluno para filtrar feedback
        if not template_id or aluno_id is None:
            opt_logger.warning("Template ID ou Aluno ID não encontrado no plano gerado para avaliação.")
            return -500.0

        # --- Avaliação de Foco e Volume (Lógica existente adaptada para penalidades mais claras) ---
        score_foco_dia_total = 0.0
        exercicios_avaliados_foco = 0

        score_volume_dia_total = 0.0
        grupos_avaliados_volume = 0
        template_vol_grupos_total = 0 # Volume total esperado pelo template

        if not exercicios_db:
            opt_logger.error("exercicios_db não carregado para avaliação de foco/volume!")
            # Continuar com o que for possível, ou retornar um score baixo se necessário
            # return -650.0 # Opção de falha crítica

        # Extrair volume total esperado do template para este aluno
        split_template = None
        for key, template_data in SPLIT_TEMPLATES.items():
             if template_data.get("id") == template_id:
                 split_template = template_data
                 break
        if split_template:
             for dia_key, dia_info in split_template.get("dias", {}).items():
                 template_vol_grupos = dia_info.get("vol_grupo", {})
                 template_vol_grupos_total += sum(template_vol_grupos.values())


        for dia_key, info_dia in dias_treino.items():
            grupos_do_dia = split_template.get("dias", {}).get(dia_key, {}).get("grupos", []) if split_template else []
            vol_grupo_template = split_template.get("dias", {}).get(dia_key, {}).get("vol_grupo", {}) if split_template else {}
            foco_dia_template = split_template.get("dias", {}).get(dia_key, {}).get("foco_dia", []) if split_template else []

            # Contar volume gerado por grupo para este dia
            volume_gerado_dia = {g: 0 for g in GRUPOS_MUSCULARES} # Inicializa com 0 para todos os grupos
            exercicios_neste_dia_chaves = set() # Usado para evitar contar exercícios de biset/conjugado duplicado no volume

            for item in info_dia.get("exercicios", []):
                 if item.get("tipo_item") == "exercicio_normal":
                     ex_info = item.get("exercicio", {})
                     chave_ex = ex_info.get("chave_original")
                     grupo_ex = ex_info.get("grupo")
                     if chave_ex and grupo_ex and grupo_ex in volume_gerado_dia:
                         if chave_ex not in exercicios_neste_dia_chaves: # Conta apenas uma vez por exercício no dia
                             volume_gerado_dia[grupo_ex] += 1
                             exercicios_neste_dia_chaves.add(chave_ex)

                 elif item.get("tipo_item") == "tecnica":
                     nome_tec = item.get("nome_tecnica")
                     if nome_tec == "biset" or nome_tec == "piramide": # Biset e Pirâmide contam volume para o grupo principal
                         ex_info = item.get("exercicio_1", {}) if nome_tec == "biset" else item.get("exercicio", {})
                         chave_ex = ex_info.get("chave_original")
                         grupo_ex = ex_info.get("grupo")
                         if chave_ex and grupo_ex and grupo_ex in volume_gerado_dia:
                            if chave_ex not in exercicios_neste_dia_chaves:
                                volume_gerado_dia[grupo_ex] += (2 if nome_tec == "biset" else 1) # Biset consome 2 slots, Piramide 1
                                exercicios_neste_dia_chaves.add(chave_ex)
                     elif nome_tec == "conjugado_antagonista": # Conjugado conta volume para o grupo agonista e antagonista
                         ex1_info = item.get("exercicio_1", {}) # Agonista
                         ex2_info = item.get("exercicio_2", {}) # Antagonista
                         chave1 = ex1_info.get("chave_original"); grupo1 = ex1_info.get("grupo")
                         chave2 = ex2_info.get("chave_original"); grupo2 = ex2_info.get("grupo")
                         if chave1 and grupo1 and grupo1 in volume_gerado_dia and chave1 not in exercicios_neste_dia_chaves:
                              volume_gerado_dia[grupo1] += 1
                              exercicios_neste_dia_chaves.add(chave1)
                         if chave2 and grupo2 and grupo2 in volume_gerado_dia and chave2 not in exercicios_neste_dia_chaves:
                              volume_gerado_dia[grupo2] += 1 # Antagonista também conta volume no seu grupo
                              exercicios_neste_dia_chaves.add(chave2)


            # Avaliar foco e volume por grupo neste dia
            for grupo in grupos_do_dia:
                 if grupo not in GRUPOS_MUSCULARES: continue # Ignora grupos não reconhecidos

                 # Avaliação de Volume por Grupo
                 volume_esperado = vol_grupo_template.get(grupo, 0)
                 volume_real = volume_gerado_dia.get(grupo, 0)
                 grupos_avaliados_volume += 1 # Conta este grupo para a média

                 if volume_esperado > 0:
                      if volume_real == volume_esperado:
                           score_volume_dia_total += BONUS_VOLUME_CERTO
                      elif volume_real > volume_esperado:
                           # Penalidade por volume excessivo
                           score_volume_dia_total += PENALIDADE_VOLUME_EXCEDIDO * ((volume_real - volume_esperado) / volume_esperado) # Penalidade proporcional
                      else: # volume_real < volume_esperado
                           # Penalidade por volume insuficiente
                           score_volume_dia_total += PENALIDADE_VOLUME_INSUFICIENTE * ((volume_esperado - volume_real) / volume_esperado) # Penalidade proporcional
                 # else: # Se volume esperado é 0, qualquer volume real > 0 é penalizado ou ignora

                 # Avaliação de Foco por Exercício dentro do Grupo
                 # Percorrer os exercícios REALMENTE adicionados a este dia
                 for item in info_dia.get("exercicios", []):
                      ex_info = item.get("exercicio") or item.get("exercicio_1") # Pega o primeiro ex para foco
                      if not ex_info: continue
                      if ex_info.get("grupo") != grupo: continue # Só avalia foco para exercícios do grupo correto

                      exercicios_avaliados_foco += 1
                      focos_ex_norm = [normalize_text(f) for f in ex_info.get("foco", []) if isinstance(f, str)]
                      foco_primario_ex = ex_info.get("foco_primario")

                      # Bônus se o foco primário do exercício estiver na lista de focos do dia/aluno
                      if foco_dia_template and foco_primario_ex and normalize_text(foco_primario_ex) in [normalize_text(f) for f in foco_dia_template]:
                           score_foco_dia_total += BONUS_FOCO_CERTO * 0.7 # Bônus por focar no músculo certo do dia
                      elif aluno_info.get("foco_treino") and normalize_text(aluno_info["foco_treino"]) in focos_ex_norm:
                            score_foco_dia_total += BONUS_FOCO_CERTO * 0.3 # Bônus menor por focar no objetivo geral do aluno

                      # Penalidade se um exercício isolado não bater com o foco do dia/aluno principal
                      if ex_info.get("tipo") == "Isolado":
                          is_relevant_foco = (foco_dia_template and foco_primario_ex and normalize_text(foco_primario_ex) in [normalize_text(f) for f in foco_dia_template]) or \
                                             (aluno_info.get("foco_treino") and normalize_text(aluno_info["foco_treino"]) in focos_ex_norm)

                          if not is_relevant_foco:
                              score_foco_dia_total += PENALIDADE_FOCO_ERRADO_ISOLADO
                              opt_logger.debug(f"   Penalidade foco isolado: {ex_info.get('nome')} no grupo {grupo}. Focos ex: {focos_ex_norm}. Focos dia: {foco_dia_template}. Foco aluno: {aluno_info.get('foco_treino')}")

                      # Penalidade se um exercício composto não bater com o foco principal (penalidade menor)
                      if ex_info.get("tipo") == "Composto":
                          is_relevant_foco = (foco_dia_template and foco_primario_ex and normalize_text(foco_primario_ex) in [normalize_text(f) for f in foco_dia_template]) or \
                                             (aluno_info.get("foco_treino") and normalize_text(aluno_info["foco_treino"]) in focos_ex_norm)
                          if not is_relevant_foco:
                               score_foco_dia_total += PENALIDADE_FOCO_ERRADO_COMPOSTO
                               opt_logger.debug(f"   Penalidade foco composto: {ex_info.get('nome')} no grupo {grupo}. Focos ex: {focos_ex_norm}. Focos dia: {foco_dia_template}. Foco aluno: {aluno_info.get('foco_treino')}")


        # Normalizar scores de foco e volume (média por item/grupo avaliado)
        score_foco_norm = score_foco_dia_total / exercicios_avaliados_foco if exercicios_avaliados_foco > 0 else 0.0
        score_volume_norm = score_volume_dia_total / grupos_avaliados_volume if grupos_avaliados_volume > 0 else 0.0

        # --- Avaliação do Feedback Histórico POR GRUPO (Adaptada para PostgreSQL) ---
        score_feedback_grupo_total = 0.0
        grupos_com_feedback = 0

        try:
            conn = get_db_connection() # Obtém conexão com o DB PostgreSQL
            cursor = conn.cursor() # Cursor padrão ou DictCursor configurado globalmente

            # Buscar feedbacks da tabela feedback_grupos para o ALUNO DE TESTE e TEMPLATE DESTE PLANO
            # Não buscamos feedbacks de treinos específicos aqui, mas sim feedbacks agregados para o template/aluno
            # Isso requer uma agregação no DB ou buscar todos os feedbacks relevantes e agregá-los aqui
            # Abordagem: Buscar todos os feedbacks de TREINOS ANTERIORES DESTE ALUNO COM ESTE TEMPLATE
            # E calcular uma média dos feedbacks por grupo muscular.

            sql_avg_feedback_grupos = """
                SELECT
                    fg.grupo_muscular,
                    AVG(CASE fg.feedback
                            WHEN 'Excelente' THEN 4
                            WHEN 'Bom' THEN 3
                            WHEN 'Médio' THEN 2
                            WHEN 'Ruim' THEN 1
                            ELSE 0
                        END) AS media_score_grupo,
                    COUNT(fg.id) as num_feedbacks
                FROM feedback_grupos fg
                JOIN treinos_gerados tg ON fg.treino_gerado_id = tg.id
                WHERE tg.aluno_id = %s
                  AND tg.treino_json -> 'plano_info' ->> 'template_id' = %s
                GROUP BY fg.grupo_muscular;
            """

            cursor.execute(sql_avg_feedback_grupos, (aluno_id, template_id))
            feedbacks_agregados = cursor.fetchall() # Retorna lista de tuplas (grupo_muscular, media_score, num_feedbacks)

            if feedbacks_agregados:
                # Calcular um score ponderado baseado nas médias por grupo
                # Podem existir diferentes estratégias de ponderação
                total_score_ponderado = 0.0
                total_pesos = 0.0

                for row in feedbacks_agregados:
                    # Ajustar acesso baseado no tipo de cursor (tupla ou DictRow)
                    grupo_muscular = row['grupo_muscular'] if isinstance(row, dict) else row[0]
                    media_score = row['media_score_grupo'] if isinstance(row, dict) else row[1]
                    num_feedbacks_grupo = row['num_feedbacks'] if isinstance(row, dict) else row[2]

                    if num_feedbacks_grupo > 0 and media_score is not None:
                         # Ponderar pela quantidade de feedbacks para aquele grupo (mais feedbacks -> peso maior)
                         # Ou ponderar pela classificação do grupo (Grande, Médio, Pequeno) - requer mapeamento
                         peso_grupo = num_feedbacks_grupo # Exemplo simples: peso = # feedbacks

                         # Normalizar a média do score do grupo (-1 a 1 ou similar)
                         score_grupo_normalizado = (media_score - 2.5) / 1.5 # De 1-4 para aprox -1 a 1

                         total_score_ponderado += score_grupo_normalizado * peso_grupo
                         total_pesos += peso_grupo
                         grupos_com_feedback += 1 # Conta quantos grupos tiveram feedback

                if total_pesos > 0:
                    score_feedback_grupo_total = (total_score_ponderado / total_pesos) * FEEDBACK_SCORE_MULTIPLIER # Ajusta pela escala desejada
                    opt_logger.debug(f"Feedback Agregado Aluno {aluno_id} Template '{template_id}': Score Ajustado={score_feedback_grupo_total:.2f} (Baseado em {grupos_com_feedback} grupos com feedback)")
                else:
                     opt_logger.debug(f"Feedback Agregado Aluno {aluno_id} Template '{template_id}': Sem pesos válidos para cálculo.")


            else:
                opt_logger.debug(f"Feedback Agregado Aluno {aluno_id} Template '{template_id}': Nenhum feedback por grupo encontrado.")

        except psycopg2.Error as db_err:
            opt_logger.error(f"Erro ao consultar feedback por grupo no DB PG: {db_err}")
        except Exception as e_fb:
             opt_logger.exception(f"Erro inesperado ao processar feedback por grupo: {e_fb}")
        finally:
             if cursor: cursor.close()
             if conn: conn.close()

        # --- Combina os Scores (Foco, Volume e Feedback POR GRUPO) ---
        # Agora usamos o score de feedback por grupo
        score_total = (score_foco_norm * PESO_FOCO) + \
                      (score_volume_norm * PESO_VOLUME) + \
                      (score_feedback_grupo_total * PESO_FEEDBACK_GRUPO)

        opt_logger.info(f"Avaliação Final T:{template_id} A:{aluno_id}: Foco={score_foco_norm:.2f} Vol={score_volume_norm:.2f} FeedbkGrupo={score_feedback_grupo_total:.2f} -> TOTAL={score_total:.4f}")
        return score_total

    except Exception as e:
        opt_logger.exception(f"ERRO inesperado durante avaliação do plano (Try Principal): {e}")
        # Tenta fechar cursor/conexão se abertos
        if cursor: cursor.close()
        if conn: conn.close()
        # Retorna um score muito baixo em caso de erro crítico
        return -10000.0

# --- Função Objetivo para o Optuna (sem mudanças na lógica principal) ---
def objective(trial: optuna.Trial) -> float:
    """
    Função que o Optuna chamará para cada tentativa (trial).
    Sugere valores, gera planos e retorna a pontuação média de qualidade (agora com feedback POR GRUPO do PG).
    """
    # Sugerindo os mesmos parâmetros que estavam no bloco de teste
    params = {
        'bonus_foco_dia': trial.suggest_float('bonus_foco_dia', 1.0, 6.0, step=0.5),
        'bonus_foco_aluno': trial.suggest_float('bonus_foco_aluno', 0.5, 4.0, step=0.25),
        'peso_prioridade': trial.suggest_float('peso_prioridade', 0.2, 2.5, step=0.1),
        'bonus_composto': trial.suggest_float('bonus_composto', 0.0, 3.0, step=0.25),
        'penalidade_isolado': trial.suggest_float('penalidade_isolado', -2.0, 0.0, step=0.25),
        # Adicionar outros parâmetros se necessário para otimizar
        'bonus_unilateral_assimetria': trial.suggest_float('bonus_unilateral_assimetria', 0.5, 4.0, step=0.5),
        'penalidade_repeticao_geral': trial.suggest_float('penalidade_repeticao_geral', -30.0, -5.0, step=2.5),
        'bonus_gc_sobrepeso': trial.suggest_float('bonus_gc_sobrepeso', 0.5, 3.0, step=0.25),
        'bonus_gc_obesidade': trial.suggest_float('bonus_gc_obesidade', 1.0, 4.0, step=0.5),
        'fator_ajuste_foco_imc': trial.suggest_float('fator_ajuste_foco_imc', 1.0, 2.0, step=0.1),
        'assimetria_limiar_abs_cm': trial.suggest_float('assimetria_limiar_abs_cm', 0.5, 2.0, step=0.1),
        'assimetria_limiar_rel': trial.suggest_float('assimetria_limiar_rel', 0.02, 0.1, step=0.01),
        # Parâmetros relacionados à técnica de pirâmide ou outras podem ser adicionados aqui
        # 'prob_tecnica_piramide': trial.suggest_float('prob_tecnica_piramide', 0.0, 1.0, step=0.05),
    }
    opt_logger.info(f"--- Trial {trial.number} --- Testando Parâmetros: {params}")

    qualidade_total = 0.0
    planos_gerados_validos = 0
    if not alunos_teste_otimizacao:
         opt_logger.error("Nenhum aluno definido em 'alunos_teste_otimizacao'. Impossível avaliar.")
         return -50000.0

    for aluno_teste in alunos_teste_otimizacao:
        try:
            # A geração do plano usa os parâmetros do trial internamente se necessário pela IA
            # Passar os params diretamente para gerar_plano_semanal_ia se a IA for modificada para aceitá-los como override
            plano = gerar_plano_semanal_ia(aluno_teste, params_otimizados_override=params)

            if plano and not plano.get("erro") and plano.get("dias_treino"):
                 # A avaliação usa a conexão PostgreSQL internamente agora
                 # e agora busca feedback por grupo
                 score_plano = avaliar_qualidade_plano(plano, aluno_teste)
                 qualidade_total += score_plano
                 planos_gerados_validos += 1
            else:
                opt_logger.warning(f"WARN: Plano inválido ou erro ao gerar para {aluno_teste.get('id','?')} no trial {trial.number}")
                qualidade_total -= 500 # Penaliza planos inválidos
        except Exception as e:
            opt_logger.exception(f"ERRO CRÍTICO trial {trial.number} aluno {aluno_teste.get('id','?')}: {e}")
            # Penaliza fortemente trials que causam exceções
            return -10000.0

    if planos_gerados_validos == 0:
        opt_logger.error(f"ERRO: Nenhum plano válido gerado no trial {trial.number}")
        return -20000.0 # Penalidade muito alta se nenhum plano válido for gerado

    media_qualidade = qualidade_total / planos_gerados_validos
    opt_logger.info(f"Trial {trial.number} - Média Qualidade (com feedback POR GRUPO PG): {media_qualidade:.4f}")
    return media_qualidade

# --- Configurar e Executar o Estudo Optuna (sem mudanças) ---
if __name__ == "__main__":
    print("\n--- Iniciando Otimização (com Avaliação de Feedback POR GRUPO PostgreSQL) ---")
    opt_logger.info("Configurando estudo Optuna...")

    # Verificar conexão com DB PG antes de iniciar (opcional, mas bom)
    try:
        conn_test = get_db_connection()
        conn_test.close()
        opt_logger.info("Conexão de teste com PostgreSQL bem-sucedida.")
    except Exception as db_test_err:
        opt_logger.error(f"Falha ao conectar ao PostgreSQL para teste inicial: {db_test_err}")
        print("\nERRO: Não foi possível conectar ao PostgreSQL. Verifique as configurações em database.py e se o servidor PostgreSQL está acessível.")
        # exit() # Descomente para parar se o DB for essencial para a otimização

    study = optuna.create_study(
        direction="maximize",
        study_name="otimizacao_gerador_treino_v3_feedback_grupo_pg" # Nome do estudo atualizado
        # storage="sqlite:///ia_optimization_results.db", # Optuna pode usar SQLite para guardar seus próprios resultados
        # load_if_exists=True
    )

    n_trials_executar = 100 # Aumentado para tentar encontrar melhores parâmetros com feedback granular
    timeout_segundos = 3600 # 1 hora (ajuste conforme necessário)
    opt_logger.info(f"Iniciando otimização com {n_trials_executar} trials (timeout: {timeout_segundos}s)...")

    try:
        study.optimize(objective, n_trials=n_trials_executar, timeout=timeout_segundos)
    except KeyboardInterrupt:
        print("\nOtimização interrompida manualmente.")
        opt_logger.warning("Otimização interrompida manualmente.")
    except Exception as e_opt:
        opt_logger.exception(f"Erro durante a otimização: {e_opt}")


    # --- Exibir os Resultados (sem mudanças significativas, apenas atualiza logs/prints) ---
    print("\n--- Otimização Concluída ---")
    opt_logger.info("Otimização finalizada.")
    try:
        if not study.trials:
             print("Nenhum trial foi completado com sucesso.")
             opt_logger.warning("Nenhum trial foi completado com sucesso.")
        else:
             print(f"Número de trials finalizados: {len(study.trials)}")
             opt_logger.info(f"Número de trials finalizados: {len(study.trials)}")
             if study.best_trial:
                 best_trial = study.best_trial
                 print(f"Melhor Trial (Número {best_trial.number}):")
                 print(f"  Valor (Score Médio - Feedback por Grupo): {best_trial.value:.4f}") # Ajuste no print
                 print("  Melhores Parâmetros Encontrados:")
                 best_params = best_trial.params
                 for key, value in best_params.items():
                     print(f"    {key}: {value:.4f}")

                 opt_logger.info(f"Melhor Trial: {best_trial.number}, Valor (Feedback Grupo): {best_trial.value:.4f}, Params: {best_params}")

                 # Salvar os melhores parâmetros (sem mudanças)
                 try:
                     # Salvando no arquivo que a IA lê por padrão
                     path_params_salvos = Path(__file__).parent / "melhores_parametros_ia.json"
                     with open(path_params_salvos, "w", encoding="utf-8") as f:
                         json.dump(best_params, f, indent=4)
                     print(f"\nMelhores parâmetros salvos em '{path_params_salvos}'")
                     opt_logger.info(f"Melhores parâmetros salvos em '{path_params_salvos}'")
                 except Exception as e_save:
                     print(f"\nErro ao salvar melhores parâmetros: {e_save}")
                     opt_logger.exception(f"Erro ao salvar melhores parâmetros: {e_save}")


                 # Visualização dos resultados (requer plotly)
                 try:
                     import plotly.io as pio
                     import plotly.express as px
                     import plotly.graph_objects as go
                     # Importações Optuna Visualization
                     from optuna.visualization import plot_optimization_history, plot_param_importances, plot_contour, plot_slice, plot_parallel_coordinate


                     print("\nGerando gráficos de otimização...")
                     # Exemplo de geração e salvamento de gráficos
                     fig_history = plot_optimization_history(study)
                     fig_history.write_html("optuna_history.html")
                     print("Gráfico de Histórico de Otimização salvo como optuna_history.html")


                     fig_importance = plot_param_importances(study)
                     fig_importance.write_html("optuna_param_importances.html")
                     print("Gráfico de Importância de Parâmetros salvo como optuna_param_importances.html")

                     # Outros gráficos úteis:
                     # if len(best_params) <= 2: # plot_contour funciona melhor com 2 parâmetros
                     #    fig_contour = plot_contour(study, params=list(best_params.keys()))
                     #    fig_contour.write_html("optuna_contour.html")
                     #    print("Gráfico de Contorno salvo como optuna_contour.html")

                     # fig_slice = plot_slice(study)
                     # fig_slice.write_html("optuna_slice.html")
                     # print("Gráfico de Slice salvo como optuna_slice.html")

                     # fig_parallel = plot_parallel_coordinate(study)
                     # fig_parallel.write_html("optuna_parallel_coordinate.html")
                     # print("Gráfico de Coordenada Paralela salvo como optuna_parallel_coordinate.html")


                     print("Gráficos gerados e salvos na pasta do script.")

                 except ImportError:
                     print("\nInstale plotly para visualizar gráficos: pip install plotly")
                     opt_logger.warning("Plotly não instalado. Gráficos não gerados.")
                 except Exception as e_plot:
                     print(f"\nErro ao gerar gráficos Optuna: {e_plot}")
                     opt_logger.exception(f"Erro ao gerar gráficos Optuna: {e_plot}")

             else:
                 print("Não foi encontrado um 'melhor trial'.")
                 opt_logger.warning("Não foi encontrado um 'melhor trial'.")


    except optuna.exceptions.OptunaError as e_study:
         print(f"Erro ao acessar resultados do estudo: {e_study}")
         opt_logger.exception(f"Erro ao acessar resultados do estudo Optuna: {e_study}")
    except Exception as e_final:
         opt_logger.exception(f"Erro inesperado ao mostrar resultados: {e_final}")
         print(f"Erro inesperado ao mostrar resultados: {e_final}")

    print("\n" + "="*30 + "\n--- FIM DO BLOCO DE OTIMIZAÇÃO ---\n" + "="*30)