import sys
from pathlib import Path

# Ensure the project root is on sys.path so `from tools.lib import ...` works
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
