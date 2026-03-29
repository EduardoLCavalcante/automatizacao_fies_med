"""Sistema de gerenciamento de progresso para retomada da automação."""

import json
import os
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
import unicodedata

from src.config import PROGRESS_FILE, AUTO_BACKUP_PROGRESS, CHECKPOINT_FREQUENCY


import re

_IES_CODIGO_RE = re.compile(r"\((\d{4,})\)\s*$")


def _nome_sem_codigo_ies(txt: str) -> str:
    """Remove código numérico entre parênteses no final do nome da IES."""
    return _IES_CODIGO_RE.sub("", txt or "").strip()


def _normalizar_texto(texto: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    ascii_text = nfkd.encode("ASCII", "ignore").decode("ASCII")
    return " ".join(ascii_text.lower().split())


def _normalizar_ies(texto: str) -> str:
    """Normaliza nome de IES removendo código e acentos."""
    sem_codigo = _nome_sem_codigo_ies(texto)
    return _normalizar_texto(sem_codigo)


@dataclass
class MunicipioProgresso:
    """Estado de progresso de um município."""
    status: str = "pendente"  # pendente, incompleto, completo
    total_ies: int = 0
    ies_coletadas: int = 0
    ies_nomes: List[str] = field(default_factory=list)
    modalidade: str = ""
    data_inicio: Optional[str] = None
    data_conclusao: Optional[str] = None
    
    def esta_completo(self) -> bool:
        """Verifica se o município foi completamente processado."""
        return self.status == "completo" or (
            self.total_ies > 0 and self.ies_coletadas >= self.total_ies
        )
    
    def adicionar_ies(self, ies_nome: str) -> None:
        """Adiciona uma IES como coletada."""
        # CORRIGIDO: Usar _normalizar_ies para remover código e normalizar
        nome_norm = _normalizar_ies(ies_nome)
        if nome_norm and nome_norm not in [_normalizar_ies(n) for n in self.ies_nomes]:
            self.ies_nomes.append(ies_nome)
            self.ies_coletadas = len(self.ies_nomes)
        
        # Atualizar status
        if self.total_ies > 0 and self.ies_coletadas >= self.total_ies:
            self.status = "completo"
            self.data_conclusao = datetime.now().isoformat()
        elif self.ies_coletadas > 0:
            self.status = "incompleto"
    
    def ies_ja_coletada(self, ies_nome: str) -> bool:
        """Verifica se uma IES já foi coletada."""
        # CORRIGIDO: Usar _normalizar_ies para remover código e normalizar
        nome_norm = _normalizar_ies(ies_nome)
        return nome_norm in [_normalizar_ies(n) for n in self.ies_nomes]
    
    def definir_total_ies(self, total: int) -> None:
        """Define o total de IES esperado para o município."""
        self.total_ies = total
        if not self.data_inicio:
            self.data_inicio = datetime.now().isoformat()
        
        # Verificar se já completou
        if total > 0 and self.ies_coletadas >= total:
            self.status = "completo"
            self.data_conclusao = datetime.now().isoformat()


@dataclass
class EstadoProgresso:
    """Estado de progresso de um estado (UF)."""
    status: str = "pendente"  # pendente, incompleto, completo
    municipios: Dict[str, MunicipioProgresso] = field(default_factory=dict)
    
    def obter_municipio(self, municipio: str) -> MunicipioProgresso:
        """Obtém ou cria progresso de um município."""
        if municipio not in self.municipios:
            self.municipios[municipio] = MunicipioProgresso()
        return self.municipios[municipio]
    
    def municipios_completos(self) -> int:
        """Conta municípios completos."""
        return sum(1 for m in self.municipios.values() if m.esta_completo())
    
    def municipios_incompletos(self) -> List[str]:
        """Lista municípios incompletos."""
        return [
            nome for nome, mun in self.municipios.items() 
            if not mun.esta_completo() and mun.ies_coletadas > 0
        ]
    
    def municipios_pendentes(self) -> List[str]:
        """Lista municípios ainda não processados."""
        return [
            nome for nome, mun in self.municipios.items() 
            if mun.status == "pendente" and mun.ies_coletadas == 0
        ]
    
    def atualizar_status(self) -> None:
        """Atualiza status do estado baseado nos municípios."""
        if not self.municipios:
            self.status = "pendente"
            return
        
        todos_completos = all(m.esta_completo() for m in self.municipios.values())
        algum_iniciado = any(m.ies_coletadas > 0 for m in self.municipios.values())
        
        if todos_completos:
            self.status = "completo"
        elif algum_iniciado:
            self.status = "incompleto"
        else:
            self.status = "pendente"


@dataclass
class ProgressoGeral:
    """Estado geral de progresso da automação."""
    versao: str = "2.0"
    criado_em: str = field(default_factory=lambda: datetime.now().isoformat())
    ultima_atualizacao: str = field(default_factory=lambda: datetime.now().isoformat())
    modalidade_atual: str = "social"
    estados: Dict[str, EstadoProgresso] = field(default_factory=dict)
    
    # Contadores internos para checkpoint
    _ies_desde_ultimo_checkpoint: int = field(default=0, repr=False)
    
    def obter_estado(self, uf: str) -> EstadoProgresso:
        """Obtém ou cria progresso de um estado."""
        if uf not in self.estados:
            self.estados[uf] = EstadoProgresso()
        return self.estados[uf]
    
    def registrar_ies_coletada(
        self, 
        uf: str, 
        municipio: str, 
        ies_nome: str,
        total_ies_municipio: int = 0
    ) -> bool:
        """
        Registra uma IES como coletada.
        
        Returns:
            True se deve salvar checkpoint (baseado em CHECKPOINT_FREQUENCY)
        """
        estado = self.obter_estado(uf)
        mun = estado.obter_municipio(municipio)
        
        if total_ies_municipio > 0:
            mun.definir_total_ies(total_ies_municipio)
        
        mun.adicionar_ies(ies_nome)
        estado.atualizar_status()
        
        self.ultima_atualizacao = datetime.now().isoformat()
        self._ies_desde_ultimo_checkpoint += 1
        
        # Verificar se deve salvar checkpoint
        deve_salvar = self._ies_desde_ultimo_checkpoint >= CHECKPOINT_FREQUENCY
        if deve_salvar:
            self._ies_desde_ultimo_checkpoint = 0
        
        return deve_salvar
    
    def ies_ja_coletada(self, uf: str, municipio: str, ies_nome: str, modalidade: str) -> bool:
        """Verifica se uma IES já foi coletada para a modalidade específica."""
        if uf not in self.estados:
            return False
        
        estado = self.estados[uf]
        if municipio not in estado.municipios:
            return False
        
        mun = estado.municipios[municipio]
        
        # Verificar modalidade
        if mun.modalidade and mun.modalidade != modalidade:
            return False  # Coletado em outra modalidade, precisa coletar nesta
        
        return mun.ies_ja_coletada(ies_nome)
    
    def municipio_completo(self, uf: str, municipio: str, modalidade: str) -> bool:
        """Verifica se um município foi completamente processado para a modalidade."""
        if uf not in self.estados:
            return False
        
        estado = self.estados[uf]
        if municipio not in estado.municipios:
            return False
        
        mun = estado.municipios[municipio]
        
        # Verificar modalidade
        if mun.modalidade and mun.modalidade != modalidade:
            return False  # Processado em outra modalidade
        
        return mun.esta_completo()
    
    def estado_completo(self, uf: str, modalidade: str) -> bool:
        """Verifica se um estado foi completamente processado."""
        if uf not in self.estados:
            return False
        
        estado = self.estados[uf]
        if estado.status != "completo":
            return False
        
        # Verificar se todos os municípios são da modalidade correta
        for mun in estado.municipios.values():
            if mun.modalidade and mun.modalidade != modalidade:
                return False
        
        return True
    
    def obter_ies_coletadas(self, uf: str, municipio: str) -> Set[str]:
        """Obtém set de IES já coletadas (normalizadas sem código) para um município."""
        if uf not in self.estados:
            return set()
        
        estado = self.estados[uf]
        if municipio not in estado.municipios:
            return set()
        
        mun = estado.municipios[municipio]
        # CORRIGIDO: Usar _normalizar_ies para remover código e normalizar
        return {_normalizar_ies(n) for n in mun.ies_nomes}
    
    def gerar_resumo(self) -> Dict:
        """Gera resumo do progresso."""
        estados_completos = sum(1 for e in self.estados.values() if e.status == "completo")
        estados_incompletos = sum(1 for e in self.estados.values() if e.status == "incompleto")
        
        municipios_completos = 0
        municipios_incompletos = 0
        total_ies = 0
        
        for estado in self.estados.values():
            municipios_completos += estado.municipios_completos()
            municipios_incompletos += len(estado.municipios_incompletos())
            for mun in estado.municipios.values():
                total_ies += mun.ies_coletadas
        
        return {
            "estados_completos": estados_completos,
            "estados_incompletos": estados_incompletos,
            "municipios_completos": municipios_completos,
            "municipios_incompletos": municipios_incompletos,
            "total_ies_coletadas": total_ies,
            "modalidade_atual": self.modalidade_atual,
            "ultima_atualizacao": self.ultima_atualizacao,
        }
    
    def to_dict(self) -> Dict:
        """Converte para dicionário serializável."""
        def converter_municipio(mun: MunicipioProgresso) -> Dict:
            return {
                "status": mun.status,
                "total_ies": mun.total_ies,
                "ies_coletadas": mun.ies_coletadas,
                "ies_nomes": mun.ies_nomes,
                "modalidade": mun.modalidade,
                "data_inicio": mun.data_inicio,
                "data_conclusao": mun.data_conclusao,
            }
        
        def converter_estado(est: EstadoProgresso) -> Dict:
            return {
                "status": est.status,
                "municipios": {
                    nome: converter_municipio(mun) 
                    for nome, mun in est.municipios.items()
                }
            }
        
        return {
            "versao": self.versao,
            "criado_em": self.criado_em,
            "ultima_atualizacao": self.ultima_atualizacao,
            "modalidade_atual": self.modalidade_atual,
            "resumo": self.gerar_resumo(),
            "estados": {
                uf: converter_estado(est) 
                for uf, est in self.estados.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ProgressoGeral":
        """Cria instância a partir de dicionário."""
        progresso = cls(
            versao=data.get("versao", "2.0"),
            criado_em=data.get("criado_em", datetime.now().isoformat()),
            ultima_atualizacao=data.get("ultima_atualizacao", datetime.now().isoformat()),
            modalidade_atual=data.get("modalidade_atual", "social"),
        )
        
        for uf, est_data in data.get("estados", {}).items():
            estado = EstadoProgresso(status=est_data.get("status", "pendente"))
            
            for mun_nome, mun_data in est_data.get("municipios", {}).items():
                municipio = MunicipioProgresso(
                    status=mun_data.get("status", "pendente"),
                    total_ies=mun_data.get("total_ies", 0),
                    ies_coletadas=mun_data.get("ies_coletadas", 0),
                    ies_nomes=mun_data.get("ies_nomes", []),
                    modalidade=mun_data.get("modalidade", ""),
                    data_inicio=mun_data.get("data_inicio"),
                    data_conclusao=mun_data.get("data_conclusao"),
                )
                estado.municipios[mun_nome] = municipio
            
            progresso.estados[uf] = estado
        
        return progresso


def carregar_progresso_json(caminho: str = PROGRESS_FILE) -> ProgressoGeral:
    """
    Carrega estado de progresso do arquivo JSON.
    
    Returns:
        ProgressoGeral com estado carregado ou novo se arquivo não existe
    """
    if not os.path.exists(caminho):
        return ProgressoGeral()
    
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        return ProgressoGeral.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"⚠️ Erro ao carregar arquivo de progresso: {e}")
        print("   Iniciando com progresso vazio")
        return ProgressoGeral()


def salvar_progresso_json(progresso: ProgressoGeral, caminho: str = PROGRESS_FILE) -> bool:
    """
    Salva estado de progresso no arquivo JSON.
    
    Returns:
        True se salvou com sucesso
    """
    try:
        # Backup automático
        if AUTO_BACKUP_PROGRESS and os.path.exists(caminho):
            backup_path = caminho.replace(".json", "_backup.json")
            try:
                shutil.copy2(caminho, backup_path)
            except Exception:
                pass  # Ignorar falha de backup
        
        progresso.ultima_atualizacao = datetime.now().isoformat()
        
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(progresso.to_dict(), f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"⚠️ Erro ao salvar arquivo de progresso: {e}")
        return False


def sincronizar_com_csv(progresso: ProgressoGeral, caminho_csv: str, modalidade: str) -> ProgressoGeral:
    """
    Sincroniza estado de progresso com dados existentes no CSV.
    
    Lê o CSV e adiciona ao progresso qualquer IES que esteja no CSV
    mas não no arquivo de progresso.
    """
    import pandas as pd
    
    if not os.path.exists(caminho_csv):
        return progresso
    
    try:
        df = pd.read_csv(caminho_csv)
    except Exception:
        return progresso
    
    if df.empty:
        return progresso
    
    df = df.fillna("")
    
    # Agrupar por estado e município para contar IES
    for _, row in df.iterrows():
        uf = str(row.get("estado", "")).strip()
        municipio = str(row.get("municipio", "")).strip()
        ies = str(row.get("ies", "")).strip()
        modalidade_csv = str(row.get("modalidade_fies", "")).strip()
        
        if not uf or not municipio or not ies:
            continue
        
        # Se modalidade do CSV corresponde, adicionar ao progresso
        if not modalidade_csv or modalidade_csv == modalidade:
            estado = progresso.obter_estado(uf)
            mun = estado.obter_municipio(municipio)
            mun.modalidade = modalidade
            
            if not mun.ies_ja_coletada(ies):
                mun.adicionar_ies(ies)
            
            estado.atualizar_status()
    
    progresso.modalidade_atual = modalidade
    return progresso


def gerar_relatorio_retomada(progresso: ProgressoGeral, modalidade: str) -> None:
    """Imprime relatório detalhado do que será processado."""
    resumo = progresso.gerar_resumo()
    
    print("\n" + "=" * 60)
    print("📊 RELATÓRIO DE RETOMADA")
    print("=" * 60)
    print(f"Modalidade: {modalidade.upper()}")
    print(f"Última atualização: {resumo['ultima_atualizacao'][:19].replace('T', ' ')}")
    print()
    print(f"✅ Estados completos: {resumo['estados_completos']}")
    print(f"🔄 Estados incompletos: {resumo['estados_incompletos']}")
    print(f"✅ Municípios completos: {resumo['municipios_completos']}")
    print(f"🔄 Municípios incompletos: {resumo['municipios_incompletos']}")
    print(f"📋 Total IES coletadas: {resumo['total_ies_coletadas']}")
    print()
    
    # Mostrar detalhes dos estados incompletos
    estados_incompletos = [
        (uf, est) for uf, est in progresso.estados.items() 
        if est.status != "completo"
    ]
    
    if estados_incompletos:
        print("📍 Estados a processar:")
        for uf, estado in estados_incompletos[:10]:  # Limitar a 10 para não poluir
            mun_completos = estado.municipios_completos()
            mun_total = len(estado.municipios) if estado.municipios else "?"
            print(f"   🟦 {uf}: {mun_completos}/{mun_total} municípios completos")
            
            # Mostrar municípios incompletos
            for mun_nome in estado.municipios_incompletos()[:3]:
                mun = estado.municipios[mun_nome]
                print(f"      📍 {mun_nome}: {mun.ies_coletadas}/{mun.total_ies or '?'} IES")
        
        if len(estados_incompletos) > 10:
            print(f"   ... e mais {len(estados_incompletos) - 10} estados")
    
    print("=" * 60 + "\n")


def marcar_municipio_iniciado(
    progresso: ProgressoGeral, 
    uf: str, 
    municipio: str, 
    total_ies: int,
    modalidade: str
) -> None:
    """Marca início do processamento de um município."""
    estado = progresso.obter_estado(uf)
    mun = estado.obter_municipio(municipio)
    mun.definir_total_ies(total_ies)
    mun.modalidade = modalidade
    
    if mun.status == "pendente":
        mun.status = "incompleto"
        mun.data_inicio = datetime.now().isoformat()


def marcar_municipio_completo(
    progresso: ProgressoGeral, 
    uf: str, 
    municipio: str
) -> None:
    """Marca município como completamente processado."""
    estado = progresso.obter_estado(uf)
    mun = estado.obter_municipio(municipio)
    mun.status = "completo"
    mun.data_conclusao = datetime.now().isoformat()
    estado.atualizar_status()
