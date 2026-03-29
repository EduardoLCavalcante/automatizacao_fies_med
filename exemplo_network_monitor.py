"""
Exemplo de uso do NetworkMonitor para detectar erros de rede (HTTP 504, etc.)

Este exemplo mostra como usar o monitoramento de rede em vez de 
depender de timeouts de UI para detectar falhas.
"""

from src.core import build_browser, NetworkMonitor, wait_for_network_idle
from src.actions import select2_interagivel, curso_existe


def exemplo_com_monitoramento_de_rede():
    """
    Exemplo: Usar NetworkMonitor para detectar erros de rede
    em vez de confiar em timeouts de elementos.
    """
    ctx = build_browser()
    driver = ctx.driver
    
    # ══════════════════════════════════════════════════════════════════════
    # 1. INICIAR MONITOR DE REDE
    # ══════════════════════════════════════════════════════════════════════
    monitor = NetworkMonitor(
        driver,
        # Filtrar apenas requisições relevantes (ignorar estáticos)
        ignore_static=True,
        # Opcional: filtrar por URL específica
        url_filter=lambda url: "api" in url or "consulta" in url
    )
    monitor.start()
    
    try:
        # Navegar para a página
        driver.get("https://sisfiesportal.mec.gov.br/consulta")
        
        # ══════════════════════════════════════════════════════════════════
        # 2. AGUARDAR REDE FICAR OCIOSA (em vez de wait por elemento)
        # ══════════════════════════════════════════════════════════════════
        if not wait_for_network_idle(driver, timeout=10):
            print("⚠️ Rede não ficou ociosa a tempo")
            # Verificar se houve erro de rede
            if monitor.has_gateway_error():
                print("🔴 Erro de gateway detectado (502/503/504)")
                monitor.print_errors()
                # Aqui você pode fazer retry ou tratamento especial
                return
        
        # ══════════════════════════════════════════════════════════════════
        # 3. ANTES DE INTERAGIR COM SELECT, VERIFICAR REDE
        # ══════════════════════════════════════════════════════════════════
        
        # Limpar erros anteriores
        monitor.clear_errors()
        
        # Fazer alguma interação que dispara requisição
        # (ex: selecionar estado, que carrega municípios via AJAX)
        
        # Após a interação, verificar se houve erro de rede
        monitor.poll_network_events()
        
        if monitor.has_errors():
            print("🔴 Erro de rede detectado após interação")
            monitor.print_errors()
            
            # Aqui está a lógica inteligente:
            # - Se foi erro de gateway (504), fazer retry da página inteira
            # - Se foi erro 404/400, é problema de dados, não retry
            
            last_error = monitor.get_last_error()
            if last_error and last_error.is_gateway_error():
                print("🔄 Tentando novamente (erro de gateway)")
                driver.refresh()
                # ... retry logic
            else:
                print("⚠️ Erro não recuperável, seguindo para próximo item")
        
        # ══════════════════════════════════════════════════════════════════
        # 4. AGORA SIM VERIFICAR SE SELECT ESTÁ INTERAGÍVEL
        # ══════════════════════════════════════════════════════════════════
        # Se não houve erro de rede, o select DEVE estar pronto
        # Se ainda assim não estiver, é bug na página
        
        if not select2_interagivel(ctx, "select2-noCursosPublico-container"):
            # Verificar se foi erro de rede que não detectamos
            monitor.poll_network_events()
            if monitor.has_errors():
                print("🔴 Select não interagível devido a erro de rede")
                monitor.print_errors()
            else:
                print("⚠️ Select não interagível (problema na página)")
            return
        
        # ══════════════════════════════════════════════════════════════════
        # 5. BUSCAR OPÇÃO SEM TIMEOUT (já sabemos que select funciona)
        # ══════════════════════════════════════════════════════════════════
        existe_medicina = curso_existe(ctx, "MEDICINA")
        
        if existe_medicina:
            print("✅ MEDICINA encontrada")
        else:
            print("⏭️ MEDICINA não existe neste município")
            # Fluxo normal - não é erro
        
        # ══════════════════════════════════════════════════════════════════
        # 6. ESTATÍSTICAS FINAIS
        # ══════════════════════════════════════════════════════════════════
        stats = monitor.get_stats()
        print(f"\n📊 Estatísticas de rede:")
        print(f"   Total de requisições: {stats['total_requests']}")
        print(f"   Requisições com erro: {stats['failed_requests']}")
        print(f"   Taxa de erro: {stats['error_rate']:.1f}%")
        
    finally:
        monitor.stop()
        driver.quit()


def abordagem_com_retry_inteligente():
    """
    Exemplo: Retry automático apenas quando há erro de rede,
    não quando elemento não está visível.
    """
    from src.core import with_network_check
    
    ctx = build_browser()
    
    def buscar_dados_municipio(municipio: str):
        """Função que será executada com monitoramento de rede."""
        # ... lógica de busca
        pass
    
    # Wrapper que adiciona retry baseado em rede
    buscar_com_retry = with_network_check(
        buscar_dados_municipio,
        ctx.driver,
        max_retries=3,
        retry_on_gateway=True,  # Retry em 502/503/504
        retry_on_server_error=True  # Retry em 5xx
    )
    
    # Executar com monitoramento automático
    resultado = buscar_com_retry("São Paulo")


# ════════════════════════════════════════════════════════════════════════════
# POR QUE ESSA ABORDAGEM É MAIS ROBUSTA?
# ════════════════════════════════════════════════════════════════════════════
"""
ANTES (baseado em timeout de UI):
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. Requisição HTTP (pode falhar com 504)                                  │
│ 2. Timeout esperando elemento aparecer                                     │
│ 3. ... 10-30 segundos desperdiçados ...                                   │
│ 4. TimeoutException: "Elemento não encontrado"                            │
│ 5. Não sabemos o que realmente falhou                                      │
└────────────────────────────────────────────────────────────────────────────┘

DEPOIS (baseado em monitoramento de rede):
┌────────────────────────────────────────────────────────────────────────────┐
│ 1. Requisição HTTP (falha com 504)                                        │
│ 2. NetworkMonitor detecta IMEDIATAMENTE                                   │
│ 3. print("🔴 Erro 504 detectado!")                                        │
│ 4. Retry inteligente OU seguir para próximo                               │
│ 5. ZERO segundos desperdiçados                                            │
└────────────────────────────────────────────────────────────────────────────┘

BENEFÍCIOS:
✅ Detecta o erro REAL (não o sintoma)
✅ Zero espera desnecessária
✅ Retry inteligente (só em erros recuperáveis)
✅ Diagnóstico preciso (qual URL falhou, qual status)
✅ Distingue erro de rede vs erro de lógica
"""


if __name__ == "__main__":
    exemplo_com_monitoramento_de_rede()
