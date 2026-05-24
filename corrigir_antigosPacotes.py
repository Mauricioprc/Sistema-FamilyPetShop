#!/usr/bin/env python3
"""
Script para Corrigir Pacotes Antigos - POS MIGRACAO (VERSÃO FINAL)
Atualiza pacotes sem data de vencimento com base no primeiro atendimento.
"""

from app import create_app
from extensions import db
from models import Pacote, Atendimento
from datetime import datetime, date


def corrigir_pacotes_antigos():
    """Corrige pacotes antigos sem data de vencimento"""
    
    print("\n" + "="*80)
    print("CORRIGINDO PACOTES ANTIGOS - PÓS MIGRAÇÃO")
    print("="*80 + "\n")
    
    try:
        # Criar aplicação Flask
        app = create_app()
        
        with app.app_context():
            print("📍 Buscando pacotes antigos sem data de vencimento...")
            
            # Busca todos os pacotes onde a data de vencimento está vazia
            pacotes_sem_vencimento = Pacote.query.filter(
                Pacote.data_vencimento == None
            ).all()
            
            total_pacotes = len(pacotes_sem_vencimento)
            print(f"✓ Encontrados {total_pacotes} pacotes para atualizar\n")
            
            if total_pacotes == 0:
                print("✅ Nenhum pacote para atualizar. Tudo já está correto!")
                return True
            
            contador = 0
            erros = 0
            
            for idx, pacote in enumerate(pacotes_sem_vencimento, 1):
                try:
                    print(f"[{idx}/{total_pacotes}] Processando pacote ID {pacote.id}...", end=" ")
                    
                    # Procura o primeiro atendimento deste pacote
                    primeiro_atendimento = Atendimento.query.filter_by(
                        pacote_id=pacote.id
                    ).order_by(Atendimento.data.asc()).first()
                    
                    data_vencimento = None
                    
                    if primeiro_atendimento:
                        # Usa a data do primeiro atendimento
                        if isinstance(primeiro_atendimento.data, date):
                            data_vencimento = primeiro_atendimento.data
                        elif isinstance(primeiro_atendimento.data, datetime):
                            data_vencimento = primeiro_atendimento.data.date()
                        else:
                            data_vencimento = datetime.now().date()
                        
                        print(f"✓ Data: {data_vencimento}")
                    else:
                        # Se não houver atendimento, usa a data de criação
                        if pacote.created_at:
                            try:
                                if isinstance(pacote.created_at, datetime):
                                    data_vencimento = pacote.created_at.date()
                                elif isinstance(pacote.created_at, date):
                                    data_vencimento = pacote.created_at
                                else:
                                    data_vencimento = datetime.now().date()
                            except:
                                data_vencimento = datetime.now().date()
                            
                            print(f"✓ Data (criação): {data_vencimento}")
                        else:
                            # Fallback: usa data de hoje
                            data_vencimento = datetime.now().date()
                            print(f"✓ Data (hoje): {data_vencimento}")
                    
                    # Atribui a data
                    pacote.data_vencimento = data_vencimento
                    contador += 1
                
                except Exception as e:
                    print(f"✗ ERRO: {str(e)}")
                    erros += 1
                    continue
            
            # Tentar salvar as mudanças
            print(f"\n💾 Salvando {contador} pacotes atualizados...")
            
            try:
                db.session.commit()
                print("\n" + "="*80)
                print(f"✅ SUCESSO! {contador} pacotes foram atualizados com sucesso.")
                if erros > 0:
                    print(f"⚠️  {erros} pacotes tiveram erro e não foram salvos.")
                print("="*80 + "\n")
                return True
                
            except Exception as e:
                db.session.rollback()
                print(f"\n❌ ERRO ao salvar no banco: {str(e)}")
                print("Todas as mudanças foram revertidas.\n")
                return False
    
    except Exception as e:
        print(f"\n❌ ERRO FATAL: {str(e)}")
        print("Verifique se a aplicação Flask está configurada corretamente.\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import sys
    
    try:
        sucesso = corrigir_pacotes_antigos()
        sys.exit(0 if sucesso else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Operação cancelada pelo usuário.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro não tratado: {str(e)}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)