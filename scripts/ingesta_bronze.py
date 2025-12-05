"""
Script de Ingesta Bronze Layer - Proyecto LIDL
Ingestar datos desde TXT, CSV y SQL a capa Bronze
"""

import os
import pandas as pd
import re
from datetime import datetime
import json
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/ingesta_bronze.log'),
        logging.StreamHandler()
    ]
)

class IngestaBronze:
    def __init__(self, output_path='bronze/ventas'):
        self.output_path = output_path
        self.stats = {
            'timestamp': datetime.now().isoformat(),
            'archivos_procesados': [],
            'registros_totales': 0,
            'errores': []
        }
        
    def validar_campos_extra(self, df):
        """Validar campos del archivo clientes_extra.txt"""
        validaciones = {
            'codigo': lambda x: pd.to_numeric(x, errors='coerce').notna(),
            'tipo_servicio': lambda x: x.astype(str).str.strip().isin(['APP', 'LOCAL', 'AMBOS']),
            'codigo_unico': lambda x: x.astype(str).str.match(r'^[A-Z]{4}\d{2}$', na=False),
            'fecha_afiliacion': lambda x: pd.to_datetime(x, errors='coerce').notna()
        }
        
        errores = []
        for campo, validacion in validaciones.items():
            if campo in df.columns:
                try:
                    invalidos = ~validacion(df[campo])
                    if invalidos.sum() > 0:
                        errores.append(f"{campo}: {invalidos.sum()} registros inválidos")
                        # Log algunos ejemplos de valores inválidos para debugging
                        ejemplos = df[campo][invalidos].head(3).tolist()
                        logging.debug(f"  Ejemplos de {campo} inválidos: {ejemplos}")
                except Exception as e:
                    errores.append(f"{campo}: Error en validación - {str(e)}")
        
        return errores
    
    def validar_campos_info(self, df):
        """Validar campos del archivo clientes_info.csv"""
        validaciones = {
            'codigo_cliente': lambda x: pd.to_numeric(x, errors='coerce').notna(),
            'tarjeta_beneficios': lambda x: x.astype(str).str.strip().isin(['SI', 'NO']),
            'tipo_cliente': lambda x: pd.to_numeric(x, errors='coerce').between(1, 5),
            'promedio_compras': lambda x: pd.to_numeric(x, errors='coerce') >= 0,
            'tiempo_permanencia_min': lambda x: pd.to_numeric(x, errors='coerce').between(0, 120)
        }
        
        errores = []
        for campo, validacion in validaciones.items():
            if campo in df.columns:
                try:
                    invalidos = ~validacion(df[campo])
                    if invalidos.sum() > 0:
                        errores.append(f"{campo}: {invalidos.sum()} registros inválidos")
                except Exception as e:
                    errores.append(f"{campo}: Error en validación - {str(e)}")
        
        return errores
    
    def parse_sql_inserts(self, sql_file):
        """Parsear archivo SQL con INSERT statements"""
        with open(sql_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Extraer CREATE TABLE
        create_match = re.search(r'CREATE TABLE clientes \((.*?)\);', content, re.DOTALL)
        if create_match:
            columns_def = create_match.group(1)
            columns = [col.strip().split()[0] for col in columns_def.split(',')]
        else:
            columns = ['codigo', 'nombre', 'apellido', 'comuna', 'rut', 'fecha_nacimiento', 'religion']
        
        # Extraer INSERT statements
        insert_pattern = r"INSERT INTO clientes VALUES \((.*?)\);"
        inserts = re.findall(insert_pattern, content)
        
        data = []
        for insert in inserts:
            # Limpiar y separar valores
            values = re.findall(r"'([^']*)'|(\d+(?:-\d+)?(?:-[K\d])?)", insert)
            row = [v[0] if v[0] else v[1] for v in values]
            data.append(row)
        
        df = pd.DataFrame(data, columns=columns)
        return df
    
    def ingestar_txt(self, filepath='clientes_extra.txt'):
        """Ingestar archivo TXT"""
        try:
            logging.info(f"Ingiriendo {filepath}...")
            
            # Leer archivo CSV (el TXT es formato CSV)
            df = pd.read_csv(filepath, header=None, names=[
                'codigo', 'tipo_servicio', 'codigo_unico', 'fecha_afiliacion'
            ])
            
            # Validar campos
            errores = self.validar_campos_extra(df)
            if errores:
                logging.warning(f"Validaciones fallidas en {filepath}: {errores}")
                self.stats['errores'].extend(errores)
            
            # Guardar en Bronze
            output_file = os.path.join(self.output_path, 'clientes_extra_bronze.parquet')
            df.to_parquet(output_file, index=False)
            
            logging.info(f"✓ {filepath} ingresado: {len(df)} registros")
            self.stats['archivos_procesados'].append(filepath)
            self.stats['registros_totales'] += len(df)
            
            return df
            
        except Exception as e:
            error_msg = f"Error ingiriendo {filepath}: {str(e)}"
            logging.error(error_msg)
            self.stats['errores'].append(error_msg)
            return None
    
    def ingestar_csv(self, filepath='clientes_info.csv'):
        """Ingestar archivo CSV"""
        try:
            logging.info(f"Ingiriendo {filepath}...")
            
            # Leer archivo CSV
            df = pd.read_csv(filepath)
            
            # Validar campos
            errores = self.validar_campos_info(df)
            if errores:
                logging.warning(f"Validaciones fallidas en {filepath}: {errores}")
                self.stats['errores'].extend(errores)
            
            # Guardar en Bronze
            output_file = os.path.join(self.output_path, 'clientes_info_bronze.parquet')
            df.to_parquet(output_file, index=False)
            
            logging.info(f"✓ {filepath} ingresado: {len(df)} registros")
            self.stats['archivos_procesados'].append(filepath)
            self.stats['registros_totales'] += len(df)
            
            return df
            
        except Exception as e:
            error_msg = f"Error ingiriendo {filepath}: {str(e)}"
            logging.error(error_msg)
            self.stats['errores'].append(error_msg)
            return None
    
    def ingestar_sql(self, filepath='clientes.sql'):
        """Ingestar archivo SQL"""
        try:
            logging.info(f"Ingiriendo {filepath}...")
            
            # Parsear SQL
            df = self.parse_sql_inserts(filepath)
            
            # Validaciones básicas
            if df.empty:
                raise ValueError("No se pudieron extraer datos del SQL")
            
            # Guardar en Bronze
            output_file = os.path.join(self.output_path, 'clientes_bronze.parquet')
            df.to_parquet(output_file, index=False)
            
            logging.info(f"✓ {filepath} ingresado: {len(df)} registros")
            self.stats['archivos_procesados'].append(filepath)
            self.stats['registros_totales'] += len(df)
            
            return df
            
        except Exception as e:
            error_msg = f"Error ingiriendo {filepath}: {str(e)}"
            logging.error(error_msg)
            self.stats['errores'].append(error_msg)
            return None
    
    def ejecutar_ingesta(self):
        """Ejecutar proceso completo de ingesta"""
        logging.info("=== Iniciando Ingesta Bronze Layer ===")
        
        # Crear directorio de salida
        os.makedirs(self.output_path, exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        # Ingestar archivos
        df_extra = self.ingestar_txt()
        df_info = self.ingestar_csv()
        df_clientes = self.ingestar_sql()
        
        # Guardar estadísticas
        stats_file = os.path.join(self.output_path, 'ingesta_stats.json')
        with open(stats_file, 'w') as f:
            json.dump(self.stats, f, indent=2)
        
        logging.info(f"\n=== Resumen de Ingesta ===")
        logging.info(f"Archivos procesados: {len(self.stats['archivos_procesados'])}")
        logging.info(f"Registros totales: {self.stats['registros_totales']}")
        logging.info(f"Errores: {len(self.stats['errores'])}")
        
        return {
            'extra': df_extra,
            'info': df_info,
            'clientes': df_clientes
        }


if __name__ == "__main__":
    ingesta = IngestaBronze()
    dataframes = ingesta.ejecutar_ingesta()