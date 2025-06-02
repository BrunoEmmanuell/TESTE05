# backend/ia/gerador_treino_ia.py
# Versão com penalidade para tag_funcional similar no mesmo dia/grupo

import json
import logging
import math
from pathlib import Path
import random
from datetime import datetime
import unicodedata
from typing import Dict, Optional, List, Any, Set, Tuple

# --- Configuração de Logging (Obtem os loggers, a configuração é centralizada em main.py) ---
ia_logger = logging.getLogger(__name__)
selection_logger = logging.getLogger('SelectionDebug')

# --- Constantes Globais ---
NIVEIS_VALIDOS = ["iniciante", "intermediario", "avancado"]
GRUPOS_MUSCULARES_FIXOS = {"Peito", "Costas", "Ombros", "Biceps", "Triceps", "Pernas", "Core", "Panturrilha", "Antebraco", "Gluteo"}
GRUPOS_MEMBROS_INFERIORES = {"Pernas", "Gluteo", "Panturrilha"}
GRUPO_CLASSIFICACAO = { "Pernas": "Grande", "Peito": "Grande", "Costas": "Grande", "Ombros": "Médio", "Core": "Médio", "Gluteo": "Médio", "Biceps": "Pequeno", "Triceps": "Pequeno", "Panturrilha": "Pequeno", "Antebraco": "Pequeno" }
GRUPO_ORDEM = {"Grande": 1, "Médio": 2, "Pequeno": 3, "Desconhecido": 99}
TEC_BISET = "biset"
TEC_CONJUGADO = "conjugado_antagonista"
TEC_PIRAMIDE = "piramide"
ARQUIVO_PARAMS_OTIMIZADOS = "melhores_parametros_ia.json"
UNIDADE_MEDIDA_PADRAO = "_cm"

# --- Função Auxiliar de Normalização ---
def normalize_text(text: str) -> str:
    if not isinstance(text, str): return ""
    try:
        nfkd_form = unicodedata.normalize('NFD', text)
        sem_acentos = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
        return sem_acentos.lower().strip()
    except Exception as e:
        ia_logger.warning(f"Erro ao normalizar texto: '{text}' - Error: {e}")
        return ""

# --- Carregamento de Dados (Exercícios) ---
def carregar_exercicios(caminho_arquivo: Optional[str | Path] = None) -> Dict[str, Dict]:
    if caminho_arquivo is None:
        script_dir = Path(__file__).parent
        caminho_arquivo_json = script_dir / "exercicios.json"
        if not caminho_arquivo_json.exists():
            caminho_pai = script_dir.parent
            caminho_arquivo_json = caminho_pai / "exercicios.json"
            if not caminho_arquivo_json.exists():
                caminho_arquivo_json = Path("exercicios.json")
    else:
        caminho_arquivo_json = Path(caminho_arquivo)

    if not caminho_arquivo_json.exists():
         ia_logger.error(f"IA CRÍTICO: Arquivo de exercícios '{caminho_arquivo_json}' não encontrado.")
         return {}
    try:
        with open(caminho_arquivo_json, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict):
            ia_logger.error(f"IA CRÍTICO: Conteúdo de '{caminho_arquivo_json}' não é um dicionário JSON.")
            return {}
        ia_logger.info(f"IA: JSON de exercícios '{caminho_arquivo_json.name}' carregado ({len(dados)} exercícios).")
        return dados
    except Exception as e:
        ia_logger.error(f"IA CRÍTICO: Erro ao carregar '{caminho_arquivo_json}': {e}")
        return {}

exercicios_db = carregar_exercicios()
if not exercicios_db:
    ia_logger.critical("IA CRÍTICO: Banco de exercícios (exercicios_db) NÃO CARREGADO ou VAZIO.")

# --- Carregamento dos Parâmetros Otimizados ---
PARAMETROS_IA_OTIMIZADOS: Dict[str, float] = {}
try:
    script_dir = Path(__file__).parent
    caminho_params = script_dir / ARQUIVO_PARAMS_OTIMIZADOS
    if not caminho_params.exists():
        caminho_params = script_dir.parent / ARQUIVO_PARAMS_OTIMIZADOS
    if caminho_params.exists():
        with open(caminho_params, "r", encoding="utf-8") as f:
            params_carregados = json.load(f)
        if isinstance(params_carregados, dict):
            PARAMETROS_IA_OTIMIZADOS = params_carregados
            ia_logger.info(f"IA: Parâmetros otimizados carregados de '{caminho_params.name}'.")
        else:
            ia_logger.warning(f"IA: Conteúdo de '{ARQUIVO_PARAMS_OTIMIZADOS}' inválido. Usando padrão.")
            PARAMETROS_IA_OTIMIZADOS = {}
    else:
        ia_logger.warning(f"IA: Arquivo '{ARQUIVO_PARAMS_OTIMIZADOS}' não encontrado. Usando padrão.")
        PARAMETROS_IA_OTIMIZADOS = {}
except Exception as e:
    ia_logger.error(f"IA: Erro ao carregar '{ARQUIVO_PARAMS_OTIMIZADOS}': {e}. Usando padrão.")
    PARAMETROS_IA_OTIMIZADOS = {}

# --- Determinação Dinâmica dos Grupos Musculares ---
GRUPOS_MUSCULARES = []
if exercicios_db:
    try:
        grupos_json = set(info.get("grupo") for info in exercicios_db.values() if isinstance(info, dict) and isinstance(info.get("grupo"), str))
        GRUPOS_MUSCULARES = sorted(list(grupos_json.union(GRUPOS_MUSCULARES_FIXOS)))
        ia_logger.info(f"IA: Grupos musculares: {GRUPOS_MUSCULARES}")
    except Exception as e:
        ia_logger.error(f"IA: Erro processar grupos do JSON: {e}. Usando fixos.")
        GRUPOS_MUSCULARES = sorted(list(GRUPOS_MUSCULARES_FIXOS))
else:
    ia_logger.warning("IA: Nenhum grupo do JSON. Usando fixos.")
    GRUPOS_MUSCULARES = sorted(list(GRUPOS_MUSCULARES_FIXOS))

# --- Templates de Treino (Mantidos como na v3) ---
SPLIT_TEMPLATES = {
    "iniciante_masculino": {"id": "iniciante_m_abc_v2", "nome": "Iniciante Masculino ABC", "dias": {"A": {"nome": "Peito, Ombro, Tríceps", "grupos": ["Peito", "Ombros", "Triceps"], "vol_grupo": {"Peito": 3, "Ombros": 3, "Triceps": 2}}, "B": {"nome": "Costas, Bíceps", "grupos": ["Costas", "Biceps"], "vol_grupo": {"Costas": 4, "Biceps": 4}}, "C": {"nome": "Pernas, Core, Pant.", "grupos": ["Pernas", "Core", "Panturrilha"], "vol_grupo": {"Pernas": 4, "Core": 2, "Panturrilha": 2}}}, "series_padrao": 3, "reps_padrao": "10-15", "descanso_sugerido": "60-90s" },
    "intermediario_masculino": {"id": "intermediario_m_abcd_v2", "nome": "Intermediário Masculino ABCD", "dias": {"A": {"nome": "Peito, Tríceps", "grupos": ["Peito", "Triceps"], "vol_grupo": {"Peito": 4, "Triceps": 3}}, "B": {"nome": "Costas, Bíceps, Anteb.", "grupos": ["Costas", "Biceps", "Antebraco"], "vol_grupo": {"Costas": 4, "Biceps": 3, "Antebraco": 1}}, "C": {"nome": "Pernas, Panturrilha", "grupos": ["Pernas", "Panturrilha"], "vol_grupo": {"Pernas": 5, "Panturrilha": 2}}, "D": {"nome": "Ombros, Core", "grupos": ["Ombros", "Core"], "vol_grupo": {"Ombros": 4, "Core": 3}}}, "series_padrao": 3, "series_intermediario": 3, "reps_padrao": "8-12", "descanso_sugerido": "60-90s", "prob_tecnica": 0.30, "max_tecnicas_grupo": 1 },
    "avancado_masculino": {"id": "avancado_m_abcde_v2", "nome": "Avançado Masculino ABCDE", "dias": {"A": {"nome": "Peito, Tríceps", "grupos": ["Peito", "Triceps"], "vol_grupo": {"Peito": 5, "Triceps": 3}}, "B": {"nome": "Costas, Bíceps, Anteb.", "grupos": ["Costas", "Biceps", "Antebraco"], "vol_grupo": {"Costas": 5, "Biceps": 3, "Antebraco": 2}}, "C": {"nome": "Pernas (Pesado), Pant.", "grupos": ["Pernas", "Panturrilha"], "vol_grupo": {"Pernas": 9, "Panturrilha": 2}}, "D": {"nome": "Ombros, Abdômen", "grupos": ["Ombros", "Core"], "vol_grupo": {"Ombros": 5, "Core": 4}}, "E": {"nome": "Full Body Leve", "grupos": ["Pernas", "Peito", "Costas"], "vol_grupo": {"Pernas": 2, "Peito": 2, "Costas": 2}, "foco_composto": True}}, "series_padrao": 3, "series_avancado": 4, "reps_padrao": "6-12", "descanso_sugerido": "60-120s", "prob_tecnica": 0.60, "max_tecnicas_grupo": 1 },
    "iniciante_feminino": {"id": "iniciante_f_spq_v1_menos_ex", "nome": "Iniciante Feminino Sup/Post/Quad (Menos Exercícios)", "dias": {"A": {"nome": "Superiores", "grupos": ["Peito", "Costas", "Ombros", "Biceps", "Triceps"], "vol_grupo": {"Peito": 1, "Costas": 2, "Ombros": 1, "Biceps": 1, "Triceps": 1}}, "B": {"nome": "Posterior e Glúteos", "grupos": ["Pernas", "Gluteo", "Core"], "vol_grupo": {"Pernas": 4, "Gluteo": 2, "Core": 1}, "foco_dia": ["posterior_coxa", "gluteo"]}, "C": {"nome": "Quadríceps e Panturrilhas", "grupos": ["Pernas", "Panturrilha", "Core"], "vol_grupo": {"Pernas": 5, "Panturrilha": 1, "Core": 1}, "foco_dia": ["quadriceps", "panturrilha"]}}, "series_padrao": 3, "reps_padrao": "10-15", "descanso_sugerido": "60-90s" },
    "intermediario_feminino": {"id": "intermediario_f_spq_v1_menos_ex", "nome": "Intermediário Feminino Sup/Post/Quad (Menos Exercícios)", "dias": {"A": {"nome": "Superiores", "grupos": ["Peito", "Costas", "Ombros", "Biceps", "Triceps"], "vol_grupo": {"Peito": 2, "Costas": 2, "Ombros": 2, "Biceps": 1, "Triceps": 1}}, "B": {"nome": "Posterior e Glúteos", "grupos": ["Pernas", "Gluteo", "Core"], "vol_grupo": {"Pernas": 4, "Gluteo": 2, "Core": 2}, "foco_dia": ["posterior_coxa", "gluteo"]}, "C": {"nome": "Quadríceps e Panturrilhas", "grupos": ["Pernas", "Panturrilha", "Core"], "vol_grupo": {"Pernas": 5, "Panturrilha": 2, "Core": 1}, "foco_dia": ["quadriceps", "panturrilha"]}}, "series_padrao": 3, "series_intermediario": 3, "reps_padrao": "10-15", "descanso_sugerido": "60-90s", "prob_tecnica": 0.35, "max_tecnicas_grupo": 1 },
    "avancado_feminino": {"id": "avancado_f_spq_v1_menos_ex", "nome": "Avançado Feminino Sup/Post/Quad (Menos Exercícios)", "dias": {"A": {"nome": "Superiores", "grupos": ["Peito", "Costas", "Ombros", "Biceps", "Triceps"], "vol_grupo": {"Peito": 2, "Costas": 3, "Ombros": 2, "Biceps": 2, "Triceps": 1}}, "B": {"nome": "Posterior e Glúteos", "grupos": ["Pernas", "Gluteo", "Core"], "vol_grupo": {"Pernas": 5, "Gluteo": 3, "Core": 2}, "foco_dia": ["posterior_coxa", "gluteo"]}, "C": {"nome": "Quadríceps e Panturrilhas", "grupos": ["Pernas", "Panturrilha", "Core"], "vol_grupo": {"Pernas": 5, "Panturrilha": 2, "Core": 2}, "foco_dia": ["quadriceps", "panturrilha"]}}, "series_padrao": 3, "series_avancado": 4, "reps_padrao": "8-15", "descanso_sugerido": "60-90s", "prob_tecnica": 0.65, "max_tecnicas_grupo": 1 }
}

# --- Funções Auxiliares da IA ---
def detectar_assimetrias(
    medidas_aluno: Dict[str, Any],
    limiar_abs_cm: float = 1.0,
    limiar_rel: float = 0.05
    ) -> Dict[str, Optional[str]]:
    assimetrias_detectadas = {}
    pares_medidas = {
        "Biceps": (f"circ_biceps_d_relaxado{UNIDADE_MEDIDA_PADRAO}", f"circ_biceps_e_relaxado{UNIDADE_MEDIDA_PADRAO}"),
        "Antebraco": (f"circ_antebraco_d{UNIDADE_MEDIDA_PADRAO}", f"circ_antebraco_e{UNIDADE_MEDIDA_PADRAO}"),
        "Pernas": (f"circ_coxa_d{UNIDADE_MEDIDA_PADRAO}", f"circ_coxa_e{UNIDADE_MEDIDA_PADRAO}"),
        "Panturrilha": (f"circ_panturrilha_d{UNIDADE_MEDIDA_PADRAO}", f"circ_panturrilha_e{UNIDADE_MEDIDA_PADRAO}"),
    }
    for grupo, (key_d, key_e) in pares_medidas.items():
        lado_mais_fraco = None
        medida_d_val = medidas_aluno.get(key_d)
        medida_e_val = medidas_aluno.get(key_e)
        if (medida_d_val is not None and isinstance(medida_d_val, (int, float)) and medida_d_val > 0 and
            medida_e_val is not None and isinstance(medida_e_val, (int, float)) and medida_e_val > 0):
            try:
                medida_d, medida_e = float(medida_d_val), float(medida_e_val)
                diff_abs, media = abs(medida_d - medida_e), (medida_d + medida_e) / 2.0
                diff_rel = diff_abs / media if media > 0 else 0.0
                if diff_abs > limiar_abs_cm or diff_rel > limiar_rel:
                    lado_mais_fraco = "direito" if medida_d < medida_e else "esquerdo"
                    selection_logger.debug(f"ASSIMETRIA: {grupo}, D={medida_d:.1f}, E={medida_e:.1f} -> Lado fraco: {lado_mais_fraco}")
            except Exception as e_calc: ia_logger.warning(f"Erro calc assimetria {grupo}: {e_calc}")
        else:
            if key_d not in medidas_aluno or key_e not in medidas_aluno:
                 selection_logger.debug(f"ASSIMETRIA: Medidas ausentes {grupo}")
        assimetrias_detectadas[grupo] = lado_mais_fraco
    return assimetrias_detectadas


def _obter_candidatos_pontuados(
    grupo_alvo: str,
    nivel_aluno_norm: str,
    foco_treino_norm: str,
    historico_lesoes_norm: str,
    exercicios_usados_semana: Set[str],
    bonus_foco_gc: float,
    sexo_norm: str,
    assimetrias_detectadas: Dict[str, Optional[str]],
    foco_dia: Optional[List[str]] = None,
    foco_composto: bool = False,
    tecnica_requerida: Optional[str] = None,
    grupo_antagonista_req: Optional[str] = None,
    params_merged: Dict[str, float] = {},
    tags_funcionais_ja_usadas_neste_grupo_dia: Optional[Set[str]] = None # NOVO PARÂMETRO
    ) -> List[Dict[str, Any]]:
    """Seleciona e pontua exercícios, aplicando penalidades e bônus."""

    p = params_merged
    selection_logger.debug(f"---- Obtendo Candidatos: GRUPO={grupo_alvo} ... Tags Func. Usadas Dia: {tags_funcionais_ja_usadas_neste_grupo_dia} ----")
    if not exercicios_db: return []

    candidatos = []
    foco_dia_norm = [normalize_text(f) for f in foco_dia] if foco_dia else []
    focos_primarios_aceitos = set()
    is_leg_day_specific = grupo_alvo in GRUPOS_MEMBROS_INFERIORES and foco_dia_norm
    if is_leg_day_specific:
        foco_map = {"quadriceps": "quadriceps", "posterior_coxa": "posterior_coxa", "gluteo": ["gluteo", "abdutores"], "panturrilha": "panturrilha", "adutores": "adutores"}
        for foco_d in foco_dia_norm:
            aceitos = foco_map.get(foco_d)
            if aceitos: focos_primarios_aceitos.update(aceitos) if isinstance(aceitos, list) else focos_primarios_aceitos.add(aceitos)
        if not focos_primarios_aceitos: is_leg_day_specific = False

    for nome_ex_chave, info_ex in exercicios_db.items():
        if not isinstance(info_ex, dict): continue
        if info_ex.get("grupo") != grupo_alvo: continue
        if nivel_aluno_norm not in [normalize_text(n) for n in info_ex.get("nivel", []) if isinstance(n, str)]: continue
        if historico_lesoes_norm and historico_lesoes_norm in {normalize_text(ci) for ci in info_ex.get("contraindicacoes", []) if isinstance(ci, str)}: continue
        if is_leg_day_specific and (not info_ex.get("foco_primario") or info_ex.get("foco_primario") not in focos_primarios_aceitos): continue
        if tecnica_requerida and (not isinstance(info_ex.get("tecnicas_adequadas", []), list) or tecnica_requerida not in info_ex.get("tecnicas_adequadas", [])): continue
        if grupo_antagonista_req:
            antag_ex = info_ex.get("grupo_antagonista")
            matches = (isinstance(antag_ex, str) and antag_ex == grupo_antagonista_req) or \
                      (isinstance(antag_ex, list) and grupo_antagonista_req in antag_ex)
            if not matches: continue

        pontuacao = 0.0
        focos_ex_norm = [normalize_text(f) for f in info_ex.get("foco", []) if isinstance(f, str)]
        foco_dia_match = False
        if foco_dia_norm and any(fd in focos_ex_norm for fd in foco_dia_norm): pontuacao += p.get('bonus_foco_dia', 3.0); foco_dia_match = True
        if foco_treino_norm and foco_treino_norm in focos_ex_norm: pontuacao += (0.5 * p.get('bonus_foco_aluno', 1.5) if foco_dia_match else p.get('bonus_foco_aluno', 1.5))
        if foco_composto: pontuacao += p.get('bonus_composto', 1.0) if info_ex.get("tipo", "").lower() == "composto" else p.get('penalidade_isolado', -0.5)
        if bonus_foco_gc > 0 and ('resistencia' in focos_ex_norm or 'emagrecimento' in focos_ex_norm): pontuacao += bonus_foco_gc
        pontuacao += info_ex.get("prioridade", 0) * p.get('peso_prioridade', 1.0)
        if sexo_norm == "feminino" and grupo_alvo in GRUPOS_MEMBROS_INFERIORES.union({"Core"}): pontuacao += 0.2
        elif sexo_norm == "masculino" and grupo_alvo in {"Peito", "Costas", "Ombros"}: pontuacao += 0.1
        if assimetrias_detectadas.get(grupo_alvo) and info_ex.get("unilateral") is True: pontuacao += p.get('bonus_unilateral_assimetria', 1.5)
        
        if nome_ex_chave in exercicios_usados_semana: # Penalidade SEMANA
            pontuacao += p.get('penalidade_repeticao_geral', -15.0)
            selection_logger.debug(f"           -> PENALIDADE REPETIÇÃO SEMANA ({p.get('penalidade_repeticao_geral', -15.0):.1f}) para {nome_ex_chave}")

        # *** NOVA PENALIDADE POR SIMILARIDADE FUNCIONAL NO MESMO DIA/GRUPO ***
        tag_funcional_ex = info_ex.get("tag_funcional") # Assume que você adicionou este campo ao exercicios.json
        if tags_funcionais_ja_usadas_neste_grupo_dia and \
           tag_funcional_ex and \
           tag_funcional_ex in tags_funcionais_ja_usadas_neste_grupo_dia:
            penalidade_similaridade_dia = -100.0 # Penalidade muito alta!
            pontuacao += penalidade_similaridade_dia
            selection_logger.debug(f"           -> PENALIDADE SIMILARIDADE FUNCIONAL DIA ({penalidade_similaridade_dia:.1f}) para {nome_ex_chave} (Tag: {tag_funcional_ex})")

        pontuacao += random.uniform(-0.05, 0.05) # Desempate
        candidatos.append({"nome_chave": nome_ex_chave, "pontos": pontuacao, "info": info_ex})

    candidatos.sort(key=lambda item: item["pontos"], reverse=True)
    selection_logger.debug(f"---- Candidatos FINAIS {grupo_alvo} (TecReq: {tecnica_requerida}): {len(candidatos)}. Top: {[c.get('nome_chave','?')+' ('+str(round(c.get('pontos',0),1))+')' for c in candidatos[:3]]} ----")
    return candidatos


def _formatar_exercicio(
    nome_chave_ex: str, info_ex: dict, template: dict, foco_treino_norm: str, nivel_aluno_norm: str
    ) -> Optional[Dict[str, Any]]:
    if not isinstance(info_ex, dict) or not nome_chave_ex: return None
    nome_formatado = info_ex.get("nome_display", "").strip() or ' '.join(word.capitalize() for word in nome_chave_ex.replace("_", " ").split())
    tipo_ex = info_ex.get("tipo", "").lower()
    series = template.get("series_padrao", 3)
    if nivel_aluno_norm == "avancado" and "series_avancado" in template: series = template["series_avancado"]
    elif nivel_aluno_norm == "intermediario" and "series_intermediario" in template: series = template["series_intermediario"]
    reps, descanso = template.get("reps_padrao", "8-12"), template.get("descanso_sugerido", "60-90s")
    if info_ex.get("sugestao_series") and str(info_ex["sugestao_series"]).strip(): series = info_ex["sugestao_series"]
    if info_ex.get("sugestao_reps") and isinstance(info_ex["sugestao_reps"], str) and info_ex["sugestao_reps"].strip(): reps = info_ex["sugestao_reps"]
    focos_ex_norm = [normalize_text(f) for f in info_ex.get("foco", []) if isinstance(f, str)]
    if tipo_ex == "isometrico" and info_ex.get("duracao_s"): reps, descanso = f"{info_ex['duracao_s']}s", template.get("descanso_isometrico", "30-60s")
    elif nivel_aluno_norm != "iniciante" and ('forca' in foco_treino_norm or 'forca' in focos_ex_norm): reps, descanso = random.choice(["4-6", "5-8", "6-8"]), template.get("descanso_forca", "90-150s")
    elif 'resistencia' in foco_treino_norm or 'resistencia' in focos_ex_norm or 'emagrecimento' in foco_treino_norm: reps, descanso = random.choice(["12-15", "15-20", "18-25"]), template.get("descanso_resistencia", "30-60s")
    equip_str = ", ".join(eq for eq in info_ex.get("equipamentos", []) if eq) if isinstance(info_ex.get("equipamentos", []), list) and info_ex.get("equipamentos", []) else "Peso Corporal / N/A"
    return {"chave_original": nome_chave_ex, "nome": nome_formatado, "series": series, "repeticoes": reps, "descanso": descanso, "equipamentos": equip_str, "grupo": info_ex.get("grupo", "N/A"), "foco_primario": info_ex.get("foco_primario"), "unilateral": info_ex.get("unilateral", False), "observacao_tecnica": None, "tag_funcional": info_ex.get("tag_funcional")} # Adicionado tag_funcional ao retorno


def _selecionar_exercicio_normal(
    grupo: str, nivel: str, foco_treino: str, lesoes: str,
    usados_semana: Set[str], bonus_gc: float, sexo: str, assimetrias: Dict,
    foco_dia: Optional[List[str]], foco_comp: bool, template: dict, params_merged: Dict,
    tags_funcionais_ja_usadas_neste_grupo_dia: Optional[Set[str]] = None # NOVO
    ) -> Optional[Tuple[Dict, str]]:
    selection_logger.debug(f"      Selecionando exercício normal para {grupo} (tags já usadas dia: {tags_funcionais_ja_usadas_neste_grupo_dia})...")
    cands_norm = _obter_candidatos_pontuados(
        grupo, nivel, foco_treino, lesoes, usados_semana, bonus_gc, sexo,
        assimetrias, foco_dia, foco_comp, params_merged=params_merged,
        tags_funcionais_ja_usadas_neste_grupo_dia=tags_funcionais_ja_usadas_neste_grupo_dia # REPASSANDO
    )
    if not cands_norm: ia_logger.warning(f"Não há exercícios normais para {grupo}."); return None
    ex_cand, ex_chave = cands_norm[0], cands_norm[0]["nome_chave"]
    ex_fmt = _formatar_exercicio(ex_chave, ex_cand["info"], template, foco_treino, nivel)
    if ex_fmt: return ex_fmt, ex_chave
    elif len(cands_norm) > 1: # Fallback
        ex_cand_fb, ex_chave_fb = cands_norm[1], cands_norm[1]["nome_chave"]
        ex_fmt_fb = _formatar_exercicio(ex_chave_fb, ex_cand_fb["info"], template, foco_treino, nivel)
        if ex_fmt_fb: ia_logger.info(f"           + Usando fallback normal: {ex_fmt_fb['nome']}"); return ex_fmt_fb, ex_chave_fb
    ia_logger.warning(f"Falha formatar exercício normal '{ex_chave}' ou fallback."); return None


def _tentar_selecionar_biset(
    grupo: str, nivel: str, foco_treino: str, lesoes: str,
    usados_semana: Set[str], bonus_gc: float, sexo: str, assimetrias: Dict,
    foco_dia: Optional[List[str]], foco_comp: bool, template: dict, params_merged: Dict,
    tags_funcionais_ja_usadas_neste_grupo_dia_atual: Optional[Set[str]] = None # NOVO
    ) -> Optional[Tuple[Dict, Dict, List[str], Optional[str], Optional[str]]]: # Retorna também as tags funcionais dos exercícios
    selection_logger.debug(f"      Tentando BISET para {grupo} (tags já usadas dia: {tags_funcionais_ja_usadas_neste_grupo_dia_atual})")
    cands1 = _obter_candidatos_pontuados(
        grupo, nivel, foco_treino, lesoes, usados_semana, bonus_gc, sexo,
        assimetrias, foco_dia, foco_comp, tecnica_requerida=TEC_BISET, params_merged=params_merged,
        tags_funcionais_ja_usadas_neste_grupo_dia=tags_funcionais_ja_usadas_neste_grupo_dia_atual
    )
    if not cands1: return None
    ex1_cand, ex1_chave = cands1[0], cands1[0]["nome_chave"]
    ex1_tag_funcional = ex1_cand["info"].get("tag_funcional")

    tags_para_ex2 = set(tags_funcionais_ja_usadas_neste_grupo_dia_atual or [])
    if ex1_tag_funcional: tags_para_ex2.add(ex1_tag_funcional)
    
    excluidos_temp_biset = usados_semana.union({ex1_chave})
    cands2 = _obter_candidatos_pontuados(
        grupo, nivel, foco_treino, lesoes, excluidos_temp_biset, bonus_gc, sexo,
        assimetrias, foco_dia, foco_comp, tecnica_requerida=TEC_BISET, params_merged=params_merged,
        tags_funcionais_ja_usadas_neste_grupo_dia=tags_para_ex2
    )
    ex2_cand_final = next((c for c in cands2 if c["nome_chave"] != ex1_chave), None)
    if not ex2_cand_final: return None
    ex2_chave = ex2_cand_final["nome_chave"]
    ex2_tag_funcional = ex2_cand_final["info"].get("tag_funcional")

    ex1_fmt = _formatar_exercicio(ex1_chave, ex1_cand["info"], template, foco_treino, nivel)
    ex2_fmt = _formatar_exercicio(ex2_chave, ex2_cand_final["info"], template, foco_treino, nivel)
    if ex1_fmt and ex2_fmt:
        ia_logger.info(f"           >> BISET: {ex1_fmt['nome']} + {ex2_fmt['nome']}")
        return ex1_fmt, ex2_fmt, [ex1_chave, ex2_chave], ex1_tag_funcional, ex2_tag_funcional
    return None


def _tentar_selecionar_conjugado(
    grupo_agonista: str, nivel: str, foco_treino: str, lesoes: str,
    usados_semana: Set[str], bonus_gc: float, sexo: str, assimetrias: Dict,
    foco_dia: Optional[List[str]], foco_comp: bool, template: dict, params_merged: Dict,
    grupos_do_dia: List[str],
    tags_funcionais_ja_usadas_agonista_dia: Optional[Set[str]] = None, # NOVO
    # tags_funcionais_ja_usadas_antagonista_dia: Optional[Set[str]] = None # Poderia ser passado se necessário
    ) -> Optional[Tuple[Dict, Dict, List[str], Optional[str]]]: # Retorna tag do agonista
    selection_logger.debug(f"      Tentando CONJUGADO para {grupo_agonista} (tags já usadas dia agonista: {tags_funcionais_ja_usadas_agonista_dia})")
    cands1 = _obter_candidatos_pontuados(
        grupo_agonista, nivel, foco_treino, lesoes, usados_semana, bonus_gc, sexo,
        assimetrias, foco_dia, foco_comp, tecnica_requerida=TEC_CONJUGADO, params_merged=params_merged,
        tags_funcionais_ja_usadas_neste_grupo_dia=tags_funcionais_ja_usadas_agonista_dia
    )
    ex1_sel, grupo_ant_req, ex1_chave, ex1_tag_func = None, None, None, None
    for c1 in cands1:
        antag = c1["info"].get("grupo_antagonista")
        if antag and isinstance(antag, str) and antag in GRUPOS_MUSCULARES:
            ex1_sel, grupo_ant_req, ex1_chave = c1, antag, c1["nome_chave"]
            ex1_tag_func = ex1_sel["info"].get("tag_funcional")
            break
    if not ex1_sel or grupo_ant_req not in grupos_do_dia: return None
    
    excluidos_temp_conj = usados_semana.union({ex1_chave})
    # Para o antagonista, idealmente usaríamos as tags já usadas para o *grupo antagonista* naquele dia.
    # Por simplicidade aqui, não estamos passando um set de tags separado para o antagonista, mas poderia ser feito.
    cands2 = _obter_candidatos_pontuados(
        grupo_ant_req, nivel, foco_treino, lesoes, excluidos_temp_conj, bonus_gc, sexo,
        assimetrias, foco_dia, foco_comp, tecnica_requerida=TEC_CONJUGADO,
        grupo_antagonista_req=grupo_agonista, params_merged=params_merged
        # tags_funcionais_ja_usadas_neste_grupo_dia=tags_funcionais_ja_usadas_antagonista_dia # Se fosse passado
    )
    if not cands2: return None
    ex2_cand, ex2_chave = cands2[0], cands2[0]["nome_chave"]
    ex1_fmt = _formatar_exercicio(ex1_chave, ex1_sel["info"], template, foco_treino, nivel)
    ex2_fmt = _formatar_exercicio(ex2_chave, ex2_cand["info"], template, foco_treino, nivel)
    if ex1_fmt and ex2_fmt:
        ia_logger.info(f"           >> CONJUGADO: {ex1_fmt['nome']} + {ex2_fmt['nome']}")
        return ex1_fmt, ex2_fmt, [ex1_chave, ex2_chave], ex1_tag_func
    return None


def _tentar_selecionar_piramide(
    grupo: str, nivel: str, foco_treino: str, lesoes: str,
    usados_semana: Set[str], bonus_gc: float, sexo: str, assimetrias: Dict,
    foco_dia: Optional[List[str]], foco_comp: bool, template: dict, params_merged: Dict,
    tags_funcionais_ja_usadas_neste_grupo_dia: Optional[Set[str]] = None # NOVO
    ) -> Optional[Tuple[Dict, str, Optional[str]]]: # Retorna também a tag funcional
    selection_logger.debug(f"      Tentando PIRÂMIDE para {grupo} (tags já usadas dia: {tags_funcionais_ja_usadas_neste_grupo_dia})")
    cands = _obter_candidatos_pontuados(
        grupo, nivel, foco_treino, lesoes, usados_semana, bonus_gc, sexo,
        assimetrias, foco_dia, foco_comp, tecnica_requerida=TEC_PIRAMIDE, params_merged=params_merged,
        tags_funcionais_ja_usadas_neste_grupo_dia=tags_funcionais_ja_usadas_neste_grupo_dia
    )
    if not cands: return None
    ex_cand, ex_chave = cands[0], cands[0]["nome_chave"]
    ex_tag_funcional = ex_cand["info"].get("tag_funcional")
    ex_fmt_base = _formatar_exercicio(ex_chave, ex_cand["info"], template, foco_treino, nivel)
    if not ex_fmt_base: return None
    
    series_p, reps_p = 4, "12-10-8-6" # Padrões, podem ser ajustados como na sua sugestão anterior
    if nivel == 'iniciante': series_p, reps_p = 3, "12-10-8"
    elif nivel == 'avancado': series_p, reps_p = random.choice([4,5]), random.choice(["12-10-8-6", "10-8-6-4", "15-12-10-8"]) if "forca" not in foco_treino else random.choice(["8-6-4-4", "10-8-6-4"])

    ex_fmt_piramide = ex_fmt_base.copy()
    ex_fmt_piramide.update({"series": series_p, "repeticoes": reps_p, "descanso": "90-120s", "observacao_tecnica": f"PIRÂMIDE ({reps_p} reps), aumente carga."})
    ia_logger.info(f"           >> PIRÂMIDE: {ex_fmt_piramide['nome']}")
    return ex_fmt_piramide, ex_chave, ex_tag_funcional


# --- ADICIONADO PARA OPÇÃO C: Regenerar Dia ---
def gerar_exercicios_para_dia(
    aluno_info: Dict[str, Any], dia_key: str, template_id: str,
    exercicios_ja_usados_outros_dias: Set[str],
    params_otimizados_override: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, Any]]: # Retorna Lista de exercícios, não mais dict com "erro"
    start_time_dia = datetime.now()
    ia_logger.info(f"-- Gerando Exercícios DIA ESPECÍFICO: Aluno {aluno_info.get('id','?')}, Dia '{dia_key}', Template '{template_id}' --")
    split_template = next((t for t in SPLIT_TEMPLATES.values() if t.get("id") == template_id), None)
    if not split_template: ia_logger.error(f"IA (Reg Dia): Template ID '{template_id}' não encontrado."); return []
    dia_info = split_template.get("dias", {}).get(dia_key)
    if not dia_info: ia_logger.error(f"IA (Reg Dia): Dia '{dia_key}' não no template '{template_id}'."); return []

    params_base = {'bonus_foco_dia': 3.0, 'bonus_foco_aluno': 1.5, 'peso_prioridade': 1.0, 'bonus_composto': 1.0, 'penalidade_isolado': -0.5, 'bonus_unilateral_assimetria': 1.5, 'penalidade_repeticao_geral': -15.0, 'bonus_gc_sobrepeso': 1.0, 'bonus_gc_obesidade': 1.5, 'fator_ajuste_foco_imc': 1.2, 'assimetria_limiar_abs_cm': 1.0, 'assimetria_limiar_rel': 0.05}
    params_merged = {**params_base, **PARAMETROS_IA_OTIMIZADOS, **(params_otimizados_override or {})}

    sexo_norm, nivel_norm = normalize_text(aluno_info.get("sexo", "M")), normalize_text(aluno_info.get("nivel", "I"))
    foco_treino_norm, lesoes_norm = normalize_text(aluno_info.get("foco_treino", "")), normalize_text(aluno_info.get("historico_lesoes", ""))
    medidas = aluno_info.get("medidas", {})
    bonus_gc = 0.0 # Adicionar lógica IMC se necessário aqui também para regeneração
    assimetrias = detectar_assimetrias(medidas, params_merged['assimetria_limiar_abs_cm'], params_merged['assimetria_limiar_rel'])

    exercicios_dia_fmt = []
    exercicios_usados_neste_dia_geracao = set() # Isola os usados apenas nesta geração de dia
    grupos_dia_orig, vol_grupo_dia = dia_info.get("grupos", []), dia_info.get("vol_grupo", {})
    foco_dia_cfg, foco_comp_cfg = dia_info.get("foco_dia"), dia_info.get("foco_composto", False)
    
    grupos_ord = sorted([g for g in grupos_dia_orig if g in GRUPOS_MUSCULARES], key=lambda g: GRUPO_ORDEM.get(GRUPO_CLASSIFICACAO.get(g, "Desconhecido"),99))
    prob_tec, max_tec_grupo = split_template.get("prob_tecnica", 0.0), split_template.get("max_tecnicas_grupo", 0 if nivel_norm == 'iniciante' else 1)
    tec_aplicadas_grupo_dia = {g: 0 for g in grupos_dia_orig}

    for grupo_atual in grupos_ord:
        num_target = vol_grupo_dia.get(grupo_atual, 0)
        if not isinstance(num_target, int) or num_target <= 0: continue
        ia_logger.info(f"  (Reg Dia {dia_key}) Grupo {grupo_atual}: Target={num_target}...")
        ex_add_grupo_dia = 0
        tags_func_usadas_grupo_dia_atual = set() # Rastreia tags funcionais para ESTE grupo NESTE dia

        while ex_add_grupo_dia < num_target:
            usados_considerar_geral = exercicios_ja_usados_outros_dias.union(exercicios_usados_neste_dia_geracao)
            tentar_tec = max_tec_grupo > 0 and tec_aplicadas_grupo_dia.get(grupo_atual, 0) < max_tec_grupo and random.random() < prob_tec
            item_add, chaves_add_item, tipo_item_add, consumo_vol_item, tags_func_item = None, [], None, 0, []

            if tentar_tec:
                # Lógica de tentativa de técnicas (Biset, Conjugado, Pirâmide)
                # Cada função de técnica deve agora aceitar e usar tags_func_usadas_grupo_dia_atual
                # e retornar as tags funcionais dos exercícios que ela adiciona.
                # Exemplo para pirâmide:
                res_pir = _tentar_selecionar_piramide(grupo_atual, nivel_norm, foco_treino_norm, lesoes_norm, usados_considerar_geral, bonus_gc, sexo_norm, assimetrias, foco_dia_cfg, foco_comp_cfg, split_template, params_merged, tags_func_usadas_grupo_dia_atual)
                if res_pir:
                    ex_fmt, ex_chave, ex_tag = res_pir
                    item_add = {"tipo_item": "tecnica", "nome_tecnica": TEC_PIRAMIDE, "exercicio": ex_fmt, "instrucao": ex_fmt.get("observacao_tecnica")}
                    chaves_add_item, tipo_item_add, consumo_vol_item = [ex_chave], "tecnica", 1
                    if ex_tag: tags_func_item.append(ex_tag)
                    tec_aplicadas_grupo_dia[grupo_atual] +=1
                # Adicionar lógica similar para Biset e Conjugado, passando e recebendo tags_funcionais
                # ...

            if not item_add: # Se não aplicou técnica ou falhou, tenta exercício normal
                res_norm = _selecionar_exercicio_normal(grupo_atual, nivel_norm, foco_treino_norm, lesoes_norm, usados_considerar_geral, bonus_gc, sexo_norm, assimetrias, foco_dia_cfg, foco_comp_cfg, split_template, params_merged, tags_func_usadas_grupo_dia_atual)
                if res_norm:
                    ex_fmt, ex_chave = res_norm
                    item_add = {"tipo_item": "exercicio_normal", "exercicio": ex_fmt}
                    chaves_add_item, tipo_item_add, consumo_vol_item = [ex_chave], "exercicio_normal", 1
                    if ex_fmt.get("tag_funcional"): tags_func_item.append(ex_fmt["tag_funcional"])
            
            if item_add and chaves_add_item:
                exercicios_dia_fmt.append(item_add)
                ex_add_grupo_dia += consumo_vol_item
                for chave in chaves_add_item: exercicios_usados_neste_dia_geracao.add(chave)
                for tag_f in tags_func_item: tags_func_usadas_grupo_dia_atual.add(tag_f)
                ia_logger.info(f"      + (Reg Dia {dia_key}) {chaves_add_item} ({tipo_item_add}) Tags Func: {tags_func_item}")
            else: ia_logger.warning(f" (Reg Dia {dia_key}) Não add mais para {grupo_atual}."); break
        if ex_add_grupo_dia < num_target: ia_logger.warning(f" (Reg Dia {dia_key}) Grupo '{grupo_atual}': Add {ex_add_grupo_dia}/{num_target}.")
    
    duration_dia = (datetime.now() - start_time_dia).total_seconds()
    ia_logger.info(f"-- Geração DIA ESPECÍFICO '{dia_key}' concluída. {len(exercicios_dia_fmt)} itens. Tempo: {duration_dia:.2f}s --")
    return exercicios_dia_fmt


# --- Função Principal de Geração do Plano ---
def gerar_plano_semanal_ia(aluno_info: Dict[str, Any], params_otimizados_override: Optional[Dict[str, float]] = None):
    start_time = datetime.now()
    if not exercicios_db: return {"erro": "Banco de exercícios indisponível."}

    try:
        aluno_id = aluno_info.get('id', 'N/A'); sexo_db = aluno_info.get("sexo", "M"); nivel_db = aluno_info.get("nivel", "I")
        foco_db = aluno_info.get("foco_treino", ""); lesoes_db = aluno_info.get("historico_lesoes", ""); medidas = aluno_info.get("medidas", {})
        sexo_norm, nivel_norm = normalize_text(sexo_db), normalize_text(nivel_db)
        foco_treino_norm, lesoes_norm = normalize_text(foco_db), normalize_text(lesoes_db)
        if sexo_norm not in ['masculino', 'feminino']: sexo_norm = "masculino"
        if nivel_norm not in NIVEIS_VALIDOS: nivel_norm = "iniciante"
        ia_logger.info(f"--- Gerando PLANO: ID={aluno_id}, Nível={nivel_norm}, Sexo={sexo_norm}, Foco={foco_treino_norm}, Lesões={lesoes_norm} ---")

        params_base = {'bonus_foco_dia': 3.0, 'bonus_foco_aluno': 1.5, 'peso_prioridade': 1.0, 'bonus_composto': 1.0, 'penalidade_isolado': -0.5, 'bonus_unilateral_assimetria': 1.5, 'penalidade_repeticao_geral': -15.0, 'bonus_gc_sobrepeso': 1.0, 'bonus_gc_obesidade': 1.5, 'fator_ajuste_foco_imc': 1.2, 'assimetria_limiar_abs_cm': 1.0, 'assimetria_limiar_rel': 0.05}
        params_merged = {**params_base, **PARAMETROS_IA_OTIMIZADOS, **(params_otimizados_override or {})}
        # Log dos parâmetros usados (pode ser útil para debug)
        # ia_logger.debug(f"--- Parâmetros da IA usados: {params_merged} ---")

    except Exception as e: ia_logger.exception(f"IA: Erro dados iniciais {aluno_id}: {e}"); return {"erro": "Erro dados aluno."}

    imc_val, imc_cat, bonus_gc, obs_imc = None, "N/A", 0.0, None
    try: # Cálculo IMC
        peso, altura = medidas.get("peso_kg"), medidas.get("altura_cm")
        if peso and altura and isinstance(peso, (int, float)) and isinstance(altura, (int,float)) and peso > 0 and altura > 100:
            imc_val = round(peso / ((altura/100)**2), 1)
            if imc_val < 18.5: imc_cat, obs_imc = "Abaixo do peso", "IMC Abaixo do Peso: Foco em nutrição."
            elif 18.5 <= imc_val < 25: imc_cat = "Peso normal"
            elif 25 <= imc_val < 30: imc_cat, bonus_gc, obs_imc = "Sobrepeso", params_merged['bonus_gc_sobrepeso'], "IMC Sobrepeso: Foco em resistência/emagrecimento."
            else: imc_cat, bonus_gc = "Obesidade", params_merged['bonus_gc_obesidade']; obs_imc="IMC Obesidade: Treino chave. Foco resistência/emagrecimento."
            if bonus_gc > 0 and foco_treino_norm in ['emagrecimento', 'resistencia']: bonus_gc *= params_merged['fator_ajuste_foco_imc']
            ia_logger.info(f"IA ({aluno_id}): IMC={imc_val} ({imc_cat}). Bônus GC: {bonus_gc:.2f}.")
    except Exception as e_imc: ia_logger.exception(f"IA ({aluno_id}): Erro IMC: {e_imc}")

    assimetrias = detectar_assimetrias(medidas, params_merged['assimetria_limiar_abs_cm'], params_merged['assimetria_limiar_rel'])
    if any(assimetrias.values()): ia_logger.info(f"IA ({aluno_id}): Assimetrias: {{k:v for k,v in assimetrias.items() if v}}")

    template_key = f"{nivel_norm}_{sexo_norm}"
    split_template = SPLIT_TEMPLATES.get(template_key, SPLIT_TEMPLATES.get(f"iniciante_{sexo_norm}", SPLIT_TEMPLATES["iniciante_masculino"]))
    ia_logger.info(f"IA ({aluno_id}): Template ID '{split_template.get('id', '?')}' ({split_template.get('nome', 'N/A')})")

    plano_final = {
        "plano_info": {"aluno_id": aluno_id, "template_id": split_template.get('id','?'), "template_nome": split_template.get('nome','?'), "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "imc_calculado": imc_val or "N/A", "imc_categoria": imc_cat, "parametros_usados": params_merged if ia_logger.isEnabledFor(logging.DEBUG) else "omitido_para_info_log"}, # Opcional: incluir params
        "dias_treino": {},
        "observacoes_gerais": ["Realize aquecimento (5-10 min cardio leve + mobilidade).", "Concentre-se na execução correta.", "Procure progredir gradualmente.", "Hidratação, dieta e sono são fundamentais.", f"Descanso: {split_template.get('descanso_sugerido','60-90s')} (ajuste conforme indicado)."]
    }
    if lesoes_norm: plano_final["observacoes_gerais"].append(f"ATENÇÃO: Lesão prévia '{lesoes_db}'. Não force.")
    if obs_imc: plano_final["observacoes_gerais"].append(obs_imc)
    if any(assimetrias.values()): plano_final["observacoes_gerais"].append(f"Assimetrias ({ {k:v for k,v in assimetrias.items() if v} }): Treino pode incluir unilaterais. Comece pelo lado fraco ou adicione séries extras se orientado.")

    exercicios_usados_semana = set() # Set GERAL para penalidade de repetição NA SEMANA

    for dia_key, dia_info in split_template.get("dias", {}).items():
        if not isinstance(dia_info, dict): continue
        nome_dia, grupos_orig, vol_grupo = dia_info.get("nome", f"T {dia_key}"), dia_info.get("grupos", []), dia_info.get("vol_grupo", {})
        foco_dia_cfg, foco_comp_cfg = dia_info.get("foco_dia"), dia_info.get("foco_composto", False)
        ia_logger.info(f"-- Gerando Dia {dia_key}: {nome_dia} --")
        treino_dia_exercicios = []
        grupos_ordenados = sorted([g for g in grupos_orig if g in GRUPOS_MUSCULARES], key=lambda g: GRUPO_ORDEM.get(GRUPO_CLASSIFICACAO.get(g, "Desconhecido"), 99))
        ia_logger.info(f"  Ordem Grupos: {grupos_ordenados}")

        prob_tec, max_tec_g = split_template.get("prob_tecnica", 0.0), split_template.get("max_tecnicas_grupo", 0 if nivel_norm == 'iniciante' else 1)
        tec_aplicadas_por_grupo_dia = {g: 0 for g in grupos_orig}

        for grupo_atual in grupos_ordenados:
            num_target_total_grupo = vol_grupo.get(grupo_atual, 0)
            if not isinstance(num_target_total_grupo, int) or num_target_total_grupo <= 0: continue
            ia_logger.info(f"  Grupo {grupo_atual}: Target={num_target_total_grupo} item(s)...")
            exercicios_adicionados_neste_grupo_dia = 0
            
            # *** NOVO: Rastreia tags funcionais usadas para ESTE grupo NESTE DIA ESPECÍFICO ***
            tags_funcionais_usadas_para_este_grupo_neste_dia = set()

            while exercicios_adicionados_neste_grupo_dia < num_target_total_grupo:
                tentar_tecnica_flag = max_tec_g > 0 and tec_aplicadas_por_grupo_dia.get(grupo_atual, 0) < max_tec_g and random.random() < prob_tec
                item_adicionado_final, chaves_adicionadas_ao_item, tipo_item_adicionado_final, consumo_volume_item, tags_funcionais_do_item_adicionado = None, [], None, 0, []

                if tentar_tecnica_flag:
                    ia_logger.info(f"      Tentando aplicar técnica para {grupo_atual}...")
                    tecnicas_disponiveis = [TEC_PIRAMIDE, TEC_BISET, TEC_CONJUGADO] # Ordem de preferência ou shuffle
                    random.shuffle(tecnicas_disponiveis)
                    
                    for tipo_tecnica_atual in tecnicas_disponiveis:
                        resultado_tecnica = None
                        temp_tags_func_item = [] # Tags do item técnico específico
                        try:
                            if tipo_tecnica_atual == TEC_PIRAMIDE:
                                resultado_tecnica = _tentar_selecionar_piramide(grupo_atual, nivel_norm, foco_treino_norm, lesoes_norm, exercicios_usados_semana, bonus_gc, sexo_norm, assimetrias, foco_dia_cfg, foco_comp_cfg, split_template, params_merged, tags_funcionais_usadas_para_este_grupo_neste_dia)
                                if resultado_tecnica: 
                                    ex_fmt, ex_chave, ex_tag = resultado_tecnica
                                    item_adicionado_final = {"tipo_item": "tecnica", "nome_tecnica": TEC_PIRAMIDE, "exercicio": ex_fmt, "instrucao": ex_fmt.get("observacao_tecnica")}
                                    chaves_adicionadas_ao_item, consumo_volume_item = [ex_chave], 1
                                    if ex_tag: temp_tags_func_item.append(ex_tag)
                            elif tipo_tecnica_atual == TEC_BISET:
                                resultado_tecnica = _tentar_selecionar_biset(grupo_atual, nivel_norm, foco_treino_norm, lesoes_norm, exercicios_usados_semana, bonus_gc, sexo_norm, assimetrias, foco_dia_cfg, foco_comp_cfg, split_template, params_merged, tags_funcionais_usadas_para_este_grupo_neste_dia)
                                if resultado_tecnica:
                                    ex1_fmt, ex2_fmt, chaves_exs, tag1, tag2 = resultado_tecnica
                                    item_adicionado_final = {"tipo_item": "tecnica", "nome_tecnica": TEC_BISET, "exercicio_1": ex1_fmt, "exercicio_2": ex2_fmt, "instrucao": f"BISET: {ex1_fmt['nome']} + {ex2_fmt['nome']}"}
                                    chaves_adicionadas_ao_item, consumo_volume_item = chaves_exs, 2 # Biset consome 2 de volume
                                    if tag1: temp_tags_func_item.append(tag1)
                                    if tag2: temp_tags_func_item.append(tag2) # Adiciona tag do ex2 também
                            elif tipo_tecnica_atual == TEC_CONJUGADO:
                                # Conjugado é mais complexo com tags se o antagonista for de grupo diferente
                                resultado_tecnica = _tentar_selecionar_conjugado(grupo_atual, nivel_norm, foco_treino_norm, lesoes_norm, exercicios_usados_semana, bonus_gc, sexo_norm, assimetrias, foco_dia_cfg, foco_comp_cfg, split_template, params_merged, grupos_ordenados, tags_funcionais_usadas_para_este_grupo_neste_dia)
                                if resultado_tecnica:
                                    ex1_fmt, ex2_fmt, chaves_exs, tag_agonista = resultado_tecnica
                                    item_adicionado_final = {"tipo_item": "tecnica", "nome_tecnica": TEC_CONJUGADO, "exercicio_1": ex1_fmt, "exercicio_2": ex2_fmt, "instrucao": f"CONJUGADO: {ex1_fmt['nome']} + {ex2_fmt['nome']}"}
                                    chaves_adicionadas_ao_item, consumo_volume_item = chaves_exs, 1 # Conjugado consome 1 do grupo atual
                                    if tag_agonista: temp_tags_func_item.append(tag_agonista)
                            
                            if item_adicionado_final: # Se uma técnica foi aplicada com sucesso
                                tipo_item_adicionado_final = "tecnica"
                                tags_funcionais_do_item_adicionado.extend(temp_tags_func_item)
                                tec_aplicadas_por_grupo_dia[grupo_atual] += 1
                                ia_logger.info(f"      + Técnica '{tipo_tecnica_atual}' para {grupo_atual}. Chaves: {chaves_adicionadas_ao_item}. Tags Func: {tags_funcionais_do_item_adicionado}")
                                break # Sai do loop de tentar técnicas
                        except Exception as tech_err: ia_logger.exception(f"           ERRO TÉCNICA '{tipo_tecnica_atual}' p/ {grupo_atual}")
                
                if not item_adicionado_final: # Se não aplicou técnica, tenta exercício normal
                    resultado_normal = _selecionar_exercicio_normal(grupo_atual, nivel_norm, foco_treino_norm, lesoes_norm, exercicios_usados_semana, bonus_gc, sexo_norm, assimetrias, foco_dia_cfg, foco_comp_cfg, split_template, params_merged, tags_funcionais_usadas_para_este_grupo_neste_dia)
                    if resultado_normal:
                        ex_fmt, ex_chave = resultado_normal
                        item_adicionado_final = {"tipo_item": "exercicio_normal", "exercicio": ex_fmt}
                        chaves_adicionadas_ao_item, tipo_item_adicionado_final, consumo_volume_item = [ex_chave], "exercicio_normal", 1
                        if ex_fmt.get("tag_funcional"): tags_funcionais_do_item_adicionado.append(ex_fmt["tag_funcional"])
                        ia_logger.info(f"      + ({exercicios_adicionados_neste_grupo_dia + 1}/{num_target_total_grupo}) {ex_fmt['nome']} (Normal). Tag Func: {ex_fmt.get('tag_funcional')}")
                    else:
                        ia_logger.warning(f"Não foi possível adicionar mais itens (normal ou técnica) para {grupo_atual}. Interrompendo."); break

                if item_adicionado_final and chaves_adicionadas_ao_item:
                    treino_dia_exercicios.append(item_adicionado_final)
                    exercicios_adicionados_neste_grupo_dia += consumo_volume_item
                    for chave_ex_add in chaves_adicionadas_ao_item:
                        if chave_ex_add: exercicios_usados_semana.add(chave_ex_add) # Adiciona ao controle geral da semana
                    for tag_f_add in tags_funcionais_do_item_adicionado:
                        if tag_f_add: tags_funcionais_usadas_para_este_grupo_neste_dia.add(tag_f_add)
                else: ia_logger.error(f"Erro lógico: Nenhum item adicionado p/ {grupo_atual}."); break
            
            if exercicios_adicionados_neste_grupo_dia < num_target_total_grupo: ia_logger.warning(f"IA ({aluno_id}): Grupo '{grupo_atual}', adicionados {exercicios_adicionados_neste_grupo_dia}/{num_target_total_grupo}.")
        
        if treino_dia_exercicios: plano_final["dias_treino"][dia_key] = { "nome_dia": nome_dia, "exercicios": treino_dia_exercicios }
        else: ia_logger.warning(f"IA ({aluno_id}): Nenhum exercício adicionado Dia {dia_key}.")

    duration = (datetime.now() - start_time).total_seconds()
    ia_logger.info(f"--- Geração PLANO (Tag Funcional) p/ Aluno {aluno_id} concluída ({len(plano_final['dias_treino'])} dias). Tempo: {duration:.2f}s ---")
    return plano_final

# --- Bloco de Teste ---
if __name__ == '__main__':
     print("\n" + "="*30 + "\n--- EXECUTANDO BLOCO DE TESTE DA IA (Tag Funcional) ---\n" + "="*30)
     logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
     ia_logger_test = logging.getLogger(__name__)
     selection_logger_test = logging.getLogger('SelectionDebug')
     selection_logger_test.setLevel(logging.DEBUG)

     if not exercicios_db: ia_logger_test.error("\nERRO CRÍTICO teste: exercicios.json não carregado.")
     else:
         ia_logger_test.info(f"\nBase de exercícios carregada com {len(exercicios_db)} entradas.")
         alunos_teste = [
             {"id": "TesteSimilaridadePeito", "nivel": "Intermediario", "sexo": "Masculino", "foco_treino": "hipertrofia", "historico_lesoes": "", "medidas": {}},
             {"id": "Assimetria_Direita_Biceps", "nivel": "Intermediario", "sexo": "Masculino", "foco_treino": "hipertrofia", "historico_lesoes": "", "medidas": {"peso_kg": 75, "altura_cm": 178, f"circ_biceps_d_relaxado{UNIDADE_MEDIDA_PADRAO}": 33.0, f"circ_biceps_e_relaxado{UNIDADE_MEDIDA_PADRAO}": 35.5}},
             {"id": "Fem_Avanc_Gluteo", "nivel": "Avancado", "sexo": "Feminino", "foco_treino": "gluteo", "historico_lesoes": "", "medidas": {}}
         ]
         for aluno_teste in alunos_teste:
             print(f"\n\n{'='*20} TESTANDO ALUNO: {aluno_teste['id']} ({aluno_teste['nivel']}/{aluno_teste['sexo']}) {'='*20}")
             plano_gerado = gerar_plano_semanal_ia(aluno_teste)
             if plano_gerado.get("erro"): ia_logger_test.error(f"ERRO: {plano_gerado['erro']}"); continue
             if not plano_gerado.get("dias_treino"): ia_logger_test.error("PLANO SEM DIAS DE TREINO"); continue
             
             ia_logger_test.info(f"  Template: {plano_gerado['plano_info'].get('template_nome')}")
             print("\n  --- EXERCÍCIOS:")
             for dia_key, info_dia in plano_gerado.get("dias_treino", {}).items():
                 print(f"      Dia {dia_key} ({info_dia.get('nome_dia','?')})")
                 exercicios_por_tag_funcional_dia = {} # Para verificar a lógica da tag funcional
                 for item_idx, item in enumerate(info_dia.get("exercicios", [])):
                     display_str = f"        {item_idx+1}. "
                     tags_func_item_log = []
                     
                     if item.get("tipo_item") == "tecnica":
                         nome_tec = item.get('nome_tecnica','?')
                         exs_tec = []
                         if "exercicio" in item: exs_tec.append(item["exercicio"]) # Piramide
                         if "exercicio_1" in item: exs_tec.append(item["exercicio_1"]) # Biset, Conjugado
                         if "exercicio_2" in item: exs_tec.append(item["exercicio_2"])
                         
                         nomes_exs_tec = " + ".join([ex.get('nome','?') for ex in exs_tec])
                         display_str += f"TEC ({nome_tec}): {nomes_exs_tec}"
                         for ex_info_tec in exs_tec:
                             tag_f = ex_info_tec.get("tag_funcional")
                             if tag_f: tags_func_item_log.append(tag_f)
                             # Para teste de similaridade no mesmo grupo
                             grupo_ex_tec = ex_info_tec.get("grupo")
                             if tag_f and grupo_ex_tec:
                                 if tag_f in exercicios_por_tag_funcional_dia.get(grupo_ex_tec, set()):
                                     display_str += f" [ALERTA SIMILARIDADE! Grupo:{grupo_ex_tec}, Tag:{tag_f}]"
                                 exercicios_por_tag_funcional_dia.setdefault(grupo_ex_tec, set()).add(tag_f)

                     elif item.get("tipo_item") == "exercicio_normal":
                         ex_info = item.get('exercicio',{})
                         display_str += f"NORMAL: {ex_info.get('nome','?')}"
                         tag_f = ex_info.get("tag_funcional")
                         if tag_f: tags_func_item_log.append(tag_f)
                         # Para teste de similaridade
                         grupo_ex_norm = ex_info.get("grupo")
                         if tag_f and grupo_ex_norm:
                             if tag_f in exercicios_por_tag_funcional_dia.get(grupo_ex_norm, set()):
                                 display_str += f" [ALERTA SIMILARIDADE! Grupo:{grupo_ex_norm}, Tag:{tag_f}]"
                             exercicios_por_tag_funcional_dia.setdefault(grupo_ex_norm, set()).add(tag_f)
                     else: display_str += f"Item Desconhecido: {item}"; continue
                     
                     if tags_func_item_log: display_str += f" (Tags Func: {', '.join(tags_func_item_log)})"
                     print(display_str)
     print("\n" + "="*30 + "\n--- FIM DO BLOCO DE TESTE DA IA ---\n" + "="*30)