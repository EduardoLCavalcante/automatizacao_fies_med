"""Sistema de logging estruturado para timeouts e métricas de retry."""

import json
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configuração padrão do arquivo de log
DEFAULT_LOG_FILE = "timeout_log.jsonl"
DEFAULT_METRICS_FILE = "timeout_metrics.json"
DEFAULT_FAILED_ITEMS_FILE = "failed_items.json"


@dataclass
class TimeoutEntry:
    """Entrada de log de timeout."""
    timestamp: str
    operation: str
    attempt: int
    max_attempts: int
    exception_type: str
    exception_message: str
    context: Dict[str, Any] = field(default_factory=dict)
    success_after_retry: bool = False
    total_time: Optional[float] = None


@dataclass
class FailedItem:
    """Item que falhou após todas as tentativas."""
    timestamp: str
    estado: str
    municipio: str
    ies: Optional[str] = None
    operation: str = ""
    total_attempts: int = 0
    last_error: str = ""
    can_retry: bool = True


@dataclass
class TimeoutMetrics:
    """Métricas agregadas de timeout."""
    total_timeouts: int = 0
    total_retries: int = 0
    successful_retries: int = 0
    final_failures: int = 0
    timeouts_by_operation: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    timeouts_by_state: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    avg_retry_time: float = 0.0
    retry_times: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte métricas para dicionário."""
        return {
            "total_timeouts": self.total_timeouts,
            "total_retries": self.total_retries,
            "successful_retries": self.successful_retries,
            "final_failures": self.final_failures,
            "success_rate_after_retry": (
                self.successful_retries / self.total_retries * 100
                if self.total_retries > 0 else 0
            ),
            "timeouts_by_operation": dict(self.timeouts_by_operation),
            "timeouts_by_state": dict(self.timeouts_by_state),
            "avg_retry_time_seconds": self.avg_retry_time,
        }


class TimeoutLogger:
    """
    Logger thread-safe para registrar timeouts e coletar métricas.
    
    Suporta:
    - Log de cada timeout individual (append JSONL)
    - Métricas agregadas
    - Lista de itens que falharam completamente
    - Exportação de relatório final
    """
    
    _instance: Optional["TimeoutLogger"] = None
    _lock = threading.Lock()
    
    def __init__(
        self,
        log_file: Optional[str] = None,
        metrics_file: Optional[str] = None,
        failed_items_file: Optional[str] = None,
        enabled: bool = True,
    ):
        self.log_file = Path(log_file or DEFAULT_LOG_FILE)
        self.metrics_file = Path(metrics_file or DEFAULT_METRICS_FILE)
        self.failed_items_file = Path(failed_items_file or DEFAULT_FAILED_ITEMS_FILE)
        self.enabled = enabled
        
        self.metrics = TimeoutMetrics()
        self.failed_items: List[FailedItem] = []
        self._file_lock = threading.Lock()
        
        # Contexto atual (estado, município sendo processado)
        self._current_context: Dict[str, Any] = {}
    
    @classmethod
    def get_instance(cls) -> "TimeoutLogger":
        """Retorna instância singleton do logger."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        log_file: Optional[str] = None,
        metrics_file: Optional[str] = None,
        failed_items_file: Optional[str] = None,
        enabled: bool = True,
    ) -> "TimeoutLogger":
        """Configura e retorna a instância singleton."""
        with cls._lock:
            cls._instance = cls(
                log_file=log_file,
                metrics_file=metrics_file,
                failed_items_file=failed_items_file,
                enabled=enabled,
            )
        return cls._instance
    
    def set_context(self, **kwargs) -> None:
        """Define contexto atual (estado, município, etc)."""
        self._current_context.update(kwargs)
    
    def clear_context(self) -> None:
        """Limpa contexto atual."""
        self._current_context.clear()
    
    def get_context(self) -> Dict[str, Any]:
        """Retorna cópia do contexto atual."""
        return dict(self._current_context)
    
    def log_timeout(
        self,
        operation: str,
        attempt: int,
        max_attempts: int,
        exception: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra um timeout."""
        if not self.enabled:
            return
        
        merged_context = {**self._current_context, **(context or {})}
        
        entry = TimeoutEntry(
            timestamp=datetime.now().isoformat(),
            operation=operation,
            attempt=attempt,
            max_attempts=max_attempts,
            exception_type=type(exception).__name__,
            exception_message=str(exception)[:500],  # Limita tamanho
            context=merged_context,
        )
        
        # Atualiza métricas
        self.metrics.total_timeouts += 1
        self.metrics.timeouts_by_operation[operation] += 1
        
        estado = merged_context.get("estado") or merged_context.get("state")
        if estado:
            self.metrics.timeouts_by_state[estado] += 1
        
        # Escreve no arquivo de log
        self._append_log(entry)
        
        # Log no console (resumido)
        print(f"⚠️ Timeout [{operation}] tentativa {attempt}/{max_attempts}: {type(exception).__name__}")
    
    def log_success_after_retry(
        self,
        operation: str,
        attempt: int,
        total_time: float,
    ) -> None:
        """Registra sucesso após retry."""
        if not self.enabled:
            return
        
        self.metrics.total_retries += 1
        self.metrics.successful_retries += 1
        self.metrics.retry_times.append(total_time)
        self._update_avg_retry_time()
        
        print(f"✅ Retry bem-sucedido [{operation}] após {attempt} tentativas ({total_time:.1f}s)")
    
    def log_final_failure(
        self,
        operation: str,
        total_attempts: int,
        total_time: float,
        exception: Exception,
    ) -> None:
        """Registra falha final após todas as tentativas."""
        if not self.enabled:
            return
        
        self.metrics.total_retries += 1
        self.metrics.final_failures += 1
        self.metrics.retry_times.append(total_time)
        self._update_avg_retry_time()
        
        print(f"❌ Falha final [{operation}] após {total_attempts} tentativas ({total_time:.1f}s)")
    
    def add_failed_item(
        self,
        estado: str,
        municipio: str,
        ies: Optional[str] = None,
        operation: str = "",
        total_attempts: int = 0,
        last_error: str = "",
        can_retry: bool = True,
    ) -> None:
        """Adiciona item à lista de falhas para reprocessamento."""
        if not self.enabled:
            return
        
        item = FailedItem(
            timestamp=datetime.now().isoformat(),
            estado=estado,
            municipio=municipio,
            ies=ies,
            operation=operation,
            total_attempts=total_attempts,
            last_error=last_error[:200],
            can_retry=can_retry,
        )
        self.failed_items.append(item)
    
    def _update_avg_retry_time(self) -> None:
        """Atualiza tempo médio de retry."""
        if self.metrics.retry_times:
            self.metrics.avg_retry_time = (
                sum(self.metrics.retry_times) / len(self.metrics.retry_times)
            )
    
    def _append_log(self, entry: TimeoutEntry) -> None:
        """Append entry ao arquivo de log JSONL."""
        with self._file_lock:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    json.dump(entry.__dict__, f, ensure_ascii=False)
                    f.write("\n")
            except Exception as e:
                print(f"⚠️ Erro ao escrever log de timeout: {e}")
    
    def save_metrics(self) -> None:
        """Salva métricas agregadas em arquivo JSON."""
        with self._file_lock:
            try:
                with open(self.metrics_file, "w", encoding="utf-8") as f:
                    json.dump(self.metrics.to_dict(), f, ensure_ascii=False, indent=2)
                print(f"📊 Métricas salvas em {self.metrics_file}")
            except Exception as e:
                print(f"⚠️ Erro ao salvar métricas: {e}")
    
    def save_failed_items(self) -> None:
        """Salva lista de itens falhados em arquivo JSON."""
        if not self.failed_items:
            return
        
        with self._file_lock:
            try:
                items_dict = [item.__dict__ for item in self.failed_items]
                with open(self.failed_items_file, "w", encoding="utf-8") as f:
                    json.dump(items_dict, f, ensure_ascii=False, indent=2)
                print(f"📋 {len(self.failed_items)} itens falhados salvos em {self.failed_items_file}")
            except Exception as e:
                print(f"⚠️ Erro ao salvar itens falhados: {e}")
    
    def load_failed_items(self) -> List[FailedItem]:
        """Carrega itens falhados de arquivo anterior."""
        try:
            if not self.failed_items_file.exists():
                return []
            
            with open(self.failed_items_file, "r", encoding="utf-8") as f:
                items_dict = json.load(f)
            
            return [
                FailedItem(**item)
                for item in items_dict
                if item.get("can_retry", True)
            ]
        except Exception as e:
            print(f"⚠️ Erro ao carregar itens falhados: {e}")
            return []
    
    def save_all(self) -> None:
        """Salva métricas e itens falhados."""
        self.save_metrics()
        self.save_failed_items()
    
    def print_summary(self) -> None:
        """Imprime resumo das métricas no console."""
        m = self.metrics
        print("\n" + "=" * 50)
        print("📊 RESUMO DE TIMEOUTS")
        print("=" * 50)
        print(f"Total de timeouts:      {m.total_timeouts}")
        print(f"Retries realizados:     {m.total_retries}")
        print(f"Retries bem-sucedidos:  {m.successful_retries}")
        print(f"Falhas finais:          {m.final_failures}")
        
        if m.total_retries > 0:
            rate = m.successful_retries / m.total_retries * 100
            print(f"Taxa de sucesso retry:  {rate:.1f}%")
        
        if m.avg_retry_time > 0:
            print(f"Tempo médio retry:      {m.avg_retry_time:.1f}s")
        
        if m.timeouts_by_operation:
            print("\nTimeouts por operação:")
            for op, count in sorted(m.timeouts_by_operation.items(), key=lambda x: -x[1])[:5]:
                print(f"  {op}: {count}")
        
        if m.timeouts_by_state:
            print("\nTimeouts por estado:")
            for state, count in sorted(m.timeouts_by_state.items(), key=lambda x: -x[1])[:5]:
                print(f"  {state}: {count}")
        
        if self.failed_items:
            print(f"\n⚠️ {len(self.failed_items)} itens falharam completamente")
        
        print("=" * 50 + "\n")


# Função helper para obter o logger global
def get_logger() -> TimeoutLogger:
    """Retorna a instância global do TimeoutLogger."""
    return TimeoutLogger.get_instance()


def configure_logger(
    log_file: Optional[str] = None,
    metrics_file: Optional[str] = None,
    failed_items_file: Optional[str] = None,
    enabled: bool = True,
) -> TimeoutLogger:
    """Configura o logger global."""
    return TimeoutLogger.configure(
        log_file=log_file,
        metrics_file=metrics_file,
        failed_items_file=failed_items_file,
        enabled=enabled,
    )
