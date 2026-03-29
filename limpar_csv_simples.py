#!/usr/bin/env python3
"""Script simples para limpar CSV existente."""

def limpar_csv_atual():
    print("🧹 Limpando CSV atual...")
    
    # Ler arquivo como texto
    with open("notas_fies_medicina.csv", 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    print(f"Total de linhas: {len(lines)}")
    
    # Processar cada linha
    lines_limpas = []
    header = lines[0].strip()
    lines_limpas.append(header)
    
    for i, line in enumerate(lines[1:], 1):
        line = line.strip()
        if not line:
            continue
            
        # Substituir textos problemáticos na linha
        line_limpa = line
        line_limpa = line_limpa.replace('TIPOS DE CONCORRÊNCIA\nAmpla', 'Ampla')
        line_limpa = line_limpa.replace('TIPOS DE CONCORRÊNCIA\nPPIQ', 'PPIQ')
        line_limpa = line_limpa.replace('TIPOS DE CONCORRÊNCIA\nPCD', 'PCD')
        line_limpa = line_limpa.replace('TIPOS DE CONCORRÊNCIA', '')
        line_limpa = line_limpa.replace('Ver detalhes', '')
        line_limpa = line_limpa.replace('ver detalhes', '')
        line_limpa = line_limpa.replace('Ver Detalhes', '')
        line_limpa = line_limpa.replace('\n', ' ')
        line_limpa = line_limpa.replace('\r', ' ')
        
        # Remover múltiplos espaços e vírgulas duplicadas
        import re
        line_limpa = re.sub(r'\s+', ' ', line_limpa)
        line_limpa = re.sub(r',\s*,', ',', line_limpa)
        line_limpa = re.sub(r'",\s*"', '","', line_limpa)
        
        lines_limpas.append(line_limpa)
    
    # Salvar arquivo limpo
    with open("notas_fies_medicina_backup.csv", 'w', encoding='utf-8-sig') as f:
        f.write('\n'.join(lines_limpas))
    
    print(f"✅ Backup salvo: {len(lines_limpas)} linhas")
    
    # Tentar carregar com pandas para validar
    try:
        import pandas as pd
        df = pd.read_csv("notas_fies_medicina_backup.csv", encoding='utf-8-sig')
        print(f"✅ Pandas validou: {len(df)} registros")
        
        # Se deu certo, sobrescrever o original
        import shutil
        shutil.copy2("notas_fies_medicina_backup.csv", "notas_fies_medicina.csv")
        print("✅ CSV original atualizado")
        
    except Exception as e:
        print(f"❌ Erro na validação: {e}")

if __name__ == "__main__":
    limpar_csv_atual()