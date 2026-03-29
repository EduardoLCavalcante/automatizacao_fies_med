#!/usr/bin/env python3
"""Script para reparar CSV com quebras de linha problemáticas."""

import csv
import re

def reparar_csv():
    """Repara o CSV removendo quebras de linha e textos indesejados."""
    
    # Ler arquivo texto bruto
    with open("notas_fies_medicina.csv", 'r', encoding='utf-8-sig') as f:
        content = f.read()
    
    print(f"Arquivo original lido. Tamanho: {len(content)} caracteres")
    
    # Substituir padrões problemáticos
    replacements = [
        (',"TIPOS DE CONCORRÊNCIA\nAmpla"', ',"Ampla"'),
        (',"TIPOS DE CONCORRÊNCIA\nPPIQ"', ',"PPIQ"'),
        (',"TIPOS DE CONCORRÊNCIA\nPCD"', ',"PCD"'),
        (',"TIPOS DE CONCORRÊNCIA\nAmpla\nPPIQ"', ',"Ampla/PPIQ"'),
        ('"TIPOS DE CONCORRÊNCIA\nAmpla"', '"Ampla"'),
        ('"TIPOS DE CONCORRÊNCIA\nPPIQ"', '"PPIQ"'),
        ('"TIPOS DE CONCORRÊNCIA\nPCD"', '"PCD"'),
        ('TIPOS DE CONCORRÊNCIA', ''),  # Remove texto residual
        ('Ver detalhes', ''),
        ('ver detalhes', ''),
    ]
    
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            print(f"Substituido: {old[:30]}... -> {new}")
    
    # Remover quebras de linha órfãs entre aspas
    content = re.sub(r'"([^"]*)\n([^"]*)"', r'"\1 \2"', content)
    
    # Processar linha por linha para garantir integridade
    lines = content.split('\n')
    header = lines[0].strip()
    valid_rows = []
    
    expected_cols = len(header.split(','))
    print(f"Header: {header}")
    print(f"Colunas esperadas: {expected_cols}")
    
    for i, line in enumerate(lines[1:], 1):
        line = line.strip()
        if not line:
            continue
            
        # Contar campos de forma mais robusta
        fields = []
        current_field = ""
        in_quotes = False
        
        for char in line:
            if char == '"':
                in_quotes = not in_quotes
                current_field += char
            elif char == ',' and not in_quotes:
                fields.append(current_field)
                current_field = ""
            else:
                current_field += char
        
        # Adicionar último campo
        if current_field or line.endswith(','):
            fields.append(current_field)
        
        if len(fields) == expected_cols:
            valid_rows.append(','.join(fields))
        else:
            print(f"Linha {i+1} ignorada - campos: {len(fields)}, esperado: {expected_cols}")
            print(f"  Conteudo: {line[:80]}...")
    
    # Escrever arquivo reparado
    final_content = header + '\n' + '\n'.join(valid_rows)
    
    with open("notas_fies_medicina_reparado.csv", 'w', encoding='utf-8-sig') as f:
        f.write(final_content)
    
    print(f"CSV reparado salvo: {len(valid_rows)} registros válidos")
    
    # Testar leitura com pandas
    try:
        import pandas as pd
        df = pd.read_csv("notas_fies_medicina_reparado.csv", encoding='utf-8-sig')
        print(f"Sucesso! Pandas carregou {len(df)} registros")
        
        # Aplicar limpeza final na coluna conceito_curso
        if 'conceito_curso' in df.columns:
            serie = df['conceito_curso'].astype('string')
            serie = serie.str.replace('TIPOS DE CONCORRÊNCIA', '', case=False, regex=False)
            serie = serie.str.replace('Ver detalhes', '', case=False, regex=False) 
            serie = serie.str.replace(r'\s+', ' ', regex=True)
            serie = serie.str.strip()
            serie = serie.where(serie.str.len() > 0, None)
            serie = serie.where(~serie.str.lower().isin({'ampla', 'ppiq', 'pcd'}), None)
            
            df['conceito_curso'] = serie
            
            # Salvar versão final
            df.to_csv("notas_fies_medicina.csv", index=False, encoding='utf-8-sig')
            print("CSV final limpo e salvo!")
        
    except Exception as e:
        print(f"Erro ao testar com pandas: {e}")

if __name__ == "__main__":
    reparar_csv()