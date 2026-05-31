import os
import sys

# Asegurar que el directorio raíz del backend esté en el PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine, Base
import models
from utils.seed import seed_data

def hard_reset():
    print('Vaciando base de datos completa...')
    Base.metadata.drop_all(bind=engine)
    print('Recreando tablas limpias...')
    Base.metadata.create_all(bind=engine)
    print('Ejecutando seeders de carga inicial...')
    seed_data()
    print('¡Base de datos reseteada exitosamente!')

if __name__ == "__main__":
    hard_reset()
