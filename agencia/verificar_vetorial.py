"""Verificação isolada: uv run python verificar_vetorial.py."""
import unittest

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_vetorial.py")
    resultado = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not resultado.wasSuccessful())
