# backend/main.py
# Versão 2.3.6 - Feedback por Dia (Endpoint Adicionado) - CORRIGIDO
# Logging Centralizado e Carregamento .env

from dotenv import load_dotenv
load_dotenv() # Carrega variáveis do .env
import sys
import logging
import json
import unicodedata
import re
import uuid
import psycopg2
import psycopg2.extras
import random
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Form, HTTPException, Depends, Body, status, Path as FastApiPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from enum import Enum # << Garanta que Enum está importado
from pydantic import BaseModel, Field, field_validator, ValidationInfo, EmailStr
from typing import Optional, List, Dict, Any, Set
import os # Adicionado import do módulo os


# Segurança - Hashing e JWT
from passlib.context import CryptContext
from jose import JWTError, jwt

# Importações locais (Database agora usa get_db_connection para PostgreSQL)
try:
    # Ajustado o import para usar o logger nomeado
    from backend.database import init_db, get_db_connection # get_db_connection agora retorna conexão PG
    import backend.ia.gerador_treino_ia as ia_gerador
except ImportError:
     try:
        from database import init_db, get_db_connection
        import ia.gerador_treino_ia as ia_gerador
     except ImportError as e_fallback:
        # Manter um logging básico de fallback CRÍTICO aqui, mas a config principal será abaixo
        logging.basicConfig(level=logging.CRITICAL, format='%(levelname)s: %(message)s')
        logging.critical(f"Falha ao importar módulos locais. Verifique a estrutura de pastas e o PYTHONPATH. Erro: {e_fallback}")
        sys.exit(1)

# --- Configuração de Logging Centralizada ---
# Configura o logger raiz. Outros loggers (como os em database.py) herdam a configuração se não tiverem handlers próprios.
logging.basicConfig(
    level=logging.INFO, # Nível padrão para a aplicação
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', # Inclui o nome do logger (__name__)
    stream=sys.stdout # Direciona o output para o console
)

# Opcional: Ajustar níveis para loggers específicos (exemplo)
# logging.getLogger("uvicorn").setLevel(logging.WARNING) # Reduz o ruído do uvicorn
# logging.getLogger("backend.database").setLevel(logging.DEBUG) # Nível mais detalhado para o módulo database

# Logger para este módulo principal (backend.main)
api_logger = logging.getLogger(__name__)

# === Configurações de Segurança ===
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# SECRET_KEY é carregado do .env, com fallback
SECRET_KEY = os.environ.get("SECRET_KEY", "uma_chave_secreta_de_fallback_apenas_para_desenvolvimento") # Import os necessário
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# === Modelos Pydantic (sem alterações, mantidos por brevidade) ===
class Token(BaseModel): access_token: str; token_type: str
class TokenData(BaseModel): username: str | None = None
class InstrutorInDB(BaseModel): id: int; username: str; email: Optional[EmailStr] = None; hashed_password: str; data_registro: datetime
class MedidasAluno(BaseModel):
    altura_cm: Optional[float] = Field(None, gt=0, le=300); peso_kg: Optional[float] = Field(None, gt=0, le=500)
    circ_ombros_cm: Optional[float] = Field(None, gt=0); circ_peito_cm: Optional[float] = Field(None, gt=0)
    circ_cintura_cm: Optional[float] = Field(None, gt=0); circ_quadril_cm: Optional[float] = Field(None, gt=0)
    circ_biceps_d_relaxado_cm: Optional[float] = Field(None, gt=0); circ_biceps_e_relaxado_cm: Optional[float] = Field(None, gt=0)
    circ_biceps_d_contraido_cm: Optional[float] = Field(None, gt=0); circ_biceps_e_contraido_cm: Optional[float] = Field(None, gt=0)
    circ_antebraco_d_cm: Optional[float] = Field(None, gt=0); circ_antebraco_e_cm: Optional[float] = Field(None, gt=0)
    circ_coxa_d_cm: Optional[float] = Field(None, gt=0); circ_coxa_e_cm: Optional[float] = Field(None, gt=0)
    circ_panturrilha_d_cm: Optional[float] = Field(None, gt=0); circ_panturrilha_e_cm: Optional[float] = Field(None, gt=0)
    dc_triceps_mm: Optional[float] = Field(None, gt=0); dc_subescapular_mm: Optional[float] = Field(None, gt=0)
    dc_peitoral_axilar_mm: Optional[float] = Field(None, gt=0); dc_suprailiaca_mm: Optional[float] = Field(None, gt=0)
    dc_abdominal_mm: Optional[float] = Field(None, gt=0); dc_coxa_mm: Optional[float] = Field(None, gt=0)
    dc_panturrilha_mm: Optional[float] = Field(None, gt=0)
    class Config: str_strip_whitespace = True

# Função auxiliar normalize_text (necessária para validadores abaixo)
def normalize_text(text: str) -> str:
    if not isinstance(text, str): return ""
    try: nfkd = unicodedata.normalize('NFD', text); return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower().strip()
    except Exception: return ""

class AlunoCreate(BaseModel):
    nome: str = Field(..., min_length=2, max_length=100); sexo: str; idade: int = Field(..., gt=9, lt=121); nivel: str
    medidas: Optional[MedidasAluno] = {}; objetivos: Optional[str] = ""; historico_lesoes: Optional[str] = ""; foco_treino: Optional[str] = ""
    @field_validator('nome')
    def nome_title_case(cls, v): return v.strip().title()
    @field_validator('sexo')
    def sexo_valido(cls, v):
        if v.capitalize() not in ['Masculino', 'Feminino']: raise ValueError("Sexo deve ser 'Masculino' ou 'Feminino'")
        return v.capitalize()
    @field_validator('nivel')
    def nivel_valido(cls, v):
        niveis_ok = ['iniciante', 'intermediario', 'avancado']
        nivel_norm = normalize_text(v) # Usa a função auxiliar
        if nivel_norm not in niveis_ok: raise ValueError(f"Nível inválido: '{v}'. Use: Iniciante, Intermediário ou Avançado.")
        niveis_db = {'iniciante': 'Iniciante', 'intermediario': 'Intermediário', 'avancado': 'Avançado'}
        return niveis_db.get(nivel_norm)

class FeedbackOption(str, Enum): # Enum para as opções de feedback
    excelente = "Excelente"
    bom = "Bom"
    medio = "Médio"
    ruim = "Ruim"

class FeedbackGrupoItem(BaseModel): # Feedback por Grupo (Existente)
    feedback: FeedbackOption # Usa o mesmo Enum 'FeedbackOption'
    comentario: Optional[str] = Field(None, max_length=500) # Opcional

class FeedbackGrupoPayload(BaseModel): # Feedback por Grupo (Existente)
    feedbacks: Dict[str, FeedbackGrupoItem] = Field(..., min_length=1) # Garante que pelo menos um feedback seja enviado

# --- NOVOS MODELOS PARA FEEDBACK POR DIA ---
class FeedbackDiaItem(BaseModel):
    feedback: FeedbackOption # Reutiliza o mesmo Enum
    # comentario: Optional[str] = Field(None, max_length=500) # Descomente se adicionar comentários por dia

class FeedbackDiaPayload(BaseModel):
    # Espera um dicionário onde a chave é a letra do dia ('A', 'B', etc.)
    # E o valor é um objeto FeedbackDiaItem
    feedbacks: Dict[str, FeedbackDiaItem] = Field(..., min_length=1) # Garante que pelo menos um feedback seja enviado
# --- FIM NOVOS MODELOS ---

class RegenerarDiaPayload(BaseModel): # Existente
    dia_key: str = Field(..., description="A chave do dia a ser regenerado (ex: 'A', 'B')")
    template_id: str = Field(..., description="O ID do template do plano original (ex: 'iniciante_m_abc_v2')")

class AlunoCompletoResponse(BaseModel): # Existente
    id: int
    instrutor_id: int
    nome: str
    sexo: str
    idade: int
    nivel: str
    objetivos: Optional[str] = ""
    historico_lesoes: Optional[str] = ""
    foco_treino: Optional[str] = ""
    data_cadastro: datetime
    medidas: Optional[Dict[str, Any]] = {} # Para retornar as últimas medidas encontradas

class AlunoUpdate(BaseModel): # Existente
    # Permitir atualizar apenas alguns campos, tornando-os opcionais
    nome: Optional[str] = Field(None, min_length=2, max_length=100)
    sexo: Optional[str] = None
    idade: Optional[int] = Field(None, gt=9, lt=121)
    nivel: Optional[str] = None # Campo chave para atualizar o nível
    objetivos: Optional[str] = None
    historico_lesoes: Optional[str] = None
    foco_treino: Optional[str] = None
    @field_validator('nivel')
    def nivel_valido_update(cls, v):
        if v is None: # Permite não enviar o campo
            return v
        niveis_ok = ['iniciante', 'intermediario', 'avancado']
        nivel_norm = normalize_text(v) # Usar a função normalize_text existente
        if nivel_norm not in niveis_ok:
            raise ValueError(f"Nível inválido: '{v}'. Use: Iniciante, Intermediário ou Avançado.")
        niveis_db = {'iniciante': 'Iniciante', 'intermediario': 'Intermediário', 'avancado': 'Avançado'}
        return niveis_db.get(nivel_norm)

class ExercicioAlternativa(BaseModel): # Existente
    chave: str
    nome: str
    # Opcional: pode adicionar outros campos se precisar mostrar no frontend

# === Instância FastAPI ===
app = FastAPI(title="VirtuFit Trainer API", version="2.3.6 - Feedback por Dia") # Versão atualizada

@app.on_event("startup")
async def startup_event():
    api_logger.info("Executando startup: inicializando DB PostgreSQL...")
    try:
        init_db() # Chama init_db do database.py atualizado
        api_logger.info("Inicialização do DB PostgreSQL concluída com sucesso.")
    except Exception as e:
        api_logger.exception("Erro CRÍTICO durante inicialização do DB PostgreSQL.")


app.add_middleware( CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# === Funções Auxiliares (Auth mantidas, DB adaptadas) ===
def dict_from_row(row: psycopg2.extras.DictRow) -> dict | None: return dict(row) if row else None
# normalize_text já definida acima
def verify_password(p: str, h: str) -> bool: return pwd_context.verify(p, h) # Mantida
def get_password_hash(p: str) -> str: return pwd_context.hash(p) # Mantida
def create_access_token(data: dict, expires_delta: timedelta | None = None): # Mantida
    to_encode = data.copy(); expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)); to_encode.update({"exp": expire}); return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- Adaptado: get_db ---
async def get_db():
    conn = None
    try:
        conn = get_db_connection() # Do database.py (já configurado p/ PG)
        yield conn
    finally:
        if conn:
            conn.close()
            api_logger.debug("Conexão PostgreSQL fechada (get_db).")

# --- Adaptado: get_instrutor ---
async def get_instrutor(db: psycopg2.extensions.connection, username: str) -> InstrutorInDB | None:
    cursor = None
    try:
        # Usar DictCursor para obter resultados como dicionários
        cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM instrutores WHERE username ILIKE %s", (username,))
        instrutor_row = cursor.fetchone()
        return InstrutorInDB(**dict_from_row(instrutor_row)) if instrutor_row else None
    except psycopg2.Error as e:
        api_logger.error(f"Erro DB (get_instrutor): {e}"); return None
    except Exception as e:
        api_logger.exception(f"Erro inesperado em get_instrutor: {e}"); return None
    finally:
        if cursor: cursor.close()

# --- Adaptado: get_current_active_instrutor ---
async def get_current_active_instrutor(token: str = Depends(oauth2_scheme), db: psycopg2.extensions.connection = Depends(get_db)) -> InstrutorInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None: raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError as e:
        api_logger.warning(f"Erro ao decodificar JWT: {e}"); raise credentials_exception
    except Exception as e:
        api_logger.exception(f"Erro inesperado ao decodificar JWT: {e}"); raise credentials_exception
    instrutor = await get_instrutor(db, username=token_data.username)
    if instrutor is None:
        api_logger.warning(f"Usuário do token ('{token_data.username}') não encontrado no banco de dados PostgreSQL."); raise credentials_exception
    return instrutor

# --- Adaptado: verificar_posse_aluno ---
async def verificar_posse_aluno(aluno_id: int, instrutor_id: int, db: psycopg2.extensions.connection):
    cursor = None
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id FROM alunos WHERE id = %s AND instrutor_id = %s", (aluno_id, instrutor_id))
        if not cursor.fetchone():
            api_logger.warning(f"Acesso negado: Instrutor {instrutor_id} -> Aluno {aluno_id}.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado ou não pertence a este instrutor.")
    except psycopg2.Error as e:
        api_logger.error(f"Erro DB (verificar_posse_aluno): {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao verificar posse do aluno.")
    except Exception as e:
        api_logger.exception(f"Erro inesperado em verificar_posse_aluno: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao verificar posse do aluno.")
    finally:
        if cursor: cursor.close()

# --- Adaptado: get_aluno_completo ---
async def get_aluno_completo(aluno_id: int, instrutor_id: int, db: psycopg2.extensions.connection = Depends(get_db)):
    cursor = None
    try:
        cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM alunos WHERE id = %s AND instrutor_id = %s", (aluno_id, instrutor_id))
        aluno_row = cursor.fetchone()
        if not aluno_row:
            api_logger.warning(f"get_aluno_completo: Aluno {aluno_id} não encontrado ou não pertence ao instrutor {instrutor_id}.")
            raise HTTPException(status_code=404, detail="Aluno não encontrado")
        aluno_dict = dict(aluno_row)
        cursor.execute("""
            SELECT m.* FROM medidas m
            JOIN alunos a ON m.aluno_id = a.id
            WHERE m.aluno_id = %s AND a.instrutor_id = %s
            ORDER BY m.data_medicao DESC, m.id DESC LIMIT 1
        """, (aluno_id, instrutor_id))
        medidas_row = cursor.fetchone()
        medidas_dict_db = dict(medidas_row) if medidas_row else {}
        medidas_para_ia = {}
        if medidas_dict_db:
            for col_db, valor in medidas_dict_db.items():
                if col_db not in ['id', 'aluno_id', 'data_medicao'] and valor is not None:
                    chave_ia = col_db # Mantém a chave do DB como chave para a IA
                    medidas_para_ia[chave_ia] = valor
        aluno_dict['medidas'] = medidas_para_ia
        return aluno_dict
    except HTTPException as he: raise he
    except psycopg2.Error as e:
        api_logger.exception(f"Erro DB buscar aluno completo {aluno_id}: {e}"); raise HTTPException(status_code=500, detail="Erro buscar dados completos do aluno.")
    except Exception as e:
        api_logger.exception(f"Erro inesperado em get_aluno_completo: {e}"); raise HTTPException(status_code=500, detail="Erro buscar dados completos do aluno.")
    finally:
        if cursor: cursor.close()

# === ROTAS DA API (EXISTENTES) ===

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(): return """<html><body><h1>VirtuFit Trainer API v2.3.6 - Feedback por Dia</h1></body></html>"""


@app.post("/token", response_model=Token, summary="Gera um token de acesso")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: psycopg2.extensions.connection = Depends(get_db)):
    api_logger.info(f"Login para: {form_data.username}")
    instrutor = await get_instrutor(db, form_data.username) # Usa função adaptada
    if not instrutor or not verify_password(form_data.password, instrutor.hashed_password):
        api_logger.warning(f"Falha auth para: {form_data.username}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Username ou senha incorretos", headers={"WWW-Authenticate": "Bearer"})
    access_token = create_access_token(data={"sub": instrutor.username})
    api_logger.info(f"Token gerado para: {form_data.username}")
    return {"access_token": access_token, "token_type": "bearer"}

# Rota Registrar - Adaptada
@app.post("/registrar", status_code=status.HTTP_201_CREATED, summary="Registra um novo instrutor (localmente)")
async def registrar(username: str = Form(..., alias="identificador_instrutor"), password: str = Form(..., alias="senha_instrutor"), confirm_password: str = Form(..., alias="confirmar_senha_instrutor"), db: psycopg2.extensions.connection = Depends(get_db)):
    api_logger.info(f"Tentativa registro: {username}")
    if password != confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="As senhas não coincidem.")
    cursor = None
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id FROM instrutores WHERE username ILIKE %s", (username,))
        if cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nome de usuário já registrado.")
        hashed_password = get_password_hash(password)
        cursor.execute("INSERT INTO instrutores (username, hashed_password) VALUES (%s, %s) RETURNING id", (username, hashed_password))
        instrutor_id_result = cursor.fetchone();
        if not instrutor_id_result: raise HTTPException(status_code=500, detail="Falha ao obter ID do instrutor registrado.")
        instrutor_id = instrutor_id_result[0]; db.commit()
        api_logger.info(f"Instrutor '{username}' (ID: {instrutor_id}) registrado localmente.")
        return {"message": "Instrutor registrado com sucesso (no sistema local)!", "instrutor_id": instrutor_id, "username": username}
    except psycopg2.IntegrityError as e: # Erro específico de integridade (ex: UNIQUE constraint)
        db.rollback(); api_logger.warning(f"Erro de integridade ao registrar '{username}': {e}")
        if "instrutores_username_key" in str(e) or "instrutores_email_key" in str(e): raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nome de usuário ou email já registrado.")
        else: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro de integridade no banco de dados.")
    except psycopg2.Error as e: # Erro genérico do psycopg2
        db.rollback(); api_logger.exception(f"Erro DB registro '{username}': {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao registrar.")
    except Exception as e:
        db.rollback(); api_logger.exception(f"Erro inesperado registrar '{username}': {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor.")
    finally:
        if cursor: cursor.close()

@app.get("/instrutores/me", response_model=Dict[str, Any], summary="Retorna dados do instrutor logado")
async def read_users_me(current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    return {"id": current_instrutor.id, "username": current_instrutor.username, "email": current_instrutor.email, "data_registro": current_instrutor.data_registro}

# Rota Criar Aluno - Adaptada
@app.post("/alunos", status_code=status.HTTP_201_CREATED, summary="Cadastra um novo aluno via JSON")
async def criar_novo_aluno( aluno_data: AlunoCreate, db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    api_logger.info(f"Instrutor {current_instrutor.id} ({current_instrutor.username}) cadastrando aluno via JSON: {aluno_data.nome}")
    cursor = None
    try:
        cursor = db.cursor()
        cursor.execute("SELECT id FROM alunos WHERE nome ILIKE %s AND instrutor_id = %s", (aluno_data.nome, current_instrutor.id))
        if cursor.fetchone(): raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Você já possui um aluno chamado '{aluno_data.nome}'.")
        sql_aluno = """INSERT INTO alunos (instrutor_id, nome, sexo, idade, nivel, objetivos, historico_lesoes, foco_treino) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id"""
        valores_aluno = (current_instrutor.id, aluno_data.nome, aluno_data.sexo, aluno_data.idade, aluno_data.nivel, aluno_data.objetivos or "", aluno_data.historico_lesoes or "", aluno_data.foco_treino or "")
        cursor.execute(sql_aluno, valores_aluno)
        aluno_id_result = cursor.fetchone();
        if not aluno_id_result: raise HTTPException(status_code=500, detail="Falha ao criar aluno (não retornou ID).")
        aluno_id = aluno_id_result[0]
        if aluno_data.medidas:
            medidas_validas = aluno_data.medidas.model_dump(exclude_unset=True)
            if medidas_validas:
                colunas = ['aluno_id'] + list(medidas_validas.keys()); placeholders = ', '.join(['%s'] * len(colunas))
                valores = [aluno_id] + list(medidas_validas.values()); sql_medidas = f"INSERT INTO medidas ({', '.join(colunas)}) VALUES ({placeholders})"
                cursor.execute(sql_medidas, tuple(valores)); api_logger.info(f"Medidas inseridas para o aluno ID: {aluno_id}")
        db.commit()
        api_logger.info(f"Aluno {aluno_data.nome} (ID:{aluno_id}) cadastrado com sucesso por instrutor {current_instrutor.id}.")
        return {"message": f"Aluno '{aluno_data.nome}' cadastrado com sucesso!", "aluno_id": aluno_id}
    except HTTPException as he: db.rollback(); raise he
    except psycopg2.Error as e: db.rollback(); api_logger.exception(f"Erro DB cadastrar aluno '{aluno_data.nome}': {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao salvar aluno.")
    except Exception as e: db.rollback(); api_logger.exception(f"Erro inesperado cadastrar aluno '{aluno_data.nome}': {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor.")
    finally:
        if cursor: cursor.close()

@app.patch("/alunos/{aluno_id}", status_code=status.HTTP_200_OK, summary="Atualiza dados do perfil de um aluno")
async def atualizar_aluno(aluno_id: int, aluno_update_data: AlunoUpdate, db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    await verificar_posse_aluno(aluno_id, current_instrutor.id, db)
    api_logger.info(f"Instrutor {current_instrutor.username} atualizando perfil Aluno ID: {aluno_id}")
    update_fields = aluno_update_data.model_dump(exclude_unset=True)
    if not update_fields: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum dado fornecido para atualização.")
    set_clause = ", ".join([f"{key} = %s" for key in update_fields.keys()])
    sql_update = f"UPDATE alunos SET {set_clause} WHERE id = %s AND instrutor_id = %s"
    values = list(update_fields.values()) + [aluno_id, current_instrutor.id]
    cursor = None
    try:
        cursor = db.cursor()
        cursor.execute(sql_update, tuple(values))
        if cursor.rowcount == 0:
             db.rollback(); cursor.execute("SELECT id FROM alunos WHERE id = %s", (aluno_id,))
             if not cursor.fetchone(): raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado.")
             else: raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Não foi possível atualizar o aluno (verifique permissões ou se houve alteração).")
        db.commit()
        api_logger.info(f"Perfil do Aluno ID: {aluno_id} atualizado com sucesso. Campos: {list(update_fields.keys())}")
        return {"message": "Perfil do aluno atualizado com sucesso!"}
    except HTTPException as he: db.rollback(); raise he
    except psycopg2.Error as e: db.rollback(); api_logger.exception(f"Erro DB ao atualizar aluno {aluno_id}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao atualizar perfil do aluno.")
    except Exception as e: db.rollback(); api_logger.exception(f"Erro inesperado ao atualizar aluno {aluno_id}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor.")
    finally:
        if cursor: cursor.close()

# Rota Listar Alunos - Adaptada
@app.get("/alunos", response_model=List[Dict[str, Optional[int | str]]], summary="Lista alunos DO instrutor LOGADO")
async def listar_alunos(db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    api_logger.info(f"Instrutor {current_instrutor.username} (ID: {current_instrutor.id}) listando SEUS alunos.")
    cursor = None
    try:
        cursor = db.cursor() # Usa o cursor padrão da conexão
        sql_query = "SELECT id, nome FROM alunos WHERE instrutor_id = %s ORDER BY nome"
        cursor.execute(sql_query, (current_instrutor.id,))
        resultados_brutos = cursor.fetchall()
        alunos_formatados = []
        if resultados_brutos:
            for linha in resultados_brutos:
                if isinstance(linha, (list, tuple)) and len(linha) >= 2:
                    alunos_formatados.append({'id': linha[0], 'nome': linha[1]})
                else:
                    api_logger.warning(f"Formato inesperado de linha recebido do DB: {linha}")
        return alunos_formatados
    except psycopg2.Error as e: api_logger.exception(f"Erro listar alunos {current_instrutor.id}: {e}"); raise HTTPException(status_code=500, detail="Erro listar alunos.")
    except Exception as e: api_logger.exception(f"Erro inesperado listar alunos {current_instrutor.id}: {e}"); raise HTTPException(status_code=500, detail="Erro listar alunos.")
    finally:
         if cursor: cursor.close()

@app.get("/alunos/{aluno_id}", response_model=AlunoCompletoResponse, summary="Busca dados completos de um aluno específico")
async def get_aluno_por_id(aluno_id: int = FastApiPath(..., title="ID do Aluno", gt=0), db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    api_logger.info(f"Instrutor {current_instrutor.username} buscando dados completos Aluno ID: {aluno_id}")
    try:
        aluno_data = await get_aluno_completo(aluno_id, current_instrutor.id, db)
        return aluno_data
    except HTTPException as he: raise he
    except Exception as e: api_logger.exception(f"Erro inesperado ao buscar dados completos do aluno {aluno_id} para GET: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor ao processar dados do aluno.")

@app.post("/gerar_treino_ia/{aluno_id}", summary="Gera plano de treino")
async def gerar_plano_semanal_endpoint(aluno_id: int, db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    await verificar_posse_aluno(aluno_id, current_instrutor.id, db)
    aluno = await get_aluno_completo(aluno_id, current_instrutor.id, db)
    aluno_nome = aluno.get("nome", "?"); api_logger.info(f"Instrutor {current_instrutor.username} gerando plano para Aluno ID: {aluno_id} ({aluno_nome})")
    plano_db_id = None; cursor = None
    try:
        plano = ia_gerador.gerar_plano_semanal_ia(aluno)
        if not isinstance(plano, dict) or plano.get("erro"):
            erro_ia = plano.get("erro", "Erro IA") if isinstance(plano, dict) else "Formato inválido IA"
            api_logger.error(f"Erro IA Aluno {aluno_id}: {erro_ia}"); raise HTTPException(status_code=500, detail=f"Erro IA: {erro_ia}")
        try: plano_json_string = json.dumps(plano, ensure_ascii=False)
        except TypeError as json_err: api_logger.exception(f"Erro JSON plano {aluno_id}: {json_err}"); raise HTTPException(status_code=500, detail="Erro formatar plano.")
        cursor = db.cursor()
        cursor.execute("INSERT INTO treinos_gerados (aluno_id, treino_json) VALUES (%s, %s) RETURNING id", (aluno_id, plano_json_string))
        plano_db_id_result = cursor.fetchone()
        if not plano_db_id_result: raise HTTPException(status_code=500, detail="Falha ao salvar plano (não retornou ID).")
        plano_db_id = plano_db_id_result[0]; db.commit(); api_logger.info(f"Plano (DB ID: {plano_db_id}) salvo para Aluno ID: {aluno_id}.")
        if plano_db_id is None: api_logger.error(f"ID plano não obtido aluno {aluno_id}."); raise HTTPException(status_code=500, detail="Erro obter ID plano salvo.")
        plano['id_treino_gerado'] = plano_db_id
        return {"status": "ok", "message": f"Plano gerado com sucesso para {aluno_nome}!", "plano_semanal": plano }
    except HTTPException as he: db.rollback(); raise he
    except psycopg2.Error as db_err: db.rollback(); api_logger.exception(f"Erro PostgreSQL SALVAR PLANO {aluno_id}: {db_err}"); raise HTTPException(status_code=500, detail="Erro interno salvar plano.")
    except Exception as e: db.rollback(); api_logger.exception(f"Erro GERAL inesperado ao gerar plano para Aluno ID {aluno_id}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor ao gerar plano.")
    finally:
        if cursor: cursor.close()

@app.post("/gerar_exercicios_dia/{aluno_id}", response_model=List[Dict[str, Any]], summary="Gera exercícios novos para um dia específico")
async def gerar_exercicios_dia_endpoint(aluno_id: int = FastApiPath(..., title="ID do Aluno", gt=0), payload: RegenerarDiaPayload = Body(...), db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    api_logger.info(f"Instrutor {current_instrutor.username} regenerando Dia '{payload.dia_key}' (Template: {payload.template_id}) para Aluno ID: {aluno_id}")
    aluno_info = await get_aluno_completo(aluno_id, current_instrutor.id, db)
    exercicios_usados_outros_dias = set() # Simplificado
    try:
        novos_exercicios_dia = ia_gerador.gerar_exercicios_para_dia(aluno_info=aluno_info, dia_key=payload.dia_key, template_id=payload.template_id, exercicios_ja_usados_outros_dias=exercicios_usados_outros_dias)
        if isinstance(novos_exercicios_dia, dict) and novos_exercicios_dia.get("erro"):
            api_logger.error(f"Erro IA (Regerar Dia {payload.dia_key}) Aluno {aluno_id}: {novos_exercicios_dia['erro']}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro da IA: {novos_exercicios_dia['erro']}")
        if not isinstance(novos_exercicios_dia, list):
             api_logger.error(f"Erro IA (Regerar Dia {payload.dia_key}) Aluno {aluno_id}: Retorno não foi uma lista."); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno da IA ao gerar exercícios para o dia.")
        api_logger.info(f"Dia '{payload.dia_key}' regenerado com {len(novos_exercicios_dia)} itens para Aluno ID: {aluno_id}.")
        return novos_exercicios_dia
    except HTTPException as he: raise he
    except Exception as e: api_logger.exception(f"Erro GERAL inesperado ao regenerar Dia '{payload.dia_key}' para Aluno ID {aluno_id}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor ao regenerar dia.")

@app.get("/alunos/{aluno_id}/historico/planos", response_model=List[Dict[str, Any]], summary="Busca histórico de planos")
async def buscar_historico_planos(aluno_id: int, db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    await verificar_posse_aluno(aluno_id, current_instrutor.id, db)
    api_logger.info(f"Instrutor {current_instrutor.username} buscando hist planos do aluno {aluno_id}")
    historico_formatado = []; cursor = None
    try:
        cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT id, data_geracao, treino_json FROM treinos_gerados WHERE aluno_id = %s ORDER BY data_geracao DESC, id DESC LIMIT 50", (aluno_id,))
        resultados = cursor.fetchall()
        for row in resultados:
            try:
                plano_dict = json.loads(row['treino_json']) if isinstance(row['treino_json'], str) else row['treino_json']
                info_plano = plano_dict.get("plano_info", {})
                historico_formatado.append({ "id_treino_gerado": row['id'], "data_geracao": row['data_geracao'], "nome_template": info_plano.get("template_nome","?") })
            except (json.JSONDecodeError, TypeError, KeyError, AttributeError) as json_err: api_logger.warning(f"JSON inválido/incompleto treino ID {row['id']} aluno {aluno_id}: {json_err}. Pulando."); continue
            except Exception as e: api_logger.exception(f"Erro inesperado processando JSON treino ID {row['id']} aluno {aluno_id}: {e}"); continue
        return historico_formatado
    except psycopg2.Error as e: api_logger.exception(f"Erro DB hist planos {aluno_id}: {e}"); raise HTTPException(status_code=500, detail="Erro servidor buscar histórico planos.")
    except Exception as e: api_logger.exception(f"Erro inesperado hist planos {aluno_id}: {e}"); raise HTTPException(status_code=500, detail="Erro inesperado no servidor.")
    finally:
        if cursor: cursor.close()

@app.get("/alunos/{aluno_id}/historico/medidas", response_model=List[Dict[str, Any]], summary="Busca histórico de medidas")
async def buscar_historico_medidas(aluno_id: int, db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    await verificar_posse_aluno(aluno_id, current_instrutor.id, db)
    api_logger.info(f"Instrutor {current_instrutor.username} buscando hist medidas do aluno {aluno_id}")
    cursor = None
    try:
        cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM medidas WHERE aluno_id = %s ORDER BY data_medicao DESC, id DESC LIMIT 50", (aluno_id,))
        resultados = cursor.fetchall()
        return [dict(row) for row in resultados]
    except psycopg2.Error as e: api_logger.exception(f"Erro DB hist medidas {aluno_id}: {e}"); raise HTTPException(status_code=500, detail="Erro servidor buscar histórico medidas.")
    except Exception as e: api_logger.exception(f"Erro inesperado hist medidas {aluno_id}: {e}"); raise HTTPException(status_code=500, detail="Erro inesperado no servidor.")
    finally:
        if cursor: cursor.close()

@app.post("/alunos/{aluno_id}/medidas", summary="Adiciona novas medidas")
async def adicionar_medidas_aluno(aluno_id: int, medidas: MedidasAluno = Body(...), db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    await verificar_posse_aluno(aluno_id, current_instrutor.id, db)
    api_logger.info(f"Instrutor {current_instrutor.username} adicionando medidas Aluno ID: {aluno_id}")
    cursor = None
    try:
        medidas_dict_validado = medidas.model_dump(exclude_unset=True)
        if not medidas_dict_validado: raise HTTPException(status_code=400, detail="Nenhuma medida válida fornecida.")
        cursor = db.cursor()
        colunas_db = ['aluno_id'] + list(medidas_dict_validado.keys()); valores = [aluno_id] + list(medidas_dict_validado.values())
        placeholders = ', '.join(['%s'] * len(colunas_db))
        sql = f"INSERT INTO medidas ({', '.join(colunas_db)}) VALUES ({placeholders}) RETURNING id"
        cursor.execute(sql, tuple(valores))
        medidas_db_id_result = cursor.fetchone();
        if not medidas_db_id_result: raise HTTPException(status_code=500, detail="Falha ao adicionar medidas (não retornou ID).")
        medidas_db_id = medidas_db_id_result[0]; db.commit(); api_logger.info(f"Novas medidas (DB ID: {medidas_db_id}) adicionadas Aluno ID: {aluno_id}.")
        return {"status": "ok", "message": "Novas medidas adicionadas.", "medidas_id": medidas_db_id}
    except HTTPException as he: db.rollback(); raise he
    except psycopg2.Error as dbe: db.rollback(); api_logger.exception(f"Erro PostgreSQL add medidas {aluno_id}: {dbe}"); raise HTTPException(status_code=500, detail="Erro DB/Valor salvar medidas.")
    except Exception as e: db.rollback(); api_logger.exception(f"Erro geral add medidas {aluno_id}: {e}"); raise HTTPException(status_code=500, detail="Erro inesperado add medidas.")
    finally:
        if cursor: cursor.close()

@app.get("/historico/planos/{treinoId}", response_model=Dict[str, Any], summary="Busca um plano específico do histórico")
async def buscar_plano_historico_especifico( treinoId: int = FastApiPath(..., title="ID do Treino Gerado", gt=0), db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    api_logger.info(f"Instrutor {current_instrutor.username} buscando plano histórico ID: {treinoId}")
    cursor = None
    try:
        cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT aluno_id, treino_json FROM treinos_gerados WHERE id = %s", (treinoId,))
        resultado = cursor.fetchone()
        if not resultado: api_logger.warning(f"buscar_plano_historico_especifico: Plano de treino ID {treinoId} não encontrado."); raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plano de treino não encontrado.")
        aluno_id_do_plano = resultado['aluno_id']; treino_json_data = resultado['treino_json']
        await verificar_posse_aluno(aluno_id_do_plano, current_instrutor.id, db); api_logger.info(f"Posse OK: Plano {treinoId} -> Aluno {aluno_id_do_plano} -> Instrutor {current_instrutor.id}.")
        try:
            plano_dict = json.loads(treino_json_data) if isinstance(treino_json_data, str) else treino_json_data
            if not isinstance(plano_dict, dict): raise ValueError("Formato JSON inválido no banco de dados.")
            plano_dict['id_treino_gerado'] = treinoId
            return plano_dict
        except (json.JSONDecodeError, ValueError, TypeError) as json_err: api_logger.error(f"JSON inválido no DB para plano histórico ID {treinoId}: {json_err}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Formato de plano armazenado inválido.")
        except Exception as e: api_logger.exception(f"Erro inesperado ao processar JSON para plano histórico ID {treinoId}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado ao processar plano.")
    except HTTPException as he: raise he
    except psycopg2.Error as e: api_logger.exception(f"Erro de banco de dados ao buscar plano histórico {treinoId}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao buscar plano histórico.")
    except Exception as e: api_logger.exception(f"Erro inesperado ao buscar plano histórico {treinoId}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor.")
    finally:
        if cursor: cursor.close()

@app.get("/alunos/{aluno_id}/plano/atual", response_model=Dict[str, Any], summary="Busca o último plano gerado")
async def buscar_ultimo_plano_aluno(aluno_id: int = FastApiPath(..., title="ID do Aluno", gt=0), db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    await verificar_posse_aluno(aluno_id, current_instrutor.id, db)
    api_logger.info(f"Instrutor {current_instrutor.username} buscando último plano Aluno ID: {aluno_id}")
    cursor = None
    try:
        cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT id, treino_json FROM treinos_gerados WHERE aluno_id = %s ORDER BY data_geracao DESC, id DESC LIMIT 1", (aluno_id,))
        resultado = cursor.fetchone()
        if not resultado: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nenhum plano de treino recente encontrado.")
        treino_json_data = resultado['treino_json']; treino_db_id = resultado['id']
        try:
            plano_dict = json.loads(treino_json_data) if isinstance(treino_json_data, str) else treino_json_data
            if not isinstance(plano_dict, dict): raise ValueError("Formato JSON inválido")
            plano_dict['id_treino_gerado'] = treino_db_id
            return plano_dict
        except (json.JSONDecodeError, ValueError, TypeError) as json_err: api_logger.error(f"JSON inválido último plano Aluno {aluno_id} (TreinoID: {treino_db_id}): {json_err}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Formato de plano armazenado inválido.")
        except Exception as e: api_logger.exception(f"Erro inesperado ao processar JSON para último plano Aluno {aluno_id} (TreinoID: {treino_db_id}): {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor.")
    except HTTPException as he: raise he
    except psycopg2.Error as e: api_logger.exception(f"Erro DB buscar último plano Aluno {aluno_id}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno buscar último plano.")
    except Exception as e: api_logger.exception(f"Erro inesperado buscar último plano Aluno {aluno_id}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor.")
    finally:
        if cursor: cursor.close()

@app.get("/exercicios/alternativas/{chave_exercicio}", response_model=List[ExercicioAlternativa], summary="Busca exercícios alternativos")
async def buscar_alternativas(chave_exercicio: str = FastApiPath(..., title="Chave do exercício a ser substituído", min_length=1), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    api_logger.info(f"Instrutor {current_instrutor.username} buscando alternativas para exercício chave: '{chave_exercicio}'")
    if not ia_gerador.exercicios_db: api_logger.error("Base de exercícios (ia_gerador.exercicios_db) não está carregada."); raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Base de dados de exercícios indisponível.")
    exercicio_original_info = ia_gerador.exercicios_db.get(chave_exercicio)
    if not exercicio_original_info or not isinstance(exercicio_original_info, dict): api_logger.warning(f"Exercício original '{chave_exercicio}' não encontrado."); raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Exercício com chave '{chave_exercicio}' não encontrado.")
    grupo_original = exercicio_original_info.get("grupo")
    if not grupo_original or not isinstance(grupo_original, str): api_logger.error(f"Exercício '{chave_exercicio}' sem grupo muscular definido."); return []
    api_logger.debug(f"Grupo muscular original '{chave_exercicio}': {grupo_original}")
    alternativas_encontradas = []
    limite_alternativas = 10
    for chave_cand, info_cand in ia_gerador.exercicios_db.items():
        if not isinstance(info_cand, dict) or chave_cand == chave_exercicio or not info_cand.get("grupo") or not info_cand.get("nome_display"): continue
        if info_cand.get("grupo") == grupo_original: alternativas_encontradas.append({"chave": chave_cand, "nome": info_cand.get("nome_display")})
        if len(alternativas_encontradas) >= limite_alternativas: break
    api_logger.info(f"Encontradas {len(alternativas_encontradas)} alternativas para '{chave_exercicio}' (Grupo: {grupo_original}).")
    if not alternativas_encontradas: api_logger.warning(f"Nenhuma alternativa encontrada para '{chave_exercicio}' no grupo '{grupo_original}'.")
    return alternativas_encontradas

@app.post("/feedback/plano/{treino_id}/grupos", status_code=status.HTTP_200_OK, summary="Salva o feedback do instrutor por grupo muscular para um plano")
async def salvar_feedback_grupo(treino_id: int = FastApiPath(..., title="ID do Treino Gerado", gt=0), payload: FeedbackGrupoPayload = Body(...), db: psycopg2.extensions.connection = Depends(get_db), current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)):
    cursor = None
    try:
        cursor = db.cursor()
        cursor.execute("SELECT aluno_id FROM treinos_gerados WHERE id = %s", (treino_id,))
        resultado = cursor.fetchone()
        if not resultado: api_logger.warning(f"feedback/grupos: Plano de treino ID {treino_id} não encontrado."); raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plano de treino não encontrado para fornecer feedback.")
        aluno_id_do_plano = resultado[0]
        await verificar_posse_aluno(aluno_id_do_plano, current_instrutor.id, db)
        api_logger.info(f"Posse OK para feedback grupo: Plano {treino_id} -> Aluno {aluno_id_do_plano} -> Instrutor {current_instrutor.id}.")
        sql_insert_feedback = """INSERT INTO feedback_grupos (treino_gerado_id, grupo_muscular, feedback, comentario) VALUES (%s, %s, %s, %s) ON CONFLICT (treino_gerado_id, grupo_muscular) DO UPDATE SET feedback = EXCLUDED.feedback, comentario = EXCLUDED.comentario, data_feedback = CURRENT_TIMESTAMP;"""
        feedbacks_a_salvar = [(treino_id, grupo, feedback_item.feedback.value, feedback_item.comentario) for grupo, feedback_item in payload.feedbacks.items()]
        if feedbacks_a_salvar: cursor.executemany(sql_insert_feedback, feedbacks_a_salvar)
        db.commit(); api_logger.info(f"Feedback por grupo salvo com sucesso para Treino ID: {treino_id} ({len(feedbacks_a_salvar)} itens)")
        return {"message": f"Feedback por grupo salvo com sucesso para o plano {treino_id}!"}
    except HTTPException as he: db.rollback(); raise he
    except psycopg2.Error as e: db.rollback(); api_logger.exception(f"Erro DB salvar feedback por grupo Treino ID {treino_id}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao salvar feedback por grupo.")
    except Exception as e: db.rollback(); api_logger.exception(f"Erro inesperado salvar feedback por grupo Treino ID {treino_id}: {e}"); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor ao salvar feedback por grupo.")
    finally:
        if cursor: cursor.close()


# --- NOVO Endpoint para Feedback por Dia ---
@app.post("/feedback/plano/{treino_id}/dias", status_code=status.HTTP_200_OK, summary="Salva o feedback do instrutor por dia para um plano")
async def salvar_feedback_dia(
    treino_id: int = FastApiPath(..., title="ID do Treino Gerado", gt=0),
    payload: FeedbackDiaPayload = Body(...), # Usa o novo modelo Pydantic
    db: psycopg2.extensions.connection = Depends(get_db),
    current_instrutor: InstrutorInDB = Depends(get_current_active_instrutor)
):
    """
    Recebe e salva o feedback (Excelente, Bom, Médio, Ruim) para cada dia
    de um treino específico gerado. Verifica se o treino pertence ao instrutor logado.
    Utiliza INSERT ... ON CONFLICT UPDATE para atualizar caso já exista feedback
    para aquele dia/treino.
    """
    cursor = None
    try:
        cursor = db.cursor()

        # 1. Verificar se o treino existe e obter o aluno_id para checar posse
        cursor.execute("SELECT aluno_id FROM treinos_gerados WHERE id = %s", (treino_id,))
        resultado = cursor.fetchone()
        if not resultado:
            api_logger.warning(f"Feedback Dia: Treino ID {treino_id} não encontrado.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plano de treino não encontrado.")
        aluno_id_do_plano = resultado[0]

        # 2. Verificar se o aluno do treino pertence ao instrutor logado
        await verificar_posse_aluno(aluno_id_do_plano, current_instrutor.id, db)
        api_logger.info(f"Instrutor {current_instrutor.username} salvando feedback por dia para Treino ID: {treino_id} (Aluno: {aluno_id_do_plano})")

        # 3. Preparar dados para inserção/atualização no banco
        feedbacks_a_salvar = []
        for dia_key, feedback_item in payload.feedbacks.items():
            # Adicionar validação para dia_key se necessário
            if not dia_key or not isinstance(dia_key, str) or len(dia_key) > 5: # Exemplo simples
                api_logger.warning(f"Feedback Dia: Chave de dia inválida '{dia_key}' recebida para treino {treino_id}.")
                continue # Pula este item inválido

            feedbacks_a_salvar.append((
                treino_id,
                dia_key.upper(), # Garante que a chave do dia seja salva em maiúsculo
                feedback_item.feedback.value, # Pega o valor do Enum ('Excelente', etc.)
                # feedback_item.comentario # Adicione se incluir comentários
            ))

        if not feedbacks_a_salvar:
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum feedback válido fornecido no payload.")

        # 4. Usar INSERT ... ON CONFLICT para inserir ou atualizar o feedback
        # Certifique-se que o UNIQUE constraint (treino_gerado_id, dia_key) existe na tabela
        # Adicione a coluna 'comentario' se estiver usando
        sql_upsert_feedback = """
            INSERT INTO feedback_dias (treino_gerado_id, dia_key, feedback)
            VALUES (%s, %s, %s)
            ON CONFLICT (treino_gerado_id, dia_key)
            DO UPDATE SET
                feedback = EXCLUDED.feedback,
                data_feedback = CURRENT_TIMESTAMP;
        """
        # Se tiver comentário:
        # sql_upsert_feedback = """
        #     INSERT INTO feedback_dias (treino_gerado_id, dia_key, feedback, comentario)
        #     VALUES (%s, %s, %s, %s)
        #     ON CONFLICT (treino_gerado_id, dia_key)
        #     DO UPDATE SET
        #         feedback = EXCLUDED.feedback,
        #         comentario = EXCLUDED.comentario,
        #         data_feedback = CURRENT_TIMESTAMP;
        # """

        # Usar executemany para processar todos os feedbacks recebidos
        cursor.executemany(sql_upsert_feedback, feedbacks_a_salvar)

        # 5. Commitar a transação
        db.commit()
        api_logger.info(f"Feedback por dia salvo/atualizado com sucesso para Treino ID: {treino_id} ({len(feedbacks_a_salvar)} dias)")
        return {"message": f"Avaliações salvas com sucesso para o plano {treino_id}!"}

    except HTTPException as he:
        if db and not db.closed: db.rollback() # Verifica se conexão está aberta antes de rollback
        raise he # Repassa exceções HTTP (404, 403, 400)
    except psycopg2.Error as e:
        if db and not db.closed: db.rollback()
        api_logger.exception(f"Erro DB ao salvar feedback por dia para Treino ID {treino_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao salvar avaliações dos dias.")
    except Exception as e:
        if db and not db.closed: db.rollback()
        api_logger.exception(f"Erro inesperado ao salvar feedback por dia para Treino ID {treino_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro inesperado no servidor ao salvar avaliações.")
    finally:
        # Fechar o cursor apenas se ele foi criado e a conexão não está fechada
        if cursor and db and not db.closed:
             try:
                 cursor.close()
             except Exception as cursor_close_err:
                  api_logger.error(f"Erro ao fechar cursor (feedback dia): {cursor_close_err}")
        # A conexão será fechada pelo `finally` do `get_db`

# --- Fim do Novo Endpoint ---


# --- Ponto de entrada ---
if __name__ == "__main__":
    import uvicorn
    print("="*50); print(" API VirtuFit v2.3.6 (Feedback por Dia)"); print(" Use: uvicorn backend.main:app --reload --port 8000"); print("="*50)
    # A configuração de logging já foi feita no início do arquivo.
    # uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True) # Exemplo para rodar em 0.0.0.0