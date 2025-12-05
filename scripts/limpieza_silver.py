"""
Script de Limpieza Silver Layer - Proyecto LIDL
Procesar datos de Bronze a Silver con PySpark
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, trim, upper, lower, regexp_replace, 
    to_date, when, coalesce, lit, current_timestamp
)
from pyspark.sql.types import IntegerType, DoubleType
import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/limpieza_silver.log'),
        logging.StreamHandler()
    ]
)

class LimpiezaSilver:
    def __init__(self, input_path='bronze/ventas', output_path='silver/ventas'):
        self.input_path = input_path
        self.output_path = output_path
        self.spark = None
        
    def iniciar_spark(self):
        """Inicializar sesión Spark"""
        self.spark = SparkSession.builder \
            .appName("LIDL - Limpieza Silver") \
            .config("spark.sql.adaptive.enabled", "true") \
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
            .config("spark.sql.legacy.timeParserPolicy", "CORRECTED") \
            .getOrCreate()
        
        logging.info("✓ Sesión Spark iniciada")
        
    def normalizar_texto(self, df, columnas):
        """Normalizar texto: trim, upper case para códigos, proper case para nombres"""
        for col_name in columnas:
            if col_name in df.columns:
                # Si es código o tipo, UPPER
                if 'codigo' in col_name.lower() or 'tipo' in col_name.lower():
                    df = df.withColumn(col_name, upper(trim(col(col_name))))
                # Si es nombre, apellido, comuna: proper case
                elif any(x in col_name.lower() for x in ['nombre', 'apellido', 'comuna']):
                    df = df.withColumn(
                        col_name,
                        regexp_replace(trim(col(col_name)), r'\s+', ' ')
                    )
                else:
                    df = df.withColumn(col_name, trim(col(col_name)))
        
        return df
    
    def estandarizar_fechas(self, df, columnas_fecha):
        """Estandarizar formato de fechas a YYYY-MM-DD"""
        for col_name in columnas_fecha:
            if col_name in df.columns:
                # CRÍTICO: Primero hacer TRIM para eliminar espacios
                df = df.withColumn(col_name, trim(col(col_name)))
                # Luego convertir a fecha
                df = df.withColumn(
                    col_name,
                    to_date(col(col_name), 'yyyy-MM-dd')
                )
        
        return df
    
    def manejar_nulos(self, df, estrategia=None):
        """
        Manejar valores nulos según estrategia
        estrategia: dict con {columna: {tipo: 'drop'/'fill', valor: None/valor_default}}
        """
        if estrategia is None:
            estrategia = {
                'codigo': {'tipo': 'drop'},
                'tarjeta_beneficios': {'tipo': 'fill', 'valor': 'NO'},
                'tipo_alimentacion': {'tipo': 'fill', 'valor': 'No Aplica'},
                'promedio_compras': {'tipo': 'fill', 'valor': 0},
                'tiempo_permanencia_min': {'tipo': 'fill', 'valor': 0}
            }
        
        for col_name, config in estrategia.items():
            if col_name in df.columns:
                if config['tipo'] == 'drop':
                    df = df.filter(col(col_name).isNotNull())
                elif config['tipo'] == 'fill':
                    df = df.withColumn(
                        col_name,
                        coalesce(col(col_name), lit(config['valor']))
                    )
        
        return df
    
    def limpiar_clientes_extra(self):
        """Limpiar tabla clientes_extra"""
        logging.info("Limpiando clientes_extra...")
        
        # Leer desde Bronze
        df = self.spark.read.parquet(f"{self.input_path}/clientes_extra_bronze.parquet")
        
        # Convertir tipos PRIMERO (antes de normalizar)
        df = df.withColumn('codigo', col('codigo').cast(IntegerType()))
        
        # Normalizar texto
        df = self.normalizar_texto(df, ['tipo_servicio', 'codigo_unico'])
        
        # Estandarizar fechas (ahora con TRIM incluido)
        df = self.estandarizar_fechas(df, ['fecha_afiliacion'])
        
        # Manejar nulos
        df = self.manejar_nulos(df, {
            'codigo': {'tipo': 'drop'},
            'tipo_servicio': {'tipo': 'fill', 'valor': 'LOCAL'},
            'codigo_unico': {'tipo': 'drop'}
        })
        
        # Agregar metadatos
        df = df.withColumn('processed_at', current_timestamp())
        
        # Guardar en Silver
        output_file = f"{self.output_path}/clientes_extra_silver.parquet"
        df.write.mode('overwrite').parquet(output_file)
        
        logging.info(f"✓ clientes_extra limpiado: {df.count()} registros")
        return df
    
    def limpiar_clientes_info(self):
        """Limpiar tabla clientes_info"""
        logging.info("Limpiando clientes_info...")
        
        # Leer desde Bronze
        df = self.spark.read.parquet(f"{self.input_path}/clientes_info_bronze.parquet")
        
        # Convertir tipos numéricos
        df = df.withColumn('codigo_cliente', col('codigo_cliente').cast(IntegerType()))
        df = df.withColumn('tipo_cliente', col('tipo_cliente').cast(IntegerType()))
        df = df.withColumn('promedio_compras', col('promedio_compras').cast(DoubleType()))
        df = df.withColumn('tiempo_permanencia_min', col('tiempo_permanencia_min').cast(IntegerType()))
        
        # Normalizar texto
        df = self.normalizar_texto(df, ['tarjeta_beneficios', 'tipo_alimentacion'])
        
        # Normalizar valores específicos
        df = df.withColumn(
            'tarjeta_beneficios',
            when(col('tarjeta_beneficios').isin(['SI', 'YES', 'Y', '1']), 'SI')
            .when(col('tarjeta_beneficios').isin(['NO', 'N', '0']), 'NO')
            .otherwise('NO')
        )
        
        df = df.withColumn(
            'tipo_alimentacion',
            when(col('tipo_alimentacion').isNull(), 'No Aplica')
            .otherwise(lower(col('tipo_alimentacion')))
        )
        
        # Manejar nulos
        df = self.manejar_nulos(df)
        
        # Validaciones de negocio
        df = df.filter(col('tipo_cliente').between(1, 5))
        df = df.filter(col('promedio_compras') >= 0)
        df = df.filter(col('tiempo_permanencia_min').between(0, 120))
        
        # Agregar metadatos
        df = df.withColumn('processed_at', current_timestamp())
        
        # Guardar en Silver
        output_file = f"{self.output_path}/clientes_info_silver.parquet"
        df.write.mode('overwrite').parquet(output_file)
        
        logging.info(f"✓ clientes_info limpiado: {df.count()} registros")
        return df
    
    def limpiar_clientes(self):
        """Limpiar tabla clientes"""
        logging.info("Limpiando clientes...")
        
        # Leer desde Bronze
        df = self.spark.read.parquet(f"{self.input_path}/clientes_bronze.parquet")
        
        # Convertir tipos
        df = df.withColumn('codigo', col('codigo').cast(IntegerType()))
        
        # Normalizar texto
        df = self.normalizar_texto(df, ['nombre', 'apellido', 'comuna', 'rut', 'religion'])
        
        # Limpiar RUT (formato chileno)
        df = df.withColumn(
            'rut',
            regexp_replace(col('rut'), r'[.\-]', '')
        )
        
        # Estandarizar fechas (ahora con TRIM incluido)
        df = self.estandarizar_fechas(df, ['fecha_nacimiento'])
        
        # Manejar nulos
        df = self.manejar_nulos(df, {
            'codigo': {'tipo': 'drop'},
            'nombre': {'tipo': 'drop'},
            'apellido': {'tipo': 'drop'},
            'rut': {'tipo': 'drop'},
            'comuna': {'tipo': 'fill', 'valor': 'Sin Comuna'},
            'religion': {'tipo': 'fill', 'valor': 'Sin especificar'}
        })
        
        # Agregar metadatos
        df = df.withColumn('processed_at', current_timestamp())
        
        # Guardar en Silver
        output_file = f"{self.output_path}/clientes_silver.parquet"
        df.write.mode('overwrite').parquet(output_file)
        
        logging.info(f"✓ clientes limpiado: {df.count()} registros")
        return df
    
    def ejecutar_limpieza(self):
        """Ejecutar proceso completo de limpieza"""
        import os
        os.makedirs(self.output_path, exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        logging.info("=== Iniciando Limpieza Silver Layer ===")
        
        # Iniciar Spark
        self.iniciar_spark()
        
        try:
            # Limpiar todas las tablas
            df_extra = self.limpiar_clientes_extra()
            df_info = self.limpiar_clientes_info()
            df_clientes = self.limpiar_clientes()
            
            logging.info("\n=== Limpieza Completada ===")
            logging.info(f"✓ Todos los archivos procesados exitosamente")
            
            return {
                'extra': df_extra,
                'info': df_info,
                'clientes': df_clientes
            }
            
        except Exception as e:
            logging.error(f"Error en limpieza: {str(e)}")
            raise
        finally:
            if self.spark:
                self.spark.stop()
                logging.info("✓ Sesión Spark cerrada")


if __name__ == "__main__":
    limpieza = LimpiezaSilver()
    dataframes = limpieza.ejecutar_limpieza()