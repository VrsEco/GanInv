import sys
import os

# Adiciona o diretório atual ao path
sys.path.insert(0, os.path.dirname(__file__))

# Importa a aplicação Flask
# O Passenger espera que o objeto se chame 'application'
from app import app as application
