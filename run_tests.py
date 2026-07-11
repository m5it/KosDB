#!/usr/bin/env python3
import sys
import unittest

# Import and run tests
loader = unittest.TestLoader()
suite = loader.discover('.', pattern='test_security.py')
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)

sys.exit(0 if result.wasSuccessful() else 1)
