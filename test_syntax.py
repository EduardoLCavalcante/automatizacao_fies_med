#!/usr/bin/env python3
"""Teste de sintaxe e validação da correção de matching de IES."""

import sys

print("=" * 60)
print("TESTE DE CORREÇÃO: MATCHING DE IES NO CSV")
print("=" * 60)

# Teste 1: Importações
print("\n🔍 Testando importações...")
try:
    from src.core.progress import _normalizar_ies, _nome_sem_codigo_ies
    print("✅ progress.py - OK")
except Exception as e:
    print(f"❌ progress.py - ERRO: {e}")
    sys.exit(1)

try:
    from src.scraping.runner import _norm_ies_para_comparacao, _norm_label
    print("✅ runner.py - OK")
except Exception as e:
    print(f"❌ runner.py - ERRO: {e}")
    sys.exit(1)

# Teste 2: Normalização de IES com código
print("\n🔍 Testando normalização de IES...")

# Simulando nomes do CSV (com código)
ies_csv = "AFYA FACULDADE DE CIÊNCIAS MÉDICAS DE CRUZEIRO DO SUL (24547)"
# Simulando nomes do Select2 (pode ter ou não código)
ies_select2_com_codigo = "AFYA FACULDADE DE CIÊNCIAS MÉDICAS DE CRUZEIRO DO SUL (24547)"
ies_select2_sem_codigo = "AFYA FACULDADE DE CIÊNCIAS MÉDICAS DE CRUZEIRO DO SUL"

print(f"\n📄 IES do CSV: '{ies_csv}'")
print(f"📄 IES do Select2 (com código): '{ies_select2_com_codigo}'")
print(f"📄 IES do Select2 (sem código): '{ies_select2_sem_codigo}'")

# Normalizar usando progress.py
norm_csv_progress = _normalizar_ies(ies_csv)
norm_select2_com_progress = _normalizar_ies(ies_select2_com_codigo)
norm_select2_sem_progress = _normalizar_ies(ies_select2_sem_codigo)

print(f"\n🔧 Normalização (progress.py - _normalizar_ies):")
print(f"   CSV: '{norm_csv_progress}'")
print(f"   Select2 (com): '{norm_select2_com_progress}'")
print(f"   Select2 (sem): '{norm_select2_sem_progress}'")

# Normalizar usando runner.py
norm_csv_runner = _norm_ies_para_comparacao(ies_csv)
norm_select2_com_runner = _norm_ies_para_comparacao(ies_select2_com_codigo)
norm_select2_sem_runner = _norm_ies_para_comparacao(ies_select2_sem_codigo)

print(f"\n🔧 Normalização (runner.py - _norm_ies_para_comparacao):")
print(f"   CSV: '{norm_csv_runner}'")
print(f"   Select2 (com): '{norm_select2_com_runner}'")
print(f"   Select2 (sem): '{norm_select2_sem_runner}'")

# Teste 3: Verificar se todos são iguais
print("\n🔍 Verificando consistência...")

todos_iguais = (
    norm_csv_progress == norm_select2_com_progress == norm_select2_sem_progress
    and norm_csv_runner == norm_select2_com_runner == norm_select2_sem_runner
    and norm_csv_progress == norm_csv_runner
)

if todos_iguais:
    print("✅ SUCESSO: Todas as normalizações são consistentes!")
    print(f"   Valor normalizado: '{norm_csv_progress}'")
else:
    print("❌ FALHA: Normalizações inconsistentes!")
    print("   Valores:")
    print(f"      progress CSV: '{norm_csv_progress}'")
    print(f"      progress Select2 com: '{norm_select2_com_progress}'")
    print(f"      progress Select2 sem: '{norm_select2_sem_progress}'")
    print(f"      runner CSV: '{norm_csv_runner}'")
    print(f"      runner Select2 com: '{norm_select2_com_runner}'")
    print(f"      runner Select2 sem: '{norm_select2_sem_runner}'")
    sys.exit(1)

# Teste 4: Simular matching real
print("\n🔍 Simulando matching real...")

# Criar set simulando ies_ja_salvos carregado do CSV
ies_ja_salvos = {
    _norm_ies_para_comparacao("AFYA FACULDADE DE CIÊNCIAS MÉDICAS DE CRUZEIRO DO SUL (24547)"),
    _norm_ies_para_comparacao("CENTRO UNIVERSITÁRIO UNINORTE (2132)"),
}

# Simular IES vindas do Select2
ies_do_select2 = [
    "AFYA FACULDADE DE CIÊNCIAS MÉDICAS DE CRUZEIRO DO SUL",  # sem código
    "CENTRO UNIVERSITÁRIO UNINORTE (2132)",  # com código
    "NOVA IES (9999)",  # não existe no CSV
]

print(f"   ies_ja_salvos: {ies_ja_salvos}")
print(f"   IES do Select2: {ies_do_select2}")

encontrados = 0
nao_encontrados = 0

for ies in ies_do_select2:
    ies_norm = _norm_ies_para_comparacao(ies)
    if ies_norm in ies_ja_salvos:
        print(f"   ⏭️ '{ies}' -> JÁ EXISTE (pulando)")
        encontrados += 1
    else:
        print(f"   🆕 '{ies}' -> NÃO EXISTE (processar)")
        nao_encontrados += 1

print(f"\n📊 Resultado: {encontrados} encontrados, {nao_encontrados} novos")

if encontrados == 2 and nao_encontrados == 1:
    print("✅ SUCESSO: Matching funcionando corretamente!")
else:
    print("❌ FALHA: Matching incorreto!")
    sys.exit(1)

print("\n" + "=" * 60)
print("✨ TODOS OS TESTES PASSARAM!")
print("=" * 60)
print("\n🎯 Correção aplicada:")
print("   - IES com código '(12345)' são normalizadas para nome sem código")
print("   - Comparação consistente entre CSV e Select2")
print("   - IES já no CSV serão puladas corretamente")

