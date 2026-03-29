"""
Monitor de rede usando Chrome DevTools Protocol (CDP).

Esta abordagem é mais robusta porque:
1. Detecta o ERRO REAL (HTTP 504, 500, etc.) em vez de sintomas na UI
2. Permite retry inteligente baseado no status da requisição
3. Evita timeouts desnecessários quando o problema é de rede
4. Fornece diagnóstico preciso do que está falhando

Uso:
    monitor = NetworkMonitor(driver)
    monitor.start()
    
    # ... interações com a página ...
    
    if monitor.has_errors():
        errors = monitor.get_errors()
        # Tratar erros de rede
    
    monitor.clear()
"""

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Callable
from enum import Enum


class NetworkErrorType(Enum):
    """Tipos de erro de rede que queremos detectar."""
    TIMEOUT = "timeout"           # Requisição expirou
    SERVER_ERROR = "server_error" # 5xx
    GATEWAY_ERROR = "gateway"     # 502, 503, 504
    CONNECTION = "connection"     # Falha de conexão
    UNKNOWN = "unknown"


@dataclass
class NetworkRequest:
    """Representa uma requisição de rede capturada."""
    request_id: str
    url: str
    method: str
    timestamp: float
    status: Optional[int] = None
    error_text: Optional[str] = None
    response_time: Optional[float] = None
    completed: bool = False
    
    def is_error(self) -> bool:
        """Verifica se a requisição resultou em erro."""
        if self.error_text:
            return True
        if self.status and self.status >= 400:
            return True
        return False
    
    def is_gateway_error(self) -> bool:
        """Verifica se é erro de gateway (502, 503, 504)."""
        return self.status in (502, 503, 504)
    
    def is_server_error(self) -> bool:
        """Verifica se é erro de servidor (5xx)."""
        return self.status is not None and 500 <= self.status < 600
    
    def get_error_type(self) -> Optional[NetworkErrorType]:
        """Retorna o tipo de erro, se houver."""
        if not self.is_error():
            return None
        if self.error_text and "timeout" in self.error_text.lower():
            return NetworkErrorType.TIMEOUT
        if self.is_gateway_error():
            return NetworkErrorType.GATEWAY_ERROR
        if self.is_server_error():
            return NetworkErrorType.SERVER_ERROR
        if self.error_text:
            return NetworkErrorType.CONNECTION
        return NetworkErrorType.UNKNOWN


@dataclass
class NetworkState:
    """Estado atual do monitoramento de rede."""
    requests: Dict[str, NetworkRequest] = field(default_factory=dict)
    errors: List[NetworkRequest] = field(default_factory=list)
    last_error_time: Optional[float] = None
    total_requests: int = 0
    failed_requests: int = 0
    
    def clear(self):
        """Limpa o estado."""
        self.requests.clear()
        self.errors.clear()
        self.last_error_time = None
        self.total_requests = 0
        self.failed_requests = 0


class NetworkMonitor:
    """
    Monitor de rede usando Chrome DevTools Protocol.
    
    Captura todas as requisições HTTP e detecta erros em tempo real.
    """
    
    def __init__(self, driver, 
                 url_filter: Optional[Callable[[str], bool]] = None,
                 ignore_static: bool = True):
        """
        Args:
            driver: WebDriver do Selenium com suporte a CDP
            url_filter: Função para filtrar URLs a monitorar (opcional)
            ignore_static: Se True, ignora arquivos estáticos (.js, .css, .png, etc.)
        """
        self.driver = driver
        self.url_filter = url_filter
        self.ignore_static = ignore_static
        self.state = NetworkState()
        self._lock = threading.Lock()
        self._active = False
        self._listeners_added = False
        
        # Extensões de arquivos estáticos a ignorar
        self._static_extensions = {
            '.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg',
            '.woff', '.woff2', '.ttf', '.eot', '.ico', '.webp'
        }
    
    def _should_track(self, url: str) -> bool:
        """Verifica se a URL deve ser monitorada."""
        if not url:
            return False
        
        # Aplicar filtro customizado
        if self.url_filter and not self.url_filter(url):
            return False
        
        # Ignorar arquivos estáticos
        if self.ignore_static:
            url_lower = url.lower().split('?')[0]  # Remove query string
            for ext in self._static_extensions:
                if url_lower.endswith(ext):
                    return False
        
        return True
    
    def start(self) -> None:
        """Inicia o monitoramento de rede via CDP."""
        if self._active:
            return
        
        try:
            # Habilitar domínio Network do CDP
            self.driver.execute_cdp_cmd('Network.enable', {})
            self._active = True
            self._setup_listeners()
            print("🌐 Monitor de rede iniciado (CDP)")
        except Exception as e:
            print(f"⚠️ Erro ao iniciar monitor de rede: {e}")
            self._active = False
    
    def _setup_listeners(self) -> None:
        """Configura listeners de eventos de rede via CDP."""
        if self._listeners_added:
            return
        
        # Nota: Selenium 4+ permite adicionar listeners CDP, mas de forma limitada.
        # A abordagem mais robusta é fazer polling do log de performance.
        self._listeners_added = True
    
    def stop(self) -> None:
        """Para o monitoramento de rede."""
        if not self._active:
            return
        
        try:
            self.driver.execute_cdp_cmd('Network.disable', {})
            self._active = False
            print("🌐 Monitor de rede parado")
        except Exception:
            pass
    
    def _process_network_event(self, event: dict) -> None:
        """Processa um evento de rede capturado."""
        method = event.get('method', '')
        params = event.get('params', {})
        
        with self._lock:
            if method == 'Network.requestWillBeSent':
                self._handle_request_sent(params)
            elif method == 'Network.responseReceived':
                self._handle_response_received(params)
            elif method == 'Network.loadingFailed':
                self._handle_loading_failed(params)
            elif method == 'Network.loadingFinished':
                self._handle_loading_finished(params)
    
    def _handle_request_sent(self, params: dict) -> None:
        """Processa evento de requisição enviada."""
        request_id = params.get('requestId')
        request = params.get('request', {})
        url = request.get('url', '')
        
        if not self._should_track(url):
            return
        
        self.state.requests[request_id] = NetworkRequest(
            request_id=request_id,
            url=url,
            method=request.get('method', 'GET'),
            timestamp=time.time()
        )
        self.state.total_requests += 1
    
    def _handle_response_received(self, params: dict) -> None:
        """Processa evento de resposta recebida."""
        request_id = params.get('requestId')
        response = params.get('response', {})
        
        if request_id not in self.state.requests:
            return
        
        req = self.state.requests[request_id]
        req.status = response.get('status')
        req.response_time = time.time() - req.timestamp
        
        # Registrar erro se status >= 400
        if req.is_error():
            req.completed = True
            self.state.errors.append(req)
            self.state.failed_requests += 1
            self.state.last_error_time = time.time()
    
    def _handle_loading_failed(self, params: dict) -> None:
        """Processa evento de falha de carregamento."""
        request_id = params.get('requestId')
        
        if request_id not in self.state.requests:
            return
        
        req = self.state.requests[request_id]
        req.error_text = params.get('errorText', 'Unknown error')
        req.completed = True
        req.response_time = time.time() - req.timestamp
        
        self.state.errors.append(req)
        self.state.failed_requests += 1
        self.state.last_error_time = time.time()
    
    def _handle_loading_finished(self, params: dict) -> None:
        """Processa evento de carregamento finalizado."""
        request_id = params.get('requestId')
        
        if request_id in self.state.requests:
            req = self.state.requests[request_id]
            req.completed = True
            if not req.response_time:
                req.response_time = time.time() - req.timestamp
    
    def poll_network_events(self) -> None:
        """
        Captura eventos de rede do log de performance.
        
        Chame periodicamente para atualizar o estado do monitor.
        """
        if not self._active:
            return
        
        try:
            # Obter logs de performance (inclui eventos de rede)
            logs = self.driver.get_log('performance')
            
            for entry in logs:
                try:
                    message = json.loads(entry['message'])
                    event = message.get('message', {})
                    self._process_network_event(event)
                except (json.JSONDecodeError, KeyError):
                    continue
        except Exception:
            # Log de performance pode não estar disponível
            pass
    
    def check_for_errors(self, poll: bool = True) -> bool:
        """
        Verifica se há erros de rede recentes.
        
        Args:
            poll: Se True, atualiza o estado antes de verificar
            
        Returns:
            True se há erros, False caso contrário
        """
        if poll:
            self.poll_network_events()
        
        with self._lock:
            return len(self.state.errors) > 0
    
    def has_gateway_error(self, poll: bool = True) -> bool:
        """Verifica se há erro de gateway (502, 503, 504)."""
        if poll:
            self.poll_network_events()
        
        with self._lock:
            return any(e.is_gateway_error() for e in self.state.errors)
    
    def has_server_error(self, poll: bool = True) -> bool:
        """Verifica se há erro de servidor (5xx)."""
        if poll:
            self.poll_network_events()
        
        with self._lock:
            return any(e.is_server_error() for e in self.state.errors)
    
    def get_errors(self) -> List[NetworkRequest]:
        """Retorna lista de requisições com erro."""
        with self._lock:
            return list(self.state.errors)
    
    def get_last_error(self) -> Optional[NetworkRequest]:
        """Retorna o último erro registrado."""
        with self._lock:
            return self.state.errors[-1] if self.state.errors else None
    
    def clear_errors(self) -> None:
        """Limpa a lista de erros."""
        with self._lock:
            self.state.errors.clear()
            self.state.last_error_time = None
    
    def clear(self) -> None:
        """Limpa todo o estado do monitor."""
        with self._lock:
            self.state.clear()
    
    def get_stats(self) -> dict:
        """Retorna estatísticas do monitoramento."""
        with self._lock:
            return {
                'total_requests': self.state.total_requests,
                'failed_requests': self.state.failed_requests,
                'pending_requests': sum(1 for r in self.state.requests.values() if not r.completed),
                'error_rate': (self.state.failed_requests / self.state.total_requests * 100) 
                              if self.state.total_requests > 0 else 0,
                'last_error_time': self.state.last_error_time,
            }
    
    def print_errors(self) -> None:
        """Imprime erros de forma legível."""
        errors = self.get_errors()
        if not errors:
            print("✅ Nenhum erro de rede detectado")
            return
        
        print(f"\n🔴 {len(errors)} erro(s) de rede detectado(s):")
        for err in errors:
            status_str = f"HTTP {err.status}" if err.status else "Sem resposta"
            error_type = err.get_error_type()
            type_str = f"[{error_type.value}]" if error_type else ""
            print(f"   {type_str} {status_str}: {err.url[:80]}...")
            if err.error_text:
                print(f"       Erro: {err.error_text}")


def wait_for_network_idle(
    driver, 
    timeout: float = 10.0,
    idle_time: float = 0.5,
    poll_interval: float = 0.1
) -> bool:
    """
    Aguarda a rede ficar ociosa (sem requisições pendentes).
    
    Mais robusto que esperar por elementos da UI, pois detecta
    quando todas as requisições de dados foram completadas.
    
    Args:
        driver: WebDriver com CDP habilitado
        timeout: Tempo máximo de espera em segundos
        idle_time: Tempo sem atividade para considerar ocioso
        poll_interval: Intervalo entre verificações
        
    Returns:
        True se rede ficou ociosa, False se timeout
    """
    start = time.time()
    last_activity = start
    
    try:
        driver.execute_cdp_cmd('Network.enable', {})
    except Exception:
        return True  # Se CDP não disponível, assume sucesso
    
    while time.time() - start < timeout:
        try:
            logs = driver.get_log('performance')
            
            if logs:
                last_activity = time.time()
            elif time.time() - last_activity >= idle_time:
                # Rede ociosa por tempo suficiente
                return True
            
            time.sleep(poll_interval)
        except Exception:
            break
    
    return time.time() - last_activity >= idle_time


def check_xhr_status(driver, url_pattern: str = None) -> Optional[int]:
    """
    Verifica o status da última requisição XHR/Fetch.
    
    Útil para verificar se uma ação na UI resultou em sucesso
    no backend, sem depender de elementos visuais.
    
    Args:
        driver: WebDriver com CDP habilitado
        url_pattern: Padrão de URL para filtrar (opcional)
        
    Returns:
        Status HTTP da última requisição, ou None se não encontrada
    """
    try:
        logs = driver.get_log('performance')
        
        for entry in reversed(logs):
            try:
                message = json.loads(entry['message'])
                event = message.get('message', {})
                
                if event.get('method') == 'Network.responseReceived':
                    params = event.get('params', {})
                    response = params.get('response', {})
                    url = response.get('url', '')
                    
                    if url_pattern is None or url_pattern in url:
                        return response.get('status')
            except:
                continue
    except Exception:
        pass
    
    return None


# ════════════════════════════════════════════════════════════════════════════
# INTEGRAÇÃO COM O FLUXO EXISTENTE
# ════════════════════════════════════════════════════════════════════════════

def with_network_check(
    func: Callable,
    driver,
    max_retries: int = 3,
    retry_on_gateway: bool = True,
    retry_on_server_error: bool = True,
    pre_check: bool = True
):
    """
    Decorator/wrapper que adiciona verificação de rede a uma função.
    
    Uso:
        result = with_network_check(minha_funcao, driver)(arg1, arg2)
        
    Ou como wrapper:
        @with_network_check_decorator(driver)
        def minha_funcao():
            ...
    """
    def wrapper(*args, **kwargs):
        monitor = NetworkMonitor(driver)
        monitor.start()
        monitor.clear()
        
        for attempt in range(1, max_retries + 1):
            try:
                # Limpar erros anteriores
                monitor.clear_errors()
                
                # Executar função
                result = func(*args, **kwargs)
                
                # Verificar erros de rede após execução
                monitor.poll_network_events()
                
                if monitor.has_gateway_error() and retry_on_gateway:
                    print(f"🔄 Erro de gateway detectado, tentativa {attempt}/{max_retries}")
                    monitor.print_errors()
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)  # Backoff exponencial
                        continue
                
                if monitor.has_server_error() and retry_on_server_error:
                    print(f"🔄 Erro de servidor detectado, tentativa {attempt}/{max_retries}")
                    monitor.print_errors()
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                
                return result
                
            except Exception as e:
                # Verificar se foi erro de rede
                monitor.poll_network_events()
                if monitor.has_errors():
                    print(f"🔄 Exceção com erro de rede, tentativa {attempt}/{max_retries}")
                    monitor.print_errors()
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                raise
        
        monitor.stop()
        return None
    
    return wrapper
