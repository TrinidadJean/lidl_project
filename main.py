"""
Workflow Principal - Proyecto LIDL
Orquestación de ingesta y limpieza de datos
"""

import sys
import os
sys.path.append('scripts')

from ingesta_bronze import IngestaBronze
from limpieza_silver import LimpiezaSilver
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/main_workflow.log'),
        logging.StreamHandler()
    ]
)

class WorkflowLIDL:
    def __init__(self):
        self.start_time = datetime.now()
        
    def ejecutar_workflow_completo(self):
        """Ejecutar workflow completo: Bronze → Silver"""
        
        logging.info("="*60)
        logging.info("🏪 PROYECTO LIDL - PIPELINE DE DATOS")
        logging.info("="*60)
        
        try:
            # ETAPA 1: Ingesta Bronze
            logging.info("\n📥 ETAPA 1: Ingesta Bronze Layer")
            logging.info("-"*60)
            ingesta = IngestaBronze()
            bronze_data = ingesta.ejecutar_ingesta()
            
            # Verificar que todos los DataFrames se cargaron correctamente
            if any(df is None for df in bronze_data.values()):
                raise Exception("Error en ingesta Bronze - Datos incompletos")
            
            # ETAPA 2: Limpieza Silver
            logging.info("\n🧹 ETAPA 2: Limpieza Silver Layer")
            logging.info("-"*60)
            limpieza = LimpiezaSilver()
            silver_data = limpieza.ejecutar_limpieza()
            
            # Resumen final
            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds()
            
            logging.info("\n" + "="*60)
            logging.info("✅ WORKFLOW COMPLETADO EXITOSAMENTE")
            logging.info("="*60)
            logging.info(f"⏱️  Duración total: {duration:.2f} segundos")
            logging.info(f"📁 Archivos Bronze: bronze/ventas/")
            logging.info(f"📁 Archivos Silver: silver/ventas/")
            logging.info(f"📋 Logs: logs/")
            logging.info("="*60)
            
            return True
            
        except Exception as e:
            logging.error(f"\n❌ ERROR EN WORKFLOW: {str(e)}")
            logging.error("Revisa los logs para más detalles")
            return False


if __name__ == "__main__":
    os.makedirs('logs', exist_ok=True)
    
    workflow = WorkflowLIDL()
    success = workflow.ejecutar_workflow_completo()
    
    sys.exit(0 if success else 1)