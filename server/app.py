import sys
import os

# Keep compatibility by injecting root directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app
from main import run

if __name__ == '__main__':
    run()
